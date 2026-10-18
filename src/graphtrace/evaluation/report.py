"""Render the evaluation report (markdown) from an EvalRun. Reports only what was measured."""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Callable, Iterable

from graphtrace.evaluation.runner import EvalRecord, EvalRun

METHOD_LABELS = {
    "baseline_k5": "Baseline RAG (k=5)",
    "baseline_k8": "Baseline RAG (k=8)",
    "graphrag": "GraphRAG (up to 8 chunks)",
}
TYPE_ORDER = ["direct_fact", "relationship", "multi_hop", "cross_document",
              "insufficient_evidence", "misleading"]

ROWS = [
    ("Evidence chunks given to the generator (mean)", "context_chunks", "num1"),
    ("Recall of gold evidence (answerable questions)", "recall", "num2"),
    ("Required-term mention rate (deterministic)", "mention_recall", "num2"),
    ("Claims with a valid citation", "claim_citation_rate", "pct"),
    ("Invented chunk/path IDs (count)", "invalid_ids", "int"),
    ("Abstention accuracy", "abstention_accuracy", "pct"),
    ("Judge: correctness (1 / 0.5 / 0, mean)", "judge_correctness", "num2"),
    ("Judge: claims unsupported or contradicted", "unsupported_claim_rate", "pct"),
    ("Judge: questions with a forbidden claim", "forbidden_violation_rate", "pct"),
    ("Retrieval latency, median (ms)", "retrieval_ms_median", "ms"),
    ("Generation latency, median (ms)", "generation_ms_median", "ms"),
    ("End-to-end latency, median (ms)", "total_ms_median", "ms"),
]

DEFINITIONS = """\
**Deterministic metrics (no LLM involved)**

- **Recall of gold evidence.** Each answerable question has hand-labeled evidence *groups*; a group is met if at least one of its alternative chunks was among the chunks given to the generator. Recall is the fraction of groups met. Limitations: labels are a human's minimal sets, so an equivalent chunk that was not listed counts as a miss; it measures retrieval, not answer quality; the number of chunks differs by method, which is why baseline k=8 is included.
- **Required-term mention rate.** Fraction of required terms (any listed alternative) found, case-insensitively, in the answer summary or claims. Limitations: lexical only; it cannot detect negation or a term used in the wrong context, and it rewards listing.
- **Claims with a valid citation.** Fraction of claims that cite at least one chunk that was actually supplied. Invented chunk or path IDs are counted separately. Limitation: a valid ID does not prove the chunk supports the claim.
- **Abstention accuracy.** The model said the evidence was insufficient exactly when the question is unanswerable.
- **Latency.** Retrieval is wall-clock time. Generation is the duration of the successful API request, excluding client-side rate-limit sleeps and retry waits; cached runs replay the originally measured value. End-to-end is their sum. Limitations: one machine, one run, network variance.

**LLM-judge metrics (a different model from the answerer when configured)**

- **Correctness**, **unsupported or contradicted claims**, and **forbidden claims** are opinions of a language model comparing answers with the human reference answer and the supplied evidence. They are not ground truth. The judge can be lenient or harsh, was not human-verified, and a model grading text from a related model family may be biased.

**Statistics.** The question set is small (20), so there are no significance tests; a difference of one question is within noise. Questions flagged `dev` were used while developing the system and are reported separately from held-out ones.
"""


def _values(items: Iterable[float | None]) -> list[float]:
    return [v for v in items if v is not None]


def _mean(items: Iterable[float | None]) -> float | None:
    vals = _values(items)
    return sum(vals) / len(vals) if vals else None


def _median(items: Iterable[float | None]) -> float | None:
    vals = _values(items)
    return statistics.median(vals) if vals else None


def summarize(records: list[EvalRecord]) -> dict[str, float | int | None]:
    judged = [r for r in records if r.judge is not None and not r.judge.error]
    total_claims = sum(r.metrics.n_claims for r in records)
    cited = sum(r.metrics.n_claims_cited for r in records)
    judged_claims = sum(r.judge.n_claims_judged for r in judged)
    bad_claims = sum(r.judge.n_unsupported + r.judge.n_contradicted for r in judged)
    with_forbidden = [r for r in judged if r.n_forbidden_claims > 0]
    return {
        "questions": len(records),
        "errors": sum(1 for r in records if r.error),
        "context_chunks": _mean(r.metrics.context_chunks for r in records),
        "recall": _mean(r.metrics.recall for r in records),
        "mention_recall": _mean(r.metrics.mention_recall for r in records),
        "claim_citation_rate": cited / total_claims if total_claims else None,
        "invalid_ids": sum(r.metrics.n_invalid_ids for r in records),
        "abstention_accuracy": _mean(1.0 if r.metrics.abstention_correct else 0.0 for r in records),
        "judge_correctness": _mean(r.judge.correctness_score for r in judged),
        "unsupported_claim_rate": bad_claims / judged_claims if judged_claims else None,
        "forbidden_violation_rate": (
            sum(1 for r in with_forbidden if r.judge.forbidden_violated) / len(with_forbidden)
            if with_forbidden else None
        ),
        "retrieval_ms_median": _median(r.metrics.retrieval_ms for r in records),
        "generation_ms_median": _median(r.metrics.generation_ms for r in records),
        "total_ms_median": _median(r.metrics.total_ms for r in records),
    }


def _fmt(value: float | int | None, kind: str) -> str:
    if value is None:
        return "n/a"
    if kind == "pct":
        return f"{100 * value:.0f}%"
    if kind == "ms":
        return f"{value:,.0f}"
    if kind == "int":
        return str(int(value))
    if kind == "num1":
        return f"{value:.1f}"
    return f"{value:.2f}"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c).replace("|", "/") for c in row) + " |" for row in rows]
    return "\n".join(out)


def _label(method: str) -> str:
    return METHOD_LABELS.get(method, method)


def _results_table(by_method: dict[str, list[EvalRecord]], methods: list[str]) -> str:
    summaries = {m: summarize(by_method[m]) for m in methods}
    rows = [["Questions (generation errors)"]
            + [f"{summaries[m]['questions']} ({summaries[m]['errors']})" for m in methods]]
    for label, key, kind in ROWS:
        rows.append([label] + [_fmt(summaries[m][key], kind) for m in methods])
    return _table(["Metric"] + [_label(m) for m in methods], rows)


def _type_table(by_method: dict[str, list[EvalRecord]], methods: list[str]) -> str:
    types = [t for t in TYPE_ORDER if any(r.type == t for rs in by_method.values() for r in rs)]
    rows = []
    for t in types:
        n = len({r.question_id for r in by_method[methods[0]] if r.type == t})
        row = [t, str(n)]
        for m in methods:
            s = summarize([r for r in by_method[m] if r.type == t])
            row.append(f"{_fmt(s['recall'], 'num2')} / {_fmt(s['judge_correctness'], 'num2')}")
        rows.append(row)
    return _table(["Question type", "n"] + [_label(m) for m in methods], rows)


def _score(r: EvalRecord) -> float | None:
    return r.judge.correctness_score if r.judge and not r.judge.error else None


def _letter(r: EvalRecord) -> str:
    if r.error:
        return "ERR"
    if r.judge is None or r.judge.error:
        return "-"
    return {"CORRECT": "C", "PARTIALLY_CORRECT": "P", "INCORRECT": "I"}.get(r.judge.correctness, "?")


def _paired(by_q: dict[str, dict[str, EvalRecord]], a: str, b: str,
            getter: Callable[[EvalRecord], float | None]) -> tuple[int, int, int]:
    better = same = worse = 0
    for recs in by_q.values():
        if a in recs and b in recs:
            x, y = getter(recs[a]), getter(recs[b])
            if x is None or y is None:
                continue
            if x > y + 1e-9:
                better += 1
            elif x < y - 1e-9:
                worse += 1
            else:
                same += 1
    return better, same, worse


def _compare_lines(by_q, order, target, ref) -> tuple[list[str], list[str]]:
    worse_lines, better_lines = [], []
    for qid in order:
        recs = by_q[qid]
        if target not in recs or ref not in recs:
            continue
        t, b = recs[target], recs[ref]
        worse, better = [], []
        ts, bs = _score(t), _score(b)
        if ts is not None and bs is not None:
            if ts < bs - 1e-9:
                worse.append(f"judge correctness {ts:.1f} vs {bs:.1f}")
            elif ts > bs + 1e-9:
                better.append(f"judge correctness {ts:.1f} vs {bs:.1f}")
        tr, br = t.metrics.recall, b.metrics.recall
        if tr is not None and br is not None:
            if tr < br - 1e-9:
                worse.append(f"recall {tr:.2f} vs {br:.2f}")
            elif tr > br + 1e-9:
                better.append(f"recall {tr:.2f} vs {br:.2f}")
        t_forb = bool(t.judge and t.judge.forbidden_violated)
        b_forb = bool(b.judge and b.judge.forbidden_violated)
        if t_forb and not b_forb:
            worse.append("made a forbidden claim that the reference system did not")
        if worse:
            note = t.judge.correctness_reason if t.judge and t.judge.correctness_reason else ""
            missing = f"; missing terms: {t.metrics.missing_mentions}" if t.metrics.missing_mentions else ""
            worse_lines.append(
                f"- **{qid}** ({t.type}{', dev' if t.dev else ''}): {'; '.join(worse)}{missing}. "
                f"Judge's note on {_label(target)}: {note}"
            )
        if better:
            better_lines.append(f"- **{qid}** ({t.type}{', dev' if t.dev else ''}): {'; '.join(better)}")
    return worse_lines, better_lines


def render_report(run: EvalRun) -> str:
    methods = list(dict.fromkeys(r.method for r in run.records))
    by_method = {m: [r for r in run.records if r.method == m] for m in methods}
    order = list(dict.fromkeys(r.question_id for r in run.records))
    by_q: dict[str, dict[str, EvalRecord]] = defaultdict(dict)
    for r in run.records:
        by_q[r.question_id][r.method] = r

    judge_text = run.judge_model or "none (judge disabled)"
    if run.judge_model and run.judge_model == run.answer_model:
        judge_text += " (same model as the answerer: self-preference bias is possible)"
    parts = [
        "# GraphTrace evaluation report",
        "",
        "_Generated from `reports/eval_results.json`. Every number below was measured in this run._",
        "",
        "## Run configuration",
        "",
        _table(["Item", "Value"], [
            ["Run started (UTC)", run.started_at],
            ["Answer model", run.answer_model],
            ["Judge model", judge_text],
            ["Answer prompt / judge prompt", f"{run.answer_prompt_version} / {run.judge_prompt_version}"],
            ["Embedding model", run.embedding_model],
            ["Questions", str(len(order))],
            ["Methods", ", ".join(_label(m) for m in methods)],
            ["LLM calls this run (API / cache)", f"{run.api_calls} / {run.cache_hits}"],
        ]),
        "",
        "## Metric definitions and limitations",
        "",
        DEFINITIONS,
        "## Results: all questions",
        "",
        _results_table(by_method, methods),
        "",
    ]

    held = {m: [r for r in rs if not r.dev] for m, rs in by_method.items()}
    n_held = len({r.question_id for rs in held.values() for r in rs})
    if n_held and n_held < len(order):
        parts += [f"## Results: held-out questions only ({n_held}; questions used during development excluded)",
                  "", _results_table(held, methods), ""]

    parts += ["## Results by question type (cell = recall / judge correctness)", "",
              _type_table(by_method, methods), ""]

    if "graphrag" in methods:
        rows = []
        for ref in [m for m in methods if m != "graphrag"]:
            c = _paired(by_q, "graphrag", ref, _score)
            r = _paired(by_q, "graphrag", ref, lambda rec: rec.metrics.recall)
            rows.append([f"GraphRAG vs {_label(ref)}",
                         f"{c[0]} better / {c[1]} same / {c[2]} worse",
                         f"{r[0]} better / {r[1]} same / {r[2]} worse"])
        parts += ["## Paired comparison (number of questions)", "",
                  _table(["Comparison", "Judge correctness", "Recall"], rows), ""]

    cells = []
    for qid in order:
        recs = by_q[qid]
        first = next(iter(recs.values()))
        row = [qid, first.type, "dev" if first.dev else ""]
        for m in methods:
            r = recs.get(m)
            if r is None:
                row.append("")
                continue
            rec = f" (R {r.metrics.recall:.2f})" if r.metrics.recall is not None else ""
            row.append(f"{_letter(r)}{rec}")
        cells.append(row)
    parts += ["## Per question (C = correct, P = partially, I = incorrect, R = recall)", "",
              _table(["Question", "Type", "Flag"] + [_label(m) for m in methods], cells), ""]

    if "graphrag" in methods and "baseline_k8" in methods:
        worse, better = _compare_lines(by_q, order, "graphrag", "baseline_k8")
        parts += ["## Questions where GraphRAG did worse than baseline k=8", ""]
        parts += worse or ["_None on correctness, recall, or forbidden claims._"]
        parts += ["", "## Questions where GraphRAG did better than baseline k=8", ""]
        parts += better or ["_None._"]
        parts.append("")
    return "\n".join(parts)