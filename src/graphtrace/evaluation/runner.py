"""Run all pipelines over the labeled questions and collect per-question records."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel, Field

from graphtrace.evaluation.dataset import EvalQuestion
from graphtrace.evaluation.judge import JUDGE_PROMPT_VERSION, Judge, JudgeResult
from graphtrace.evaluation.metrics import DeterministicMetrics, compute_metrics
from graphtrace.generation.answerer import Answerer
from graphtrace.generation.prompts import ANSWER_PROMPT_VERSION
from graphtrace.models import GroundedAnswer
from graphtrace.pipeline import GraphTrace


@dataclass(frozen=True)
class MethodSpec:
    label: str
    method: str  # "baseline" | "graphrag"
    k: int | None = None


DEFAULT_SPECS = (
    MethodSpec("baseline_k5", "baseline", 5),
    MethodSpec("baseline_k8", "baseline", 8),  # same context budget as GraphRAG
    MethodSpec("graphrag", "graphrag"),
)


class EvalRecord(BaseModel):
    question_id: str
    question: str
    type: str
    dev: bool
    answerable: bool
    n_forbidden_claims: int
    method: str
    retrieved_chunk_ids: list[str]
    n_graph_paths: int
    answer: GroundedAnswer | None
    error: str | None
    metrics: DeterministicMetrics
    judge: JudgeResult | None


class EvalRun(BaseModel):
    started_at: str
    answer_model: str
    judge_model: str | None
    answer_prompt_version: str
    judge_prompt_version: str
    embedding_model: str
    records: list[EvalRecord] = Field(default_factory=list)
    api_calls: int = 0
    cache_hits: int = 0


ProgressFn = Callable[[int, int, EvalQuestion, MethodSpec, EvalRecord], None]


def run_evaluation(
    system: GraphTrace,
    answerer: Answerer,
    judge: Judge | None,
    questions: list[EvalQuestion],
    *,
    answer_model: str,
    judge_model: str | None,
    specs: tuple[MethodSpec, ...] = DEFAULT_SPECS,
    progress: ProgressFn | None = None,
) -> EvalRun:
    run = EvalRun(
        started_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        answer_model=answer_model,
        judge_model=judge_model if judge else None,
        answer_prompt_version=ANSWER_PROMPT_VERSION,
        judge_prompt_version=JUDGE_PROMPT_VERSION,
        embedding_model=system.index.model_name,
    )
    total = len(questions) * len(specs)
    for question in questions:
        for spec in specs:
            retrieval = system.retrieve(question.question, spec.method, spec.k)
            result = answerer.answer(retrieval)
            judgement = judge.judge(question, result) if judge else None
            record = EvalRecord(
                question_id=question.id,
                question=question.question,
                type=question.type,
                dev=question.dev,
                answerable=question.answerable,
                n_forbidden_claims=len(question.forbidden_claims),
                method=spec.label,
                retrieved_chunk_ids=[rc.chunk.chunk_id for rc in retrieval.chunks],
                n_graph_paths=len(retrieval.graph_paths),
                answer=result.answer,
                error=result.error,
                metrics=compute_metrics(question, result),
                judge=judgement,
            )
            run.records.append(record)
            if progress:
                progress(len(run.records), total, question, spec, record)
    return run