from __future__ import annotations
"""MemChip v16: chunks-first for ALL categories. Profile = fallback only."""

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
    candidates = storage.search_raw_chunks(terms, limit=80)
    if entity:
        entity_results = storage.search_raw_chunks([entity], limit=50)
        seen = {c["id"] for c in candidates}
        for r in entity_results:
            if r["id"] not in seen:
                candidates.append(r)
                seen.add(r["id"])
    return rerank_chunks(question, candidates) if candidates else []


def _answer_from_chunks(api_key: str, question: str, passages: str, profile_text: str = "", num_chunks: int = 6) -> str:
    """v16: Answer any question using reranked chunks + profile as secondary context."""
    profile_section = ""
    if profile_text:
        profile_section = f"""
Entity Profile (secondary context — conversation excerpts are the PRIMARY source):
{profile_text}

"""

    prompt = f"""Answer this question using the conversation excerpts below as your PRIMARY source.
The profile provides background context but excerpts are more reliable for specific details.

RULES:
- Be MAXIMALLY CONCISE — answer like a trivia quiz
- ONLY include facts that DIRECTLY answer the specific question asked
- Do NOT list everything you know about the person — only what the question asks
- Use EXACT words from the conversation when possible (specific names, places, titles, descriptions)
- For "What does X do to Y?" — list ONLY activities specifically described as being for Y
- For "recently" or "latest" — give ONLY the most recent item
- For "how many" — give the exact number
- For descriptive questions ("What kind of...") — use the EXACT description from the conversation, not a paraphrase
- PRECISION over RECALL: fewer correct items beats many items with extras
- No explanations, no context, no "Based on..."
- If multiple items: comma-separated, no bullets

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
            return self._recall_chunks_first(question, "single-hop")
        if category == 2:
            return self._recall_temporal(question)
        if category == 4:
            return self._recall_multihop(question)
        # Unknown category — use chunks
        return self._recall_chunks_first(question, "unknown")

    def _recall_chunks_first(self, question: str, label: str) -> dict:
        """v16: All non-special categories use reranked chunks as primary source."""
        profiles = self.storage.get_all_profiles()
        target_entity = self._extract_entity_from_question(question, profiles)
        
        reranked = retrieve_and_rerank(self.storage, question, target_entity)
        
        if not reranked:
            # Fallback to profile-based answering
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
        return {"answer": answer, "strategy": f"v16_{label}", "strategies_tried": [f"v16_{label}"]}

    def _recall_temporal(self, question: str) -> dict:
        """Temporal: chunks + temporal events timeline."""
        profiles = self.storage.get_all_profiles()
        target_entity = self._extract_entity_from_question(question, profiles)
        
        # Get temporal events
        temporal_events = self.storage.query_temporal_events(limit=50)
        temporal_ctx = ""
        if temporal_events:
            timeline = "\n".join(f"- {ev['date']}: {ev['entity']} — {ev['event_text']}" for ev in temporal_events)
            temporal_ctx = f"\n\nTimeline of Events:\n{timeline}"
        
        reranked = retrieve_and_rerank(self.storage, question, target_entity)
        
        if reranked:
            top_chunks = reranked[:6]
            passages = "\n\n---\n\n".join(f"[{c.get('date', '?')}] {c['text']}" for c in top_chunks)
            passages += temporal_ctx
            
            profile_text = ""
            if target_entity:
                for p in profiles:
                    if p["entity"].lower() == target_entity.lower():
                        profile_text = p["profile_text"]
                        break
            
            answer = _answer_from_chunks(self.api_key, question, passages, profile_text)
            return {"answer": answer, "strategy": "v16_temporal", "strategies_tried": ["v16_temporal"]}
        
        # Fallback
        episodes = self.storage.get_all_episodes()
        answer = answer_strategy_b(self.api_key, question, profiles, episodes, temporal_context=temporal_ctx)
        return {"answer": answer, "strategy": "temporal_fallback_B", "strategies_tried": ["temporal_fallback_B"]}

    def _recall_multihop(self, question: str) -> dict:
        """Multi-hop: decompose into sub-questions, answer each with chunks."""
        sub_questions = decompose_multihop(self.api_key, question)
        
        if len(sub_questions) <= 1:
            # Not decomposable — answer directly with chunks
            return self._recall_chunks_first(question, "multihop_direct")
        
        sub_qas = []
        all_strategies = []
        for sq in sub_questions:
            result = self._recall_chunks_first(sq, "multihop_sub")
            sub_qas.append((sq, result["answer"]))
            all_strategies.extend(result["strategies_tried"])
        
        final_answer = synthesize_subanswers(self.api_key, question, sub_qas)
        
        if not is_confident(final_answer):
            # Fallback: answer the full question directly with more chunks
            result = self._recall_chunks_first(question, "multihop_fallback")
            return {
                "answer": result["answer"],
                "strategy": f"multihop_fallback",
                "strategies_tried": all_strategies + result["strategies_tried"],
            }
        
        return {
            "answer": final_answer,
            "strategy": f"multihop({','.join(all_strategies)})",
            "strategies_tried": all_strategies,
        }

    def _recall_open_domain(self, question: str) -> dict:
        """Open-domain: needs inference + world knowledge."""
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
        """Adversarial: mask entities + reranked chunks."""
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
        return {"answer": answer, "strategy": "adversarial_masked_v16", "strategies_tried": ["adversarial_masked_v16"]}

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
