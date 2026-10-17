"""Run extraction over chunks and print the results for inspection."""

from __future__ import annotations

import argparse
import logging

from graphtrace.config import DOCS_DIR, EXTRACTION_CACHE_DIR, load_settings
from graphtrace.extraction.extractor import extract_chunk
from graphtrace.generation.llm_client import GeminiClient, LLMError, LLMRateLimitError
from graphtrace.ingestion.chunker import chunk_documents
from graphtrace.ingestion.loader import load_documents
from graphtrace.models import ChunkExtraction


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunk-ids", nargs="*", help="Only these chunk IDs (quote them).")
    parser.add_argument("--limit", type=int, help="Only the first N chunks.")
    return parser.parse_args()


def print_extraction(ex: ChunkExtraction) -> None:
    names = ", ".join(f"{e.name} ({e.type.value})" for e in ex.entities) or "(none)"
    print(f"   entities ({len(ex.entities)}): {names}")
    for r in ex.relationships:
        flag = "quote ok" if r.quote_verified else "QUOTE NOT FOUND IN CHUNK"
        print(f"   {r.source} --{r.relation.value}--> {r.target}   [{flag}]")
        print(f"       \"{r.evidence_quote}\"")
    for reason in ex.rejected:
        print(f"   REJECTED: {reason}")


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    settings = load_settings()

    chunks = chunk_documents(load_documents(DOCS_DIR))
    if args.chunk_ids:
        unknown = set(args.chunk_ids) - {c.chunk_id for c in chunks}
        if unknown:
            print(f"Unknown chunk IDs: {sorted(unknown)}")
            return 1
        chunks = [c for c in chunks if c.chunk_id in set(args.chunk_ids)]
    elif args.limit:
        chunks = chunks[: args.limit]

    client = GeminiClient(settings.require_api_key(), settings.gemini_model, rpm=settings.gemini_rpm)
    print(f"Model: {settings.gemini_model} | RPM cap: {settings.gemini_rpm} | chunks: {len(chunks)}\n")

    api_calls = cache_hits = n_entities = n_rels = n_verified = n_rejected = 0
    for i, chunk in enumerate(chunks, start=1):
        try:
            extraction, from_cache = extract_chunk(chunk, client, EXTRACTION_CACHE_DIR)
        except LLMRateLimitError as exc:
            print(f"\nStopped: {exc}\nProgress is cached; re-run later to resume.")
            return 2
        except LLMError as exc:
            print(f"\nStopped on {chunk.chunk_id}: {exc}")
            return 1

        api_calls += 0 if from_cache else 1
        cache_hits += 1 if from_cache else 0
        n_entities += len(extraction.entities)
        n_rels += len(extraction.relationships)
        n_verified += sum(r.quote_verified for r in extraction.relationships)
        n_rejected += len(extraction.rejected)

        source = "cache" if from_cache else "API"
        print(f"[{i}/{len(chunks)}] {chunk.chunk_id} [{chunk.section}] ({source})")
        print_extraction(extraction)

    print("\n--- Summary ---")
    print(f"chunks={len(chunks)}  api_calls={api_calls}  cache_hits={cache_hits}")
    print(f"entities={n_entities}  relationships={n_rels}  rejected_items={n_rejected}")
    if n_rels:
        print(f"quotes verified: {n_verified}/{n_rels} ({100 * n_verified / n_rels:.0f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())