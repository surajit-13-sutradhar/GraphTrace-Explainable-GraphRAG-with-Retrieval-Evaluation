"""Streamlit interface. Presentation only: retrieval, generation and evaluation logic live in graphtrace.*"""

from __future__ import annotations

import networkx as nx
import streamlit as st

from graphtrace.config import LLM_CACHE_DIR, REPORTS_DIR, load_settings
from graphtrace.evaluation.report import METHOD_LABELS, ROWS, summarize
from graphtrace.evaluation.report import _fmt as format_metric  # reused so numbers format exactly as in the report
from graphtrace.evaluation.runner import EvalRun
from graphtrace.generation.answerer import Answerer
from graphtrace.generation.cached_client import CachedJsonGenerator
from graphtrace.generation.llm_client import GeminiClient, LLMError, LLMRateLimitError
from graphtrace.graph.visualize import to_dot
from graphtrace.models import PipelineResult
from graphtrace.pipeline import MAX_QUESTION_CHARS, GraphTrace, validate_question
from graphtrace.presentation import cited_chunk_ids, escape_markdown, highlighted_edges

BASELINE_LABEL = "Baseline RAG"
GRAPH_LABEL = "GraphRAG"
EXAMPLES = {
    "Multi-hop impact": "If the authentication service fails, which user-facing features could be affected, "
                        "and what is the dependency chain?",
    "Misleading dependency": "Will the Pricing Page stop working if the Authentication Service fails?",
    "Negation": "Does the Checkout Service call the Authentication Service to identify the user, "
                "and how does it learn who the caller is?",
    "Absent fact": "What programming language is the Billing Service written in?",
}
LETTERS = {"CORRECT": "C", "PARTIALLY_CORRECT": "P", "INCORRECT": "I"}


# ------------------------------------------------------------------ resources
@st.cache_resource(show_spinner="Loading embedding model, vector index and graph...")
def load_system() -> GraphTrace:
    return GraphTrace.load(with_llm=False)


@st.cache_resource
def load_answerer(use_cache: bool) -> Answerer:
    settings = load_settings()
    client = GeminiClient(settings.require_api_key(), settings.gemini_model, rpm=settings.gemini_rpm)
    return Answerer(CachedJsonGenerator(client, LLM_CACHE_DIR) if use_cache else client)


def set_example(text: str) -> None:
    st.session_state["question"] = text


# --------------------------------------------------------------------- running
def run_question(system: GraphTrace, question: str, methods: list[str], baseline_k: int, use_cache: bool) -> None:
    try:
        cleaned = validate_question(question)
    except ValueError as exc:
        st.warning(str(exc))
        return
    if not methods:
        st.warning("Select at least one method.")
        return
    try:
        answerer = load_answerer(use_cache)
    except RuntimeError as exc:  # missing API key
        st.error(str(exc))
        return

    results: dict[str, PipelineResult] = {}
    for label in methods:
        method = "baseline" if label == BASELINE_LABEL else "graphrag"
        with st.spinner(f"{label}: retrieving and generating..."):
            try:
                retrieval = system.retrieve(cleaned, method, baseline_k if method == "baseline" else None)
                results[label] = answerer.answer(retrieval)
            except LLMRateLimitError as exc:
                st.error(f"Rate or quota limit reached. Try again later. Details: {exc}")
                break
            except LLMError as exc:
                st.error(f"Model error: {exc}")
                break
    st.session_state["results"] = results
    st.session_state["asked"] = cleaned


# ---------------------------------------------------------------------- display
def show_answer(result: PipelineResult) -> None:
    retrieval = result.retrieval
    for note in retrieval.notes:
        st.info(note)
    if result.error:
        st.error(result.error)
        return
    answer = result.answer
    st.markdown(escape_markdown(answer.answer))
    if not answer.sufficient_evidence:
        detail = f" Missing: {answer.missing_information}" if answer.missing_information else ""
        st.warning("The system reports that the evidence is insufficient." + detail)

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Retrieval", f"{retrieval.retrieval_ms:.0f} ms")
    col_b.metric("Generation", f"{result.generation_ms:,.0f} ms")
    col_c.metric("End to end", f"{result.total_ms:,.0f} ms")

    st.markdown("**Claims**")
    if not answer.claims:
        st.caption("No claims were returned.")
    for claim in answer.claims:
        cites = ", ".join(f"`{c}`" for c in claim.citations) or ":red[none]"
        line = f"- **{claim.support.value}**: {escape_markdown(claim.text)}  \n  cites: {cites}"
        if claim.path_ids:
            line += f" · paths: {', '.join(claim.path_ids)}"
        invalid = claim.invalid_citations + claim.invalid_path_ids
        if invalid:
            line += f" · :red[invalid IDs removed: {escape_markdown(', '.join(invalid))}]"
        st.markdown(line)


def show_evidence(system: GraphTrace, results: dict[str, PipelineResult]) -> None:
    for label, result in results.items():
        retrieval = result.retrieval
        st.subheader(label)
        if retrieval.seed_entities:
            st.caption("Seed entities: " + ", ".join(retrieval.seed_entities))
        cited = cited_chunk_ids(result)
        for rc in retrieval.chunks:
            chunk = rc.chunk
            status = "cited" if chunk.chunk_id in cited else "not cited"
            title = f"{chunk.chunk_id} · {chunk.section} · score {rc.score:.3f} · {rc.origin} · {status}"
            with st.expander(escape_markdown(title)):
                st.markdown(escape_markdown(chunk.text))
                st.caption(f"Document: {chunk.doc_title}")

    shown_graph = False
    for label, result in results.items():
        retrieval = result.retrieval
        if not retrieval.graph_paths:
            continue
        shown_graph = True
        st.subheader(f"{label}: graph evidence")
        st.graphviz_chart(to_dot(
            system.graph,
            nodes=retrieval.graph_nodes,
            highlight_nodes=retrieval.seed_entities,
            highlight_edges=highlighted_edges(retrieval.graph_paths),
        ))
        st.caption(
            "Red marks the seed entities and the edges on the paths used. Edges point from the component that "
            "acts to the one acted on (a consumer points at its queue). A path shows a documented dependency, "
            "not proof that anything will fail."
        )
        for path in retrieval.graph_paths:
            with st.expander(escape_markdown(f"{path.path_id} ({path.kind}): {path.description}")):
                for step in path.steps:
                    sources = ", ".join(f"`{c}`" for c in step.chunk_ids)
                    st.markdown(
                        f"- {escape_markdown(step.source)} → **{step.relation}** → "
                        f"{escape_markdown(step.target)} · sources: {sources}"
                    )
    if not shown_graph:
        st.info("No graph paths for the methods that were run. Baseline RAG does not use the graph.")


def show_evaluation() -> None:
    results_path = REPORTS_DIR / "eval_results.json"
    if not results_path.exists():
        st.info("No evaluation results yet. Run `python scripts\\run_eval.py` first.")
        return
    try:
        run = EvalRun.model_validate_json(results_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 (show any parse problem instead of crashing the page)
        st.error(f"Could not read {results_path.name}: {exc}")
        return

    st.caption(
        f"Run started {run.started_at} · answer model `{run.answer_model}` · judge `{run.judge_model}` · "
        f"prompts {run.answer_prompt_version} / {run.judge_prompt_version}"
    )
    held_out = st.checkbox("Held-out questions only (exclude questions used while developing)")
    records = [r for r in run.records if not (held_out and r.dev)]
    methods = list(dict.fromkeys(r.method for r in records))
    summaries = {m: summarize([r for r in records if r.method == m]) for m in methods}

    table: dict[str, list[str]] = {
        "Metric": ["Questions (generation errors)"] + [label for label, _, _ in ROWS]
    }
    for m in methods:
        s = summaries[m]
        table[METHOD_LABELS.get(m, m)] = [f"{s['questions']} ({s['errors']})"] + [
            format_metric(s[key], kind) for _, key, kind in ROWS
        ]
    st.dataframe(table, hide_index=True)
    st.caption(
        "Recall, mention rate, citation validity and latency are deterministic. Judge rows are a language "
        "model's opinion, not ground truth, and the unsupported-claim rows showed 0% for every method even "
        "though the audit found a case the judge missed. 20 questions written by the system's author, with "
        "no significance testing."
    )

    by_q: dict[str, dict] = {}
    for r in records:
        by_q.setdefault(r.question_id, {})[r.method] = r
    rows = []
    for qid, recs in by_q.items():
        first = next(iter(recs.values()))
        row = {"Question": qid, "Type": first.type, "Flag": "dev" if first.dev else ""}
        for m in methods:
            r = recs.get(m)
            if r is None:
                row[METHOD_LABELS.get(m, m)] = ""
                continue
            if r.error:
                letter = "ERR"
            elif r.judge is None or r.judge.error:
                letter = "-"
            else:
                letter = LETTERS.get(r.judge.correctness, "?")
            recall = "" if r.metrics.recall is None else f" (recall {r.metrics.recall:.2f})"
            row[METHOD_LABELS.get(m, m)] = letter + recall
        rows.append(row)
    st.markdown("**Per question** (C = correct, P = partially correct, I = incorrect, by the LLM judge)")
    st.dataframe(rows, hide_index=True)

    report_path = REPORTS_DIR / "eval_report.md"
    if report_path.exists():
        with st.expander("Full report (definitions, limitations, adjudicated records)"):
            st.markdown(report_path.read_text(encoding="utf-8"))


def show_knowledge_graph(graph: nx.MultiDiGraph) -> None:
    st.graphviz_chart(to_dot(graph))
    st.caption("Node color shows the entity type. Arrows point from the component that acts to the one acted on.")
    entities = [
        {"Entity": n, "Type": d["type"], "Aliases": ", ".join(d.get("aliases", [])),
         "Source chunks": len(d.get("chunk_ids", []))}
        for n, d in graph.nodes(data=True)
    ]
    edges = [
        {"Source": u, "Relation": d["relation"], "Target": v, "Source chunks": ", ".join(d["chunk_ids"])}
        for u, v, d in graph.edges(data=True)
    ]
    with st.expander(f"Entities ({len(entities)})"):
        st.dataframe(entities, hide_index=True)
    with st.expander(f"Relationships ({len(edges)})"):
        st.dataframe(edges, hide_index=True)


# ------------------------------------------------------------------------ page
st.set_page_config(page_title="GraphTrace", layout="wide")
st.title("GraphTrace")
st.caption("Explainable GraphRAG over a fictional platform's architecture docs, compared with plain vector RAG.")

try:
    system = load_system()
except FileNotFoundError as exc:
    st.error(f"{exc}")
    st.stop()

settings = load_settings()
with st.sidebar:
    st.header("About this setup")
    st.write(f"Answer model: `{settings.gemini_model}`")
    st.write(f"Embedding model: `{system.index.model_name}`")
    st.write(
        f"{len(system.index.chunks)} chunks · graph: {system.graph.number_of_nodes()} entities, "
        f"{system.graph.number_of_edges()} relationships"
    )
    baseline_k = st.slider("Baseline top-k", 3, 10, 5)
    use_cache = st.checkbox(
        "Reuse cached LLM responses", value=True,
        help="Identical inputs are answered from disk with no API call; latency shows the original timing.",
    )
    st.caption("Each question makes up to one Gemini call per selected method. Cached questions make none.")

tab_ask, tab_evidence, tab_eval, tab_graph = st.tabs(
    ["Ask and compare", "Evidence and graph paths", "Evaluation", "Knowledge graph"]
)

with tab_ask:
    st.session_state.setdefault("question", "")
    st.write("Examples:")
    for column, (name, text) in zip(st.columns(len(EXAMPLES)), EXAMPLES.items()):
        column.button(name, on_click=set_example, args=(text,), key=f"example_{name}")
    with st.form("ask_form"):
        st.text_area("Question", key="question", height=90, max_chars=MAX_QUESTION_CHARS)
        chosen = st.multiselect("Methods to run", [BASELINE_LABEL, GRAPH_LABEL], default=[BASELINE_LABEL, GRAPH_LABEL])
        submitted = st.form_submit_button("Ask")
    if submitted:
        run_question(system, st.session_state["question"], chosen, baseline_k, use_cache)

    shown = st.session_state.get("results")
    if shown:
        st.markdown(f"**Question:** {escape_markdown(st.session_state.get('asked', ''))}")
        for column, (label, result) in zip(st.columns(len(shown)), shown.items()):
            with column:
                st.subheader(label)
                show_answer(result)
        st.caption(
            "Generation time is the successful API request only (no rate-limit waits). "
            "Cached answers replay the originally measured time."
        )

with tab_evidence:
    shown = st.session_state.get("results")
    if shown:
        show_evidence(system, shown)
    else:
        st.info("Ask a question in the first tab to see its evidence and graph paths here.")

with tab_eval:
    show_evaluation()

with tab_graph:
    show_knowledge_graph(system.graph)