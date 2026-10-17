"""Heading-based chunking with a size cap and deterministic IDs."""

from __future__ import annotations

import re

from graphtrace.models import Chunk, Document

DEFAULT_MAX_CHARS = 1200

_SPLIT_LEVELS = (
    (r"\n\s*\n", "\n\n"),         # paragraphs
    (r"(?<=[.!?])\s+", " "),      # sentences
)


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Split on '## ' headings into (section_name, body). The '# ' title line is dropped."""
    sections: list[tuple[str, str]] = []
    name = "Introduction"
    buffer: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            sections.append((name, "\n".join(buffer).strip()))
            name = line[3:].strip()
            buffer = []
        elif line.startswith("# "):
            continue
        else:
            buffer.append(line)
    sections.append((name, "\n".join(buffer).strip()))
    return sections


def _pack(units: list[str], max_chars: int, sep: str) -> list[str]:
    """Greedily join units with sep without exceeding max_chars (unless one unit alone does)."""
    pieces: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}{sep}{unit}" if current else unit
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                pieces.append(current)
            current = unit
    if current:
        pieces.append(current)
    return pieces


def _split_long(text: str, max_chars: int) -> list[str]:
    """Split text into pieces <= max_chars: paragraphs, then sentences, then a hard cut."""
    if len(text) <= max_chars:
        return [text]
    for pattern, sep in _SPLIT_LEVELS:
        units = [u.strip() for u in re.split(pattern, text) if u.strip()]
        if len(units) > 1:
            pieces: list[str] = []
            for piece in _pack(units, max_chars, sep):
                pieces.extend(_split_long(piece, max_chars))
            return pieces
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def chunk_document(doc: Document, max_chars: int = DEFAULT_MAX_CHARS) -> list[Chunk]:
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    chunks: list[Chunk] = []
    for section, body in _split_sections(doc.text):
        if not body:
            continue
        for piece in _split_long(body, max_chars):
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.doc_id}#{len(chunks) + 1:02d}",
                    doc_id=doc.doc_id,
                    doc_title=doc.title,
                    section=section,
                    text=piece,
                )
            )
    return chunks


def chunk_documents(docs: list[Document], max_chars: int = DEFAULT_MAX_CHARS) -> list[Chunk]:
    return [chunk for doc in docs for chunk in chunk_document(doc, max_chars)]