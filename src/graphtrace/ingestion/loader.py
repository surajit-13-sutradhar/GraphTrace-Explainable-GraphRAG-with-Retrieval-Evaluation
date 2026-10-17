"""Load markdown documents from a directory."""

from __future__ import annotations

import logging
from pathlib import Path

from graphtrace.models import Document

logger = logging.getLogger(__name__)


def _extract_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def load_documents(docs_dir: Path) -> list[Document]:
    """Load every .md file in docs_dir, sorted by name for deterministic ordering."""
    if not docs_dir.is_dir():
        raise FileNotFoundError(f"Documents directory not found: {docs_dir}")

    documents: list[Document] = []
    for path in sorted(docs_dir.glob("*.md")):
        # utf-8-sig also strips the BOM that some Windows editors add.
        text = path.read_text(encoding="utf-8-sig").strip()
        if not text:
            logger.warning("Skipping empty document: %s", path.name)
            continue
        documents.append(
            Document(
                doc_id=path.stem,
                title=_extract_title(text, fallback=path.stem),
                path=path,
                text=text,
            )
        )
    return documents