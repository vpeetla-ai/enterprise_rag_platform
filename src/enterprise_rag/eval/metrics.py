"""Offline evaluation metrics for RAG regression suites."""

from __future__ import annotations

from dataclasses import dataclass

from enterprise_rag.core.models import Answer, RetrievalHit


@dataclass(frozen=True)
class RetrievalExpectation:
    query: str
    expected_document_ids: frozenset[str]


@dataclass(frozen=True)
class EvaluationReport:
    retrieval_recall_at_k: float
    citation_coverage: float
    grounded_rate: float


class EvaluationEngine:
    def retrieval_recall(
        self, expectations: tuple[RetrievalExpectation, ...], results: tuple[tuple[RetrievalHit, ...], ...]
    ) -> float:
        if not expectations:
            return 0.0
        total = 0.0
        for expectation, hits in zip(expectations, results, strict=True):
            retrieved = {hit.chunk.document_id for hit in hits}
            total += len(retrieved & expectation.expected_document_ids) / max(
                len(expectation.expected_document_ids), 1
            )
        return total / len(expectations)

    @staticmethod
    def citation_coverage(answers: tuple[Answer, ...]) -> float:
        if not answers:
            return 0.0
        return sum(1 for answer in answers if answer.citations) / len(answers)

    @staticmethod
    def grounded_rate(answers: tuple[Answer, ...]) -> float:
        if not answers:
            return 0.0
        return sum(1 for answer in answers if answer.grounded) / len(answers)
