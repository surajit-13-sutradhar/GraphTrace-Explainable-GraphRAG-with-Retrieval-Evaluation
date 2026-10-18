"""Build, save, and load the knowledge graph."""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from graphtrace.models import GraphData


def save_graph_data(data: GraphData, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data.model_dump_json(indent=2), encoding="utf-8")


def load_graph_data(path: Path) -> GraphData:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run scripts/build_graph.py first.")
    return GraphData.model_validate_json(path.read_text(encoding="utf-8"))


def build_graph(data: GraphData) -> nx.MultiDiGraph:
    """One node per canonical entity; one edge per (source, relation, target), keyed by relation."""
    graph = nx.MultiDiGraph()
    for entity in data.entities:
        graph.add_node(
            entity.name,
            type=entity.type.value,
            aliases=list(entity.aliases),
            chunk_ids=list(entity.chunk_ids),
        )
    for edge in data.edges:
        graph.add_edge(
            edge.source,
            edge.target,
            key=edge.relation.value,
            relation=edge.relation.value,
            evidence=[ev.model_dump() for ev in edge.evidence],
            chunk_ids=edge.chunk_ids,
        )
    return graph