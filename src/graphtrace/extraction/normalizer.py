"""Entity resolution, type-constraint checks, and edge merging with provenance."""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from graphtrace.models import (
    CanonicalEdge,
    CanonicalEntity,
    ChunkExtraction,
    DroppedItem,
    EdgeEvidence,
    EntityType,
    GraphData,
    RelationType,
)

logger = logging.getLogger(__name__)

_STORES = frozenset({EntityType.DATABASE, EntityType.CACHE, EntityType.STORAGE})
_SERVICE = frozenset({EntityType.SERVICE})

# relation -> (allowed source types, allowed target types)
RELATION_TYPE_RULES: dict[RelationType, tuple[frozenset[EntityType], frozenset[EntityType]]] = {
    RelationType.CALLS: (_SERVICE, frozenset({EntityType.SERVICE, EntityType.EXTERNAL_PROVIDER})),
    RelationType.ROUTES_TO: (_SERVICE, _SERVICE),
    RelationType.READS_FROM: (_SERVICE, _STORES),
    RelationType.WRITES_TO: (_SERVICE, _STORES),
    RelationType.PUBLISHES_TO: (_SERVICE, frozenset({EntityType.QUEUE})),
    RelationType.CONSUMES_FROM: (_SERVICE, frozenset({EntityType.QUEUE})),
    RelationType.SERVES: (_SERVICE, frozenset({EntityType.FEATURE})),
    RelationType.FALLS_BACK_TO: (_SERVICE, _STORES | _SERVICE),
    RelationType.REPLICATES_TO: (frozenset({EntityType.DATABASE}), frozenset({EntityType.DATABASE})),
}


def name_key(name: str) -> str:
    """Comparison key: case-folded, whitespace-collapsed, leading article removed."""
    key = re.sub(r"\s+", " ", name).strip().casefold()
    key = re.sub(r"^(the|an|a)\s+", "", key)
    return key.strip(" .,:;")


@dataclass(frozen=True)
class AliasConfig:
    alias_to_canonical: dict[str, str]  # name_key -> canonical display name
    ignored: frozenset[str]             # name_keys that are not real entities
    # (name_key(source), RELATION, name_key(target)) -> reason; manual corrections
    dropped_edges: dict[tuple[str, str, str], str] = field(default_factory=dict)


def load_alias_config(path: Path | None) -> AliasConfig:
    if path is None or not path.exists():
        return AliasConfig({}, frozenset())
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    mapping: dict[str, str] = {}
    for canonical, aliases in data.get("aliases", {}).items():
        mapping[name_key(canonical)] = canonical
        for alias in aliases:
            mapping[name_key(alias)] = canonical
    ignored = frozenset(name_key(n) for n in data.get("ignore", []))
    dropped_edges = {
        (name_key(e["source"]), e["relation"].upper(), name_key(e["target"])):
            e.get("reason", "manual override")
        for e in data.get("drop_edges", [])
    }
    return AliasConfig(mapping, ignored, dropped_edges)


class EntityResolver:
    """Maps surface names to one canonical display name (or None if the name is ignored)."""

    def __init__(self, config: AliasConfig, observed_names: Iterable[str]) -> None:
        self._config = config
        forms: dict[str, Counter] = defaultdict(Counter)
        for name in observed_names:
            forms[name_key(name)][name.strip()] += 1
        # For names without an alias rule, use the most common spelling (ties: alphabetical).
        self._display = {
            key: sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            for key, counter in forms.items()
        }

    def resolve(self, name: str) -> str | None:
        key = name_key(name)
        if not key or key in self._config.ignored:
            return None
        if key in self._config.alias_to_canonical:
            return self._config.alias_to_canonical[key]
        return self._display.get(key, name.strip())


def normalize(
    extractions: list[ChunkExtraction],
    config: AliasConfig,
    require_verified: bool = True,
) -> GraphData:
    """Merge per-chunk extractions into canonical entities and deduplicated edges."""
    observed = [e.name for ex in extractions for e in ex.entities]
    observed += [n for ex in extractions for r in ex.relationships for n in (r.source, r.target)]
    resolver = EntityResolver(config, observed)

    dropped: list[DroppedItem] = []
    type_votes: dict[str, Counter] = defaultdict(Counter)
    chunk_ids: dict[str, set[str]] = defaultdict(set)
    aliases: dict[str, set[str]] = defaultdict(set)

    def note(canonical: str, surface: str, chunk_id: str) -> None:
        chunk_ids[canonical].add(chunk_id)
        if surface.strip() != canonical:
            aliases[canonical].add(surface.strip())

    # Pass 1: entities and their types (majority vote across chunks).
    for ex in extractions:
        for ent in ex.entities:
            canonical = resolver.resolve(ent.name)
            if canonical is None:
                dropped.append(DroppedItem(
                    description=f"entity '{ent.name}' ({ex.chunk_id})",
                    reason="ignored generic or non-entity name",
                ))
                continue
            type_votes[canonical][ent.type] += 1
            note(canonical, ent.name, ex.chunk_id)

    entity_type: dict[str, EntityType] = {}
    for canonical, votes in type_votes.items():
        ranked = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0].value))
        entity_type[canonical] = ranked[0][0]
        if len(ranked) > 1:
            logger.warning("Type conflict for %r: %s", canonical, {t.value: n for t, n in ranked})

    # Pass 2: relationships.
    grouped: dict[tuple[str, RelationType, str], list[EdgeEvidence]] = defaultdict(list)
    for ex in extractions:
        for rel in ex.relationships:
            label = f"{rel.source} --{rel.relation.value}--> {rel.target} ({rel.chunk_id})"
            src, tgt = resolver.resolve(rel.source), resolver.resolve(rel.target)
            if src is None or tgt is None:
                dropped.append(DroppedItem(description=label, reason="endpoint is an ignored generic name"))
                continue
            if src == tgt:
                dropped.append(DroppedItem(description=label, reason="self-loop after normalization"))
                continue
            override = config.dropped_edges.get((name_key(src), rel.relation.value, name_key(tgt)))
            if override is not None:
                dropped.append(DroppedItem(description=label, reason=f"manual override: {override}"))
                continue
            src_type, tgt_type = entity_type.get(src), entity_type.get(tgt)
            if src_type is None or tgt_type is None:
                dropped.append(DroppedItem(description=label, reason="endpoint never declared as an entity (type unknown)"))
                continue
            allowed_src, allowed_tgt = RELATION_TYPE_RULES[rel.relation]
            if src_type not in allowed_src or tgt_type not in allowed_tgt:
                dropped.append(DroppedItem(
                    description=label,
                    reason=f"type constraint: {rel.relation.value} from {src_type.value} to {tgt_type.value}",
                ))
                continue
            note(src, rel.source, rel.chunk_id)
            note(tgt, rel.target, rel.chunk_id)
            grouped[(src, rel.relation, tgt)].append(
                EdgeEvidence(chunk_id=rel.chunk_id, quote=rel.evidence_quote, verified=rel.quote_verified)
            )

    edges: list[CanonicalEdge] = []
    for (src, relation, tgt), evidence in grouped.items():
        unique = sorted(set(evidence), key=lambda e: (e.chunk_id, e.quote))
        if require_verified and not any(e.verified for e in unique):
            dropped.append(DroppedItem(
                description=f"{src} --{relation.value}--> {tgt}",
                reason="no evidence quote could be verified in its source chunk",
            ))
            continue
        edges.append(CanonicalEdge(source=src, relation=relation, target=tgt, evidence=unique))
    edges.sort(key=lambda e: (e.source.casefold(), e.relation.value, e.target.casefold()))

    entities = [
        CanonicalEntity(
            name=name,
            type=entity_type[name],
            aliases=sorted(aliases[name]),
            chunk_ids=sorted(chunk_ids[name]),
        )
        for name in sorted(entity_type, key=str.casefold)
    ]
    return GraphData(entities=entities, edges=edges, dropped=dropped)