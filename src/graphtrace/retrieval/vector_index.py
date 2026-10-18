"""FAISS index over chunk embeddings, persisted next to the chunk list it was built from."""

from __future__ import annotations

import json
from pathlib import Path

import faiss
import numpy as np

from graphtrace.models import Chunk, RetrievedChunk
from graphtrace.retrieval.embedder import Embedder


class VectorIndex:
    def __init__(self, index: faiss.Index, chunks: list[Chunk], model_name: str) -> None:
        if index.ntotal != len(chunks):
            raise ValueError("index size does not match chunk list")
        self._index = index
        self.chunks = chunks
        self.model_name = model_name

    @classmethod
    def build(cls, chunks: list[Chunk], embedder: Embedder) -> "VectorIndex":
        if not chunks:
            raise ValueError("cannot build an index from zero chunks")
        vectors = embedder.encode([c.contextual_text() for c in chunks])
        index = faiss.IndexFlatIP(vectors.shape[1])  # exact inner-product search
        index.add(vectors)
        return cls(index, list(chunks), embedder.model_name)

    def search(self, query_vector: np.ndarray, k: int) -> list[RetrievedChunk]:
        """Top-k chunks by cosine similarity, best first."""
        k = min(k, len(self.chunks))
        if k < 1:
            return []
        query = np.asarray(query_vector, dtype=np.float32).reshape(1, -1)
        scores, ids = self._index.search(query, k)
        return [
            RetrievedChunk(chunk=self.chunks[i], score=float(score), origin="vector")
            for score, i in zip(scores[0], ids[0])
            if i >= 0
        ]

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(directory / "vectors.faiss"))
        (directory / "chunks.json").write_text(
            json.dumps([c.model_dump(mode="json") for c in self.chunks], indent=1), encoding="utf-8"
        )
        (directory / "meta.json").write_text(
            json.dumps({"model_name": self.model_name, "num_chunks": len(self.chunks)}),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, directory: Path) -> "VectorIndex":
        needed = [directory / n for n in ("vectors.faiss", "chunks.json", "meta.json")]
        if not all(p.exists() for p in needed):
            raise FileNotFoundError(f"No vector index in {directory}. Run scripts/build_vectors.py.")
        index = faiss.read_index(str(directory / "vectors.faiss"))
        chunks = [Chunk.model_validate(c) for c in json.loads(needed[1].read_text(encoding="utf-8"))]
        meta = json.loads(needed[2].read_text(encoding="utf-8"))
        return cls(index, chunks, meta["model_name"])