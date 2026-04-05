from __future__ import annotations
"""Main MemChip v10 class: v8.2 structured extraction + CrossEncoder reranker retrieval."""

from .storage import Storage
from .consolidation import consolidate_session
from .router import classify_query, is_confident, escalate, decompose_multihop
from .answerer import (
    answer_strategy_a, answer_strategy_b, answer_strategy_c, answer_strategy_d,
    answer_open_domain, synthesize_subanswers, _mask_entities_in_context,
)

# Lazy-loaded reranker
_reranker = None

def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder("mixedbread-ai/mxbai-rerank-large-v1")
    return _reranker


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


def rerank_chunks(question: str, chunks: list[dict], min_keep: int = 6, max_tokens: int = 4000) -> list[dict]:
    """Rerank chunks with CrossEncoder and score-adaptive truncation."""
    if not chunks:
        return []
    model = _get_reranker()
    pairs = [(question, c["text"]) for c in chunks]
    scores = model.predict(pairs)
    for c, s in zip(chunks, scores):
        c["rerank_score"] = float(s)
    ranked = sorted(chunks, key=lambda x: -x["rerank_score"])
    
    # Score-adaptive truncation
    top_n = min(20, len(ranked))
    if top_n > 1:
        max_gap = 0
        cut_idx = top_n
        for i in range(1, top_n):
            gap = ranked[i-1]["rerank_score"] - ranked[i]["rerank_score"]
            if gap > max_gap and i >= min_keep:
                max_gap = gap
                cut_idx = i
        if max_gap > 2.0:
            ranked = ranked[:cut_idx]
        else:
            ranked = ranked[:top_n]
    
    # Token budget
    result = []
    token_count = 0
    for c in ranked:
        chunk_tokens = len(c["text"].split())
        if token_count + chunk_tokens > max_tokens and result:
            break
        result.append(c)
        token_count += chunk_tokens
    return result


def extract_atomic_sentences(text: str) -> list[str]:
    """Split text into atomic sentences/facts."""
    import re
    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+|\n+', text)
    # Clean and filter
    result = []
    for s in sentences:
        s = s.strip()
        # Skip very short or non-informative fragments
        if len(s) > 15 and any(c.isalpha() for c in s):
            result.append(s)
    return result


def filter_facts_by_relevance(question: str, chunks: list[dict], max_facts: int = 8) -> list[str]:
    """CRAG-style: decompose chunks into atomic facts, rerank each fact, keep top-K."""
    model = _get_reranker()
    
    # Extract all atomic facts from chunks
    all_facts = []
    for c in chunks:
        sentences = extract_atomic_sentences(c["text"])
        for s in sentences:
            all_facts.append({"text": s, "date": c.get("date", "?")})
    
    if not all_facts:
        return []
    
    # Score each individual fact against the question
    pairs = [(question, f["text"]) for f in all_facts]
    scores = model.predict(pairs)
    
    for f, s in zip(all_facts, scores):
        f["score"] = float(s)
    
    # Sort by relevance, keep top-K
    ranked = sorted(all_facts, key=lambda x: -x["score"])
    top = ranked[:max_facts]
    
    # Return as formatted strings
    return [f"[{f['date']}] {f['text']}" for f in top]


def _answer_from_chunks(api_key: str, question: str, passages: str) -> str:
    """Answer a single-hop question using ONLY reranked conversation excerpts."""
    from .answerer import _llm_call, ANSWER_RULES
    prompt = f"""Answer this question using ONLY the conversation excerpts below.

{ANSWER_RULES}

Conversation excerpts:
{passages}

Question: {question}

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=100)


def _answer_single_hop_v3(api_key: str, question: str, passages: str, profile_text: str = "", is_multihop: bool = False) -> str:
    """v10.4.2: Answer using raw chunks. Restored from run49 prompt (86.8%)."""
    from .answerer import _llm_call
    
    prompt = f"""Answer this question using the conversation excerpts below as your PRIMARY source.

RULES:
- Be MAXIMALLY CONCISE — answer like a trivia quiz
- ONLY include facts that DIRECTLY answer the specific question asked
- Do NOT list everything you know about the person — only what the question asks
- For "What does X do to Y?" — list ONLY activities specifically described as being for Y
- For "recently" or "latest" — give ONLY the most recent item
- For "how many" — give the EXACT number (never "multiple" or "several")
- Resolve references: convert "yesterday" to actual dates, "that book" to the actual title
- PRECISION over RECALL: fewer correct items beats many items with extras
- No explanations, no context, no "Based on..."
- If multiple items: comma-separated, no bullets

Conversation excerpts:
{passages}

Question: {question}

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=100, model="openai/gpt-4.1")


def retrieve_and_rerank(storage: Storage, question: str, entity: str | None = None) -> list[dict]:
    """Retrieve raw chunks via FTS5 + person search, then rerank with CrossEncoder."""
    import re
    # Build search terms
    stop = {"what","when","where","who","how","did","does","do","is","are","was","were",
            "the","a","an","in","on","at","to","for","of","with","has","have","had",
            "and","or","but","not","this","that","they","their","it","its","about","from","by"}
    words = re.findall(r'\b\w+\b', question.lower())
    terms = [w for w in words if w not in stop and len(w) > 2]
    
    # Always include entity name in search
    if entity:
        for part in entity.split():
            if part.lower() not in [t.lower() for t in terms]:
                terms.append(part)
    
    # Search raw chunks
    candidates = storage.search_raw_chunks(terms, limit=80)
    
    # Also search by entity name alone for broader recall
    if entity:
        entity_results = storage.search_raw_chunks([entity], limit=50)
        seen_ids = {c["id"] for c in candidates}
        for r in entity_results:
            if r["id"] not in seen_ids:
                candidates.append(r)
                seen_ids.add(r["id"])
    
    if not candidates:
        return []
    
    return rerank_chunks(question, candidates)


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
        
        # Single-hop (category 4): skip classify, go direct to targeted search
        if category == 4:
            return self._recall_single_hop(question, "B", top_k=4)
        
        # Temporal (category 2): skip classify, use B with temporal enrichment
        if category == 2:
            return self._recall_temporal(question, "B")
        
        # Multi-hop (category 1): use single-hop handler (chunks only, no profiles)
        # with top-6 chunks for broader coverage
        if category == 1:
            return self._recall_single_hop(question, "B", top_k=6)
        
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

    def _recall_single_hop(self, question: str, strategy: str, top_k: int = 4) -> dict:
        """Single-hop recall: tight top-K chunks + precision-focused prompt (v10.3)."""
        profiles = self.storage.get_all_profiles()
        
        # Extract main entity for targeted retrieval
        target_entity = self._extract_entity_from_question(question, profiles)
        
        # Retrieve and rerank raw chunks
        reranked = retrieve_and_rerank(self.storage, question, target_entity)
        
        if not reranked:
            # Fallback to profiles if no chunks found
            filtered_profiles = profiles
            if target_entity:
                filtered_profiles = [p for p in profiles if p["entity"].lower() == target_entity.lower()]
            episodes = self.storage.get_all_episodes()
            if target_entity:
                episodes = [ep for ep in episodes if target_entity.lower() in ep["summary"].lower()]
            answer = answer_strategy_b(self.api_key, question, filtered_profiles, episodes)
            return {"answer": answer, "strategy": "fallback_B", "strategies_tried": ["fallback_B"]}
        
        # v10.4.2: Use top_k chunks, NO profiles (profiles cause vague/over-listed answers)
        top_chunks = reranked[:top_k]
        passages = "\n\n---\n\n".join(
            f"[{c.get('date', '?')}] {c['text']}" for c in top_chunks
        )
        
        # Detect if this is being used for multi-hop (top_k > 4)
        is_multihop = top_k > 4
        
        answer = _answer_single_hop_v3(self.api_key, question, passages, is_multihop=is_multihop)
        return {
            "answer": answer,
            "strategy": "v10.3_hybrid",
            "strategies_tried": ["v10.3_hybrid"],
        }
    
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
        """Adversarial recall: mask entity names + reranked chunks (v10)."""
        profiles = self.storage.get_all_profiles()
        episodes = self.storage.get_all_episodes()
        
        # Get relevant raw sessions
        relevant_ids = self._identify_relevant_sessions(question, episodes)
        raw_sessions = self.storage.get_engrams(relevant_ids)
        
        # v10: Reranked raw chunks
        reranked = retrieve_and_rerank(self.storage, question)
        reranked_context = ""
        if reranked:
            passages = "\n\n---\n\n".join(f"[{c.get('date', '?')}] {c['text']}" for c in reranked[:8])
            reranked_context = f"\n\nRelevant Conversation Excerpts:\n{passages}"
        
        # v8: Get atomic facts for supplementary evidence
        atomic_facts = self.storage.search_atomic_facts(question, limit=10)
        if atomic_facts:
            facts_text = "\n".join(f"- {f['fact_text']}" for f in atomic_facts)
            reranked_context += f"\n\nRelevant Atomic Facts:\n{facts_text}"
        
        # Mask entities
        masked_profiles, masked_episodes, masked_raw = _mask_entities_in_context(
            question, profiles, episodes, raw_sessions
        )
        
        answer = answer_strategy_c(self.api_key, question, masked_profiles, masked_episodes, masked_raw, temporal_context=reranked_context)
        
        return {
            "answer": answer,
            "strategy": "adversarial_masked_v10",
            "strategies_tried": ["adversarial_masked_v10"],
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
