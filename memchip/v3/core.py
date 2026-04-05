"""MemChip v3 core: SmartSearch-style raw text retrieval + reranking."""
from __future__ import annotations
from .storage import RawTextStore
from .retriever import retrieve
from .reranker import rerank
from .answerer import answer_question


def chunk_conversation(turns: list[dict], speaker_a: str, speaker_b: str, 
                       max_tokens: int = 250, overlap_tokens: int = 50) -> list[str]:
    """Split conversation turns into overlapping text chunks."""
    # Build full text with speaker labels
    lines = []
    for turn in turns:
        speaker = turn.get("speaker", "Unknown")
        text = turn.get("text", "")
        lines.append(f"{speaker}: {text}")
    
    full_text = "\n".join(lines)
    words = full_text.split()
    
    if len(words) <= max_tokens:
        return [full_text]
    
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + max_tokens, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end >= len(words):
            break
        start = end - overlap_tokens
    
    return chunks


class MemChipV3:
    def __init__(self, api_key: str, db_path: str):
        self.api_key = api_key
        self.store = RawTextStore(db_path)
    
    def ingest_session(self, session_id: str, date: str, turns: list[dict],
                       speaker_a: str, speaker_b: str):
        """Ingest a conversation session as raw text chunks."""
        chunks = chunk_conversation(turns, speaker_a, speaker_b)
        self.store.add_chunks(session_id, date, chunks)
    
    def query(self, question: str, category: int = 1) -> dict:
        """Full pipeline: retrieve → rerank → answer."""
        # Retrieve candidates
        candidates = retrieve(self.store, question, max_candidates=80)
        
        # Rerank and truncate
        ranked = rerank(question, candidates, max_tokens=4000)
        
        if not ranked:
            return {
                "answer": "I don't have enough information to answer this question.",
                "num_candidates": len(candidates),
                "num_ranked": 0,
            }
        
        # Answer
        answer = answer_question(self.api_key, question, ranked, category=category)
        
        return {
            "answer": answer,
            "num_candidates": len(candidates),
            "num_ranked": len(ranked),
            "top_score": ranked[0]["rerank_score"] if ranked else 0,
        }
    
    def close(self):
        self.store.close()
