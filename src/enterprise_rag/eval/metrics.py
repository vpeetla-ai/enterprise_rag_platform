"""Offline evaluation metrics for RAG regression suites."""

from __future__ import annotations

from dataclasses import dataclass

from enterprise_rag.core.models import Answer, RetrievalHit


@dataclass(frozen=True)
class RetrievalExpectation:
    query: str
    expected_document_ids: frozenset[str]


@dataclass(frozen=True)
class PageCitationExpectation:
    query: str
    expected_page: int
    document_id: str | None = None


@dataclass(frozen=True)
class EvaluationReport:
    retrieval_recall_at_k: float
    citation_coverage: float
    grounded_rate: float
    page_citation_accuracy: float = 0.0
    faithfulness_rate: float = 0.0


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
        """Share of answers that include at least one *used* citation (no spoof)."""
        if not answers:
            return 0.0
        return sum(1 for answer in answers if answer.citations) / len(answers)

    @staticmethod
    def grounded_rate(answers: tuple[Answer, ...]) -> float:
        if not answers:
            return 0.0
        return sum(1 for answer in answers if answer.grounded) / len(answers)

    @staticmethod
    def page_citation_accuracy(
        expectations: tuple[PageCitationExpectation, ...], answers: tuple[Answer, ...]
    ) -> float:
        if not expectations:
            return 0.0
        hits = 0
        for exp, answer in zip(expectations, answers, strict=True):
            pages = {c.page for c in answer.citations if c.page is not None}
            ok_doc = True
            if exp.document_id:
                ok_doc = any(c.document_id == exp.document_id for c in answer.citations)
            if exp.expected_page in pages and ok_doc:
                hits += 1
        return hits / len(expectations)

    @staticmethod
    def faithfulness_rate(answers: tuple[Answer, ...]) -> float:
        if not answers:
            return 0.0
        return sum(
            1 for a in answers if "faithfulness_failed" not in a.risk_flags and a.grounded
        ) / len(answers)
