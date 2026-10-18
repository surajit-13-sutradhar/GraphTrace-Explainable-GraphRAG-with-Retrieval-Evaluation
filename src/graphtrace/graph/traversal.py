"""Bounded, cycle-safe traversal. Pure functions over the MultiDiGraph from builder.py.

Results describe POSSIBLE dependencies found in documentation, never proof of failure.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import networkx as nx


@dataclass(frozen=True)
class PathStep:
    source: str
    relation: str
    target: str
    chunk_ids: tuple[str, ...]

    def label(self) -> str:
        return f"{self.source} --{self.relation}--> {self.target}"


@dataclass(frozen=True)
class GraphPath:
    nodes: tuple[str, ...]
    steps: tuple[PathStep, ...]

    @property
    def chunk_ids(self) -> list[str]:
        return sorted({c for step in self.steps for c in step.chunk_ids})

    def describe(self) -> str:
        return " | ".join(step.label() for step in self.steps) or self.nodes[0]


@dataclass(frozen=True)
class NodeHit:
    node: str
    depth: int


def edge_steps(graph: nx.MultiDiGraph, source: str, target: str) -> list[PathStep]:
    """All edges source -> target as PathSteps, sorted by relation."""
    data = graph.get_edge_data(source, target, default={}) or {}
    steps = [
        PathStep(source, attrs["relation"], target, tuple(attrs["chunk_ids"]))
        for attrs in data.values()
    ]
    return sorted(steps, key=lambda s: s.relation)


def steps_among(graph: nx.MultiDiGraph, nodes: set[str] | list[str]) -> list[PathStep]:
    """Every edge whose two endpoints are both in `nodes`."""
    steps = [
        PathStep(u, data["relation"], v, tuple(data["chunk_ids"]))
        for u, v, data in graph.subgraph(set(nodes)).edges(data=True)
    ]
    return sorted(steps, key=lambda s: (s.source, s.relation, s.target))


def neighborhood(
    graph: nx.MultiDiGraph,
    seeds: list[str],
    max_depth: int = 1,
    max_nodes: int = 25,
    directed: bool = False,
) -> list[NodeHit]:
    """Breadth-first expansion from seeds, bounded by depth and node count.

    Unknown seeds are ignored. Cycles are safe (visited set). Seeds are always
    kept even if they alone exceed max_nodes.
    """
    if max_depth < 0 or max_nodes < 1:
        raise ValueError("max_depth must be >= 0 and max_nodes >= 1")
    depth_of: dict[str, int] = {}
    queue: deque[str] = deque()
    for seed in dict.fromkeys(seeds):
        if seed in graph:
            depth_of[seed] = 0
            queue.append(seed)
    while queue and len(depth_of) < max_nodes:
        node = queue.popleft()
        depth = depth_of[node]
        if depth >= max_depth:
            continue
        neighbors = set(graph.successors(node))
        if not directed:
            neighbors |= set(graph.predecessors(node))
        for neighbor in sorted(neighbors):
            if neighbor in depth_of:
                continue
            depth_of[neighbor] = depth + 1
            queue.append(neighbor)
            if len(depth_of) >= max_nodes:
                break
    return [NodeHit(node, depth) for node, depth in depth_of.items()]


def shortest_connection(
    graph: nx.MultiDiGraph, a: str, b: str, max_depth: int = 4
) -> GraphPath | None:
    """Shortest path between a and b ignoring edge direction; steps keep their true direction."""
    if a not in graph or b not in graph:
        return None
    if a == b:
        return GraphPath((a,), ())
    try:
        nodes = nx.shortest_path(nx.Graph(graph), a, b)
    except nx.NetworkXNoPath:
        return None
    if len(nodes) - 1 > max_depth:
        return None
    steps = []
    for u, v in zip(nodes, nodes[1:]):
        found = edge_steps(graph, u, v) or edge_steps(graph, v, u)
        steps.append(found[0])
    return GraphPath(tuple(nodes), tuple(steps))


# How each relation creates a *possible* dependency between nodes.
#   forward : source may depend on target (A calls B  -> A depends on B)
#   reverse : target may depend on source (Gateway routes to X -> X needs the gateway to be
#             reachable; Service serves Feature -> Feature depends on Service; primary
#             replicates to replica -> replica depends on primary)
#   conditional : only relevant when the primary path is down (fallbacks)
FORWARD = {"CALLS", "READS_FROM", "WRITES_TO", "PUBLISHES_TO", "CONSUMES_FROM"}
REVERSE = {"ROUTES_TO", "SERVES", "REPLICATES_TO"}
CONDITIONAL = {"FALLS_BACK_TO"}


def dependency_graph(graph: nx.MultiDiGraph, include_conditional: bool = False) -> nx.DiGraph:
    """Edge u -> v means 'u may depend on v'. Each edge keeps the original steps that justify it."""
    dep = nx.DiGraph()
    dep.add_nodes_from(graph.nodes)
    for u, v, data in graph.edges(data=True):
        relation = data["relation"]
        step = PathStep(u, relation, v, tuple(data["chunk_ids"]))
        if relation in FORWARD or (relation in CONDITIONAL and include_conditional):
            a, b = u, v
        elif relation in REVERSE:
            a, b = v, u
        else:
            continue
        if dep.has_edge(a, b):
            dep[a][b]["steps"].append(step)
        else:
            dep.add_edge(a, b, steps=[step])
    return dep


def impact_chains(
    graph: nx.MultiDiGraph,
    failed: str,
    max_depth: int = 4,
    max_chains: int = 25,
    include_conditional: bool = False,
) -> list[GraphPath]:
    """Nodes that MAY depend on `failed`, nearest first, each with one shortest chain.

    A chain's nodes run from the dependent down to the failed node. Whether a
    dependent really fails depends on timeouts, retries, caches, and fallbacks,
    none of which the graph encodes.

    ROUTES_TO means "client traffic reaches X through the gateway". Once a chain has
    crossed such a step, it may only continue to user-facing features (SERVES);
    continuing through CALLS edges would claim dependencies that are not on the
    user-request path.
    """
    if failed not in graph:
        return []
    dep = dependency_graph(graph, include_conditional)

    State = tuple[str, bool]  # (node, chain has crossed a ROUTES_TO step)
    start: State = (failed, False)
    depth_of: dict[State, int] = {start: 0}
    parent: dict[State, State] = {}
    first_state: dict[str, State] = {}
    order: list[str] = []
    queue: deque[State] = deque([start])

    while queue:
        state = queue.popleft()
        node, routed = state
        if depth_of[state] >= max_depth:
            continue
        for dependent in sorted(dep.predecessors(node)):
            if dependent == failed:
                continue
            steps = dep[dependent][node]["steps"]
            if routed and not all(s.relation == "SERVES" for s in steps):
                continue
            new_state: State = (dependent, routed or any(s.relation == "ROUTES_TO" for s in steps))
            if new_state in depth_of:
                continue
            depth_of[new_state] = depth_of[state] + 1
            parent[new_state] = state
            queue.append(new_state)
            if dependent not in first_state:
                first_state[dependent] = new_state
                order.append(dependent)

    chains: list[GraphPath] = []
    for dependent in order[:max_chains]:
        state = first_state[dependent]
        nodes, steps_out = [dependent], []
        while state in parent:
            prev = parent[state]
            best = sorted(dep[state[0]][prev[0]]["steps"], key=lambda s: s.relation)[0]
            steps_out.append(best)
            nodes.append(prev[0])
            state = prev
        chains.append(GraphPath(tuple(nodes), tuple(steps_out)))
    return chains