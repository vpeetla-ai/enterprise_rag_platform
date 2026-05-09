from __future__ import annotations

import unittest
from datetime import UTC, datetime

from enterprise_rag.core.ingestion import DocumentChunker
from enterprise_rag.core.models import Classification, Principal, RetrievalQuery, SourceDocument
from enterprise_rag.core.pipeline import RagPipeline
from enterprise_rag.core.retrieval import InMemoryHybridRetriever


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


class PipelineTests(unittest.TestCase):
    def test_pipeline_returns_grounded_cited_answer(self) -> None:
        document = make_document(
            "doc-1",
            "Production RAG requires hybrid retrieval, grounded citations, access control, and evaluation.",
        )
        chunks = DocumentChunker(max_words=60, overlap_words=5).chunk(document).chunks
        principal = Principal("u1", "acme", frozenset({"engineering"}), Classification.INTERNAL)
        pipeline = RagPipeline(InMemoryHybridRetriever(chunks))

        answer = pipeline.answer(RetrievalQuery("Why does production RAG need evaluation?", "acme", principal))

        self.assertTrue(answer.grounded)
        self.assertEqual(answer.risk_flags, ())
        self.assertEqual(answer.citations[0].document_id, "doc-1")

    def test_retrieval_filters_unauthorized_chunks_before_answering(self) -> None:
        allowed = make_document("allowed", "Hybrid retrieval improves enterprise RAG quality.")
        restricted = make_document(
            "restricted",
            "Secret merger plan and confidential account update.",
            groups=frozenset({"executives"}),
            classification=Classification.RESTRICTED,
        )
        chunker = DocumentChunker(max_words=60, overlap_words=5)
        chunks = chunker.chunk(allowed).chunks + chunker.chunk(restricted).chunks
        principal = Principal("u1", "acme", frozenset({"engineering"}), Classification.INTERNAL)
        retriever = InMemoryHybridRetriever(chunks)

        hits = retriever.search(RetrievalQuery("confidential account update", "acme", principal))

        self.assertEqual(hits, ())

    def test_guardrails_redact_sensitive_input_and_flag_approval(self) -> None:
        document = make_document(
            "doc-1",
            "Account changes require human approval for destructive workflows.",
        )
        chunks = DocumentChunker(max_words=60, overlap_words=5).chunk(document).chunks
        principal = Principal("u1", "acme", frozenset({"engineering"}), Classification.INTERNAL)
        pipeline = RagPipeline(InMemoryHybridRetriever(chunks))

        answer = pipeline.answer(
            RetrievalQuery("Delete account for jane@example.com", "acme", principal)
        )

        self.assertIn("sensitive_input_redacted", answer.risk_flags)
        self.assertIn("human_approval_required", answer.risk_flags)


if __name__ == "__main__":
    unittest.main()
