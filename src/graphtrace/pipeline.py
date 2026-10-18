"""Top-level system: owns the loaded resources and exposes one `ask` entry point."""

from __future__ import annotations

from graphtrace.config import ALIASES_PATH, GRAPH_PATH, VECTOR_DIR, Settings, load_settings
from graphtrace.extraction.normalizer import load_alias_config
from graphtrace.generation.answerer import Answerer, JsonGenerator
from graphtrace.generation.llm_client import GeminiClient
from graphtrace.graph.builder import build_graph, load_graph_data
from graphtrace.models import PipelineResult, RetrievalResult
from graphtrace.retrieval.baseline import DEFAULT_TOP_K, BaselineRetriever
from graphtrace.retrieval.embedder import Embedder
from graphtrace.retrieval.entity_linker import EntityLinker
from graphtrace.retrieval.graph_retriever import GraphRetrievalConfig, GraphRetriever
from graphtrace.retrieval.vector_index import VectorIndex

MAX_QUESTION_CHARS = 1000
METHODS = ("baseline", "graphrag")


def validate_question(question: str) -> str:
    cleaned = " ".join((question or "").split())
    if not cleaned:
        raise ValueError("Question is empty.")
    if len(cleaned) > MAX_QUESTION_CHARS:
        raise ValueError(f"Question is too long ({len(cleaned)} > {MAX_QUESTION_CHARS} characters).")
    return cleaned


class GraphTrace:
    def __init__(
        self,
        index: VectorIndex,
        embedder: Embedder,
        graph,
        linker: EntityLinker,
        client: JsonGenerator | None = None,
        graph_config: GraphRetrievalConfig | None = None,
    ) -> None:
        self.index = index
        self.embedder = embedder
        self.graph = graph
        self.linker = linker
        self._graph_retriever = GraphRetriever(index, embedder, graph, linker, graph_config)
        self._answerer = Answerer(client) if client is not None else None

    @classmethod
    def load(cls, settings: Settings | None = None, with_llm: bool = True) -> "GraphTrace":
        settings = settings or load_settings()
        index = VectorIndex.load(VECTOR_DIR)
        embedder = Embedder(index.model_name)
        graph = build_graph(load_graph_data(GRAPH_PATH))
        linker = EntityLinker.from_graph(graph, load_alias_config(ALIASES_PATH))
        client = None
        if with_llm:
            client = GeminiClient(settings.require_api_key(), settings.gemini_model, rpm=settings.gemini_rpm)
        return cls(index, embedder, graph, linker, client)

    def retrieve(self, question: str, method: str = "graphrag", k: int | None = None) -> RetrievalResult:
        question = validate_question(question)
        if method == "baseline":
            return BaselineRetriever(self.index, self.embedder, k or DEFAULT_TOP_K).retrieve(question)
        if method == "graphrag":
            return self._graph_retriever.retrieve(question)
        raise ValueError(f"Unknown method {method!r}; expected one of {METHODS}")

    def ask(self, question: str, method: str = "graphrag", k: int | None = None) -> PipelineResult:
        if self._answerer is None:
            raise RuntimeError("This GraphTrace instance was loaded without an LLM client.")
        return self._answerer.answer(self.retrieve(question, method, k))