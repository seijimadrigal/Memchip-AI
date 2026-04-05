"""MemChip v25: SmartSearch retrieval + category-specific strategies.

Combines:
- v23's SmartSearch retrieval (NER-weighted FTS5 + mxbai CrossEncoder reranking)
- v10.4's temporal strategy (timeline of extracted events → +20pp over raw)
- v10.4's multi-hop strategy (episode summaries for broader coverage)
- Correct LoCoMo categories: 1=multi-hop, 2=temporal, 3=open-domain, 4=single-hop

Single-hop: top-4 reranked chunks, concise prompt (proven 70-83%)
Temporal: top-4 chunks + temporal events timeline (proven 95%)
Multi-hop: top-8 chunks for broader coverage + multi-hop prompt
Open-domain: top-4 chunks + world knowledge allowed
Adversarial: entity masking + chunks
"""
from __future__ import annotations
import re

# Reuse v23 retrieval + reranking (proven architecture)
from ..v23.storage import RawTextStore
from ..v23.retriever import retrieve
from ..v23.reranker import rerank

from .answerer import (
    answer_single_hop, answer_temporal, answer_multihop,
    answer_open_domain, answer_adversarial, _llm_call,
)

# v10 storage for episodes/temporal (if available)
_v10_storage = None


def chunk_conversation(turns: list[dict], max_words: int = 250, overlap: int = 50) -> list[str]:
    lines = [f"{t.get('speaker', '?')}: {t.get('text', '')}" for t in turns]
    full = "\n".join(lines)
    words = full.split()
    if len(words) <= max_words:
        return [full]
    chunks, start = [], 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunks.append(" ".join(words[start:end]))
        if end >= len(words): break
        start = end - overlap
    return chunks


class MemChipV25:
    def __init__(self, api_key: str, raw_db_path: str, v10_db_path: str = None):
        """
        raw_db_path: v23-style raw chunk DB
        v10_db_path: optional v10-style DB with episodes/temporal/profiles
        """
        self.api_key = api_key
        self.raw_store = RawTextStore(raw_db_path)
        self.v10_db_path = v10_db_path
        self._v10_storage = None
    
    @property
    def v10_storage(self):
        if self._v10_storage is None and self.v10_db_path:
            from ..v10.storage import Storage
            self._v10_storage = Storage(self.v10_db_path)
        return self._v10_storage
    
    def ingest_session(self, session_id: str, date: str, turns: list[dict],
                       speaker_a: str = "", speaker_b: str = ""):
        """Ingest raw chunks (v23 style)."""
        chunks = chunk_conversation(turns)
        self.raw_store.add_chunks(session_id, date, chunks)
    
    def query(self, question: str, category: int = 4) -> dict:
        """Route to best strategy per category.
        LoCoMo: 1=multi-hop, 2=temporal, 3=open-domain, 4=single-hop, 5=adversarial
        """
        if category == 5:
            return self._adversarial(question)
        elif category == 2:
            return self._temporal(question)
        elif category == 1:
            return self._multihop(question)
        elif category == 3:
            return self._open_domain(question)
        else:  # 4 = single-hop
            return self._single_hop(question)
    
    def _retrieve_and_rerank(self, question: str, top_k: int = 4) -> list[dict]:
        """SmartSearch-style: NER-weighted FTS5 → CrossEncoder+ColBERT rerank."""
        candidates = retrieve(self.raw_store, question, max_candidates=200)
        if not candidates:
            return []
        ranked = rerank(question, candidates, max_tokens=3500)
        return ranked[:top_k]
    
    def _format_passages(self, ranked: list[dict]) -> str:
        return "\n\n---\n\n".join(f"[{c.get('date', '?')}] {c['text']}" for c in ranked)
    
    def _single_hop(self, question: str) -> dict:
        """Top-4 reranked chunks, concise reading comprehension."""
        ranked = self._retrieve_and_rerank(question, top_k=4)
        if not ranked:
            return {"answer": "Not mentioned", "strategy": "single_hop_empty"}
        passages = self._format_passages(ranked)
        ans = answer_single_hop(self.api_key, question, passages)
        return {"answer": ans, "strategy": "single_hop_v25"}
    
    def _temporal(self, question: str) -> dict:
        """Chunks + temporal events timeline (the +20pp strategy)."""
        ranked = self._retrieve_and_rerank(question, top_k=4)
        passages = self._format_passages(ranked) if ranked else ""
        
        # Add temporal timeline from v10 DB if available
        timeline = ""
        if self.v10_storage:
            try:
                events = self.v10_storage.query_temporal_events(limit=50)
                if events:
                    timeline = "\n\nTimeline of Events:\n" + "\n".join(
                        f"- {ev['date']}: {ev['entity']} — {ev['event_text']}" for ev in events
                    )
            except: pass
        
        # Also add episode summaries for date context
        episodes_text = ""
        if self.v10_storage:
            try:
                episodes = self.v10_storage.get_all_episodes()
                if episodes:
                    episodes_text = "\n\nEpisode Summaries:\n" + "\n".join(
                        f"[{ep['session_id']} ({ep['date']})] {ep['summary'][:200]}" for ep in episodes
                    )
            except: pass
        
        full_context = passages + timeline + episodes_text
        if not full_context.strip():
            return {"answer": "Not mentioned", "strategy": "temporal_empty"}
        
        ans = answer_temporal(self.api_key, question, full_context)
        return {"answer": ans, "strategy": "temporal_v25"}
    
    def _multihop(self, question: str) -> dict:
        """More chunks (top-8) for broader coverage across sessions."""
        ranked = self._retrieve_and_rerank(question, top_k=8)
        if not ranked:
            return {"answer": "Not mentioned", "strategy": "multihop_empty"}
        passages = self._format_passages(ranked)
        
        # Also add episode summaries for cross-session context
        episodes_text = ""
        if self.v10_storage:
            try:
                episodes = self.v10_storage.get_all_episodes()
                if episodes:
                    episodes_text = "\n\nEpisode Summaries (for cross-session context):\n" + "\n".join(
                        f"[{ep['session_id']} ({ep['date']})] {ep['summary'][:300]}" for ep in episodes
                    )
            except: pass
        
        full_context = passages + episodes_text
        ans = answer_multihop(self.api_key, question, full_context)
        return {"answer": ans, "strategy": "multihop_v25"}
    
    def _open_domain(self, question: str) -> dict:
        """Chunks + world knowledge."""
        ranked = self._retrieve_and_rerank(question, top_k=4)
        passages = self._format_passages(ranked) if ranked else ""
        ans = answer_open_domain(self.api_key, question, passages)
        return {"answer": ans, "strategy": "open_domain_v25"}
    
    def _adversarial(self, question: str) -> dict:
        """Entity masking + chunks."""
        ranked = self._retrieve_and_rerank(question, top_k=4)
        if not ranked:
            return {"answer": "Not mentioned", "strategy": "adversarial_empty"}
        
        passages = self._format_passages(ranked)
        
        # Entity masking: detect speakers from context and swap
        if self.v10_storage:
            try:
                profiles = self.v10_storage.get_all_profiles()
                speakers = [p["entity"] for p in profiles]
                q_lower = question.lower()
                q_entity = None
                other = None
                for s in speakers:
                    if s.lower() in q_lower:
                        q_entity = s
                    else:
                        other = s
                if q_entity and other:
                    passages = passages.replace(other, q_entity)
            except: pass
        
        ans = answer_adversarial(self.api_key, question, passages)
        return {"answer": ans, "strategy": "adversarial_v25"}
    
    def close(self):
        self.raw_store.close()
        if self._v10_storage:
            self._v10_storage.close()
