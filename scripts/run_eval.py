"""Run the evaluation: baseline (k=5, k=8) vs GraphRAG on the labeled questions."""

from __future__ import annotations

import argparse
import json

from graphtrace.config import (
    EVAL_QUESTIONS_PATH,
    HUMAN_GRADES_PATH,
    LLM_CACHE_DIR,
    REPORTS_DIR,
    load_settings,
)
from graphtrace.evaluation.dataset import load_questions
from graphtrace.evaluation.judge import Judge
from graphtrace.evaluation.report import METHOD_LABELS, render_report, summarize
from graphtrace.evaluation.runner import DEFAULT_SPECS, EvalRun, run_evaluation
from graphtrace.generation.answerer import Answerer
from graphtrace.generation.cached_client import CachedJsonGenerator
from graphtrace.generation.llm_client import GeminiClient, LLMError, LLMRateLimitError
from graphtrace.pipeline import GraphTrace

RESULTS_PATH = REPORTS_DIR / "eval_results.json"
REPORT_PATH = REPORTS_DIR / "eval_report.md"


def load_human_grades() -> dict[str, dict]:
    if not HUMAN_GRADES_PATH.exists():
        return {}
    return json.loads(HUMAN_GRADES_PATH.read_text(encoding="utf-8-sig")).get("grades", {})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="Only the first N questions (smoke test).")
    parser.add_argument("--no-judge", action="store_true", help="Skip the LLM judge.")
    parser.add_argument("--report-only", action="store_true",
                        help="Rebuild the report from reports/eval_results.json without any LLM calls.")
    args = parser.parse_args()
    REPORTS_DIR.mkdir(exist_ok=True)

    if args.report_only:
        run = EvalRun.model_validate_json(RESULTS_PATH.read_text(encoding="utf-8"))
        REPORT_PATH.write_text(render_report(run, load_human_grades()), encoding="utf-8")
        print(f"Wrote {REPORT_PATH}")
        return 0

    settings = load_settings()
    api_key = settings.require_api_key()
    questions = load_questions(EVAL_QUESTIONS_PATH)
    if args.limit:
        questions = questions[: args.limit]

    system = GraphTrace.load(settings, with_llm=False)
    answer_client = CachedJsonGenerator(
        GeminiClient(api_key, settings.gemini_model, rpm=settings.gemini_rpm), LLM_CACHE_DIR
    )
    judge_client = None
    if not args.no_judge:
        judge_client = CachedJsonGenerator(
            GeminiClient(api_key, settings.effective_judge_model, rpm=settings.judge_rpm), LLM_CACHE_DIR
        )
    judge = Judge(judge_client) if judge_client else None

    print(f"Answer model: {settings.gemini_model} | judge model: "
          f"{settings.effective_judge_model if judge else 'none'} | questions: {len(questions)}")
    if judge and settings.effective_judge_model == settings.gemini_model:
        print("WARNING: judge and answerer are the same model; set GEMINI_JUDGE_MODEL for a separate judge.")

    def progress(done, total, question, spec, record) -> None:
        verdict = record.judge.correctness if record.judge and not record.judge.error else "-"
        recall = "n/a" if record.metrics.recall is None else f"{record.metrics.recall:.2f}"
        print(f"[{done}/{total}] {question.id} {spec.label:<12} recall={recall} judge={verdict}"
              f"{'  ERROR: ' + record.error if record.error else ''}")

    try:
        run = run_evaluation(
            system, Answerer(answer_client), judge, questions,
            answer_model=settings.gemini_model, judge_model=settings.effective_judge_model,
            progress=progress,
        )
    except LLMRateLimitError as exc:
        print(f"\nStopped: {exc}\nCompleted calls are cached; re-run later to resume.")
        return 2
    except LLMError as exc:
        print(f"\nStopped: {exc}")
        return 1

    run.api_calls = answer_client.api_calls + (judge_client.api_calls if judge_client else 0)
    run.cache_hits = answer_client.cache_hits + (judge_client.cache_hits if judge_client else 0)
    RESULTS_PATH.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    REPORT_PATH.write_text(render_report(run, load_human_grades()), encoding="utf-8")

    print(f"\nLLM calls: {run.api_calls} API, {run.cache_hits} from cache")
    for spec in DEFAULT_SPECS:
        s = summarize([r for r in run.records if r.method == spec.label])
        print(f"  {METHOD_LABELS[spec.label]:<28} recall={s['recall']} judge_correctness={s['judge_correctness']}")
    print(f"\nWrote {RESULTS_PATH}\nWrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())