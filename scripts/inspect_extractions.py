"""Summarize cached extractions: entity inventory, alias candidates, edges, anomalies.

Reads only the cache; makes no API calls.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from difflib import SequenceMatcher
from itertools import combinations

from graphtrace.config import DOCS_DIR, EXTRACTION_CACHE_DIR, load_settings
from graphtrace.extraction.extractor import load_cached_extraction
from graphtrace.ingestion.chunker import chunk_documents
from graphtrace.ingestion.loader import load_documents

ALIAS_SIMILARITY = 0.65


def main() -> int:
    settings = load_settings()
    chunks = chunk_documents(load_documents(DOCS_DIR))

    types: dict[str, Counter] = defaultdict(Counter)   # name -> {type: count}
    mentions: Counter = Counter()                      # name -> number of chunks mentioning it
    triples: dict[tuple, dict] = {}                    # (src, rel, tgt) -> {"chunks": set, "unverified": int}
    relation_counts: Counter = Counter()
    rejected: list[str] = []
    missing: list[str] = []

    for chunk in chunks:
        ex = load_cached_extraction(chunk, settings.gemini_model, EXTRACTION_CACHE_DIR)
        if ex is None:
            missing.append(chunk.chunk_id)
            continue

        declared = {e.name for e in ex.entities}
        in_chunk = set(declared)
        for e in ex.entities:
            types[e.name][e.type.value] += 1
        for r in ex.relationships:
            relation_counts[r.relation.value] += 1
            for endpoint in (r.source, r.target):
                in_chunk.add(endpoint)
                if endpoint not in declared:
                    types[endpoint]["(undeclared)"] += 1
            info = triples.setdefault((r.source, r.relation.value, r.target),
                                      {"chunks": set(), "unverified": 0})
            info["chunks"].add(r.chunk_id)
            info["unverified"] += 0 if r.quote_verified else 1
        for name in in_chunk:
            mentions[name] += 1
        rejected.extend(f"{chunk.chunk_id}: {reason}" for reason in ex.rejected)

    if missing:
        print(f"{len(missing)} chunks are not cached yet (run scripts/extract_graph.py): {missing}")
        return 1

    print(f"=== Entity names ({len(types)} distinct) ===")
    for name in sorted(types, key=str.casefold):
        type_text = ", ".join(f"{t} x{n}" for t, n in types[name].items())
        print(f"  {name:<34} chunks={mentions[name]:<3} {type_text}")

    print("\n=== Alias candidates (similar names; for human review) ===")
    found = False
    for a, b in combinations(sorted(types, key=str.casefold), 2):
        ratio = SequenceMatcher(None, a.casefold(), b.casefold()).ratio()
        if ratio >= ALIAS_SIMILARITY:
            print(f"  {a!r} ~ {b!r}  ({ratio:.2f})")
            found = True
    if not found:
        print("  (none)")

    print("\n=== Names with conflicting types ===")
    conflicts = [n for n, c in types.items() if len(c) > 1]
    for name in sorted(conflicts, key=str.casefold):
        print(f"  {name}: {dict(types[name])}")
    if not conflicts:
        print("  (none)")

    print(f"\n=== Distinct edges ({len(triples)}) ===")
    for (src, rel, tgt), info in sorted(triples.items(), key=lambda kv: (kv[0][0].casefold(), kv[0][1], kv[0][2].casefold())):
        flag = f"  [UNVERIFIED x{info['unverified']}]" if info["unverified"] else ""
        print(f"  {src} --{rel}--> {tgt}  ({len(info['chunks'])} chunk(s)){flag}")

    print("\n=== Relation type counts ===")
    for rel, n in relation_counts.most_common():
        print(f"  {rel:<14} {n}")

    print(f"\n=== Rejected items ({len(rejected)}) ===")
    for line in rejected:
        print(f"  {line}")

    total_rel = sum(relation_counts.values())
    unverified = sum(i["unverified"] for i in triples.values())
    print(f"\nchunks={len(chunks)}  raw_relationships={total_rel}  distinct_edges={len(triples)}  unverified_quotes={unverified}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())