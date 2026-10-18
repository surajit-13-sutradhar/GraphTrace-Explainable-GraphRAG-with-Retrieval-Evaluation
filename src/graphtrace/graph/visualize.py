"""Graphviz DOT export (also used by the Streamlit app via st.graphviz_chart)."""

from __future__ import annotations

from typing import Iterable

import networkx as nx

TYPE_COLORS = {
    "SERVICE": "#BBDEFB",
    "DATABASE": "#C8E6C9",
    "CACHE": "#FFF9C4",
    "QUEUE": "#FFE0B2",
    "STORAGE": "#D7CCC8",
    "EXTERNAL_PROVIDER": "#E1BEE7",
    "FEATURE": "#F8BBD0",
}
HIGHLIGHT = "#D62728"


def _q(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def to_dot(
    graph: nx.MultiDiGraph,
    nodes: Iterable[str] | None = None,
    highlight_nodes: Iterable[str] = (),
    highlight_edges: Iterable[tuple[str, str, str]] = (),
) -> str:
    """DOT text. `nodes` restricts the view; highlight_edges are (source, relation, target)."""
    node_set = set(nodes) if nodes is not None else set(graph.nodes)
    hot_nodes, hot_edges = set(highlight_nodes), set(highlight_edges)
    lines = [
        "digraph G {",
        "  rankdir=LR;",
        '  node [shape=box, style="rounded,filled", fontname="Helvetica"];',
        '  edge [fontname="Helvetica", fontsize=10];',
    ]
    for node in sorted(node_set):
        if node not in graph:
            continue
        color = TYPE_COLORS.get(graph.nodes[node].get("type"), "#EEEEEE")
        extra = f', color="{HIGHLIGHT}", penwidth=3' if node in hot_nodes else ""
        lines.append(f"  {_q(node)} [fillcolor={_q(color)}{extra}];")
    for u, v, data in graph.edges(data=True):
        if u in node_set and v in node_set:
            hot = (u, data["relation"], v) in hot_edges
            extra = f', color="{HIGHLIGHT}", penwidth=2.5' if hot else ""
            lines.append(f"  {_q(u)} -> {_q(v)} [label={_q(data['relation'])}{extra}];")
    lines.append("}")
    return "\n".join(lines)