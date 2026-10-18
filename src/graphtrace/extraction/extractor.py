"""Extract entities and relationships from one chunk, with on-disk caching of raw responses."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from graphtrace.extraction.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_extraction_prompt,
)
from graphtrace.extraction.validation import validate_extraction
from graphtrace.generation.llm_client import LLMEmptyResponseError
from graphtrace.models import Chunk, ChunkExtraction, LLMExtraction


class JsonGenerator(Protocol):
    """Anything that can produce schema-constrained JSON. Lets tests use a fake."""

    model: str

    def generate_json(
        self, *, system_instruction: str, prompt: str, schema: type[BaseModel]
    ) -> str: ...


def _cache_path(cache_dir: Path, chunk: Chunk) -> Path:
    return cache_dir / f"{chunk.chunk_id.replace('#', '__')}.json"


def _cache_key(model: str, chunk: Chunk) -> str:
    material = f"{PROMPT_VERSION}\n{model}\n{chunk.doc_title}\n{chunk.section}\n{chunk.text}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _read_cache(path: Path, key: str) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None  # missing or corrupted cache is simply a miss
    if not isinstance(payload, dict) or payload.get("cache_key") != key:
        return None
    raw = payload.get("raw_response")
    return raw if isinstance(raw, str) else None


def _is_json(text: str) -> bool:
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return False
    return True


def extract_chunk(
    chunk: Chunk, client: JsonGenerator, cache_dir: Path
) -> tuple[ChunkExtraction, bool]:
    """Return (validated extraction, served_from_cache).

    Rate-limit and other API errors propagate to the caller; an empty response
    becomes a rejected extraction so one blocked chunk doesn't stop the whole run.
    """
    path = _cache_path(cache_dir, chunk)
    key = _cache_key(client.model, chunk)

    cached = _read_cache(path, key)
    if cached is not None:
        return validate_extraction(cached, chunk), True

    try:
        raw = client.generate_json(
            system_instruction=EXTRACTION_SYSTEM_PROMPT,
            prompt=build_extraction_prompt(chunk),
            schema=LLMExtraction,
        )
    except LLMEmptyResponseError as exc:
        return ChunkExtraction(chunk_id=chunk.chunk_id, rejected=[f"empty response: {exc}"]), False

    if _is_json(raw):  # never cache garbage, so a re-run retries it
        cache_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "cache_key": key,
            "model": client.model,
            "prompt_version": PROMPT_VERSION,
            "raw_response": raw,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return validate_extraction(raw, chunk), False

def load_cached_extraction(chunk: Chunk, model: str, cache_dir: Path) -> ChunkExtraction | None:
    """Read-only cache lookup; returns None on a miss. Never calls the API."""
    cached = _read_cache(_cache_path(cache_dir, chunk), _cache_key(model, chunk))
    return validate_extraction(cached, chunk) if cached is not None else None