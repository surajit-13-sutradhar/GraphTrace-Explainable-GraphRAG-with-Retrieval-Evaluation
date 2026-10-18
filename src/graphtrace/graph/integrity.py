"""Sanity checks for the knowledge graph."""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from graphtrace.extraction.normalizer import RELATION_TYPE_RULES
from graphtrace.models import EntityType, RelationType


@dataclass
class IntegrityReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def check_integrity(graph: nx.MultiDiGraph, known_chunk_ids: set[str] | None = None) -> IntegrityReport:
    report = IntegrityReport()
    valid_types = {t.value for t in EntityType}

    for node, data in graph.nodes(data=True):
        if data.get("type") not in valid_types:
            report.errors.append(f"node '{node}' has invalid type {data.get('type')!r}")

    for u, v, data in graph.edges(data=True):
        label = f"{u} --{data.get('relation')}--> {v}"
        if u == v:
            report.errors.append(f"self-loop: {label}")
        chunk_ids = data.get("chunk_ids") or []
        evidence = data.get("evidence") or []
        if not chunk_ids or not evidence:
            report.errors.append(f"edge has no provenance: {label}")
        if known_chunk_ids is not None:
            unknown = set(chunk_ids) - known_chunk_ids
            if unknown:
                report.errors.append(f"edge cites unknown chunks {sorted(unknown)}: {label}")
        if evidence and not any(ev.get("verified") for ev in evidence):
            report.warnings.append(f"no verified quote: {label}")
        try:
            relation = RelationType(data.get("relation"))
        except ValueError:
            report.errors.append(f"unknown relation type: {label}")
            continue
        src_type, tgt_type = graph.nodes[u].get("type"), graph.nodes[v].get("type")
        if src_type in valid_types and tgt_type in valid_types:
            allowed_src, allowed_tgt = RELATION_TYPE_RULES[relation]
            if EntityType(src_type) not in allowed_src or EntityType(tgt_type) not in allowed_tgt:
                report.errors.append(f"type constraint violated: {label} ({src_type} -> {tgt_type})")

    isolated = sorted(n for n in graph if graph.degree(n) == 0)
    if isolated:
        report.warnings.append(f"isolated nodes (no edges): {isolated}")
    if len(graph) and nx.number_weakly_connected_components(graph) > 1:
        report.warnings.append(
            f"graph has {nx.number_weakly_connected_components(graph)} weakly connected components"
        )
    return report