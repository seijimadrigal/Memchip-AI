"""CrossEncoder + ColBERT dual reranking with RRF fusion (SmartSearch-style).

Key differences from v3:
- mxbai-rerank-large-v1 (435M DeBERTaV3) instead of ms-marco-MiniLM-L-6-v2 (22M)
- ColBERT late-interaction scoring as second signal
- RRF (Reciprocal Rank Fusion) to merge both rankings
- Better score-adaptive truncation
"""
from __future__ import annotations
import numpy as np
from sentence_transformers import CrossEncoder, SentenceTransformer

_cross_encoder = None
_colbert = None


def _get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        _cross_encoder = CrossEncoder("mixedbread-ai/mxbai-rerank-large-v1")
    return _cross_encoder


def _get_colbert():
    global _colbert
    if _colbert is None:
        try:
            _colbert = SentenceTransformer("answerdotai/answerai-colbert-small-v1")
        except Exception:
            _colbert = False  # Mark as unavailable
    return _colbert


def _colbert_score(query_emb: np.ndarray, doc_emb: np.ndarray) -> float:
    """Late-interaction ColBERT scoring: MaxSim over token embeddings."""
    # query_emb: (q_tokens, dim), doc_emb: (d_tokens, dim)
    # For each query token, find max similarity to any doc token
    sim_matrix = np.dot(query_emb, doc_emb.T)  # (q_tokens, d_tokens)
    max_sims = sim_matrix.max(axis=1)  # (q_tokens,)
    return float(max_sims.mean())


def rerank(question: str, candidates: list[dict], max_tokens: int = 3500,
           use_colbert: bool = True) -> list[dict]:
    """Dual reranking with CrossEncoder + ColBERT, fused via RRF.
    
    Returns truncated list sorted by fused relevance score.
    """
    if not candidates:
        return []
    
    ce = _get_cross_encoder()
    texts = [c["text"] for c in candidates]
    
    # === CrossEncoder scoring ===
    pairs = [(question, t) for t in texts]
    ce_scores = ce.predict(pairs)
    
    # === ColBERT scoring (optional) ===
    colbert = _get_colbert() if use_colbert else False
    
    if colbert and colbert is not False:
        try:
            # Encode query and all docs
            q_emb = colbert.encode(question, output_value="token_embeddings")
            d_embs = colbert.encode(texts, output_value="token_embeddings")
            
            if isinstance(q_emb, np.ndarray) and q_emb.ndim == 2:
                col_scores = [_colbert_score(q_emb, d) for d in d_embs]
            else:
                # Fallback: standard similarity
                q_emb_s = colbert.encode(question)
                d_embs_s = colbert.encode(texts)
                col_scores = np.dot(d_embs_s, q_emb_s).tolist()
        except Exception:
            col_scores = None
    else:
        col_scores = None
    
    # === RRF Fusion ===
    k = 60  # RRF constant
    
    # Rank by CrossEncoder
    ce_ranked = np.argsort(-np.array(ce_scores))
    
    rrf_scores = {}
    for rank, idx in enumerate(ce_ranked):
        rrf_scores[idx] = 1.0 / (k + rank + 1)
    
    if col_scores is not None:
        col_ranked = np.argsort(-np.array(col_scores))
        for rank, idx in enumerate(col_ranked):
            rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (k + rank + 1)
    
    # Sort by RRF score
    sorted_indices = sorted(rrf_scores.keys(), key=lambda i: -rrf_scores[i])
    
    ranked = []
    for idx in sorted_indices:
        c = candidates[idx].copy()
        c["ce_score"] = float(ce_scores[idx])
        c["rrf_score"] = rrf_scores[idx]
        if col_scores is not None:
            c["col_score"] = float(col_scores[idx])
        ranked.append(c)
    
    # === Score-adaptive truncation ===
    # Find natural breakpoint in RRF scores
    if len(ranked) > 3:
        scores = [r["rrf_score"] for r in ranked]
        max_gap = 0
        cut_idx = min(15, len(ranked))  # Default: top 15
        
        for i in range(2, min(20, len(ranked))):
            gap = scores[i-1] - scores[i]
            # Relative gap matters more than absolute
            if gap > max_gap and scores[i-1] > 0:
                rel_gap = gap / scores[i-1]
                if rel_gap > 0.15:  # 15% relative drop = natural break
                    max_gap = gap
                    cut_idx = i
        
        ranked = ranked[:cut_idx]
    
    # === Token budget truncation ===
    result = []
    token_count = 0
    for c in ranked:
        chunk_tokens = len(c["text"].split()) * 1.3  # Rough token estimate
        if token_count + chunk_tokens > max_tokens and result:
            break
        result.append(c)
        token_count += chunk_tokens
    
    return result
