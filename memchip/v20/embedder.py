from __future__ import annotations
"""v20 embedder: Sentence-transformer embeddings for atomic facts."""

import numpy as np
from typing import Optional

_model = None
_model_name = "all-MiniLM-L6-v2"  # 384-dim, fast, good for short texts


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_model_name)
        print(f"  Loaded embedding model: {_model_name}")
    return _model


def embed_text(text: str) -> np.ndarray:
    """Embed a single text string."""
    model = get_model()
    return model.encode(text, normalize_embeddings=True)


def embed_texts(texts: list[str], batch_size: int = 64) -> np.ndarray:
    """Embed multiple texts efficiently."""
    model = get_model()
    return model.encode(texts, normalize_embeddings=True, batch_size=batch_size)


def cosine_similarity(query_vec: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between query and multiple document vectors.
    Assumes vectors are already normalized (from normalize_embeddings=True).
    """
    return np.dot(doc_vecs, query_vec)
