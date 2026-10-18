"""Render the knowledge graph to reports/graph.png and reports/graph.dot."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx

from graphtrace.config import GRAPH_PATH, PROJECT_ROOT
from graphtrace.graph.builder import build_graph, load_graph_data
from graphtrace.graph.visualize import TYPE_COLORS, to_dot


def main() -> None:
    graph = build_graph(load_graph_data(GRAPH_PATH))
    out_dir = PROJECT_ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "graph.dot").write_text(to_dot(graph), encoding="utf-8")

    pos = nx.spring_layout(nx.Graph(graph), seed=7, k=1.4)
    colors = [TYPE_COLORS.get(graph.nodes[n].get("type"), "#EEEEEE") for n in graph]
    fig, ax = plt.subplots(figsize=(18, 12))
    nx.draw_networkx_nodes(graph, pos, node_color=colors, node_size=2200, ax=ax, edgecolors="#555")
    nx.draw_networkx_labels(graph, pos, font_size=7, ax=ax)
    nx.draw_networkx_edges(graph, pos, arrows=True, arrowsize=14, node_size=2200,
                           connectionstyle="arc3,rad=0.12", edge_color="#777", ax=ax)
    ax.set_axis_off()
    fig.savefig(out_dir / "graph.png", dpi=130, bbox_inches="tight")
    print(f"Wrote {out_dir / 'graph.png'} and graph.dot ({len(graph)} nodes, {graph.number_of_edges()} edges)")


if __name__ == "__main__":
    main()