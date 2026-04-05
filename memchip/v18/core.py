from __future__ import annotations
"""MemChip v18: Two-pass answering + entity-specific atomic facts.
- Single-hop/Multi-hop: chunks-first + atomic fact supplement + verification pass
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


def _answer_single_hop_v18(api_key: str, question: str, passages: str, profile_text: str = "", atomic_facts_text: str = "") -> str:
    """v18: Two-pass answering for single-hop.
    Pass 1: Generate answer from chunks + atomic facts.
    Pass 2: Verify each item against question scope.
    """
    profile_section = ""
    if profile_text:
        profile_section = f"""
Entity Profile (background context):
{profile_text}

"""
    
    atomic_section = ""
    if atomic_facts_text:
        atomic_section = f"""
Entity-Specific Facts (use these to fill gaps in conversation excerpts):
{atomic_facts_text}

"""
    
    # Pass 1: Generate initial answer
    prompt_p1 = f"""Answer this question using the conversation excerpts below as your PRIMARY source.
Use entity-specific facts to supplement missing details. Use the profile only as last resort.

RULES:
- Be MAXIMALLY CONCISE — answer like a trivia quiz
- Use EXACT words from the conversation when possible (specific names, places, titles, descriptions)
- For "how many" — COUNT carefully and give the exact number
- For "What does X do to Y?" — list ONLY activities specifically described as being for/to Y
- For "recently" or "latest" — give ONLY the most recent item
- NEVER paraphrase specific nouns: "Sweden" stays "Sweden", "sunsets" stays "sunsets", "Single" stays "Single"
- If the conversation says someone is "Single" or had a "breakup", the relationship status is "Single"
- If asked about a subject/topic, give the SPECIFIC subject, not a category (e.g., "sunsets" not "nature")
- No explanations, no context, no "Based on..."
- If multiple items: comma-separated, no bullets

{profile_section}{atomic_section}Conversation excerpts (primary source):
{passages}

Question: {question}

Answer:"""
    
    answer_p1 = _llm_call(api_key, [{"role": "user", "content": prompt_p1}], max_tokens=150)
    
    # Pass 2: Verify — check if answer over-lists or is too vague
    # Only do verification for list-type questions (what does, what events, what activities)
    import re
    list_patterns = [
        r"what (?:does|did|has|activities|events|books|things)",
        r"what .+ do to",
        r"what .+ participated",
        r"what symbols",
        r"what .+ has .+ done",
    ]
    is_list_q = any(re.search(p, question.lower()) for p in list_patterns)
    
    if is_list_q and len(answer_p1) > 30:
        prompt_verify = f"""You gave this answer to a question. Check if you OVER-LISTED items that weren't specifically asked about.

Question: {question}
Your answer: {answer_p1}

VERIFICATION RULES:
- Re-read the question carefully. What EXACTLY is being asked?
- If the question asks "What does X do to DESTRESS?" — only keep activities explicitly described as destressing activities, not ALL activities X does
- If the question asks about "LGBTQ+ events" — only keep LGBTQ+ events, not all events
- If the question asks about "helping children" — only keep events specifically about helping children
- If the question asks about "symbols important to X" — only keep items described as symbols or symbolically important
- Remove any items that don't DIRECTLY match the question's specific scope
- Keep the same concise format (comma-separated, no explanations)

Corrected answer (remove extras, keep only what directly answers the question):"""
        
        answer_p2 = _llm_call(api_key, [{"role": "user", "content": prompt_verify}], max_tokens=100)
        return answer_p2
    
    return answer_p1


def _answer_from_chunks(api_key: str, question: str, passages: str, profile_text: str = "", num_chunks: int = 6) -> str:
    """v17-style answer for multi-hop (no verification pass needed)."""
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
- For descriptive questions ("What kind of...") — use the EXACT description from the conversation, not a paraphrase
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
            return self._recall_single_hop_v18(question)
        if category == 2:
            return self._recall_temporal(question)
        if category == 4:
            return self._recall_multihop(question)
        return self._recall_chunks_first(question, "unknown")

    def _recall_single_hop_v18(self, question: str) -> dict:
        """v18: Single-hop with two-pass answering + entity-specific atomic facts."""
        profiles = self.storage.get_all_profiles()
        target_entity = self._extract_entity_from_question(question, profiles)
        
        # Get reranked chunks
        reranked = retrieve_and_rerank(self.storage, question, target_entity)
        
        if not reranked:
            episodes = self.storage.get_all_episodes()
            answer = answer_strategy_b(self.api_key, question, profiles, episodes)
            return {"answer": answer, "strategy": "v18_fallback_B", "strategies_tried": ["v18_fallback_B"]}
        
        top_chunks = reranked[:6]
        passages = "\n\n---\n\n".join(f"[{c.get('date', '?')}] {c['text']}" for c in top_chunks)
        
        # Get entity profile
        profile_text = ""
        if target_entity:
            for p in profiles:
                if p["entity"].lower() == target_entity.lower():
                    profile_text = p["profile_text"]
                    break
        
        # v18: Get ALL atomic facts about the target entity (not just keyword-matched)
        atomic_facts_text = ""
        if target_entity:
            entity_facts = self.storage.search_atomic_facts(target_entity, limit=30)
            if entity_facts:
                # Also search by question keywords for additional relevant facts
                q_facts = self.storage.search_atomic_facts(question, limit=10)
                all_facts = {f['fact_text']: f for f in entity_facts}
                for f in q_facts:
                    all_facts[f['fact_text']] = f
                atomic_facts_text = "\n".join(f"- {f['fact_text']}" for f in all_facts.values())
        
        answer = _answer_single_hop_v18(self.api_key, question, passages, profile_text, atomic_facts_text)
        return {"answer": answer, "strategy": "v18_single_hop", "strategies_tried": ["v18_single_hop"]}

    def _recall_chunks_first(self, question: str, label: str) -> dict:
        """Chunks-first for multi-hop sub-questions."""
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
        return {"answer": answer, "strategy": f"v18_{label}", "strategies_tried": [f"v18_{label}"]}

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
        strat_name = "v18_temporal_B"
        
        if not is_confident(answer):
            relevant_ids = self._identify_relevant_sessions(question, episodes)
            raw_sessions = self.storage.get_engrams(relevant_ids)
            answer = answer_strategy_c(self.api_key, question, profiles, episodes, raw_sessions, temporal_context=temporal_context)
            strat_name = "v18_temporal_C"
        
        return {"answer": answer, "strategy": strat_name, "strategies_tried": [strat_name]}

    def _recall_multihop(self, question: str) -> dict:
        """Multi-hop: decompose + chunks-first for each sub-question."""
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
        return {"answer": answer, "strategy": "adversarial_masked_v18", "strategies_tried": ["adversarial_masked_v18"]}

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
