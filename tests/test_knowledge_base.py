from graphtrace.config import DOCS_DIR
from graphtrace.ingestion.chunker import chunk_documents
from graphtrace.ingestion.loader import load_documents


def test_real_knowledge_base_chunks_cleanly():
    docs = load_documents(DOCS_DIR)
    assert len(docs) >= 8

    chunks = chunk_documents(docs)
    ids = [c.chunk_id for c in chunks]

    assert len(ids) == len(set(ids)), "chunk IDs must be unique"
    assert len(chunks) >= 30
    assert all(c.text.strip() for c in chunks)
    assert {c.doc_id for c in chunks} == {d.doc_id for d in docs}