"""Map free text (questions, chunks) to canonical graph nodes."""

from __future__ import annotations

import re

import networkx as nx

from graphtrace.extraction.normalizer import AliasConfig, name_key


class EntityLinker:
    """Whole-phrase, case-insensitive matching against node names and known aliases."""

    def __init__(self, lookup: dict[str, str]) -> None:
        self._lookup = lookup  # name_key -> canonical node name
        keys = sorted(lookup, key=len, reverse=True)  # longest phrase wins
        if keys:
            pattern = "|".join(re.escape(k).replace(r"\ ", r"\s+") for k in keys)
            self._regex: re.Pattern[str] | None = re.compile(
                rf"(?<![\w-])(?:{pattern})(?![\w-])", re.IGNORECASE
            )
        else:
            self._regex = None

    @classmethod
    def from_graph(cls, graph: nx.MultiDiGraph, config: AliasConfig | None = None) -> "EntityLinker":
        lookup: dict[str, str] = {}
        for node, data in graph.nodes(data=True):
            lookup[name_key(node)] = node
        for node, data in graph.nodes(data=True):
            for alias in data.get("aliases", []):
                lookup.setdefault(name_key(alias), node)
        if config is not None:
            for key, canonical in config.alias_to_canonical.items():
                if canonical in graph:
                    lookup.setdefault(key, canonical)
            for key in config.ignored:
                lookup.pop(key, None)
        return cls(lookup)

    def link(self, text: str) -> list[str]:
        """Canonical node names in order of first appearance, without duplicates."""
        if not self._regex or not text:
            return []
        found: list[str] = []
        for match in self._regex.finditer(text):
            canonical = self._lookup.get(name_key(match.group(0)))
            if canonical and canonical not in found:
                found.append(canonical)
        return found