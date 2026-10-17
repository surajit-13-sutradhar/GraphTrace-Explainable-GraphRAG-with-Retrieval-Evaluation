"""Core data models shared across GraphTrace modules."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------- ingestion
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


# --------------------------------------------------------------- vocabulary
class EntityType(str, Enum):
    SERVICE = "SERVICE"
    DATABASE = "DATABASE"
    CACHE = "CACHE"
    QUEUE = "QUEUE"
    STORAGE = "STORAGE"
    EXTERNAL_PROVIDER = "EXTERNAL_PROVIDER"
    FEATURE = "FEATURE"


class RelationType(str, Enum):
    CALLS = "CALLS"
    ROUTES_TO = "ROUTES_TO"
    READS_FROM = "READS_FROM"
    WRITES_TO = "WRITES_TO"
    PUBLISHES_TO = "PUBLISHES_TO"
    CONSUMES_FROM = "CONSUMES_FROM"
    SERVES = "SERVES"
    FALLS_BACK_TO = "FALLS_BACK_TO"
    REPLICATES_TO = "REPLICATES_TO"


# ------------------------------------------- LLM-facing schema (what Gemini fills in)
class LLMEntity(BaseModel):
    name: str
    type: EntityType


class LLMRelationship(BaseModel):
    source: str
    relation: RelationType
    target: str
    evidence_quote: str


class LLMExtraction(BaseModel):
    entities: list[LLMEntity]
    relationships: list[LLMRelationship]


# ------------------------------------------ validated records (what we trust and store)
_STRICT = ConfigDict(frozen=True, str_strip_whitespace=True)


class ExtractedEntity(BaseModel):
    model_config = _STRICT

    name: str = Field(min_length=1)
    type: EntityType


class ExtractedRelationship(BaseModel):
    """A directed edge: source --relation--> target, with provenance."""

    model_config = _STRICT

    source: str = Field(min_length=1)
    relation: RelationType
    target: str = Field(min_length=1)
    evidence_quote: str = Field(min_length=1)
    chunk_id: str  # set by us, never by the LLM
    quote_verified: bool = False  # True if evidence_quote appears in the chunk text

    @model_validator(mode="after")
    def _reject_self_loops(self) -> "ExtractedRelationship":
        if self.source.casefold() == self.target.casefold():
            raise ValueError("self-referential relationship")
        return self


class ChunkExtraction(BaseModel):
    """Validated extraction result for one chunk, including what was rejected and why."""

    chunk_id: str
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list)