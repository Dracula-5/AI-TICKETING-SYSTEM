"""Sentence-embedding helpers with an on-disk cache keyed by model + text hash,
so repeated experiment runs don't re-encode identical corpora."""

import hashlib

import numpy as np

from nexadesk_ml.paths import ROOT

CACHE = ROOT / "data" / "cache" / "embeddings"
CACHE.mkdir(parents=True, exist_ok=True)

_models: dict = {}


def load(model_name: str):
    if model_name not in _models:
        from sentence_transformers import SentenceTransformer

        _models[model_name] = SentenceTransformer(model_name, device="cpu")
    return _models[model_name]


def encode(model_name: str, texts: list[str], batch_size: int = 64, prefix: str = "") -> np.ndarray:
    """L2-normalized embeddings (cosine similarity = dot product)."""
    digest = hashlib.sha256(("\x1f".join(texts) + "|" + prefix).encode()).hexdigest()[:24]
    path = CACHE / f"{model_name.replace('/', '__')}-{digest}.npy"
    if path.exists():
        return np.load(path)
    model = load(model_name)
    vecs = model.encode([prefix + t for t in texts], batch_size=batch_size, normalize_embeddings=True,
                        show_progress_bar=False, convert_to_numpy=True)
    np.save(path, vecs.astype(np.float32))
    return vecs.astype(np.float32)
