"""MemChip v23: SmartSearch-style raw text retrieval + dual reranking.

Architecture:
1. Ingest: Raw conversation → overlapping chunks (250 words, 50 overlap) → SQLite+FTS5
2. Query: SpaCy NER/POS → weighted FTS5 search → multi-hop expansion → 200 candidates
3. Rank: CrossEncoder (mxbai-rerank-large-v1) + ColBERT (answerai-colbert-small-v1) → RRF fusion
4. Truncate: Score-adaptive + token budget
5. Answer: Category-specific reading comprehension prompts
"""
from __future__ import annotations
from .storage import RawTextStore
from .retriever import retrieve
from .reranker import rerank
from .answerer import answer_question


def chunk_conversation(turns: list[dict], max_words: int = 250, overlap: int = 50) -> list[str]:
    """Split conversation turns into overlapping text chunks with speaker labels."""
    lines = []
    for turn in turns:
        speaker = turn.get("speaker", "Unknown")
        text = turn.get("text", "")
        lines.append(f"{speaker}: {text}")
    
    full_text = "\n".join(lines)
    words = full_text.split()
    
    if len(words) <= max_words:
        return [full_text]
    
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end >= len(words):
            break
        start = end - overlap
    
    return chunks


class MemChipV23:
    def __init__(self, api_key: str, db_path: str):
        self.api_key = api_key
        self.store = RawTextStore(db_path)
    
    def ingest_session(self, session_id: str, date: str, turns: list[dict],
                       speaker_a: str = "", speaker_b: str = ""):
        """Ingest a conversation session as raw text chunks."""
        chunks = chunk_conversation(turns)
        self.store.add_chunks(session_id, date, chunks)
    
    def query(self, question: str, category: int = 4) -> dict:
        """Full pipeline: retrieve → rerank → answer."""
        # Retrieve candidates (NER-weighted)
        candidates = retrieve(self.store, question, max_candidates=200)
        
        if not candidates:
            return {
                "answer": "Not mentioned in the conversations.",
                "num_candidates": 0,
                "num_ranked": 0,
            }
        
        # Dual rerank (CrossEncoder + ColBERT + RRF)
        ranked = rerank(question, candidates, max_tokens=3500)
        
        if not ranked:
            return {
                "answer": "Not mentioned in the conversations.",
                "num_candidates": len(candidates),
                "num_ranked": 0,
            }
        
        # Answer (reading comprehension)
        answer = answer_question(self.api_key, question, ranked, category=category)
        
        return {
            "answer": answer,
            "num_candidates": len(candidates),
            "num_ranked": len(ranked),
            "top_score": ranked[0].get("rrf_score", 0),
            "top_ce_score": ranked[0].get("ce_score", 0),
        }
    
    def close(self):
        self.store.close()
