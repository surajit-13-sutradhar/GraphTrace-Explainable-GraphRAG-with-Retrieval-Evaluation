"""Central place for environment-driven settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# src/graphtrace/config.py -> parents[2] is the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "data" / "docs"
ARTIFACTS_DIR = PROJECT_ROOT / "data" / "artifacts"
EXTRACTION_CACHE_DIR = ARTIFACTS_DIR / "extraction_cache"

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_RPM = 10


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    gemini_model: str
    gemini_rpm: int = DEFAULT_RPM

    def require_api_key(self) -> str:
        """Return the API key or fail with an actionable message."""
        if not self.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        return self.gemini_api_key


def load_settings() -> Settings:
    """Load settings from .env (if present) and the process environment."""
    load_dotenv(PROJECT_ROOT / ".env")
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        gemini_model=os.getenv("GEMINI_MODEL", DEFAULT_MODEL),
        gemini_rpm=int(os.getenv("GEMINI_RPM", DEFAULT_RPM)),
    )