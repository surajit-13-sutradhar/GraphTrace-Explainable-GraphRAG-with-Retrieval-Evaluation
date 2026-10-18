"""Embed all chunks locally and persist a FAISS index."""

import time

from graphtrace.config import DOCS_DIR, VECTOR_DIR
from graphtrace.ingestion.chunker import chunk_documents
from graphtrace.ingestion.loader import load_documents
from graphtrace.retrieval.embedder import Embedder
from graphtrace.retrieval.vector_index import VectorIndex


def main() -> None:
    chunks = chunk_documents(load_documents(DOCS_DIR))
    start = time.perf_counter()
    embedder = Embedder()  # first run downloads the model
    index = VectorIndex.build(chunks, embedder)
    index.save(VECTOR_DIR)
    print(f"Indexed {len(chunks)} chunks with {embedder.model_name} "
          f"(dim {embedder.dimension}) in {time.perf_counter() - start:.1f}s -> {VECTOR_DIR}")


if __name__ == "__main__":
    main()