import logging

import pytest

from graphtrace.ingestion.loader import load_documents


def test_loads_sorted_md_files_and_extracts_titles(tmp_path):
    (tmp_path / "b.md").write_text("# Beta Doc\n\n## S\ntext", encoding="utf-8")
    (tmp_path / "a.md").write_text("no title here", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")

    docs = load_documents(tmp_path)

    assert [d.doc_id for d in docs] == ["a", "b"]
    assert docs[0].title == "a"  # falls back to the file stem
    assert docs[1].title == "Beta Doc"


def test_empty_files_are_skipped_with_a_warning(tmp_path, caplog):
    (tmp_path / "empty.md").write_text("  \n", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        docs = load_documents(tmp_path)
    assert docs == []
    assert "empty.md" in caplog.text


def test_missing_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_documents(tmp_path / "does_not_exist")


def test_utf8_bom_is_stripped_from_title(tmp_path):
    (tmp_path / "bom.md").write_bytes(b"\xef\xbb\xbf# Titled\n\n## S\ntext")
    assert load_documents(tmp_path)[0].title == "Titled"