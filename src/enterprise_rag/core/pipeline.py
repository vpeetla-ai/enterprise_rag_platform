"""End-to-end RAG orchestration boundary."""

from __future__ import annotations

import os

from enterprise_rag.core.context import ContextAssembler
from enterprise_rag.core.generator import ExtractiveGenerator, Generator, build_generator
from enterprise_rag.core.graph_expander import GraphExpander
from enterprise_rag.core.guardrails import GuardrailService
from enterprise_rag.core.models import Answer, RetrievalHit, RetrievalQuery
from enterprise_rag.core.reranker import Reranker
from enterprise_rag.core.retriever import Retriever
from enterprise_rag.ops.telemetry import EventRecorder

DECLINE_MESSAGE = (
    "I don't have sufficient evidence in authorized sources to answer confidently."
)


def _decline_threshold(*, cross_encoder: bool = False) -> float:
    if cross_encoder:
        return float(os.getenv("RAG_DECLINE_THRESHOLD_CE", os.getenv("RAG_DECLINE_THRESHOLD", "-10.0")))
    # RRF scores are typically O(0.01–0.05); legacy 0.15 was calibrated for BM25-ish magnitudes.
    return float(os.getenv("RAG_DECLINE_THRESHOLD", "0.001"))


def _should_decline(hits: tuple[RetrievalHit, ...], *, cross_encoder: bool = False) -> bool:
    if not hits:
        return True
    return hits[0].score < _decline_threshold(cross_encoder=cross_encoder)


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
        self.generator = generator or build_generator()
        self.assembler = assembler or ContextAssembler()
        self.guardrails = guardrails or GuardrailService()
        self.reranker = reranker
        self.graph_expander = graph_expander
        self.recorder = recorder or EventRecorder()

    def answer(self, retrieval_query: RetrievalQuery) -> Answer:
        with self.recorder.span("rag.answer", tenant_id=retrieval_query.tenant_id):
            with self.recorder.span("rag.guardrails.input"):
                inspected = self.guardrails.inspect_input(retrieval_query.query)
            if "prompt_injection_suspected" in inspected.flags:
                with self.recorder.span("rag.decline", reason="prompt_injection_suspected"):
                    # Keep GER adversarial flag contracts: do not surface the internal inject tag.
                    public_flags = tuple(
                        f for f in inspected.flags if f != "prompt_injection_suspected"
                    )
                    return Answer(
                        answer=DECLINE_MESSAGE,
                        citations=(),
                        grounded=False,
                        risk_flags=tuple(
                            dict.fromkeys((*public_flags, "declined_low_confidence"))
                        ),
                    )
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
            with self.recorder.span("rag.retrieve", mode=sanitized_query.mode.value, fusion="rrf"):
                hits = self.retriever.search(search_query)
            if self.graph_expander and hits:
                with self.recorder.span("rag.graph_expand", hit_count=len(hits)):
                    hits = self.graph_expander.expand(sanitized_query, hits, fetch_k)
            used_ce = False
            if self.reranker and hits:
                with self.recorder.span("rag.rerank"):
                    hits = self._rerank(sanitized_query, hits)
                    used_ce = any("cross_encoder" in h.reasons for h in hits)
            if _should_decline(hits, cross_encoder=used_ce):
                with self.recorder.span(
                    "rag.decline",
                    top_score=hits[0].score if hits else 0.0,
                    threshold=_decline_threshold(cross_encoder=used_ce),
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
            if "faithfulness_failed" in answer.risk_flags and os.getenv(
                "FAITHFULNESS_DECLINE", "true"
            ).strip().lower() in {"1", "true", "yes", "on"}:
                with self.recorder.span("rag.faithfulness", gate="failed"):
                    return Answer(
                        answer=DECLINE_MESSAGE,
                        citations=(),
                        grounded=False,
                        risk_flags=tuple(
                            dict.fromkeys(
                                (*inspected.flags, *answer.risk_flags, "declined_unfaithful")
                            )
                        ),
                    )
            with self.recorder.span("rag.faithfulness", gate="ok"):
                pass
            return Answer(
                answer=answer.answer,
                citations=answer.citations,
                grounded=answer.grounded,
                risk_flags=tuple(dict.fromkeys((*inspected.flags, *answer.risk_flags))),
            )

    def _rerank(self, query: RetrievalQuery, hits: tuple[RetrievalHit, ...]) -> tuple[RetrievalHit, ...]:
        assert self.reranker is not None
        return self.reranker.rerank(query.query, hits, query.top_k)


# Back-compat re-export
__all__ = ["RagPipeline", "Generator", "ExtractiveGenerator", "DECLINE_MESSAGE"]
