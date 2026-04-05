from __future__ import annotations
"""MemChip v21.4: Hybrid — KG for multi-hop/temporal, v10 FTS5+CrossEncoder for single-hop."""

import re
from .storage import Storage
from .consolidation import consolidate_session
from .router import classify_route, is_confident, KG_DIRECT, KG_RELATIONSHIP, KG_TEMPORAL, TEXT_SEARCH, ADVERSARIAL, OPEN_DOMAIN
from .answerer import answer_kg_direct, answer_kg_relationship, answer_kg_temporal

# Import v10 retrieval/answering for fallback paths
from memchip.v10.core import retrieve_and_rerank, rerank_chunks, _answer_single_hop_v3
from memchip.v10.answerer import (
    answer_strategy_b, answer_strategy_c, answer_strategy_d,
    answer_open_domain, synthesize_subanswers, _mask_entities_in_context,
)
from memchip.v10.router import classify_query, escalate, decompose_multihop


class MemChipV21_4:
    def __init__(self, api_key: str, db_path: str = ":memory:"):
        self.api_key = api_key
        self.storage = Storage(db_path)

    def add(self, session_id: str, date: str, conversation: list[dict],
            speaker_a: str, speaker_b: str):
        consolidate_session(self.api_key, self.storage, session_id, date,
                          conversation, speaker_a, speaker_b)

    def recall(self, question: str, category: int | None = None) -> dict:
        """v21.4 hybrid routing: KG for multi-hop/temporal, v10 for single-hop."""
        # Single-hop → ALWAYS v10 FTS5+CrossEncoder (65% vs KG's 43%)
        if category == 1:
            return self._recall_single_hop_v10(question)
        
        # Adversarial → entity-masked (same as v21)
        if category == 5:
            return self._recall_adversarial(question)
        
        # Open-domain → same as v21
        if category == 3:
            return self._recall_open_domain(question)
        
        # Temporal (cat 2) → KG temporal (85%)
        if category == 2:
            route = classify_route(self.api_key, question, category)
            if route in (KG_DIRECT, KG_RELATIONSHIP, KG_TEMPORAL):
                return self._recall_kg(question, route, category)
            return self._recall_temporal(question)
        
        # Multi-hop (cat 4) → KG first (83-85%), fallback to decompose
        if category == 4:
            route = classify_route(self.api_key, question, category)
            if route in (KG_DIRECT, KG_RELATIONSHIP, KG_TEMPORAL):
                return self._recall_kg(question, route, category)
            return self._recall_multihop(question)
        
        # Unknown category → try KG router
        route = classify_route(self.api_key, question, category)
        if route == ADVERSARIAL:
            return self._recall_adversarial(question)
        if route == OPEN_DOMAIN:
            return self._recall_open_domain(question)
        if route in (KG_DIRECT, KG_RELATIONSHIP, KG_TEMPORAL):
            return self._recall_kg(question, route, category)
        return self._recall_single_hop_v10(question)

    # ── v10 single-hop (FTS5 + CrossEncoder) ─────────────────

    def _recall_single_hop_v10(self, question: str) -> dict:
        """Use v10's proven FTS5+CrossEncoder pipeline for single-hop questions."""
        profiles = self.storage.get_all_profiles()
        target_entity = self._extract_entity_from_question(question, profiles)
        
        # v10's retrieve + rerank
        reranked = retrieve_and_rerank(self.storage, question, target_entity)
        
        if not reranked:
            # Fallback to profiles+episodes
            episodes = self.storage.get_all_episodes()
            answer = answer_strategy_b(self.api_key, question, profiles, episodes)
            return {"answer": answer, "strategy": "v10_fallback_B", "strategies_tried": ["v10_fallback_B"]}
        
        # v10.3: top 4 chunks + entity profile
        top_chunks = reranked[:4]
        passages = "\n\n---\n\n".join(
            f"[{c.get('date', '?')}] {c['text']}" for c in top_chunks
        )
        
        profile_text = ""
        if target_entity:
            for p in profiles:
                if p["entity"].lower() == target_entity.lower():
                    profile_text = p["profile_text"]
                    break
        
        answer = _answer_single_hop_v3(self.api_key, question, passages, profile_text)
        return {"answer": answer, "strategy": "v10_single_hop", "strategies_tried": ["v10_single_hop"]}

    # ── KG routes ──────────────────────────────────────────────

    def _recall_kg(self, question: str, route: str, category: int | None = None) -> dict:
        """Answer using KG triples as primary source + supplementary chunks."""
        profiles = self.storage.get_all_profiles()
        target_entity = self._extract_entity_from_question(question, profiles)
        kg = self.storage.kg

        # Gather KG triples based on route
        triples = []
        timeline = None
        entity2 = None

        if route == KG_DIRECT:
            if target_entity:
                triples = kg.get_entity_facts(target_entity, limit=30)
            if not triples:
                triples = kg.search_triples(question, limit=20)

        elif route == KG_RELATIONSHIP:
            entities = self._extract_all_entities(question, profiles)
            if len(entities) >= 2:
                target_entity = entities[0]
                entity2 = entities[1]
                triples = kg.get_relationship(entities[0], entities[1], limit=20)
            if not triples and target_entity:
                triples = kg.get_entity_facts(target_entity, limit=20)
            if not triples:
                triples = kg.search_triples(question, limit=20)

        elif route == KG_TEMPORAL:
            if target_entity:
                timeline = kg.get_timeline(target_entity, limit=30)
                triples = kg.get_entity_facts(target_entity, limit=20)
            if not triples:
                triples = kg.search_triples(question, limit=20)

        # If KG has nothing, fall back to text search
        if not triples and not timeline:
            if category == 2:
                return self._recall_temporal(question)
            return self._recall_single_hop(question)

        # Get supplementary chunks (top 6 — need enough raw text for specific details)
        reranked = retrieve_and_rerank(self.storage, question, target_entity)
        supp_chunks = ""
        if reranked:
            supp_chunks = "\n\n---\n\n".join(
                f"[{c.get('date', '?')}] {c['text']}" for c in reranked[:6]
            )

        # Get profile text
        profile_text = ""
        if target_entity:
            for p in profiles:
                if p["entity"].lower() == target_entity.lower():
                    profile_text = p["profile_text"]
                    break

        # Answer based on route
        if route == KG_DIRECT:
            answer = answer_kg_direct(self.api_key, question, triples,
                                      supp_chunks, profile_text, target_entity)
        elif route == KG_RELATIONSHIP:
            answer = answer_kg_relationship(self.api_key, question, triples,
                                            supp_chunks, target_entity, entity2)
        elif route == KG_TEMPORAL:
            answer = answer_kg_temporal(self.api_key, question, triples,
                                        timeline, supp_chunks)
        else:
            answer = answer_kg_direct(self.api_key, question, triples,
                                      supp_chunks, profile_text, target_entity)

        # If not confident, fall back to text search
        if not is_confident(answer):
            fallback = self._recall_single_hop(question)
            return {
                "answer": fallback["answer"],
                "strategy": f"kg_{route}→fallback",
                "strategies_tried": [route, fallback["strategy"]],
            }

        return {"answer": answer, "strategy": f"kg_{route}", "strategies_tried": [route]}

    # ── Text search fallbacks (from v10) ──────────────────────

    def _recall_single_hop(self, question: str) -> dict:
        profiles = self.storage.get_all_profiles()
        target_entity = self._extract_entity_from_question(question, profiles)
        reranked = retrieve_and_rerank(self.storage, question, target_entity)
        if not reranked:
            episodes = self.storage.get_all_episodes()
            answer = answer_strategy_b(self.api_key, question, profiles, episodes)
            return {"answer": answer, "strategy": "fallback_B", "strategies_tried": ["fallback_B"]}
        top_chunks = reranked[:6]
        passages = "\n\n---\n\n".join(f"[{c.get('date', '?')}] {c['text']}" for c in top_chunks)
        # Anti-hallucination single-hop prompt
        from .answerer import _llm_call, ANSWER_RULES, MODEL_ANSWER
        prompt = f"""Answer this question using ONLY the conversation excerpts below.

CRITICAL ANTI-HALLUCINATION RULES:
1. ONLY include facts EXPLICITLY stated in the excerpts — nothing from general knowledge
2. Adding items NOT in the excerpts is the WORST mistake — when in doubt, LEAVE IT OUT
3. Use EXACT words from the excerpts: exact titles, names, colors, numbers
4. For "how many": count ONLY items explicitly mentioned in excerpts
5. For lists: include ONLY items you can point to in the text
6. NEVER paraphrase or generalize

{ANSWER_RULES}

Conversation excerpts:
{passages}

Question: {question}

Answer (ONLY facts from above excerpts):"""
        answer = _llm_call(self.api_key, [{"role": "user", "content": prompt}],
                          max_tokens=150, model=MODEL_ANSWER)
        return {"answer": answer, "strategy": "v10_single_hop", "strategies_tried": ["v10_single_hop"]}

    def _recall_temporal(self, question: str) -> dict:
        temporal_events = self.storage.query_temporal_events(limit=50)
        temporal_context = ""
        if temporal_events:
            timeline = "\n".join(f"- {ev['date']}: {ev['entity']} — {ev['event_text']}" for ev in temporal_events)
            temporal_context = f"\n\nTimeline of Events:\n{timeline}"
        profiles = self.storage.get_all_profiles()
        episodes = self.storage.get_all_episodes()
        answer = answer_strategy_b(self.api_key, question, profiles, episodes, temporal_context=temporal_context)
        if not is_confident(answer):
            relevant_ids = self._identify_relevant_sessions(question, episodes)
            raw_sessions = self.storage.get_engrams(relevant_ids)
            answer = answer_strategy_c(self.api_key, question, profiles, episodes, raw_sessions, temporal_context=temporal_context)
            return {"answer": answer, "strategy": "temporal_C", "strategies_tried": ["temporal_B", "temporal_C"]}
        return {"answer": answer, "strategy": "temporal_B", "strategies_tried": ["temporal_B"]}

    def _recall_multihop(self, question: str) -> dict:
        sub_questions = decompose_multihop(self.api_key, question)
        if len(sub_questions) <= 1:
            profiles = self.storage.get_all_profiles()
            episodes = self.storage.get_all_episodes()
            relevant_ids = self._identify_relevant_sessions(question, episodes)
            raw_sessions = self.storage.get_engrams(relevant_ids)
            answer = answer_strategy_c(self.api_key, question, profiles, episodes, raw_sessions)
            return {"answer": answer, "strategy": "multihop_C", "strategies_tried": ["multihop_C"]}
        sub_qas = []
        for sq in sub_questions:
            result = self._recall_single_hop(sq)
            sub_qas.append((sq, result["answer"]))
        final = synthesize_subanswers(self.api_key, question, sub_qas)
        return {"answer": final, "strategy": "multihop_decompose", "strategies_tried": ["multihop_decompose"]}

    def _recall_open_domain(self, question: str) -> dict:
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
        profiles = self.storage.get_all_profiles()
        episodes = self.storage.get_all_episodes()
        relevant_ids = self._identify_relevant_sessions(question, episodes)
        raw_sessions = self.storage.get_engrams(relevant_ids)
        reranked = retrieve_and_rerank(self.storage, question)
        reranked_context = ""
        if reranked:
            passages = "\n\n---\n\n".join(f"[{c.get('date', '?')}] {c['text']}" for c in reranked[:8])
            reranked_context = f"\n\nRelevant Conversation Excerpts:\n{passages}"
        atomic_facts = self.storage.search_atomic_facts(question, limit=10)
        if atomic_facts:
            facts_text = "\n".join(f"- {f['fact_text']}" for f in atomic_facts)
            reranked_context += f"\n\nRelevant Atomic Facts:\n{facts_text}"
        masked_profiles, masked_episodes, masked_raw = _mask_entities_in_context(
            question, profiles, episodes, raw_sessions)
        answer = answer_strategy_c(self.api_key, question, masked_profiles, masked_episodes, masked_raw, temporal_context=reranked_context)
        return {"answer": answer, "strategy": "adversarial_masked", "strategies_tried": ["adversarial_masked"]}

    # ── Helpers ────────────────────────────────────────────────

    def _extract_entity_from_question(self, question: str, profiles: list[dict]) -> str | None:
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

    def _extract_all_entities(self, question: str, profiles: list[dict]) -> list[str]:
        question_lower = question.lower()
        matches = []
        for p in profiles:
            name = p["entity"]
            if name.lower() in question_lower or name.split()[0].lower() in question_lower:
                matches.append(name)
        return matches

    def _identify_relevant_sessions(self, question: str, episodes: list[dict], max_sessions: int = 5) -> list[str]:
        fts_results = self.storage.search_episodes(question, limit=max_sessions)
        if fts_results:
            return [r["session_id"] for r in fts_results]
        words = re.findall(r'\b\w+\b', question.lower())
        stop = {'what','when','where','who','how','did','does','do','is','are','was','were',
                'the','a','an','in','on','at','to','for','of','with','has','have','had',
                'and','or','but','not','this','that','they','their','it','its','about','from','by'}
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
