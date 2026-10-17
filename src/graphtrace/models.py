"""Core data models shared across GraphTrace modules."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Document(BaseModel):
    """A source document loaded from disk."""

    model_config = ConfigDict(frozen=True)

    doc_id: str  # file stem, e.g. "authentication_service"
    title: str
    path: Path
    text: str


class Chunk(BaseModel):
    """A citable piece of a document. chunk_id is the provenance key used everywhere."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str  # e.g. "authentication_service#04"
    doc_id: str
    doc_title: str
    section: str
    text: str = Field(min_length=1)

    def contextual_text(self) -> str:
        """Text with its title and section prepended; used later for embedding."""
        return f"{self.doc_title} > {self.section}\n{self.text}"