"""End-to-end RAG orchestration boundary."""

from __future__ import annotations

import os
from typing import Protocol

from enterprise_rag.core.context import ContextAssembler
from enterprise_rag.core.graph_expander import GraphExpander
from enterprise_rag.core.guardrails import GuardrailService
from enterprise_rag.core.models import Answer, RetrievalHit, RetrievalQuery
from enterprise_rag.core.reranker import Reranker
from enterprise_rag.core.retriever import Retriever
from enterprise_rag.core.text import query_terms, tokenize
from enterprise_rag.ops.telemetry import EventRecorder

DECLINE_MESSAGE = (
    "I don't have sufficient evidence in authorized sources to answer confidently."
)


def _decline_threshold() -> float:
    return float(os.getenv("RAG_DECLINE_THRESHOLD", "0.15"))


def _should_decline(hits: tuple[RetrievalHit, ...]) -> bool:
    if not hits:
        return True
    return hits[0].score < _decline_threshold()


class Generator(Protocol):
    def generate(self, query: str, context: str) -> str:
        """Generate a grounded answer from assembled context."""


class ExtractiveGenerator:
    """Deterministic generator used for tests and local demos."""

    def generate(self, query: str, context: str) -> str:
        if not context:
            return "I do not have enough authorized context to answer."
        terms = set(query_terms(query))
        best_section = ""
        best_score = -1.0
        best_citation = "S1"
        for section in context.split("\n\n"):
            if not section.strip():
                continue
            lines = section.split("\n")
            header = lines[0] if lines else ""
            body = "\n".join(lines[2:]) if len(lines) > 2 else lines[-1]
            title_part = header.split("]", 1)[-1].strip() if header.startswith("[") else header
            section_score = len(terms & set(tokenize(f"{title_part} {body}")))
            section_score += len(terms & set(tokenize(title_part))) * 2
            if section_score > best_score:
                best_score = section_score
                best_section = section
                best_citation = header.split("]", 1)[0].lstrip("[") if header.startswith("[") else "S1"
        if not best_section:
            best_section = context.split("\n\n", maxsplit=1)[0]
            best_citation = best_section.split("]", 1)[0].lstrip("[") if best_section.startswith("[") else "S1"
        evidence = best_section.split("\n")[-1]
        return f"{evidence} [{best_citation}]"


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
            fetch_k = sanitized_query.top_k
            if self.reranker is not None:
                fetch_k = max(sanitized_query.top_k, sanitized_query.top_k * 4)
            search_query = RetrievalQuery(
                query=sanitized_query.query,
                tenant_id=sanitized_query.tenant_id,
                principal=sanitized_query.principal,
                mode=sanitized_query.mode,
                filters=sanitized_query.filters,
                top_k=fetch_k,
            )
            with self.recorder.span("rag.retrieve", mode=sanitized_query.mode.value):
                hits = self.retriever.search(search_query)
            if self.graph_expander and hits:
                with self.recorder.span("rag.graph_expand", hit_count=len(hits)):
                    hits = self.graph_expander.expand(sanitized_query, hits, fetch_k)
            if self.reranker and hits:
                with self.recorder.span("rag.rerank"):
                    hits = self._rerank(sanitized_query, hits)
            if _should_decline(hits):
                with self.recorder.span(
                    "rag.decline",
                    top_score=hits[0].score if hits else 0.0,
                    threshold=_decline_threshold(),
                ):
                    return Answer(
                        answer=DECLINE_MESSAGE,
                        citations=(),
                        grounded=False,
                        risk_flags=tuple(
                            dict.fromkeys((*inspected.flags, "declined_low_confidence"))
                        ),
                    )
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
