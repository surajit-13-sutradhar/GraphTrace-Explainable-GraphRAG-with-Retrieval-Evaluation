"""Ask a question with baseline RAG, GraphRAG, or both."""

from __future__ import annotations

import argparse

from graphtrace.generation.llm_client import LLMRateLimitError
from graphtrace.models import PipelineResult
from graphtrace.pipeline import GraphTrace


def show(result: PipelineResult) -> None:
    r = result.retrieval
    print(f"\n{'=' * 80}")
    print(f"{result.method.upper()}   retrieval={r.retrieval_ms:.0f} ms   "
          f"generation={result.generation_ms:.0f} ms   total={result.total_ms:.0f} ms")
    print("=" * 80)
    for note in r.notes:
        print(f"note: {note}")
    if result.error:
        print(f"ERROR: {result.error}")
    elif result.answer:
        a = result.answer
        print(a.answer)
        print(f"\nSufficient evidence: {a.sufficient_evidence}")
        if a.missing_information:
            print(f"Missing: {a.missing_information}")
        print("\nClaims:")
        for claim in a.claims:
            print(f"  [{claim.support.value}] {claim.text}")
            extra = f"   paths: {', '.join(claim.path_ids)}" if claim.path_ids else ""
            print(f"      cites: {', '.join(claim.citations) or '(NONE)'}{extra}")
            if claim.invalid_citations or claim.invalid_path_ids:
                print(f"      INVALID: {claim.invalid_citations + claim.invalid_path_ids}")

    print("\nEvidence chunks:")
    for rc in r.chunks:
        print(f"  {rc.score:.3f} {rc.origin:<6} {rc.chunk.chunk_id:<40} [{rc.chunk.section}]")
    if r.seed_entities:
        print(f"\nSeed entities: {', '.join(r.seed_entities)}")
    if r.graph_paths:
        print("\nGraph paths:")
        for p in r.graph_paths:
            print(f"  {p.path_id} ({p.kind}) {p.description}")
            for s in p.steps:
                print(f"       {s.source} --{s.relation}--> {s.target}   {s.chunk_ids}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--method", choices=["baseline", "graphrag", "both"], default="both")
    parser.add_argument("--k", type=int, help="Top-k for the baseline (default 5).")
    args = parser.parse_args()

    system = GraphTrace.load()
    methods = ["baseline", "graphrag"] if args.method == "both" else [args.method]
    for method in methods:
        try:
            show(system.ask(args.question, method, k=args.k))
        except LLMRateLimitError as exc:
            print(f"\nStopped: {exc}")
            return 2
        except ValueError as exc:
            print(f"Invalid input: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())