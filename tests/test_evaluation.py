from __future__ import annotations

import unittest
from datetime import UTC, datetime

from enterprise_rag.core.ingestion import DocumentChunker
from enterprise_rag.core.models import Classification, Principal, RetrievalQuery, SourceDocument
from enterprise_rag.core.pipeline import RagPipeline
from enterprise_rag.core.retrieval import InMemoryHybridRetriever
from enterprise_rag.eval.metrics import EvaluationEngine, RetrievalExpectation


class EvaluationTests(unittest.TestCase):
    def test_retrieval_recall_and_grounding_metrics(self) -> None:
        document = SourceDocument(
            document_id="doc-1",
            tenant_id="acme",
            title="RAG Evaluation",
            body="Evaluation measures retrieval quality, citation coverage, and grounded answer quality.",
            uri="https://docs.example/eval",
            owner="quality",
            classification=Classification.INTERNAL,
            allowed_groups=frozenset({"engineering"}),
            metadata={"effective_date": "2026-01-01"},
            updated_at=datetime.now(UTC),
        )
        chunks = DocumentChunker(max_words=50, overlap_words=5).chunk(document).chunks
        principal = Principal("u1", "acme", frozenset({"engineering"}), Classification.INTERNAL)
        query = RetrievalQuery("What does evaluation measure?", "acme", principal)
        retriever = InMemoryHybridRetriever(chunks)
        hits = retriever.search(query)
        answer = RagPipeline(retriever).answer(query)
        engine = EvaluationEngine()

        recall = engine.retrieval_recall(
            (RetrievalExpectation(query.query, frozenset({"doc-1"})),),
            (hits,),
        )

        self.assertEqual(recall, 1.0)
        self.assertEqual(engine.citation_coverage((answer,)), 1.0)
        self.assertEqual(engine.grounded_rate((answer,)), 1.0)


if __name__ == "__main__":
    unittest.main()
