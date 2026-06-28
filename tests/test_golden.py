from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from pathlib import Path

from enterprise_rag.core.ingestion import DocumentChunker
from enterprise_rag.core.models import Classification, Principal, RetrievalQuery, SourceDocument
from enterprise_rag.core.pipeline import RagPipeline
from enterprise_rag.core.reranker import ScoreBoostReranker
from enterprise_rag.core.retrieval import InMemoryHybridRetriever
from enterprise_rag.ops.telemetry import EventRecorder

FIXTURES = Path(__file__).parent / "fixtures" / "golden_queries.json"


def make_document(
    document_id: str,
    body: str,
    groups: frozenset[str] = frozenset({"engineering"}),
    classification: Classification = Classification.INTERNAL,
) -> SourceDocument:
    return SourceDocument(
        document_id=document_id,
        tenant_id="acme",
        title=f"Document {document_id}",
        body=body,
        uri=f"https://docs.example/{document_id}",
        owner="knowledge-team",
        classification=classification,
        allowed_groups=groups,
        metadata={"effective_date": "2026-01-01", "domain": "ai"},
        updated_at=datetime.now(UTC),
    )


class GoldenQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        policy = make_document(
            "policy-001",
            (
                "Production RAG requires hybrid retrieval, grounded citations, access control, "
                "evaluation, and human approval for high-risk actions."
            ),
        )
        chunks = DocumentChunker(max_words=60, overlap_words=5).chunk(policy).chunks
        cls.pipeline = RagPipeline(InMemoryHybridRetriever(chunks), reranker=ScoreBoostReranker())

    def test_golden_queries(self) -> None:
        principal = Principal("u1", "acme", frozenset({"engineering"}), Classification.INTERNAL)
        cases = json.loads(FIXTURES.read_text())
        for case in cases:
            with self.subTest(query=case["query"]):
                answer = self.pipeline.answer(
                    RetrievalQuery(case["query"], case["tenant_id"], principal)
                )
                if case.get("expect_grounded"):
                    self.assertTrue(answer.grounded)
                if case.get("expect_document_id"):
                    self.assertEqual(answer.citations[0].document_id, case["expect_document_id"])
                for flag in case.get("expect_risk_flags", []):
                    self.assertIn(flag, answer.risk_flags)


class TelemetryTests(unittest.TestCase):
    def test_pipeline_emits_spans(self) -> None:
        document = make_document("doc-telemetry", "Telemetry spans record retrieve and generate stages.")
        chunks = DocumentChunker(max_words=60, overlap_words=5).chunk(document).chunks
        recorder = EventRecorder()
        pipeline = RagPipeline(InMemoryHybridRetriever(chunks), recorder=recorder)
        principal = Principal("u1", "acme", frozenset({"engineering"}), Classification.INTERNAL)
        pipeline.answer(RetrievalQuery("telemetry spans", "acme", principal))
        names = [event["name"] for event in recorder.events]
        self.assertIn("rag.answer", names)
        self.assertIn("rag.retrieve", names)
        self.assertIn("rag.generate", names)


class IngestTests(unittest.TestCase):
    def test_retriever_upsert_extends_corpus(self) -> None:
        retriever = InMemoryHybridRetriever(())
        document = make_document("new-doc", "Upsert adds chunks to the in-memory index.")
        chunks = DocumentChunker(max_words=60, overlap_words=5).chunk(document).chunks
        added = retriever.upsert(chunks)
        self.assertEqual(added, len(chunks))
        principal = Principal("u1", "acme", frozenset({"engineering"}), Classification.INTERNAL)
        hits = retriever.search(RetrievalQuery("upsert in-memory index", "acme", principal))
        self.assertTrue(hits)


if __name__ == "__main__":
    unittest.main()
