"""Evaluation question schema and loader."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class EvalQuestion(BaseModel):
    id: str
    type: str
    question: str
    reference_answer: str
    evidence: list[list[str]] = Field(default_factory=list)  # groups of alternative chunk IDs
    answerable: bool
    must_mention: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    dev: bool = False
    notes: str = ""


def load_questions(path: Path) -> list[EvalQuestion]:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Copy questions.json into data/eval/.")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    questions = [EvalQuestion.model_validate(q) for q in data["questions"]]
    ids = [q.id for q in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate question ids")
    return questions