from __future__ import annotations
"""MemChip v19: Entity-attributed narrative facts via re-ingestion.
- Single-hop/Multi-hop: chunks + entity_facts reranked together
- Temporal: v10.4 episodes+timeline (proven 94.6%)
- Adversarial: entity masking (proven 83%)
"""

from .storage import Storage
from .consolidation import consolidate_session
from .router import classify_query, is_confident, escalate, decompose_multihop
from .answerer import (
    answer_strategy_a, answer_strategy_b, answer_strategy_c, answer_strategy_d,
    answer_open_domain, synthesize_subanswers, _mask_entities_in_context,
    _llm_call, ANSWER_RULES, judge_answer,
)

_reranker = None

def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder("mixedbread-ai/mxbai-rerank-large-v1")
    return _reranker


def chunk_text(text: str, max_tokens: int = 250, overlap_tokens: int = 50) -> list[str]:
    words = text.split()
    if len(words) <= max_tokens:
        return [text]
    chunks, start = [], 0
    while start < len(words):
        end = min(start + max_tokens, len(words))
        chunks.append(" ".join(words[start:end]))
        if end >= len(words): break
        start = end - overlap_tokens
    return chunks


def rerank_chunks(question: str, chunks: list[dict], min_keep: int = 6, max_tokens: int = 4000) -> list[dict]:
    if not chunks: return []
    model = _get_reranker()
    pairs = [(question, c["text"]) for c in chunks]
    scores = model.predict(pairs)
    for c, s in zip(chunks, scores):
        c["rerank_score"] = float(s)
    ranked = sorted(chunks, key=lambda x: -x["rerank_score"])
    top_n = min(20, len(ranked))
    if top_n > 1:
        max_gap, cut_idx = 0, top_n
        for i in range(1, top_n):
            gap = ranked[i-1]["rerank_score"] - ranked[i]["rerank_score"]
            if gap > max_gap and i >= min_keep:
                max_gap = gap
                cut_idx = i
        if max_gap > 2.0:
            ranked = ranked[:cut_idx]
        else:
            ranked = ranked[:top_n]
    result, token_count = [], 0
    for c in ranked:
        ct = len(c["text"].split())
        if token_count + ct > max_tokens and result: break
        result.append(c)
        token_count += ct
    return result


def retrieve_and_rerank(storage: Storage, question: str, entity: str | None = None) -> list[dict]:
    """Retrieve raw chunks + entity_facts, rerank together."""
    import re
    stop = {"what","when","where","who","how","did","does","do","is","are","was","were",
            "the","a","an","in","on","at","to","for","of","with","has","have","had",
            "and","or","but","not","this","that","they","their","it","its","about","from","by"}
    words = re.findall(r'\b\w+\b', question.lower())
    terms = [w for w in words if w not in stop and len(w) > 2]
    if entity:
        for part in entity.split():
            if part.lower() not in [t.lower() for t in terms]:
                terms.append(part)
    
    # Get raw chunks
    candidates = storage.search_raw_chunks(terms, limit=80)
    if entity:
        entity_results = storage.search_raw_chunks([entity], limit=50)
        seen = {c["id"] for c in candidates}
        for r in entity_results:
            if r["id"] not in seen:
                candidates.append(r)
                seen.add(r["id"])
    
    # v19: Also pull entity_facts and convert to chunk-like dicts for joint reranking
    entity_fact_chunks = _get_entity_fact_chunks(storage, question, entity)
    candidates.extend(entity_fact_chunks)
    
    return rerank_chunks(question, candidates) if candidates else []


def _get_entity_fact_chunks(storage: Storage, question: str, entity: str | None) -> list[dict]:
    """Pull entity facts and format as pseudo-chunks for reranking."""
    fact_chunks = []
    seen_facts = set()
    
    # Search by question keywords
    q_facts = storage.search_entity_facts(question, entity=entity, limit=20)
    for f in q_facts:
        if f["fact"] not in seen_facts:
            seen_facts.add(f["fact"])
            fact_chunks.append({
                "id": f"ef_{len(fact_chunks)}",
                "session_id": f.get("session_id", ""),
                "chunk_idx": -1,
                "text": f"[{f['entity']}] {f['fact']}",
                "date": f.get("date", ""),
                "source": "entity_fact",
            })
    
    # If we have a target entity, also get ALL their facts (FTS-filtered by question)
    if entity:
        e_facts = storage.search_entity_facts(question, entity=entity, limit=30)
        for f in e_facts:
            if f["fact"] not in seen_facts:
                seen_facts.add(f["fact"])
                fact_chunks.append({
                    "id": f"ef_{len(fact_chunks)}",
                    "session_id": f.get("session_id", ""),
                    "chunk_idx": -1,
                    "text": f"[{f['entity']}] {f['fact']}",
                    "date": f.get("date", ""),
                    "source": "entity_fact",
                })
    
    # Also search without entity filter for multi-entity questions
    if not entity:
        all_facts = storage.search_entity_facts(question, limit=20)
        for f in all_facts:
            if f["fact"] not in seen_facts:
                seen_facts.add(f["fact"])
                fact_chunks.append({
                    "id": f"ef_{len(fact_chunks)}",
                    "session_id": f.get("session_id", ""),
                    "chunk_idx": -1,
                    "text": f"[{f['entity']}] {f['fact']}",
                    "date": f.get("date", ""),
                    "source": "entity_fact",
                })
    
    return fact_chunks


def _answer_single_hop_v19(api_key: str, question: str, passages: str, profile_text: str = "", entity_facts_text: str = "") -> str:
    """v19: Answer from chunks + entity-attributed facts. No verification pass (v18 regression)."""
    profile_section = ""
    if profile_text:
        profile_section = f"""
Entity Profile (background context):
{profile_text}

"""
    
    ef_section = ""
    if entity_facts_text:
        ef_section = f"""
Entity-Attributed Facts (each fact is tagged with WHO it belongs to — trust entity attribution):
{entity_facts_text}

"""
    
    prompt = f"""Answer this question using the conversation excerpts and entity-attributed facts below.
Entity-attributed facts have [PersonName] tags — these tell you WHO a fact belongs to. Trust these tags to avoid confusing people.

RULES:
- Be MAXIMALLY CONCISE — answer like a trivia quiz
- Use EXACT words from the source when possible (specific names, places, titles, descriptions)
- Pay attention to [PersonName] tags: if asked about Melanie, use facts tagged [Melanie]
- For "how many" — COUNT carefully and give the exact number
- NEVER paraphrase specific nouns
- No explanations, no context, no "Based on..."
- If multiple items: comma-separated, no bullets

{profile_section}{ef_section}Conversation excerpts (primary source):
{passages}

Question: {question}

Answer:"""
    
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=150)


def _answer_from_chunks(api_key: str, question: str, passages: str, profile_text: str = "") -> str:
    """Chunk-based answer for multi-hop sub-questions."""
    profile_section = ""
    if profile_text:
        profile_section = f"""
Entity Profile (secondary context):
{profile_text}

"""
    prompt = f"""Answer this question using the conversation excerpts below as your PRIMARY source.

RULES:
- Be MAXIMALLY CONCISE — answer like a trivia quiz
- ONLY include facts that DIRECTLY answer the specific question asked
- Use EXACT words from the conversation when possible
- NEVER say "multiple" or "several" — give exact numbers or specific items
- No explanations, no context, no "Based on..."

{profile_section}Conversation excerpts (primary source):
{passages}

Question: {question}

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=100)


class MemChipV2:
    def __init__(self, api_key: str, db_path: str = ":memory:"):
        self.api_key = api_key
        self.storage = Storage(db_path)

    def add(self, session_id: str, date: str, conversation: list[dict], speaker_a: str, speaker_b: str):
        consolidate_session(self.api_key, self.storage, session_id, date, conversation, speaker_a, speaker_b)

    def recall(self, question: str, category: int | None = None, max_escalations: int = 3) -> dict:
        if category == 5:
            return self._recall_adversarial(question)
        if category == 3:
            return self._recall_open_domain(question)
        if category == 1:
            return self._recall_single_hop_v19(question)
        if category == 2:
            return self._recall_temporal(question)
        if category == 4:
            return self._recall_multihop(question)
        return self._recall_chunks_first(question, "unknown")

    def _recall_single_hop_v19(self, question: str) -> dict:
        """v19: Single-hop with entity-attributed facts mixed into reranking."""
        profiles = self.storage.get_all_profiles()
        target_entity = self._extract_entity_from_question(question, profiles)
        
        # Retrieve chunks + entity_facts, reranked together
        reranked = retrieve_and_rerank(self.storage, question, target_entity)
        
        if not reranked:
            episodes = self.storage.get_all_episodes()
            answer = answer_strategy_b(self.api_key, question, profiles, episodes)
            return {"answer": answer, "strategy": "v19_fallback_B", "strategies_tried": ["v19_fallback_B"]}
        
        # Separate entity_facts from chunks for distinct presentation
        chunk_items = [c for c in reranked if c.get("source") != "entity_fact"][:6]
        ef_items = [c for c in reranked if c.get("source") == "entity_fact"][:10]
        
        passages = "\n\n---\n\n".join(f"[{c.get('date', '?')}] {c['text']}" for c in chunk_items)
        
        entity_facts_text = ""
        if ef_items:
            entity_facts_text = "\n".join(f"- {c['text']}" for c in ef_items)
        
        # Get entity profile as fallback context
        profile_text = ""
        if target_entity:
            for p in profiles:
                if p["entity"].lower() == target_entity.lower():
                    profile_text = p["profile_text"]
                    break
        
        answer = _answer_single_hop_v19(self.api_key, question, passages, profile_text, entity_facts_text)
        return {"answer": answer, "strategy": "v19_single_hop", "strategies_tried": ["v19_single_hop"]}

    def _recall_chunks_first(self, question: str, label: str) -> dict:
        """Chunks-first + entity_facts for multi-hop sub-questions."""
        profiles = self.storage.get_all_profiles()
        target_entity = self._extract_entity_from_question(question, profiles)
        
        reranked = retrieve_and_rerank(self.storage, question, target_entity)
        
        if not reranked:
            episodes = self.storage.get_all_episodes()
            answer = answer_strategy_b(self.api_key, question, profiles, episodes)
            return {"answer": answer, "strategy": f"{label}_fallback_B", "strategies_tried": [f"{label}_fallback_B"]}
        
        top_chunks = reranked[:6]
        passages = "\n\n---\n\n".join(f"[{c.get('date', '?')}] {c['text']}" for c in top_chunks)
        
        profile_text = ""
        if target_entity:
            for p in profiles:
                if p["entity"].lower() == target_entity.lower():
                    profile_text = p["profile_text"]
                    break
        
        answer = _answer_from_chunks(self.api_key, question, passages, profile_text)
        return {"answer": answer, "strategy": f"v19_{label}", "strategies_tried": [f"v19_{label}"]}

    def _recall_temporal(self, question: str) -> dict:
        """Temporal: v10.4 strategy — episodes + timeline (proven 94.6%)."""
        profiles = self.storage.get_all_profiles()
        episodes = self.storage.get_all_episodes()
        
        temporal_events = self.storage.query_temporal_events(limit=50)
        temporal_context = ""
        if temporal_events:
            timeline = "\n".join(f"- {ev['date']}: {ev['entity']} — {ev['event_text']}" for ev in temporal_events)
            temporal_context = f"\n\nTimeline of Events:\n{timeline}"
        
        answer = answer_strategy_b(self.api_key, question, profiles, episodes, temporal_context=temporal_context)
        strat_name = "v19_temporal_B"
        
        if not is_confident(answer):
            relevant_ids = self._identify_relevant_sessions(question, episodes)
            raw_sessions = self.storage.get_engrams(relevant_ids)
            answer = answer_strategy_c(self.api_key, question, profiles, episodes, raw_sessions, temporal_context=temporal_context)
            strat_name = "v19_temporal_C"
        
        return {"answer": answer, "strategy": strat_name, "strategies_tried": [strat_name]}

    def _recall_multihop(self, question: str) -> dict:
        """Multi-hop: decompose + chunks-first (with entity_facts) for each sub."""
        sub_questions = decompose_multihop(self.api_key, question)
        
        if len(sub_questions) <= 1:
            return self._recall_chunks_first(question, "multihop_direct")
        
        sub_qas = []
        all_strategies = []
        for sq in sub_questions:
            result = self._recall_chunks_first(sq, "multihop_sub")
            sub_qas.append((sq, result["answer"]))
            all_strategies.extend(result["strategies_tried"])
        
        final_answer = synthesize_subanswers(self.api_key, question, sub_qas)
        
        if not is_confident(final_answer):
            result = self._recall_chunks_first(question, "multihop_fallback")
            return {
                "answer": result["answer"],
                "strategy": "multihop_fallback",
                "strategies_tried": all_strategies + result["strategies_tried"],
            }
        
        return {
            "answer": final_answer,
            "strategy": f"multihop({','.join(all_strategies)})",
            "strategies_tried": all_strategies,
        }

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
            question, profiles, episodes, raw_sessions
        )
        
        answer = answer_strategy_c(self.api_key, question, masked_profiles, masked_episodes, masked_raw, temporal_context=reranked_context)
        return {"answer": answer, "strategy": "adversarial_masked_v19", "strategies_tried": ["adversarial_masked_v19"]}

    def _extract_entity_from_question(self, question: str, profiles: list[dict]) -> str | None:
        import re
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

    def _identify_relevant_sessions(self, question: str, episodes: list[dict], max_sessions: int = 5) -> list[str]:
        fts_results = self.storage.search_episodes(question, limit=max_sessions)
        if fts_results:
            return [r["session_id"] for r in fts_results]
        import re
        words = re.findall(r'\b\w+\b', question.lower())
        stop = {'what','when','where','who','how','did','does','do','is','are','was','were','the','a','an','in','on','at','to','for','of','with','has','have','had','and','or','but','not','this','that','they','their','it','its','about','from','by'}
        keywords = [w for w in words if w not in stop and len(w) > 2]
        scored = []
        for ep in episodes:
            sl = ep["summary"].lower()
            score = sum(1 for kw in keywords if kw in sl)
            if score > 0: scored.append((score, ep["session_id"]))
        scored.sort(reverse=True)
        return [sid for _, sid in scored[:max_sessions]]

    def close(self):
        self.storage.close()
