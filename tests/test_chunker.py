from pathlib import Path

import pytest

from graphtrace.ingestion.chunker import chunk_document
from graphtrace.models import Document


def make_doc(text: str, doc_id: str = "svc") -> Document:
    return Document(doc_id=doc_id, title="Svc", path=Path(f"{doc_id}.md"), text=text)


def test_splits_on_second_level_headings():
    chunks = chunk_document(make_doc("# Svc\n\n## A\nalpha text\n\n## B\nbeta text"))
    assert [c.section for c in chunks] == ["A", "B"]
    assert [c.text for c in chunks] == ["alpha text", "beta text"]


def test_ids_are_sequential_and_deterministic():
    doc = make_doc("# Svc\n\n## A\none\n\n## B\ntwo")
    ids = [c.chunk_id for c in chunk_document(doc)]
    assert ids == ["svc#01", "svc#02"]
    assert ids == [c.chunk_id for c in chunk_document(doc)]


def test_text_before_first_heading_becomes_introduction():
    chunks = chunk_document(make_doc("# Svc\nIntro line.\n\n## A\nbody"))
    assert chunks[0].section == "Introduction"
    assert chunks[0].text == "Intro line."


def test_empty_sections_and_title_only_documents_yield_no_chunks():
    assert chunk_document(make_doc("# Svc\n\n## Empty\n\n## Also empty\n")) == []
    assert chunk_document(make_doc("# Svc")) == []


def test_long_section_is_split_without_exceeding_max_chars():
    text = "# Svc\n\n## Long\n" + "The gateway forwards the request. " * 50
    chunks = chunk_document(make_doc(text), max_chars=200)
    assert len(chunks) > 1
    assert all(len(c.text) <= 200 for c in chunks)
    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_text_without_break_points_is_hard_split():
    chunks = chunk_document(make_doc("# Svc\n\n## Blob\n" + "x" * 500), max_chars=100)
    assert len(chunks) == 5
    assert all(len(c.text) == 100 for c in chunks)


def test_invalid_max_chars_is_rejected():
    with pytest.raises(ValueError):
        chunk_document(make_doc("# Svc\n\n## A\nbody"), max_chars=0)