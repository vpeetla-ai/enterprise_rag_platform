"""End-to-end RAG orchestration boundary."""

from __future__ import annotations

from typing import Protocol

from enterprise_rag.core.context import ContextAssembler
from enterprise_rag.core.guardrails import GuardrailService
from enterprise_rag.core.models import Answer, RetrievalQuery
from enterprise_rag.core.retrieval import InMemoryHybridRetriever


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
        retriever: InMemoryHybridRetriever,
        generator: Generator | None = None,
        assembler: ContextAssembler | None = None,
        guardrails: GuardrailService | None = None,
    ) -> None:
        self.retriever = retriever
        self.generator = generator or ExtractiveGenerator()
        self.assembler = assembler or ContextAssembler()
        self.guardrails = guardrails or GuardrailService()

    def answer(self, retrieval_query: RetrievalQuery) -> Answer:
        inspected = self.guardrails.inspect_input(retrieval_query.query)
        sanitized_query = RetrievalQuery(
            query=inspected.redacted_text,
            tenant_id=retrieval_query.tenant_id,
            principal=retrieval_query.principal,
            mode=retrieval_query.mode,
            filters=retrieval_query.filters,
            top_k=retrieval_query.top_k,
        )
        hits = self.retriever.search(sanitized_query)
        context = self.assembler.assemble(sanitized_query.query, hits)
        raw_answer = self.generator.generate(sanitized_query.query, context.context)
        answer = self.guardrails.validate_output(raw_answer, context)
        return Answer(
            answer=answer.answer,
            citations=answer.citations,
            grounded=answer.grounded,
            risk_flags=tuple(dict.fromkeys((*inspected.flags, *answer.risk_flags))),
        )
