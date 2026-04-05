from __future__ import annotations
"""v20 retriever: Hybrid BM25+Embedding search with RRF fusion and CrossEncoder reranking."""

import re
import numpy as np
from typing import Optional
from .embedder import embed_text, cosine_similarity
from .storage import Storage

_reranker = None


def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder("mixedbread-ai/mxbai-rerank-large-v1")
        print("  Loaded CrossEncoder reranker")
    return _reranker


def _tokenize_for_bm25(text: str) -> list[str]:
    """Simple tokenization for BM25."""
    stop = {'what','when','where','who','how','did','does','do','is','are','was','were',
            'the','a','an','in','on','at','to','for','of','with','has','have','had',
            'and','or','but','not','this','that','they','their','it','its','about',
            'from','by','she','he','her','his','him','was','been','being','would',
            'could','should','will','can','may','might','shall','must','need'}
    words = re.findall(r'\b\w+\b', text.lower())
    return [w for w in words if w not in stop and len(w) > 1]


def embedding_search(query: str, storage: Storage, top_n: int = 50) -> list[dict]:
    """Vector similarity search over atomic fact embeddings."""
    query_vec = embed_text(query)
    all_embs = storage.get_all_embeddings()
    
    if not all_embs:
        return []
    
    # Build matrix of all embeddings
    ids = [e["fact_id"] for e in all_embs]
    texts = [e["fact_text"] for e in all_embs]
    entities = [e["entity"] for e in all_embs]
    dates = [e["date"] for e in all_embs]
    sessions = [e["session_id"] for e in all_embs]
    emb_matrix = np.array([e["embedding"] for e in all_embs])
    
    # Cosine similarity (vectors already normalized)
    scores = cosine_similarity(query_vec, emb_matrix)
    
    # Get top_n indices
    top_indices = np.argsort(scores)[::-1][:top_n]
    
    results = []
    for idx in top_indices:
        results.append({
            "fact_id": ids[idx],
            "fact_text": texts[idx],
            "entity": entities[idx],
            "date": dates[idx],
            "session_id": sessions[idx],
            "score": float(scores[idx]),
            "source": "embedding",
        })
    
    return results


def bm25_search(query: str, storage: Storage, top_n: int = 50) -> list[dict]:
    """BM25 search via FTS5 on atomic facts."""
    results = storage.search_facts_fts(query, limit=top_n)
    output = []
    for i, r in enumerate(results):
        output.append({
            "fact_id": r["fact_id"],
            "fact_text": r["fact_text"],
            "entity": r["entity"],
            "date": r.get("date", ""),
            "session_id": r.get("session_id", ""),
            "score": float(-r.get("rank", 0)),  # FTS5 rank is negative (lower = better)
            "source": "bm25",
        })
    return output


def rrf_fusion(results_list: list[list[dict]], k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion across multiple result lists.
    
    RRF score(doc) = Σ(1 / (k + rank_i)) for each result list.
    No score normalization needed — purely rank-based.
    """
    doc_scores = {}  # fact_id -> rrf_score
    doc_map = {}     # fact_id -> doc dict
    
    for results in results_list:
        for rank, doc in enumerate(results, start=1):
            fid = doc["fact_id"]
            if fid not in doc_map:
                doc_map[fid] = doc
            doc_scores[fid] = doc_scores.get(fid, 0.0) + 1.0 / (k + rank)
    
    # Sort by RRF score descending
    sorted_ids = sorted(doc_scores.keys(), key=lambda fid: -doc_scores[fid])
    
    fused = []
    for fid in sorted_ids:
        doc = doc_map[fid].copy()
        doc["rrf_score"] = doc_scores[fid]
        doc["source"] = "rrf"
        fused.append(doc)
    
    return fused


def rerank(query: str, facts: list[dict], top_n: int = 20) -> list[dict]:
    """Rerank facts using CrossEncoder."""
    if not facts:
        return []
    
    model = _get_reranker()
    pairs = [(query, f["fact_text"]) for f in facts]
    scores = model.predict(pairs)
    
    for f, s in zip(facts, scores):
        f["rerank_score"] = float(s)
    
    ranked = sorted(facts, key=lambda x: -x["rerank_score"])
    return ranked[:top_n]


def hybrid_retrieve(query: str, storage: Storage,
                     emb_top_n: int = 50, bm25_top_n: int = 50,
                     rerank_top_n: int = 20, rrf_k: int = 60,
                     entity: str | None = None) -> list[dict]:
    """Full hybrid retrieval pipeline: BM25 + Embedding → RRF → Rerank.
    
    1. Run BM25 and embedding search in parallel (both top 50)
    2. Fuse with RRF (k=60)
    3. Rerank top results with CrossEncoder
    4. Return top 20
    """
    # If we have a target entity, boost the query
    boosted_query = query
    if entity:
        boosted_query = f"{entity} {query}"
    
    # Run both searches
    emb_results = embedding_search(boosted_query, storage, top_n=emb_top_n)
    bm25_results = bm25_search(query, storage, top_n=bm25_top_n)
    
    # RRF fusion
    fused = rrf_fusion([emb_results, bm25_results], k=rrf_k)
    
    if not fused:
        return []
    
    # Take top candidates for reranking (reranking is expensive)
    candidates = fused[:min(40, len(fused))]
    
    # Rerank
    reranked = rerank(query, candidates, top_n=rerank_top_n)
    
    return reranked
