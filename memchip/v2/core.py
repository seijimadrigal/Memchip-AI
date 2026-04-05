from __future__ import annotations
"""Main MemChip v2 class with add() and recall()."""

from .storage import Storage
from .consolidation import consolidate_session
from .router import classify_query, is_confident, escalate, decompose_multihop
from .answerer import (
    answer_strategy_a, answer_strategy_b, answer_strategy_c, answer_strategy_d,
    answer_open_domain, synthesize_subanswers, _mask_entities_in_context,
)
from .reranker import rerank_dicts


class MemChipV2:
    def __init__(self, api_key: str, db_path: str = ":memory:"):
        self.api_key = api_key
        self.storage = Storage(db_path)

    def add(self, session_id: str, date: str, conversation: list[dict], speaker_a: str, speaker_b: str):
        """Ingest a session: store raw, build episode summary, update entity profiles."""
        consolidate_session(self.api_key, self.storage, session_id, date, conversation, speaker_a, speaker_b)

    def recall(self, question: str, category: int | None = None, max_escalations: int = 3) -> dict:
        """Answer a question using adaptive recall routing with confidence escalation."""
        
        # Adversarial (category 5): use entity-masked answering
        if category == 5:
            return self._recall_adversarial(question)
        
        # Open-domain (category 3): use inference-capable answering
        if category == 3:
            return self._recall_open_domain(question)
        
        # Single-hop (category 1): skip classify, go direct to targeted search
        if category == 1:
            return self._recall_single_hop(question, "B")
        
        # Temporal (category 2): skip classify, use B with temporal enrichment
        if category == 2:
            return self._recall_temporal(question, "B")
        
        strategy = classify_query(self.api_key, question, category)
        
        # For multi-hop (strategy C), try decomposition
        if strategy == "C":
            return self._recall_multihop(question, strategy)
        
        return self._recall_single(question, strategy, max_escalations)

    def _recall_temporal(self, question: str, strategy: str) -> dict:
        """Temporal recall: enrich context with temporal events timeline + escalation."""
        # Get temporal events
        temporal_events = self.storage.query_temporal_events(limit=50)
        temporal_context = ""
        if temporal_events:
            timeline = "\n".join(f"- {ev['date']}: {ev['entity']} — {ev['event_text']}" for ev in temporal_events)
            temporal_context = f"\n\nTimeline of Events:\n{timeline}"
        
        profiles = self.storage.get_all_profiles()
        episodes = self.storage.get_all_episodes()
        # v9: Rerank episodes
        episodes = rerank_dicts(question, episodes, "summary", top_k=8)
        
        # Strategy B with temporal enrichment
        answer = answer_strategy_b(self.api_key, question, profiles, episodes, temporal_context=temporal_context)
        strat_name = "temporal_B"
        
        # Escalate to C if not confident
        if not is_confident(answer):
            relevant_ids = self._identify_relevant_sessions(question, episodes)
            raw_sessions = self.storage.get_engrams(relevant_ids)
            answer = answer_strategy_c(self.api_key, question, profiles, episodes, raw_sessions, temporal_context=temporal_context)
            strat_name = "temporal_C"
        
        return {
            "answer": answer,
            "strategy": strat_name,
            "strategies_tried": [strat_name],
        }

    def _recall_single_hop(self, question: str, strategy: str) -> dict:
        """Single-hop recall: v9 — reranker + cross-entity support."""
        profiles = self.storage.get_all_profiles()
        episodes = self.storage.get_all_episodes()
        
        # v9 Fix 3: Detect cross-entity questions ("both", "together", two names)
        is_cross = self._is_cross_entity_question(question, profiles)
        
        if is_cross:
            # Retrieve for ALL mentioned entities, don't filter
            # Get atomic facts from all entities mentioned
            atomic_facts = self.storage.search_atomic_facts(question, limit=30)
            # v9 Fix 1: Rerank atomic facts
            atomic_facts = rerank_dicts(question, atomic_facts, "fact_text", top_k=10)
            atomic_context = ""
            if atomic_facts:
                facts_text = "\n".join(f"- {f['fact_text']}" for f in atomic_facts)
                atomic_context = f"\n\nRelevant Atomic Facts:\n{facts_text}"
            # Rerank episodes
            episodes = rerank_dicts(question, episodes, "summary", top_k=8)
            answer = answer_strategy_b(self.api_key, question, profiles, episodes, temporal_context=atomic_context)
            strat_name = "cross_entity_B"
        else:
            # Single entity path
            target_entity = self._extract_entity_from_question(question, profiles)
            if target_entity:
                profiles = [p for p in profiles if p["entity"].lower() == target_entity.lower()]
                episodes = [ep for ep in episodes if target_entity.lower() in ep["summary"].lower()]
            
            # v9.1: Rerank episodes only (no atomic facts for single-hop — they add noise)
            episodes = rerank_dicts(question, episodes, "summary", top_k=5)
            
            answer = answer_strategy_b(self.api_key, question, profiles, episodes)
            strat_name = "reranked_B"
            
            if not is_confident(answer):
                relevant_ids = self._identify_relevant_sessions(question, episodes)
                raw_sessions = self.storage.get_engrams(relevant_ids)
                if target_entity and raw_sessions:
                    raw_sessions = [r for r in raw_sessions if target_entity.lower() in r["raw_text"].lower()]
                if raw_sessions:
                    answer = answer_strategy_c(self.api_key, question, profiles, episodes, raw_sessions, temporal_context=atomic_context)
                    strat_name = "reranked_C"
        
        return {
            "answer": answer,
            "strategy": strat_name,
            "strategies_tried": [strat_name],
        }
    
    def _is_cross_entity_question(self, question: str, profiles: list[dict]) -> bool:
        """Detect if question asks about multiple entities (both/together)."""
        import re
        q_lower = question.lower()
        
        # Check for cross-entity keywords
        cross_keywords = ["both", "together", "in common", "shared", "each of them", "the two"]
        has_cross_keyword = any(kw in q_lower for kw in cross_keywords)
        
        if not has_cross_keyword:
            return False
        
        # Check if 2+ entity names are mentioned (or implied by "both")
        matches = set()
        for p in profiles:
            name = p["entity"]
            if name.lower() in q_lower:
                matches.add(name)
            else:
                first = name.split()[0]
                if first.lower() in q_lower:
                    matches.add(name)
        
        # "both" implies 2 entities even if only one is named
        if "both" in q_lower and len(matches) >= 1:
            return True
        return len(matches) >= 2
    
    def _extract_entity_from_question(self, question: str, profiles: list[dict]) -> str | None:
        """Extract the main entity/person from a question using profile name matching."""
        import re
        question_lower = question.lower()
        # Check which profile entities are mentioned in the question
        matches = []
        for p in profiles:
            name = p["entity"]
            if name.lower() in question_lower:
                matches.append(name)
            else:
                # Try first name
                first = name.split()[0]
                if first.lower() in question_lower:
                    matches.append(name)
        # If exactly one match, that's our target
        if len(matches) == 1:
            return matches[0]
        # If multiple or none, check possessives like "Emma's"
        poss_match = re.search(r"(\b\w+)'s\b", question)
        if poss_match:
            poss_name = poss_match.group(1).lower()
            for p in profiles:
                if p["entity"].lower().startswith(poss_name):
                    return p["entity"]
                first = p["entity"].split()[0].lower()
                if first == poss_name:
                    return p["entity"]
        return matches[0] if matches else None

    def _recall_open_domain(self, question: str) -> dict:
        """Open-domain recall: uses inference + world knowledge + atomic facts (v8.1)."""
        profiles = self.storage.get_all_profiles()
        episodes = self.storage.get_all_episodes()
        
        # Get relevant raw sessions for additional context
        relevant_ids = self._identify_relevant_sessions(question, episodes)
        raw_sessions = self.storage.get_engrams(relevant_ids)
        
        # v8.1: Inject atomic facts for open-domain (gave +24.6% in v8)
        atomic_facts = self.storage.search_atomic_facts(question, limit=15)
        atomic_context = ""
        if atomic_facts:
            facts_text = "\n".join(f"- {f['fact_text']}" for f in atomic_facts)
            atomic_context = f"\n\nRelevant Atomic Facts:\n{facts_text}"
        
        answer = answer_open_domain(self.api_key, question, profiles, episodes, raw_sessions, atomic_context=atomic_context)
        
        return {
            "answer": answer,
            "strategy": "open_domain",
            "strategies_tried": ["open_domain"],
        }

    def _recall_adversarial(self, question: str) -> dict:
        """Adversarial recall: mask entity names so LLM can't detect the swap."""
        profiles = self.storage.get_all_profiles()
        episodes = self.storage.get_all_episodes()
        
        # Get relevant raw sessions
        relevant_ids = self._identify_relevant_sessions(question, episodes)
        raw_sessions = self.storage.get_engrams(relevant_ids)
        
        # v8: Get atomic facts for supplementary evidence
        atomic_facts = self.storage.search_atomic_facts(question, limit=10)
        atomic_context = ""
        if atomic_facts:
            facts_text = "\n".join(f"- {f['fact_text']}" for f in atomic_facts)
            atomic_context = f"\n\nRelevant Atomic Facts:\n{facts_text}"
        
        # Mask entities: replace OTHER entity with QUESTION entity in all context
        masked_profiles, masked_episodes, masked_raw = _mask_entities_in_context(
            question, profiles, episodes, raw_sessions
        )
        
        # Use strategy C with masked context
        answer = answer_strategy_c(self.api_key, question, masked_profiles, masked_episodes, masked_raw, temporal_context=atomic_context)
        
        return {
            "answer": answer,
            "strategy": "adversarial_masked",
            "strategies_tried": ["adversarial_masked"],
        }

    def _recall_single(self, question: str, strategy: str, max_escalations: int = 3) -> dict:
        """Single question recall with confidence escalation."""
        strategies_tried = []
        
        for _ in range(max_escalations + 1):
            answer = self._execute_strategy(question, strategy)
            strategies_tried.append(strategy)
            
            if is_confident(answer) or strategy == "D":
                return {
                    "answer": answer,
                    "strategy": strategy,
                    "strategies_tried": strategies_tried,
                }
            
            next_s = escalate(strategy)
            if next_s is None:
                break
            strategy = next_s
        
        return {
            "answer": answer,
            "strategy": strategy,
            "strategies_tried": strategies_tried,
        }

    def _recall_multihop(self, question: str, initial_strategy: str) -> dict:
        """Multi-hop recall: decompose, route each sub-q, synthesize. v8.1: inject atomic facts."""
        sub_questions = decompose_multihop(self.api_key, question)
        
        if len(sub_questions) <= 1:
            # Not really decomposable, use deep strategy
            return self._recall_single(question, max(initial_strategy, "B"), 3)
        
        sub_qas = []
        all_strategies = []
        for sq in sub_questions:
            sub_strategy = classify_query(self.api_key, sq)
            result = self._recall_single(sq, sub_strategy, 2)
            sub_qas.append((sq, result["answer"]))
            all_strategies.extend(result["strategies_tried"])
        
        final_answer = synthesize_subanswers(self.api_key, question, sub_qas)
        
        # Check confidence of synthesized answer; if low, fallback to strategy C/D on full question
        if not is_confident(final_answer):
            result = self._recall_single(question, "C", 2)
            return {
                "answer": result["answer"],
                "strategy": f"multihop→{result['strategy']}",
                "strategies_tried": all_strategies + result["strategies_tried"],
            }
        
        return {
            "answer": final_answer,
            "strategy": f"multihop({','.join(all_strategies)})",
            "strategies_tried": all_strategies,
        }

    def _execute_strategy(self, question: str, strategy: str) -> str:
        """Execute a specific retrieval strategy."""
        profiles = self.storage.get_all_profiles()
        
        if strategy == "A":
            return answer_strategy_a(self.api_key, question, profiles)
        
        episodes = self.storage.get_all_episodes()
        
        if strategy == "B":
            return answer_strategy_b(self.api_key, question, profiles, episodes)
        
        if strategy == "C":
            # Identify relevant sessions from episodes
            relevant_ids = self._identify_relevant_sessions(question, episodes)
            raw_sessions = self.storage.get_engrams(relevant_ids)
            # v8.1: Inject atomic facts as supplementary for multi-hop/general C
            atomic_facts = self.storage.search_atomic_facts(question, limit=10)
            atomic_ctx = ""
            if atomic_facts:
                facts_text = "\n".join(f"- {f['fact_text']}" for f in atomic_facts)
                atomic_ctx = f"\n\nRelevant Atomic Facts:\n{facts_text}"
            return answer_strategy_c(self.api_key, question, profiles, episodes, raw_sessions, temporal_context=atomic_ctx)
        
        # Strategy D: everything
        all_raw = self.storage.get_all_engrams()
        return answer_strategy_d(self.api_key, question, profiles, episodes, all_raw)

    def _identify_relevant_sessions(self, question: str, episodes: list[dict], max_sessions: int = 5) -> list[str]:
        """Identify relevant sessions using FTS5 ranked search with temporal decay."""
        # Try FTS5 ranked search first
        fts_results = self.storage.search_episodes(question, limit=max_sessions)
        if fts_results:
            return [r["session_id"] for r in fts_results]
        
        # Fallback to keyword overlap if FTS returns nothing
        import re
        words = re.findall(r'\b\w+\b', question.lower())
        stop = {'what', 'when', 'where', 'who', 'how', 'did', 'does', 'do', 'is', 'are', 'was', 'were', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'has', 'have', 'had', 'and', 'or', 'but', 'not', 'this', 'that', 'they', 'their', 'it', 'its', 'about', 'from', 'by'}
        keywords = [w for w in words if w not in stop and len(w) > 2]
        
        scored = []
        for ep in episodes:
            summary_lower = ep["summary"].lower()
            score = sum(1 for kw in keywords if kw in summary_lower)
            if score > 0:
                scored.append((score, ep["session_id"]))
        
        scored.sort(reverse=True)
        return [sid for _, sid in scored[:max_sessions]]

    def close(self):
        self.storage.close()
