"""Local CPU sentence-transformers wrapper."""

from __future__ import annotations

import numpy as np

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class Embedder:
    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL) -> None:
        from sentence_transformers import SentenceTransformer  # heavy import, so loaded lazily

        self.model_name = model_name
        self._model = SentenceTransformer(model_name, device="cpu")
        self.dimension = int(self._model.encode(["probe"]).shape[1])

    def encode(self, texts: list[str]) -> np.ndarray:
        """L2-normalized float32 vectors, so inner product equals cosine similarity."""
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        vectors = self._model.encode(
            texts,
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return np.asarray(vectors, dtype=np.float32)