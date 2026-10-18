"""Baseline RAG retrieval: embed the question, return the top-k most similar chunks."""

from __future__ import annotations

import time

from graphtrace.models import RetrievalResult
from graphtrace.retrieval.embedder import Embedder
from graphtrace.retrieval.vector_index import VectorIndex

DEFAULT_TOP_K = 5


class BaselineRetriever:
    def __init__(self, index: VectorIndex, embedder: Embedder, k: int = DEFAULT_TOP_K) -> None:
        if k < 1:
            raise ValueError("k must be at least 1")
        self._index = index
        self._embedder = embedder
        self.k = k

    def retrieve(self, question: str) -> RetrievalResult:
        start = time.perf_counter()
        hits = self._index.search(self._embedder.encode([question])[0], self.k)
        return RetrievalResult(
            question=question,
            method="baseline",
            chunks=hits,
            retrieval_ms=(time.perf_counter() - start) * 1000,
        )