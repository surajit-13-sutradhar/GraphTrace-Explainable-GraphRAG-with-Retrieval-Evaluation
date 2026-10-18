"""Thin Gemini wrapper: request throttling, retry with backoff, typed errors."""

from __future__ import annotations

import logging
import random
import re
import time

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

logger = logging.getLogger(__name__)

RETRYABLE_CODES = {429, 500, 502, 503, 504}
MAX_AUTO_WAIT_SECONDS = 90.0

_RETRY_IN = re.compile(r"retry in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", re.IGNORECASE)


def parse_retry_delay(message: str | None) -> float | None:
    """Parse a server hint like 'Please retry in 3h46m7.8s' into seconds; None if absent."""
    if not message:
        return None
    match = _RETRY_IN.search(message)
    if not match or not any(match.groups()):
        return None
    hours, minutes, seconds = match.groups()
    return int(hours or 0) * 3600 + int(minutes or 0) * 60 + float(seconds or 0)


class LLMError(RuntimeError):
    """Any failure talking to the LLM."""


class LLMRateLimitError(LLMError):
    """Rate or quota limit still hit after all retries."""


class LLMEmptyResponseError(LLMError):
    """The API returned no text (for example, blocked by a safety filter)."""


class GeminiClient:
    def __init__(self, api_key: str, model: str, rpm: int = 10, max_retries: int = 5) -> None:
        if rpm < 1:
            raise ValueError("rpm must be at least 1")
        self._client = genai.Client(api_key=api_key)
        self.model = model
        self._min_interval = 60.0 / rpm
        self._max_retries = max_retries
        self._last_call_started: float | None = None
        # Duration of the last SUCCESSFUL request only: excludes our own throttle sleeps and retry waits.
        self.last_latency_ms: float | None = None

    def _throttle(self) -> None:
        """Sleep just long enough to stay under the configured requests-per-minute."""
        if self._last_call_started is not None:
            wait = self._min_interval - (time.monotonic() - self._last_call_started)
            if wait > 0:
                time.sleep(wait)
        self._last_call_started = time.monotonic()

    def generate_json(
        self, *, system_instruction: str, prompt: str, schema: type[BaseModel]
    ) -> str:
        """Return the model's JSON text, constrained to `schema`. Retries transient errors."""
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.0,
        )
        for attempt in range(self._max_retries + 1):
            self._throttle()
            started = time.perf_counter()
            try:
                response = self._client.models.generate_content(
                    model=self.model, contents=prompt, config=config
                )
            except errors.APIError as exc:
                hint = parse_retry_delay(exc.message) if exc.code == 429 else None
                if hint is not None and hint > MAX_AUTO_WAIT_SECONDS:
                    raise LLMRateLimitError(
                        f"Quota exhausted; server says retry in ~{hint / 60:.0f} min. {exc.message}"
                    ) from exc
                if exc.code in RETRYABLE_CODES and attempt < self._max_retries:
                    delay = min(60.0, 2.0 * 2**attempt) + random.uniform(0, 1)
                    logger.warning(
                        "API error %s, retry %d/%d in %.0fs",
                        exc.code, attempt + 1, self._max_retries, delay,
                    )
                    time.sleep(delay)
                    continue
                if exc.code == 429:
                    raise LLMRateLimitError(
                        f"Rate/quota limit hit (HTTP 429): {exc.message}"
                    ) from exc
                raise LLMError(f"Gemini API error {exc.code}: {exc.message}") from exc
            if not response.text:
                raise LLMEmptyResponseError("Gemini returned no text")
            self.last_latency_ms = (time.perf_counter() - started) * 1000
            return response.text
        raise AssertionError("unreachable")  # the loop always returns or raises