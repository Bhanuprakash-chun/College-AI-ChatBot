"""Sentence-Transformer embeddings shared by ingestion and query time.

The model is loaded lazily and cached process-wide: importing this module is
cheap, so the API can boot in under a second and pay the ~1s model load on the
first embedding call instead.
"""

import logging
import threading

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

_model = None
_model_name: str | None = None
_lock = threading.Lock()


def get_model(model_name: str | None = None):
    """Load (once) and return the SentenceTransformer instance."""
    global _model, _model_name
    name = model_name or settings.EMBEDDING_MODEL
    if _model is not None and _model_name == name:
        return _model
    with _lock:
        if _model is not None and _model_name == name:
            return _model
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model %s ...", name)
        _model = SentenceTransformer(name)
        _model_name = name
        logger.info(
            "Embedding model ready (dim=%s, max_seq_length=%s)",
            getattr(_model, "get_embedding_dimension", _model.get_sentence_embedding_dimension)(),
            getattr(_model, "max_seq_length", "unknown"),
        )
        return _model


class Embedder:
    """Embeds documents and questions into the same vector space."""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.EMBEDDING_MODEL

    @property
    def model(self):
        return get_model(self.model_name)

    @property
    def dimension(self) -> int:
        getter = getattr(self.model, "get_embedding_dimension", None) or self.model.get_sentence_embedding_dimension
        return int(getter())

    def embed_texts(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        """Embed a batch of chunks. Returns an (N, dim) float32 array."""
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        vectors = self.model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,  # unit norm, so cosine == dot product
            show_progress_bar=False,
        )
        return vectors.astype(np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        """Embed a single student question."""
        return self.embed_texts([text])[0]


embedder = Embedder()
