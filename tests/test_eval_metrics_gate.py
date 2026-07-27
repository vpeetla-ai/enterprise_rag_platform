"""CI gate: page-citation accuracy + faithfulness metrics (Top-1% DoD #5)."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from enterprise_rag.core.ingestion import DocumentChunker
from enterprise_rag.core.models import (
    Answer,
    Citation,
    Classification,
    Principal,
    RetrievalQuery,
    SourceDocument,
)
from enterprise_rag.core.pipeline import RagPipeline
from enterprise_rag.core.retrieval import InMemoryHybridRetriever
from enterprise_rag.eval.metrics import EvaluationEngine, PageCitationExpectation, RetrievalExpectation


class EvalMetricsGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = SourceDocument(
            document_id="policy-pages",
            tenant_id="acme",
            title="Policy",
            body="",
            uri="upload://policy.pdf",
            owner="security",
            classification=Classification.INTERNAL,
            allowed_groups=frozenset({"engineering"}),
            metadata={},
            updated_at=datetime.now(UTC),
            pages=(
                (1, "Introduction and scope for Zephyr Cloud."),
                (2, "The mandatory rotation period for API keys is 90 days."),
                (3, "Incident response contacts are listed in appendix A."),
            ),
        )
        chunks = DocumentChunker(max_words=40, overlap_words=5).chunk(self.document).chunks
        self.retriever = InMemoryHybridRetriever(chunks)
        self.principal = Principal(
            "u1", "acme", frozenset({"engineering"}), Classification.INTERNAL
        )
        self.pipeline = RagPipeline(self.retriever)

    def test_page_citation_accuracy_and_faithfulness_gate(self) -> None:
        query = RetrievalQuery(
            "What is the mandatory rotation period for API keys?",
            "acme",
            self.principal,
        )
        answer = self.pipeline.answer(query)
        engine = EvaluationEngine()
        page_acc = engine.page_citation_accuracy(
            (
                PageCitationExpectation(
                    query=query.query, expected_page=2, document_id="policy-pages"
                ),
            ),
            (answer,),
        )
        faith = engine.faithfulness_rate((answer,))
        self.assertGreaterEqual(page_acc, 1.0, msg=f"page_acc={page_acc} answer={answer}")
        self.assertGreaterEqual(faith, 1.0, msg=f"faith={faith} flags={answer.risk_flags}")
        self.assertTrue(answer.grounded)
        self.assertTrue(any(c.page == 2 for c in answer.citations))

    def test_paraphrase_retrieval_recall(self) -> None:
        """Dense+RRF path must find the planted page fact under paraphrase (not only exact terms)."""
        query = RetrievalQuery(
            "How often must we rotate production API credentials?",
            "acme",
            self.principal,
        )
        hits = self.retriever.search(query)
        engine = EvaluationEngine()
        recall = engine.retrieval_recall(
            (RetrievalExpectation(query.query, frozenset({"policy-pages"})),),
            (hits,),
        )
        self.assertGreaterEqual(recall, 1.0)
        self.assertTrue(any(h.chunk.page_start == 2 for h in hits))

    def test_faithfulness_rate_penalizes_failed_flag(self) -> None:
        bad = Answer(
            answer="Invented claim",
            citations=(
                Citation(
                    citation_id="S1",
                    document_id="policy-pages",
                    title="Policy",
                    uri="u",
                    owner="o",
                    updated_at=datetime.now(UTC),
                    page=2,
                ),
            ),
            grounded=False,
            risk_flags=("faithfulness_failed",),
        )
        self.assertEqual(EvaluationEngine.faithfulness_rate((bad,)), 0.0)


if __name__ == "__main__":
    unittest.main()
