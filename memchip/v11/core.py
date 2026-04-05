from __future__ import annotations
"""MemChip v11: No reranker, FTS5-only retrieval, gpt-4.1-nano answering, precision-focused."""

from .storage import Storage
from .consolidation import consolidate_session
from .router import classify_query, is_confident, escalate, decompose_multihop
from .answerer import (
    answer_strategy_a, answer_strategy_b, answer_strategy_c, answer_strategy_d,
    answer_open_domain, synthesize_subanswers, _mask_entities_in_context,
    answer_from_chunks,
)
import re


def chunk_text(text: str, max_tokens: int = 250, overlap_tokens: int = 50) -> list[str]:
    """Split text into overlapping chunks."""
    words = text.split()
    if len(words) <= max_tokens:
        return [text]
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + max_tokens, len(words))
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = end - overlap_tokens
    return chunks


def _keyword_score(question: str, text: str) -> float:
    """Score a chunk by keyword overlap density with the question."""
    stop = {"what","when","where","who","how","did","does","do","is","are","was","were",
            "the","a","an","in","on","at","to","for","of","with","has","have","had",
            "and","or","but","not","this","that","they","their","it","its","about","from","by",
            "been","being","can","could","would","should","will","shall","may","might"}
    q_words = set(w for w in re.findall(r'\b\w+\b', question.lower()) if w not in stop and len(w) > 2)
    t_words = re.findall(r'\b\w+\b', text.lower())
    if not q_words or not t_words:
        return 0.0
    matches = sum(1 for w in t_words if w in q_words)
    # Density = matches / total words (rewards concentrated relevance)
    return matches / len(t_words) * len(q_words)


def retrieve_chunks_fts(storage: Storage, question: str, entity: str | None = None, limit: int = 12) -> list[dict]:
    """Retrieve raw chunks via FTS5, scored by keyword density. No reranker."""
    stop = {"what","when","where","who","how","did","does","do","is","are","was","were",
            "the","a","an","in","on","at","to","for","of","with","has","have","had",
            "and","or","but","not","this","that","they","their","it","its","about","from","by"}
    words = re.findall(r'\b\w+\b', question.lower())
    terms = [w for w in words if w not in stop and len(w) > 2]
    
    if entity:
        for part in entity.split():
            if part.lower() not in [t.lower() for t in terms]:
                terms.append(part)
    
    # Search raw chunks with FTS5
    candidates = storage.search_raw_chunks(terms, limit=80)
    
    # Also search by entity name alone
    if entity:
        entity_results = storage.search_raw_chunks([entity], limit=50)
        seen_ids = {c["id"] for c in candidates}
        for r in entity_results:
            if r["id"] not in seen_ids:
                candidates.append(r)
                seen_ids.add(r["id"])
    
    if not candidates:
        return []
    
    # Score by keyword density and sort
    for c in candidates:
        c["relevance_score"] = _keyword_score(question, c["text"])
    
    candidates.sort(key=lambda x: -x["relevance_score"])
    
    # Take top chunks within token budget
    result = []
    token_count = 0
    max_tokens = 4000
    for c in candidates:
        if c["relevance_score"] <= 0:
            break
        chunk_tokens = len(c["text"].split())
        if token_count + chunk_tokens > max_tokens and result:
            break
        result.append(c)
        token_count += chunk_tokens
        if len(result) >= limit:
            break
    
    return result


class MemChipV2:
    def __init__(self, api_key: str, db_path: str = ":memory:"):
        self.api_key = api_key
        self.storage = Storage(db_path)

    def add(self, session_id: str, date: str, conversation: list[dict], speaker_a: str, speaker_b: str):
        """Ingest a session."""
        consolidate_session(self.api_key, self.storage, session_id, date, conversation, speaker_a, speaker_b)

    def recall(self, question: str, category: int | None = None, max_escalations: int = 3) -> dict:
        """Answer a question using adaptive recall routing."""
        if category == 5:
            return self._recall_adversarial(question)
        if category == 3:
            return self._recall_open_domain(question)
        if category == 1:
            return self._recall_single_hop(question)
        if category == 2:
            return self._recall_temporal(question)
        
        strategy = classify_query(self.api_key, question, category)
        if strategy == "C":
            return self._recall_multihop(question, strategy)
        return self._recall_single(question, strategy, max_escalations)

    def _recall_temporal(self, question: str) -> dict:
        """Temporal recall with timeline enrichment."""
        temporal_events = self.storage.query_temporal_events(limit=50)
        temporal_context = ""
        if temporal_events:
            timeline = "\n".join(f"- {ev['date']}: {ev['entity']} — {ev['event_text']}" for ev in temporal_events)
            temporal_context = f"\n\nTimeline of Events:\n{timeline}"
        
        profiles = self.storage.get_all_profiles()
        episodes = self.storage.get_all_episodes()
        answer = answer_strategy_b(self.api_key, question, profiles, episodes, temporal_context=temporal_context)
        strat_name = "temporal_B"
        
        if not is_confident(answer):
            relevant_ids = self._identify_relevant_sessions(question, episodes)
            raw_sessions = self.storage.get_engrams(relevant_ids)
            answer = answer_strategy_c(self.api_key, question, profiles, episodes, raw_sessions, temporal_context=temporal_context)
            strat_name = "temporal_C"
        
        return {"answer": answer, "strategy": strat_name, "strategies_tried": [strat_name]}

    def _recall_single_hop(self, question: str) -> dict:
        """Single-hop: profiles + atomic facts + targeted episodes. Precision-focused."""
        profiles = self.storage.get_all_profiles()
        target_entity = self._extract_entity_from_question(question, profiles)
        episodes = self.storage.get_all_episodes()
        
        # Filter profiles and episodes to target entity when possible
        filtered_profiles = profiles
        filtered_episodes = episodes
        if target_entity:
            entity_profiles = [p for p in profiles if p["entity"].lower() == target_entity.lower()]
            if entity_profiles:
                filtered_profiles = entity_profiles
            filtered_episodes = [ep for ep in episodes if target_entity.lower() in ep["summary"].lower()]
            if not filtered_episodes:
                filtered_episodes = episodes  # fallback to all
        
        # Get atomic facts for precision
        atomic_facts = self.storage.search_atomic_facts(question, limit=15)
        atomic_context = ""
        if atomic_facts:
            facts_text = "\n".join(f"- {f['fact_text']}" for f in atomic_facts)
            atomic_context = f"\n\nRelevant Atomic Facts:\n{facts_text}"
        
        # Also get a few targeted chunks for detail
        chunks = retrieve_chunks_fts(self.storage, question, target_entity, limit=5)
        chunk_context = ""
        if chunks:
            passages = "\n\n".join(f"[{c.get('date', '?')}] {c['text']}" for c in chunks[:5])
            chunk_context = f"\n\nRelevant Conversation Excerpts:\n{passages}"
        
        answer = answer_strategy_b(self.api_key, question, filtered_profiles, filtered_episodes, 
                                    temporal_context=atomic_context + chunk_context)
        
        return {"answer": answer, "strategy": "single_hop_B", "strategies_tried": ["single_hop_B"]}
    
    def _extract_entity_from_question(self, question: str, profiles: list[dict]) -> str | None:
        """Extract the main entity/person from a question."""
        question_lower = question.lower()
        matches = []
        for p in profiles:
            name = p["entity"]
            if name.lower() in question_lower:
                matches.append(name)
            else:
                first = name.split()[0]
                if first.lower() in question_lower:
                    matches.append(name)
        if len(matches) == 1:
            return matches[0]
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
        """Open-domain recall with inference."""
        profiles = self.storage.get_all_profiles()
        episodes = self.storage.get_all_episodes()
        relevant_ids = self._identify_relevant_sessions(question, episodes)
        raw_sessions = self.storage.get_engrams(relevant_ids)
        
        atomic_facts = self.storage.search_atomic_facts(question, limit=15)
        atomic_context = ""
        if atomic_facts:
            facts_text = "\n".join(f"- {f['fact_text']}" for f in atomic_facts)
            atomic_context = f"\n\nRelevant Atomic Facts:\n{facts_text}"
        
        answer = answer_open_domain(self.api_key, question, profiles, episodes, raw_sessions, atomic_context=atomic_context)
        return {"answer": answer, "strategy": "open_domain", "strategies_tried": ["open_domain"]}

    def _recall_adversarial(self, question: str) -> dict:
        """Adversarial recall with entity masking."""
        profiles = self.storage.get_all_profiles()
        episodes = self.storage.get_all_episodes()
        relevant_ids = self._identify_relevant_sessions(question, episodes)
        raw_sessions = self.storage.get_engrams(relevant_ids)
        
        # FTS5 chunks for supplementary context
        chunks = retrieve_chunks_fts(self.storage, question, limit=8)
        extra_context = ""
        if chunks:
            passages = "\n\n---\n\n".join(f"[{c.get('date', '?')}] {c['text']}" for c in chunks[:8])
            extra_context = f"\n\nRelevant Conversation Excerpts:\n{passages}"
        
        atomic_facts = self.storage.search_atomic_facts(question, limit=10)
        if atomic_facts:
            facts_text = "\n".join(f"- {f['fact_text']}" for f in atomic_facts)
            extra_context += f"\n\nRelevant Atomic Facts:\n{facts_text}"
        
        masked_profiles, masked_episodes, masked_raw = _mask_entities_in_context(
            question, profiles, episodes, raw_sessions
        )
        answer = answer_strategy_c(self.api_key, question, masked_profiles, masked_episodes, masked_raw, temporal_context=extra_context)
        return {"answer": answer, "strategy": "adversarial_masked", "strategies_tried": ["adversarial_masked"]}

    def _recall_single(self, question: str, strategy: str, max_escalations: int = 3) -> dict:
        """Single question recall with confidence escalation."""
        strategies_tried = []
        for _ in range(max_escalations + 1):
            answer = self._execute_strategy(question, strategy)
            strategies_tried.append(strategy)
            if is_confident(answer) or strategy == "D":
                return {"answer": answer, "strategy": strategy, "strategies_tried": strategies_tried}
            next_s = escalate(strategy)
            if next_s is None:
                break
            strategy = next_s
        return {"answer": answer, "strategy": strategy, "strategies_tried": strategies_tried}

    def _recall_multihop(self, question: str, initial_strategy: str) -> dict:
        """Multi-hop: decompose, route each sub-q, synthesize."""
        sub_questions = decompose_multihop(self.api_key, question)
        if len(sub_questions) <= 1:
            return self._recall_single(question, max(initial_strategy, "B"), 3)
        
        sub_qas = []
        all_strategies = []
        for sq in sub_questions:
            sub_strategy = classify_query(self.api_key, sq)
            result = self._recall_single(sq, sub_strategy, 2)
            sub_qas.append((sq, result["answer"]))
            all_strategies.extend(result["strategies_tried"])
        
        final_answer = synthesize_subanswers(self.api_key, question, sub_qas)
        if not is_confident(final_answer):
            result = self._recall_single(question, "C", 2)
            return {"answer": result["answer"], "strategy": f"multihop→{result['strategy']}", "strategies_tried": all_strategies + result["strategies_tried"]}
        return {"answer": final_answer, "strategy": f"multihop({','.join(all_strategies)})", "strategies_tried": all_strategies}

    def _execute_strategy(self, question: str, strategy: str) -> str:
        """Execute a specific retrieval strategy."""
        profiles = self.storage.get_all_profiles()
        if strategy == "A":
            return answer_strategy_a(self.api_key, question, profiles)
        episodes = self.storage.get_all_episodes()
        if strategy == "B":
            return answer_strategy_b(self.api_key, question, profiles, episodes)
        if strategy == "C":
            relevant_ids = self._identify_relevant_sessions(question, episodes)
            raw_sessions = self.storage.get_engrams(relevant_ids)
            atomic_facts = self.storage.search_atomic_facts(question, limit=10)
            atomic_ctx = ""
            if atomic_facts:
                facts_text = "\n".join(f"- {f['fact_text']}" for f in atomic_facts)
                atomic_ctx = f"\n\nRelevant Atomic Facts:\n{facts_text}"
            return answer_strategy_c(self.api_key, question, profiles, episodes, raw_sessions, temporal_context=atomic_ctx)
        all_raw = self.storage.get_all_engrams()
        return answer_strategy_d(self.api_key, question, profiles, episodes, all_raw)

    def _identify_relevant_sessions(self, question: str, episodes: list[dict], max_sessions: int = 5) -> list[str]:
        """Identify relevant sessions using FTS5."""
        fts_results = self.storage.search_episodes(question, limit=max_sessions)
        if fts_results:
            return [r["session_id"] for r in fts_results]
        words = re.findall(r'\b\w+\b', question.lower())
        stop = {'what','when','where','who','how','did','does','do','is','are','was','were','the','a','an','in','on','at','to','for','of','with','has','have','had','and','or','but','not','this','that','they','their','it','its','about','from','by'}
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
