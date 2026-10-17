"""Turn a raw LLM JSON response into validated, provenance-tagged extraction results."""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from graphtrace.models import (
    Chunk,
    ChunkExtraction,
    ExtractedEntity,
    ExtractedRelationship,
)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _summarize(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        parts.append(f"{loc}: {err['msg']}" if loc else err["msg"])
    return "; ".join(parts)


def _get_list(data: dict, key: str, rejected: list[str]) -> list:
    value = data.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        rejected.append(f"'{key}' is not a list")
        return []
    return value


def validate_extraction(raw_response: str, chunk: Chunk) -> ChunkExtraction:
    """Validate item by item so one bad entry never discards the rest of the chunk."""
    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        return ChunkExtraction(chunk_id=chunk.chunk_id, rejected=[f"invalid JSON: {exc}"])
    if not isinstance(data, dict):
        return ChunkExtraction(
            chunk_id=chunk.chunk_id, rejected=["response is not a JSON object"]
        )

    rejected: list[str] = []

    entities: list[ExtractedEntity] = []
    for i, item in enumerate(_get_list(data, "entities", rejected)):
        try:
            entities.append(ExtractedEntity.model_validate(item))
        except ValidationError as exc:
            rejected.append(f"entity[{i}]: {_summarize(exc)}")

    chunk_text = _normalize_text(chunk.text)
    relationships: list[ExtractedRelationship] = []
    for i, item in enumerate(_get_list(data, "relationships", rejected)):
        if not isinstance(item, dict):
            rejected.append(f"relationship[{i}]: not an object")
            continue
        try:
            # chunk_id is always overwritten with ours; the LLM's value is never trusted.
            rel = ExtractedRelationship.model_validate(
                {**item, "chunk_id": chunk.chunk_id, "quote_verified": False}
            )
        except ValidationError as exc:
            rejected.append(f"relationship[{i}]: {_summarize(exc)}")
            continue
        verified = _normalize_text(rel.evidence_quote) in chunk_text
        relationships.append(rel.model_copy(update={"quote_verified": verified}))

    return ChunkExtraction(
        chunk_id=chunk.chunk_id,
        entities=entities,
        relationships=relationships,
        rejected=rejected,
    )