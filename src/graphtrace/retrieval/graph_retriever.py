"""GraphRAG retrieval: vector hits + entity linking + bounded traversal + provenance-aware ranking."""

from __future__ import annotations

import itertools
import re
import time
from collections import Counter
from dataclasses import dataclass

import networkx as nx

from graphtrace.graph.traversal import (
    GraphPath,
    impact_chains,
    neighborhood,
    shortest_connection,
    steps_among,
)
from graphtrace.models import GraphPathView, PathStepView, RetrievalResult, RetrievedChunk
from graphtrace.retrieval.embedder import Embedder
from graphtrace.retrieval.entity_linker import EntityLinker
from graphtrace.retrieval.vector_index import VectorIndex

# Failure / impact wording that switches on "who may depend on this entity" search.
IMPACT_INTENT = re.compile(
    r"\b(fail\w*|down|outage|unavailable|unreachable|crash\w*|affect\w*|impact\w*|break\w*|broken)\b",
    re.IGNORECASE,
)

# Path kinds whose steps must each be backed by at least one chunk in the evidence.
COVERED_KINDS = {"impact", "connection"}


@dataclass(frozen=True)
class GraphRetrievalConfig:
    vector_k: int = 5            # vector hits used as seeds and ranking candidates
    max_chunks: int = 8          # evidence chunks passed to the generator
    anchor_chunks: int = 2       # top vector hits that can never be displaced by graph chunks
    chunk_seed_limit: int = 3    # entities taken from retrieved chunks
    neighborhood_depth: int = 1
    max_nodes: int = 20
    impact_depth: int = 4
    max_chains: int = 15
    max_neighbor_paths: int = 12
    chain_bonus: float = 0.15    # ranking bonus for chunks backing impact/connection paths
    neighbor_bonus: float = 0.05  # ranking bonus for chunks backing neighbor edges


def _view(path_id: str, kind: str, path: GraphPath) -> GraphPathView:
    if kind == "impact":
        description = f"{path.nodes[0]} may depend on {path.nodes[-1]}"
    elif kind == "connection":
        description = f"Connection between {path.nodes[0]} and {path.nodes[-1]}"
    else:
        description = path.describe()
    steps = [
        PathStepView(source=s.source, relation=s.relation, target=s.target, chunk_ids=list(s.chunk_ids))
        for s in path.steps
    ]
    return GraphPathView(path_id=path_id, kind=kind, description=description, steps=steps)


def cover_path_steps(
    typed_paths: list[tuple[str, GraphPath]],
    scored: dict[str, float],
    already: list[str],
    budget: int,
) -> tuple[list[str], int]:
    """Greedy set cover over path steps.

    Picks chunks until every impact/connection step has at least one backing chunk in the
    evidence, or the budget runs out. Returns (chunks to add, number of steps left uncovered).
    """
    uncovered: dict[tuple[str, str, str], set[str]] = {}
    for kind, path in typed_paths:
        if kind not in COVERED_KINDS:
            continue
        for step in path.steps:
            key = (step.source, step.relation, step.target)
            uncovered.setdefault(key, {c for c in step.chunk_ids if c in scored})

    chosen = set(already)
    # Steps with no known source chunk cannot be covered; steps already covered need nothing.
    uncovered = {k: v for k, v in uncovered.items() if v and not (v & chosen)}

    added: list[str] = []
    while uncovered and len(added) < budget:
        counts = Counter(c for chunk_ids in uncovered.values() for c in chunk_ids)
        best = max(counts, key=lambda c: (counts[c], scored[c], c))  # deterministic tie-break
        added.append(best)
        uncovered = {k: v for k, v in uncovered.items() if best not in v}
    return added, len(uncovered)


class GraphRetriever:
    def __init__(
        self,
        index: VectorIndex,
        embedder: Embedder,
        graph: nx.MultiDiGraph,
        linker: EntityLinker,
        config: GraphRetrievalConfig | None = None,
    ) -> None:
        self._index = index
        self._embedder = embedder
        self._graph = graph
        self._linker = linker
        self._cfg = config or GraphRetrievalConfig()

    def _chunk_seeds(self, hits: list[RetrievedChunk], exclude: set[str]) -> list[str]:
        counts: Counter[str] = Counter()
        for hit in hits:
            counts.update(set(self._linker.link(hit.chunk.text)))
        ordered = [name for name, _ in counts.most_common() if name not in exclude]
        return ordered[: self._cfg.chunk_seed_limit]

    def retrieve(self, question: str) -> RetrievalResult:
        cfg = self._cfg
        start = time.perf_counter()
        query_vector = self._embedder.encode([question])[0]
        vector_hits = self._index.search(query_vector, cfg.vector_k)

        question_seeds = self._linker.link(question)
        chunk_seeds = self._chunk_seeds(vector_hits, exclude=set(question_seeds))
        seeds = question_seeds or chunk_seeds
        notes: list[str] = []

        def finish(chunks, nodes, paths) -> RetrievalResult:
            return RetrievalResult(
                question=question,
                method="graphrag",
                chunks=chunks,
                seed_entities=seeds,
                graph_nodes=nodes,
                graph_paths=paths,
                retrieval_ms=(time.perf_counter() - start) * 1000,
                notes=notes,
            )

        if not seeds:
            notes.append("No known graph entity found; fell back to vector results only.")
            return finish(vector_hits[: cfg.max_chunks], [], [])
        if not question_seeds:
            notes.append("No known entity in the question; graph seeded from the retrieved chunks.")

        typed_paths: list[tuple[str, GraphPath]] = []

        # 1. Connections between entities named in the question (multi-entity questions).
        for a, b in itertools.combinations(question_seeds[:3], 2):
            connection = shortest_connection(self._graph, a, b, max_depth=3)
            if connection and connection.steps:
                typed_paths.append(("connection", connection))

        # 2. Impact mode: what may depend on the entity the question is about.
        chains: list[GraphPath] = []
        if question_seeds and IMPACT_INTENT.search(question):
            for seed in question_seeds[:2]:
                chains += impact_chains(self._graph, seed, cfg.impact_depth, cfg.max_chains)
            if not chains:
                notes.append("Failure wording found but nothing documented depends on the entity; "
                             "using neighborhood expansion instead.")
        typed_paths += [("impact", c) for c in chains]

        # 3. Neighborhood mode (also the fallback): bounded expansion around the seeds.
        nodes: list[str] = list(seeds)
        if not chains:
            hits = neighborhood(self._graph, seeds, cfg.neighborhood_depth, cfg.max_nodes)
            neighbor_nodes = [h.node for h in hits]
            seed_set = set(seeds)
            steps = [
                s for s in steps_among(self._graph, neighbor_nodes)
                if s.source in seed_set or s.target in seed_set
            ][: cfg.max_neighbor_paths]
            typed_paths += [("neighbor", GraphPath((s.source, s.target), (s,))) for s in steps]
            nodes += neighbor_nodes
        for _, path in typed_paths:
            nodes += list(path.nodes)
        nodes = list(dict.fromkeys(nodes))

        # Score: cosine similarity + bonus for being cited by a graph path.
        bonus: dict[str, float] = {}
        for kind, path in typed_paths:
            value = cfg.neighbor_bonus if kind == "neighbor" else cfg.chain_bonus
            for chunk_id in path.chunk_ids:
                bonus[chunk_id] = max(bonus.get(chunk_id, 0.0), value)

        similarity = {h.chunk.chunk_id: h.score for h in vector_hits}
        missing = [c for c in bonus if c not in similarity]
        similarity.update(self._index.similarity_to(query_vector, missing))
        scored = {cid: sim + bonus.get(cid, 0.0) for cid, sim in similarity.items()}

        # Select: (1) top vector hits as anchors, (2) chunks needed so every impact/connection
        # step has source text in the evidence, (3) fill remaining slots by score.
        chosen = [h.chunk.chunk_id for h in vector_hits[: cfg.anchor_chunks]]
        covering, uncovered = cover_path_steps(typed_paths, scored, chosen, cfg.max_chunks - len(chosen))
        chosen += covering
        if uncovered:
            notes.append(f"{uncovered} path step(s) have no backing chunk in the evidence (budget reached).")
        for chunk_id in sorted(scored, key=lambda c: scored[c], reverse=True):
            if len(chosen) >= cfg.max_chunks:
                break
            if chunk_id not in chosen:
                chosen.append(chunk_id)
        chosen.sort(key=lambda c: scored[c], reverse=True)

        vector_ids = {h.chunk.chunk_id for h in vector_hits}
        chunks: list[RetrievedChunk] = []
        for chunk_id in chosen:
            chunk = self._index.get_chunk(chunk_id)
            if chunk is None:
                continue
            if chunk_id in vector_ids and chunk_id in bonus:
                origin = "both"
            else:
                origin = "vector" if chunk_id in vector_ids else "graph"
            chunks.append(RetrievedChunk(chunk=chunk, score=scored[chunk_id], origin=origin))

        views = [_view(f"P{i}", kind, path) for i, (kind, path) in enumerate(typed_paths, start=1)]
        return finish(chunks, nodes, views)