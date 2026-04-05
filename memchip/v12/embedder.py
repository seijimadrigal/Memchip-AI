from __future__ import annotations
"""Embedding utilities for MemChip v12 hybrid retrieval."""

import numpy as np

_embed_model = None


def get_embed_model():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer('all-MiniLM-L6-v2')
    return _embed_model


def embed_texts(texts: list[str]) -> np.ndarray:
    model = get_embed_model()
    return model.encode(texts, normalize_embeddings=True)


def embed_query(query: str) -> np.ndarray:
    model = get_embed_model()
    return model.encode(query, normalize_embeddings=True)
