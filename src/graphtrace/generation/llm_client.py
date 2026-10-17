"""Thin Gemini wrapper: request throttling, retry with backoff, typed errors."""

from __future__ import annotations

import logging
import random
import time

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

logger = logging.getLogger(__name__)

RETRYABLE_CODES = {429, 500, 502, 503, 504}


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
            try:
                response = self._client.models.generate_content(
                    model=self.model, contents=prompt, config=config
                )
            except errors.APIError as exc:
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
            return response.text
        raise AssertionError("unreachable")  # the loop always returns or raises