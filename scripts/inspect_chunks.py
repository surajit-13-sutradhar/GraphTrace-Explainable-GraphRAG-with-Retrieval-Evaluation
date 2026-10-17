"""Print a summary of the loaded documents and chunks."""

from collections import Counter

from graphtrace.config import DOCS_DIR
from graphtrace.ingestion.chunker import chunk_documents
from graphtrace.ingestion.loader import load_documents


def main() -> None:
    docs = load_documents(DOCS_DIR)
    chunks = chunk_documents(docs)
    print(f"Documents: {len(docs)}")
    print(f"Chunks:    {len(chunks)}")
    if not chunks:
        return

    per_doc = Counter(c.doc_id for c in chunks)
    for doc in docs:
        print(f"  {doc.doc_id:<34} {per_doc[doc.doc_id]:>2} chunks")

    lengths = [len(c.text) for c in chunks]
    print(f"\nChunk length (chars): min={min(lengths)}  avg={sum(lengths) // len(lengths)}  max={max(lengths)}")

    sample = chunks[len(chunks) // 2]
    print(f"\nSample chunk: {sample.chunk_id} [{sample.section}]")
    print(sample.contextual_text())


if __name__ == "__main__":
    main()