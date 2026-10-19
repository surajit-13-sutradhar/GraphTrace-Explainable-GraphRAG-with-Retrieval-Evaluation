"""Validate data/eval/questions.json against the real chunk IDs."""

import json
from collections import Counter

from graphtrace.config import DOCS_DIR, PROJECT_ROOT
from graphtrace.ingestion.chunker import chunk_documents
from graphtrace.ingestion.loader import load_documents

QUESTIONS_PATH = PROJECT_ROOT / "data" / "eval" / "questions.json"
TYPES = {"direct_fact", "relationship", "multi_hop", "cross_document", "insufficient_evidence", "misleading"}
REQUIRED = {"id", "type", "question", "reference_answer", "evidence", "answerable",
            "must_mention", "forbidden_claims", "dev", "notes"}


def main() -> int:
    chunk_ids = {c.chunk_id for c in chunk_documents(load_documents(DOCS_DIR))}
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8-sig"))["questions"]
    problems: list[str] = []
    seen: set[str] = set()
    for q in questions:
        qid = q.get("id", "?")
        if qid in seen:
            problems.append(f"{qid}: duplicate id")
        seen.add(qid)
        if REQUIRED - q.keys():
            problems.append(f"{qid}: missing fields {sorted(REQUIRED - q.keys())}")
            continue
        if q["type"] not in TYPES:
            problems.append(f"{qid}: unknown type {q['type']!r}")
        for group in q["evidence"]:
            if not group:
                problems.append(f"{qid}: empty evidence group")
            for cid in group:
                if cid not in chunk_ids:
                    problems.append(f"{qid}: unknown chunk id {cid!r}")
        if q["answerable"] and not q["evidence"]:
            problems.append(f"{qid}: answerable but no evidence groups")
        if not q["answerable"] and q["evidence"]:
            problems.append(f"{qid}: unanswerable but has evidence groups")

    print(f"{len(questions)} questions; by type: {dict(Counter(q['type'] for q in questions))}")
    print(f"dev questions: {[q['id'] for q in questions if q.get('dev')]}")
    for p in problems:
        print(f"PROBLEM: {p}")
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())