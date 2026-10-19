"""Print a readable audit view of evaluation records for chosen questions."""

import argparse

from graphtrace.config import EVAL_QUESTIONS_PATH, REPORTS_DIR
from graphtrace.evaluation.dataset import load_questions
from graphtrace.evaluation.runner import EvalRun


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question_ids", nargs="+")
    args = parser.parse_args()

    run = EvalRun.model_validate_json((REPORTS_DIR / "eval_results.json").read_text(encoding="utf-8"))
    questions = {q.id: q for q in load_questions(EVAL_QUESTIONS_PATH)}

    for qid in args.question_ids:
        q = questions.get(qid)
        if q is None:
            print(f"Unknown question id {qid}")
            continue
        gold = {c for group in q.evidence for c in group}
        print("=" * 90)
        print(f"{q.id} [{q.type}{', dev' if q.dev else ''}] {q.question}")
        print(f"REFERENCE: {q.reference_answer}")
        print(f"GOLD EVIDENCE GROUPS: {q.evidence}")
        if q.forbidden_claims:
            print(f"FORBIDDEN: {q.forbidden_claims}")
        for record in (r for r in run.records if r.question_id == qid):
            m = record.metrics
            print("-" * 90)
            print(f"{record.method}  recall={m.recall}  mention_recall={m.mention_recall}  "
                  f"missing={m.missing_mentions}  claims={m.n_claims} (inference {m.n_inference})  "
                  f"invalid_ids={m.n_invalid_ids}  abstained={m.abstained}")
            marked = [f"{c}{'*' if c in gold else ''}" for c in record.retrieved_chunk_ids]
            print(f"retrieved (* = gold): {', '.join(marked)}")
            if record.error:
                print(f"ERROR: {record.error}")
            if record.answer:
                print(f"ANSWER: {record.answer.answer}")
                for claim in record.answer.claims:
                    paths = f" paths={claim.path_ids}" if claim.path_ids else ""
                    print(f"   [{claim.support.value}] {claim.text}  cites={claim.citations}{paths}")
            j = record.judge
            if j is None:
                print("JUDGE: (none)")
            elif j.error:
                print(f"JUDGE ERROR: {j.error}")
            else:
                print(f"JUDGE: {j.correctness} | supported={j.n_supported} unsupported={j.n_unsupported} "
                      f"contradicted={j.n_contradicted} unjudged={j.n_unjudged}")
                print(f"   reason: {j.correctness_reason}")
                if j.forbidden_violated:
                    print(f"   FORBIDDEN VIOLATED: {j.forbidden_violated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())