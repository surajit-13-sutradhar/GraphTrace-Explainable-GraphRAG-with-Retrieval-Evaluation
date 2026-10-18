"""Disk cache around any JSON generator: identical LLM inputs are never paid for twice.

The original API latency is stored and replayed, so cached runs still report honest latency.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel


def _is_json(text: str) -> bool:
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return False
    return True


class CachedJsonGenerator:
    def __init__(self, inner, cache_dir: Path) -> None:
        self._inner = inner
        self._cache_dir = cache_dir
        self.model: str = inner.model
        self.last_latency_ms: float | None = None
        self.api_calls = 0
        self.cache_hits = 0

    def _path(self, system_instruction: str, prompt: str, schema: type[BaseModel]) -> Path:
        material = json.dumps(
            {
                "model": self.model,
                "system": system_instruction,
                "prompt": prompt,
                "schema": schema.model_json_schema(),
            },
            sort_keys=True,
        )
        return self._cache_dir / f"{hashlib.sha256(material.encode('utf-8')).hexdigest()}.json"

    def generate_json(
        self, *, system_instruction: str, prompt: str, schema: type[BaseModel]
    ) -> str:
        path = self._path(system_instruction, prompt, schema)
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                raw = payload["raw_response"]
                if isinstance(raw, str):
                    self.last_latency_ms = payload.get("latency_ms")
                    self.cache_hits += 1
                    return raw
            except (OSError, json.JSONDecodeError, KeyError):
                pass  # unreadable cache entry is a miss

        raw = self._inner.generate_json(
            system_instruction=system_instruction, prompt=prompt, schema=schema
        )
        self.last_latency_ms = getattr(self._inner, "last_latency_ms", None)
        self.api_calls += 1
        if _is_json(raw):  # never cache garbage, so a re-run retries it
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {"model": self.model, "latency_ms": self.last_latency_ms, "raw_response": raw},
                    indent=2,
                ),
                encoding="utf-8",
            )
        return raw