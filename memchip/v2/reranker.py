from __future__ import annotations
"""Lightweight CrossEncoder reranker for post-retrieval reranking."""

import os

_reranker = None


def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _reranker


def rerank(query: str, passages: list[str], top_k: int = 5) -> list[int]:
    """Rerank passages by relevance to query. Returns indices of top-k passages."""
    if not passages:
        return []
    if len(passages) <= top_k:
        return list(range(len(passages)))
    
    model = _get_reranker()
    pairs = [[query, p] for p in passages]
    scores = model.predict(pairs)
    
    # Sort by score descending, return top-k indices
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return ranked[:top_k]


def rerank_dicts(query: str, items: list[dict], text_key: str, top_k: int = 5) -> list[dict]:
    """Rerank a list of dicts by a text field. Returns top-k items reranked."""
    if not items or len(items) <= top_k:
        return items
    
    passages = [item[text_key] for item in items]
    top_indices = rerank(query, passages, top_k)
    return [items[i] for i in top_indices]
