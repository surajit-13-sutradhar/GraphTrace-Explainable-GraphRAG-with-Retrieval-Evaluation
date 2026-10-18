"""Turn retrieved evidence into a grounded answer, then check its citations deterministically."""

from __future__ import annotations

import time
from typing import Protocol

from pydantic import BaseModel, ValidationError

from graphtrace.generation.llm_client import LLMError, LLMRateLimitError
from graphtrace.generation.prompts import ANSWER_SYSTEM_PROMPT, build_answer_prompt
from graphtrace.models import (
    Claim,
    GroundedAnswer,
    LLMAnswer,
    PipelineResult,
    RetrievalResult,
)


class JsonGenerator(Protocol):
    model: str

    def generate_json(
        self, *, system_instruction: str, prompt: str, schema: type[BaseModel]
    ) -> str: ...


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(i.strip() for i in items if i and i.strip()))


def validate_answer(llm: LLMAnswer, retrieval: RetrievalResult) -> GroundedAnswer:
    """Keep only citations and path IDs that exist; record the invented ones."""
    valid_chunks = {rc.chunk.chunk_id for rc in retrieval.chunks}
    valid_paths = {p.path_id for p in retrieval.graph_paths}
    claims: list[Claim] = []
    for claim in llm.claims:
        cites = _unique(claim.citations)
        path_ids = _unique(claim.path_ids)
        claims.append(
            Claim(
                text=claim.text.strip(),
                support=claim.support,
                citations=[c for c in cites if c in valid_chunks],
                path_ids=[p for p in path_ids if p in valid_paths],
                invalid_citations=[c for c in cites if c not in valid_chunks],
                invalid_path_ids=[p for p in path_ids if p not in valid_paths],
            )
        )
    return GroundedAnswer(
        answer=llm.answer.strip(),
        claims=claims,
        sufficient_evidence=llm.sufficient_evidence,
        missing_information=llm.missing_information.strip(),
    )


class Answerer:
    def __init__(self, client: JsonGenerator) -> None:
        self._client = client

    def answer(self, retrieval: RetrievalResult) -> PipelineResult:
        """Rate-limit errors propagate (so batch runs can stop); other failures become result.error."""
        prompt = build_answer_prompt(retrieval)
        start = time.perf_counter()
        grounded: GroundedAnswer | None = None
        error: str | None = None
        try:
            raw = self._client.generate_json(
                system_instruction=ANSWER_SYSTEM_PROMPT, prompt=prompt, schema=LLMAnswer
            )
            grounded = validate_answer(LLMAnswer.model_validate_json(raw), retrieval)
        except LLMRateLimitError:
            raise
        except LLMError as exc:
            error = str(exc)
        except ValidationError as exc:
            error = f"model returned an invalid answer structure ({exc.error_count()} problems)"
        generation_ms = (time.perf_counter() - start) * 1000
        return PipelineResult(
            method=retrieval.method,
            question=retrieval.question,
            retrieval=retrieval,
            answer=grounded,
            generation_ms=generation_ms,
            total_ms=retrieval.retrieval_ms + generation_ms,
            error=error,
        )