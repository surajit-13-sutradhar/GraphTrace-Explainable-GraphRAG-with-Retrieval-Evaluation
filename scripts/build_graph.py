"""Normalize cached extractions into the knowledge graph (no API calls)."""

from __future__ import annotations

import argparse
from collections import Counter

from graphtrace.config import ALIASES_PATH, DOCS_DIR, EXTRACTION_CACHE_DIR, GRAPH_PATH, load_settings
from graphtrace.extraction.extractor import load_cached_extraction
from graphtrace.extraction.normalizer import load_alias_config, normalize
from graphtrace.graph.builder import build_graph, save_graph_data
from graphtrace.graph.integrity import check_integrity
from graphtrace.ingestion.chunker import chunk_documents
from graphtrace.ingestion.loader import load_documents


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partial", action="store_true", help="Build from whatever is cached.")
    parser.add_argument("--keep-unverified", action="store_true",
                        help="Keep edges whose evidence quote was not found in the chunk.")
    args = parser.parse_args()

    settings = load_settings()
    chunks = chunk_documents(load_documents(DOCS_DIR))
    extractions, missing = [], []
    for chunk in chunks:
        ex = load_cached_extraction(chunk, settings.gemini_model, EXTRACTION_CACHE_DIR)
        if ex is None:
            missing.append(chunk.chunk_id)
        else:
            extractions.append(ex)

    if missing and not args.partial:
        print(f"{len(missing)} chunks not extracted yet (model {settings.gemini_model}). "
              f"Run extract_graph.py, or use --partial.")
        return 1
    if missing:
        print(f"PARTIAL BUILD: {len(extractions)}/{len(chunks)} chunks available.\n")

    data = normalize(extractions, load_alias_config(ALIASES_PATH), require_verified=not args.keep_unverified)
    save_graph_data(data, GRAPH_PATH)
    graph = build_graph(data)
    report = check_integrity(graph, {c.chunk_id for c in chunks})

    print(f"Entities: {len(data.entities)}  Edges: {len(data.edges)}  Dropped: {len(data.dropped)}")
    print("Entity types:", dict(Counter(e.type.value for e in data.entities)))
    print("Relations:   ", dict(Counter(e.relation.value for e in data.edges)))
    print("\nEntities and aliases merged into them:")
    for e in data.entities:
        alias_text = f"  <- {e.aliases}" if e.aliases else ""
        print(f"  {e.name} ({e.type.value}){alias_text}")
    print("\nDropped items:")
    for item in data.dropped:
        print(f"  {item.description}\n      reason: {item.reason}")
    print(f"\nIntegrity: {'OK' if report.ok else 'ERRORS'}")
    for line in report.errors:
        print(f"  ERROR: {line}")
    for line in report.warnings:
        print(f"  warning: {line}")
    print(f"\nSaved {GRAPH_PATH}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())