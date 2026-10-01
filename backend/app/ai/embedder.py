"""
Sentence embeddings for tickets and knowledge (ONNX via fastembed — no torch
in the API image).

The model is chosen by the P4 benchmark (reports/classification/*,
reports/duplicates/*) and configured with EMBEDDING_MODEL. Models are
downloaded at image build time (Dockerfile), so containers never fetch them at
runtime.

`HashingEmbedder` is a deterministic, dependency-free stand-in used by the test
suite (EMBEDDING_MODEL=test-hashing): it makes tests fast and offline while
exercising the same code paths. It is never used to produce reported metrics.
"""

import hashlib
import logging
import re
import threading
from typing import Protocol

import numpy as np

from app.core.config import settings
from app.db.database import EMBEDDING_DIM

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


class FastEmbedEmbedder:
    def __init__(self, model_name: str):
        from fastembed import TextEmbedding

        self.name = model_name
        self._model = TextEmbedding(
            model_name=model_name,
            cache_dir=settings.model_cache_dir or None,
            threads=settings.embedding_threads or None,
        )

    def embed(self, texts: list[str]) -> np.ndarray:
        batch_size = max(1, settings.embedding_batch_size)
        vecs = np.asarray(list(self._model.embed(texts, batch_size=batch_size)), dtype=np.float32)
        return vecs / np.maximum(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-12)


class HashingEmbedder:
    """Bag-of-words hashing trick into EMBEDDING_DIM buckets, L2-normalized."""

    name = "test-hashing"

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), EMBEDDING_DIM), dtype=np.float32)
        for i, text in enumerate(texts):
            for token in re.findall(r"[a-z0-9]+", text.lower()):
                h = int(hashlib.md5(token.encode(), usedforsecurity=False).hexdigest(), 16)
                out[i, h % EMBEDDING_DIM] += 1.0 if (h >> 20) & 1 else -1.0
        return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)


_lock = threading.Lock()
_instance: Embedder | None = None


def get_embedder() -> Embedder | None:
    """Process-wide embedder, or None when AI is disabled or the model can't load
    (the product then runs on the rules engine alone)."""
    global _instance
    if not settings.ai_enabled:
        return None
    if _instance is None:
        with _lock:
            if _instance is None:
                try:
                    if settings.embedding_model == HashingEmbedder.name:
                        _instance = HashingEmbedder()
                    else:
                        _instance = FastEmbedEmbedder(settings.embedding_model)
                except Exception:
                    logger.exception("embedder_unavailable", extra={"model": settings.embedding_model})
                    return None
    return _instance


def reset_embedder() -> None:
    global _instance
    _instance = None


def ticket_text(title: str, description: str) -> str:
    return f"{title.strip()}\n{description.strip()}"[:4000]
