"""Page-aware ingest and citation tests (ADR-0007 / Phase 1)."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from enterprise_rag.core.ingestion import DocumentChunker
from enterprise_rag.core.models import Classification, Principal, RetrievalQuery, SourceDocument
from enterprise_rag.core.pipeline import RagPipeline
from enterprise_rag.core.retrieval import InMemoryHybridRetriever, rrf_fuse


class PageIngestTests(unittest.TestCase):
    def test_page_chunker_preserves_page_numbers(self) -> None:
        doc = SourceDocument(
            document_id="pdf-1",
            tenant_id="acme",
            title="Multi Page Policy",
            body="ignored when pages set",
            uri="upload://policy.pdf",
            owner="demo",
            classification=Classification.INTERNAL,
            allowed_groups=frozenset({"engineering"}),
            metadata={"source": "test"},
            updated_at=datetime.now(UTC),
            pages=(
                (1, "Introduction and scope for Zephyr Corporation security controls."),
                (2, "The mandatory rotation period for API keys is 90 days per policy."),
                (3, "Appendix with contact information for the security team."),
            ),
        )
        result = DocumentChunker(max_words=40, overlap_words=5).chunk(doc)
        self.assertFalse(result.blocking_issues)
        pages = {c.page_start for c in result.chunks}
        self.assertIn(1, pages)
        self.assertIn(2, pages)
        self.assertIn(3, pages)
        page2 = [c for c in result.chunks if c.page_start == 2]
        self.assertTrue(any("90 days" in c.text for c in page2))

    def test_answer_cites_correct_page(self) -> None:
        doc = SourceDocument(
            document_id="pdf-zephyr",
            tenant_id="acme",
            title="Zephyr Cloud Security Policy",
            body="",
            uri="upload://zephyr.pdf",
            owner="demo",
            classification=Classification.INTERNAL,
            allowed_groups=frozenset({"engineering"}),
            metadata={"source": "test"},
            updated_at=datetime.now(UTC),
            pages=(
                (1, "Gateway approval is required before customer notifications are sent."),
                (2, "The mandatory rotation period for API keys is 90 days."),
                (3, "Restricted documents always require human approval."),
            ),
        )
        chunks = DocumentChunker(max_words=40, overlap_words=5).chunk(doc).chunks
        pipeline = RagPipeline(InMemoryHybridRetriever(chunks))
        principal = Principal("u1", "acme", frozenset({"engineering"}), Classification.INTERNAL)
        answer = pipeline.answer(
            RetrievalQuery(
                "What is the mandatory API key rotation period?",
                "acme",
                principal,
            )
        )
        self.assertTrue(answer.grounded)
        self.assertTrue(answer.citations)
        self.assertTrue(any(c.page == 2 for c in answer.citations))

    def test_rrf_fuse_prefers_shared_ranks(self) -> None:
        scores = rrf_fuse([["a", "b", "c"], ["b", "a", "d"]])
        self.assertGreater(scores["b"], scores["c"])
        self.assertGreater(scores["a"], scores["d"])

    def test_no_citation_spoof_when_missing_markers(self) -> None:
        from enterprise_rag.core.context import ContextAssembler
        from enterprise_rag.core.guardrails import GuardrailService
        from enterprise_rag.core.models import Chunk, RetrievalHit

        chunk = Chunk(
            chunk_id="c1",
            document_id="d1",
            tenant_id="acme",
            text="The mandatory rotation period for API keys is 90 days.",
            source_title="Policy",
            source_uri="u",
            owner="o",
            classification=Classification.INTERNAL,
            allowed_groups=frozenset({"engineering"}),
            metadata={},
            updated_at=datetime.now(UTC),
            page_start=2,
            page_end=2,
        )
        ctx = ContextAssembler().assemble("q", (RetrievalHit(chunk, 1.0, ("bm25",)),))
        out = GuardrailService().validate_output("No markers here about keys.", ctx)
        self.assertEqual(out.citations, ())
        self.assertIn("missing_citation", out.risk_flags)


if __name__ == "__main__":
    unittest.main()
