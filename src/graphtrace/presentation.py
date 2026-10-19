"""Pure presentation helpers (no Streamlit import, so they can be unit-tested)."""

from __future__ import annotations

import re

from graphtrace.models import GraphPathView, PipelineResult

_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-!|<>~$])")


def escape_markdown(text: str) -> str:
    """Backslash-escape characters that Markdown or LaTeX would interpret, so model output renders literally."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


def highlighted_edges(paths: list[GraphPathView]) -> set[tuple[str, str, str]]:
    """Every (source, relation, target) edge used by any path, for highlighting in the graph view."""
    return {(s.source, s.relation, s.target) for p in paths for s in p.steps}


def cited_chunk_ids(result: PipelineResult) -> set[str]:
    """Chunk IDs that at least one claim cites (invalid citations were already removed)."""
    if result.answer is None:
        return set()
    return {c for claim in result.answer.claims for c in claim.citations}