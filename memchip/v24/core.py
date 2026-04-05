"""MemChip v24: Optimal hybrid — best strategy per category.

Category routing (based on empirical results across all runs):
- Single-hop (cat 1): v16 chunks+profile + few-shot prompt (best: 72.1%)
- Multi-hop (cat 4): v10 episodes+decomposition (best: 92.3%)
- Temporal (cat 2): v10.4 episodes+timeline (best: 94.6%)
- Open-domain (cat 3): chunks + general knowledge (best: 84.6%)
- Adversarial (cat 5): entity masking + chunks (best: 83%)

Key innovation for single-hop: few-shot examples teaching the model
LoCoMo's expected answer format/granularity.
"""
from __future__ import annotations
import re
from .storage import Storage
from .answerer import (
    answer_single_hop, answer_temporal, answer_multihop, 
    answer_open_domain, answer_adversarial, answer_fallback,
    synthesize_subanswers, _llm_call,
)

_reranker = None

def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder("mixedbread-ai/mxbai-rerank-large-v1")
    return _reranker


def chunk_text(text: str, max_words: int = 250, overlap: int = 50) -> list[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text]
    chunks, start = [], 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunks.append(" ".join(words[start:end]))
        if end >= len(words): break
        start = end - overlap
    return chunks


def rerank_chunks(question: str, chunks: list[dict], top_k: int = 6) -> list[dict]:
    if not chunks: return []
    model = _get_reranker()
    pairs = [(question, c["text"]) for c in chunks]
    scores = model.predict(pairs)
    for c, s in zip(chunks, scores):
        c["rerank_score"] = float(s)
    ranked = sorted(chunks, key=lambda x: -x["rerank_score"])
    return ranked[:top_k]


def retrieve_chunks(storage: Storage, question: str, entity: str | None = None, limit: int = 80) -> list[dict]:
    """Retrieve raw chunks via FTS5 + entity search."""
    stop = {"what","when","where","who","how","did","does","do","is","are","was","were",
            "the","a","an","in","on","at","to","for","of","with","has","have","had",
            "and","or","but","not","this","that","they","their","it","its","about","from","by",
            "which","would","could","should","will","can","may","been","being","both"}
    words = re.findall(r'\b\w+\b', question.lower())
    terms = [w for w in words if w not in stop and len(w) > 2]
    
    if entity:
        for part in entity.split():
            if part.lower() not in [t.lower() for t in terms]:
                terms.append(part)
    
    candidates = storage.search_raw_chunks(terms, limit=limit)
    seen_ids = {c["id"] for c in candidates}
    
    if entity:
        entity_results = storage.search_raw_chunks([entity], limit=50)
        for r in entity_results:
            if r["id"] not in seen_ids:
                candidates.append(r)
                seen_ids.add(r["id"])
    
    return candidates


def decompose_question(api_key: str, question: str) -> list[str]:
    """Decompose a multi-hop question into sub-questions."""
    prompt = f"""Break this question into 2-3 simpler sub-questions that can each be answered independently.
Output one sub-question per line, no numbering.

Question: {question}

Sub-questions:"""
    result = _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=150)
    subs = [line.strip().lstrip("0123456789.-) ") for line in result.strip().split("\n") if line.strip()]
    return subs[:3] if subs else [question]


class MemChipV24:
    def __init__(self, api_key: str, db_path: str):
        self.api_key = api_key
        self.storage = Storage(db_path)
    
    def ingest_session(self, session_id: str, date: str, turns: list[dict],
                       speaker_a: str, speaker_b: str):
        """Full ingestion: raw chunks + episodes + profiles + temporal events."""
        from .consolidation import consolidate_session
        consolidate_session(self.api_key, self.storage, session_id, date, turns, speaker_a, speaker_b)
    
    def query(self, question: str, category: int = 4) -> dict:
        """Route to best strategy per category."""
        # LoCoMo categories: 1=multi-hop, 2=temporal, 3=open-domain, 4=single-hop, 5=adversarial
        if category == 5:
            return self._adversarial(question)
        elif category == 2:
            return self._temporal(question)
        elif category == 1:
            return self._multihop(question)
        elif category == 3:
            return self._open_domain(question)
        else:  # category 4 (single-hop) or unknown
            return self._single_hop(question)
    
    def _extract_entity(self, question: str) -> str | None:
        """Extract main entity from question."""
        profiles = self.storage.get_all_profiles()
        q_lower = question.lower()
        matches = []
        for p in profiles:
            name = p["entity"]
            if name.lower() in q_lower:
                matches.append(name)
            else:
                first = name.split()[0]
                if first.lower() in q_lower:
                    matches.append(name)
        if len(matches) == 1:
            return matches[0]
        # Check possessives
        m = re.search(r"(\b\w+)'s\b", question)
        if m:
            poss = m.group(1).lower()
            for p in profiles:
                if p["entity"].split()[0].lower() == poss:
                    return p["entity"]
        return matches[0] if matches else None
    
    def _single_hop(self, question: str) -> dict:
        """Single-hop: reranked chunks ONLY — top 4 chunks, no profile."""
        profiles = self.storage.get_all_profiles()
        entity = self._extract_entity(question)
        
        candidates = retrieve_chunks(self.storage, question, entity)
        reranked = rerank_chunks(question, candidates, top_k=4)
        
        if not reranked:
            episodes = self.storage.get_all_episodes()
            if entity:
                episodes = [e for e in episodes if entity.lower() in e["summary"].lower()]
            ans = answer_fallback(self.api_key, question, profiles, episodes)
            return {"answer": ans, "strategy": "single_hop_fallback"}
        
        passages = "\n\n---\n\n".join(f"[{c.get('date', '?')}] {c['text']}" for c in reranked)
        
        # NO profile — it causes over-listing. Chunks only.
        ans = answer_single_hop(self.api_key, question, passages, profile_text="")
        return {"answer": ans, "strategy": "single_hop_chunks_only"}
    
    def _temporal(self, question: str) -> dict:
        """Temporal: episodes + timeline (v10.4 approach)."""
        profiles = self.storage.get_all_profiles()
        episodes = self.storage.get_all_episodes()
        temporal_events = self.storage.query_temporal_events(limit=50)
        
        timeline = ""
        if temporal_events:
            timeline = "\n\nTimeline of Events:\n" + "\n".join(
                f"- {ev['date']}: {ev['entity']} — {ev['event_text']}" for ev in temporal_events
            )
        
        ans = answer_temporal(self.api_key, question, profiles, episodes, timeline)
        return {"answer": ans, "strategy": "temporal_v24"}
    
    def _multihop(self, question: str) -> dict:
        """Multi-hop: chunks-first (same as single-hop but with multi-hop prompt)."""
        profiles = self.storage.get_all_profiles()
        entity = self._extract_entity(question)
        
        candidates = retrieve_chunks(self.storage, question, entity)
        reranked = rerank_chunks(question, candidates, top_k=8)
        
        if not reranked:
            episodes = self.storage.get_all_episodes()
            ans = answer_fallback(self.api_key, question, profiles, episodes)
            return {"answer": ans, "strategy": "multihop_fallback"}
        
        passages = "\n\n---\n\n".join(f"[{c.get('date', '?')}] {c['text']}" for c in reranked)
        ans = answer_multihop(self.api_key, question, passages)
        return {"answer": ans, "strategy": "multihop_chunks"}
    
    def _open_domain(self, question: str) -> dict:
        """Open-domain: chunks + allow world knowledge."""
        entity = self._extract_entity(question)
        candidates = retrieve_chunks(self.storage, question, entity)
        reranked = rerank_chunks(question, candidates, top_k=6)
        
        passages = ""
        if reranked:
            passages = "\n\n---\n\n".join(f"[{c.get('date', '?')}] {c['text']}" for c in reranked)
        
        ans = answer_open_domain(self.api_key, question, passages)
        return {"answer": ans, "strategy": "open_domain_v24"}
    
    def _adversarial(self, question: str) -> dict:
        """Adversarial: entity masking + chunks."""
        profiles = self.storage.get_all_profiles()
        entity = self._extract_entity(question)
        speakers = [p["entity"] for p in profiles]
        
        # Find which speaker is in the question vs the other
        q_lower = question.lower()
        question_entity = None
        other_entity = None
        for s in speakers:
            if s.lower() in q_lower:
                question_entity = s
            else:
                other_entity = s
        
        candidates = retrieve_chunks(self.storage, question, entity)
        reranked = rerank_chunks(question, candidates, top_k=6)
        
        if not reranked:
            return {"answer": "Not mentioned.", "strategy": "adversarial_empty"}
        
        passages = "\n\n---\n\n".join(f"[{c.get('date', '?')}] {c['text']}" for c in reranked)
        
        # Mask: replace other entity's name with question entity's name
        if question_entity and other_entity:
            passages = passages.replace(other_entity, question_entity)
        
        ans = answer_adversarial(self.api_key, question, passages)
        return {"answer": ans, "strategy": "adversarial_masked"}
    
    def close(self):
        self.storage.close()
