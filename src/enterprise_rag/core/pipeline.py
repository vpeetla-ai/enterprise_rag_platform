"""End-to-end RAG orchestration boundary."""

from __future__ import annotations

from typing import Protocol

from enterprise_rag.core.context import ContextAssembler
from enterprise_rag.core.graph_expander import GraphExpander
from enterprise_rag.core.guardrails import GuardrailService
from enterprise_rag.core.models import Answer, RetrievalHit, RetrievalQuery
from enterprise_rag.core.reranker import Reranker
from enterprise_rag.core.retriever import Retriever
from enterprise_rag.ops.telemetry import EventRecorder


class Generator(Protocol):
    def generate(self, query: str, context: str) -> str:
        """Generate a grounded answer from assembled context."""


class ExtractiveGenerator:
    """Deterministic generator used for tests and local demos."""

    def generate(self, query: str, context: str) -> str:
        if not context:
            return "I do not have enough authorized context to answer."
        first_source = context.split("\n\n", maxsplit=1)[0]
        citation = first_source.split("]", maxsplit=1)[0].lstrip("[")
        evidence = first_source.split("\n")[-1]
        return f"{evidence} [{citation}]"


class RagPipeline:
    def __init__(
        self,
        retriever: Retriever,
        generator: Generator | None = None,
        assembler: ContextAssembler | None = None,
        guardrails: GuardrailService | None = None,
        reranker: Reranker | None = None,
        graph_expander: GraphExpander | None = None,
        recorder: EventRecorder | None = None,
    ) -> None:
        self.retriever = retriever
        self.generator = generator or ExtractiveGenerator()
        self.assembler = assembler or ContextAssembler()
        self.guardrails = guardrails or GuardrailService()
        self.reranker = reranker
        self.graph_expander = graph_expander
        self.recorder = recorder or EventRecorder()

    def answer(self, retrieval_query: RetrievalQuery) -> Answer:
        with self.recorder.span("rag.answer", tenant_id=retrieval_query.tenant_id):
            with self.recorder.span("rag.guardrails.input"):
                inspected = self.guardrails.inspect_input(retrieval_query.query)
            sanitized_query = RetrievalQuery(
                query=inspected.redacted_text,
                tenant_id=retrieval_query.tenant_id,
                principal=retrieval_query.principal,
                mode=retrieval_query.mode,
                filters=retrieval_query.filters,
                top_k=retrieval_query.top_k,
            )
            with self.recorder.span("rag.retrieve", mode=sanitized_query.mode.value):
                hits = self.retriever.search(sanitized_query)
            if self.graph_expander and hits:
                with self.recorder.span("rag.graph_expand", hit_count=len(hits)):
                    hits = self.graph_expander.expand(sanitized_query, hits, sanitized_query.top_k)
            if self.reranker and hits:
                with self.recorder.span("rag.rerank"):
                    hits = self._rerank(sanitized_query, hits)
            with self.recorder.span("rag.assemble", hit_count=len(hits)):
                context = self.assembler.assemble(sanitized_query.query, hits)
            with self.recorder.span("rag.generate"):
                raw_answer = self.generator.generate(sanitized_query.query, context.context)
            with self.recorder.span("rag.guardrails.output"):
                answer = self.guardrails.validate_output(raw_answer, context)
            return Answer(
                answer=answer.answer,
                citations=answer.citations,
                grounded=answer.grounded,
                risk_flags=tuple(dict.fromkeys((*inspected.flags, *answer.risk_flags))),
            )

    def _rerank(self, query: RetrievalQuery, hits: tuple[RetrievalHit, ...]) -> tuple[RetrievalHit, ...]:
        assert self.reranker is not None
        return self.reranker.rerank(query.query, hits, query.top_k)
