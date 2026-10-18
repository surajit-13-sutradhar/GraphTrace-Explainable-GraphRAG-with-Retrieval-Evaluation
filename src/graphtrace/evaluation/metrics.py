"""Deterministic evaluation metrics. No LLM involved; every number is reproducible from the records."""

from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel

from graphtrace.evaluation.dataset import EvalQuestion
from graphtrace.models import GroundedAnswer, PipelineResult, SupportType


class DeterministicMetrics(BaseModel):
    context_chunks: int
    recall: float | None          # None when the question has no gold evidence (unanswerable)
    mention_recall: float | None  # None when the question has no must_mention terms
    missing_mentions: list[str]
    n_claims: int
    n_inference: int
    n_claims_cited: int           # claims with at least one valid citation
    n_invalid_ids: int            # invented chunk or path IDs
    abstained: bool               # the model said the evidence is insufficient
    abstention_correct: bool      # abstained exactly when the question is unanswerable
    retrieval_ms: float
    generation_ms: float
    total_ms: float


def recall_at_k(evidence_groups: list[list[str]], retrieved_ids: Iterable[str]) -> float | None:
    """Fraction of gold evidence groups with at least one acceptable chunk among the retrieved ones."""
    if not evidence_groups:
        return None
    got = set(retrieved_ids)
    return sum(1 for group in evidence_groups if got & set(group)) / len(evidence_groups)


def mention_rate(must_mention: list[str], text: str) -> tuple[float | None, list[str]]:
    """Fraction of required terms present (case-insensitive substring; 'a|b' means either)."""
    if not must_mention:
        return None, []
    lowered = text.casefold()
    missing = []
    for entry in must_mention:
        options = [o.strip().casefold() for o in entry.split("|") if o.strip()]
        if not any(option in lowered for option in options):
            missing.append(entry)
    return 1 - len(missing) / len(must_mention), missing


def answer_text(answer: GroundedAnswer) -> str:
    """Summary plus every claim: what a reader of the full response sees."""
    return " ".join([answer.answer, *(claim.text for claim in answer.claims)])


def compute_metrics(question: EvalQuestion, result: PipelineResult) -> DeterministicMetrics:
    chunk_ids = [rc.chunk.chunk_id for rc in result.retrieval.chunks]
    answer = result.answer
    claims = answer.claims if answer else []
    mention, missing = mention_rate(question.must_mention, answer_text(answer) if answer else "")
    abstained = answer is not None and not answer.sufficient_evidence
    return DeterministicMetrics(
        context_chunks=len(chunk_ids),
        recall=recall_at_k(question.evidence, chunk_ids),
        mention_recall=mention,
        missing_mentions=missing,
        n_claims=len(claims),
        n_inference=sum(c.support == SupportType.INFERENCE for c in claims),
        n_claims_cited=sum(c.has_valid_citation for c in claims),
        n_invalid_ids=sum(len(c.invalid_citations) + len(c.invalid_path_ids) for c in claims),
        abstained=abstained,
        abstention_correct=answer is not None and abstained == (not question.answerable),
        retrieval_ms=result.retrieval.retrieval_ms,
        generation_ms=result.generation_ms,
        total_ms=result.total_ms,
    )