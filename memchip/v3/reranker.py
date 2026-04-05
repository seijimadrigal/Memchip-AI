"""CrossEncoder reranker with score-adaptive truncation."""
from __future__ import annotations
from sentence_transformers import CrossEncoder

_model = None

def _get_model():
    global _model
    if _model is None:
        _model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _model


def rerank(question: str, candidates: list[dict], max_tokens: int = 4000) -> list[dict]:
    """Rerank candidates using CrossEncoder and apply score-adaptive truncation.
    
    Returns truncated list of candidates sorted by relevance score.
    """
    if not candidates:
        return []
    
    model = _get_model()
    
    # Score all candidates
    pairs = [(question, c["text"]) for c in candidates]
    scores = model.predict(pairs)
    
    # Attach scores
    for c, s in zip(candidates, scores):
        c["rerank_score"] = float(s)
    
    # Sort by score descending
    ranked = sorted(candidates, key=lambda x: -x["rerank_score"])
    
    # Score-adaptive truncation
    # Find biggest score gap in top-20, truncate there
    MIN_KEEP = 6  # Always keep at least 6 for aggregation questions
    top_n = min(20, len(ranked))
    if top_n > 1:
        max_gap = 0
        cut_idx = top_n
        for i in range(1, top_n):
            gap = ranked[i-1]["rerank_score"] - ranked[i]["rerank_score"]
            if gap > max_gap and i >= MIN_KEEP:
                max_gap = gap
                cut_idx = i
        
        # Only cut if gap is very significant (> 2.0 score difference)
        if max_gap > 2.0:
            ranked = ranked[:cut_idx]
        else:
            ranked = ranked[:top_n]
    
    # Token budget truncation
    result = []
    token_count = 0
    for c in ranked:
        # Rough token estimate: words / 0.75
        chunk_tokens = len(c["text"].split())
        if token_count + chunk_tokens > max_tokens and result:
            break
        result.append(c)
        token_count += chunk_tokens
    
    return result
