"""Test vector retrieval on its own (no Gemini needed)."""

import argparse
import time

from graphtrace.config import VECTOR_DIR
from graphtrace.retrieval.embedder import Embedder
from graphtrace.retrieval.vector_index import VectorIndex


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    index = VectorIndex.load(VECTOR_DIR)
    embedder = Embedder(index.model_name)
    start = time.perf_counter()
    results = index.search(embedder.encode([args.query])[0], args.k)
    elapsed_ms = (time.perf_counter() - start) * 1000
    print(f"Query: {args.query!r}  ({elapsed_ms:.1f} ms incl. query embedding)\n")
    for r in results:
        print(f"{r.score:.3f}  {r.chunk.chunk_id:<40} [{r.chunk.section}]")
        print(f"       {r.chunk.text[:110]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())