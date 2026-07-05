"""Tests for the ingestion data contract and lineage metadata (Phase D).

Previously `DocumentChunker._validate()` computed `IngestionIssue`s that the
`/v1/ingest` route silently discarded — a document with no owner, no lineage
URI, or near-empty content was accepted anyway. This closes that gap: hard
issues now reject ingestion (422), and every chunk carries a real
content_hash + ingested_at, not just an id derived from a hash.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from enterprise_rag.api.app import app
from enterprise_rag.core.ingestion import DocumentChunker
from enterprise_rag.core.models import Classification, SourceDocument

client = TestClient(app)

VALID_INGEST_BODY = {
    "tenant_id": "acme",
    "document_id": "contract-doc-1",
    "title": "Contract test doc",
    "body": "Production RAG requires hybrid retrieval, grounded citations, access control, and evaluation before shipping any answer to a real user.",
    "uri": "https://example.internal/contract-doc-1",
    "owner": "test-owner",
    "metadata": {"effective_date": "2026-01-01"},
}


def _document(**overrides) -> SourceDocument:
    fields = dict(
        document_id="doc-1",
        tenant_id="acme",
        title="Doc",
        body="Production RAG requires hybrid retrieval, grounded citations, access control, and evaluation.",
        uri="https://example.internal/doc-1",
        owner="owner",
        classification=Classification.INTERNAL,
        allowed_groups=frozenset({"engineering"}),
        metadata={"effective_date": "2026-01-01"},
    )
    fields.update(overrides)
    return SourceDocument(**fields)


def test_chunk_carries_a_real_content_hash():
    result = DocumentChunker(max_words=80, overlap_words=10).chunk(_document())
    assert result.chunks
    for chunk in result.chunks:
        assert len(chunk.content_hash) == 64  # full sha256 hex digest


def test_content_hash_is_stable_for_identical_text_across_reingestion():
    first = DocumentChunker(max_words=80, overlap_words=10).chunk(_document())
    second = DocumentChunker(max_words=80, overlap_words=10).chunk(_document())
    assert [c.content_hash for c in first.chunks] == [c.content_hash for c in second.chunks]


def test_content_hash_differs_when_text_changes():
    first = DocumentChunker(max_words=80, overlap_words=10).chunk(_document())
    second = DocumentChunker(max_words=80, overlap_words=10).chunk(
        _document(body="Completely different content that shares no words with the original at all.")
    )
    assert first.chunks[0].content_hash != second.chunks[0].content_hash


def test_ingested_at_is_set_to_a_real_recent_timestamp():
    before = datetime.now(UTC)
    result = DocumentChunker(max_words=80, overlap_words=10).chunk(_document())
    after = datetime.now(UTC)
    for chunk in result.chunks:
        assert before <= chunk.ingested_at <= after


def test_missing_owner_is_a_blocking_issue():
    result = DocumentChunker(max_words=80, overlap_words=10).chunk(_document(owner=""))
    codes = {issue.code for issue in result.blocking_issues}
    assert "missing_owner" in codes


def test_missing_uri_is_a_blocking_issue():
    result = DocumentChunker(max_words=80, overlap_words=10).chunk(_document(uri=""))
    codes = {issue.code for issue in result.blocking_issues}
    assert "missing_lineage" in codes


def test_missing_freshness_metadata_is_not_blocking():
    result = DocumentChunker(max_words=80, overlap_words=10).chunk(_document(metadata={}))
    codes = {issue.code for issue in result.blocking_issues}
    assert "missing_freshness_metadata" not in codes
    all_codes = {issue.code for issue in result.issues}
    assert "missing_freshness_metadata" in all_codes


def test_api_ingest_rejects_document_with_no_owner(monkeypatch):
    monkeypatch.delenv("RAG_API_KEY", raising=False)
    body = dict(VALID_INGEST_BODY, document_id="contract-doc-reject-1", owner="")
    resp = client.post("/v1/ingest", json=body)
    assert resp.status_code == 422
    assert any(issue["code"] == "missing_owner" for issue in resp.json()["detail"])


def test_api_ingest_accepts_valid_document_and_returns_lineage(monkeypatch):
    monkeypatch.delenv("RAG_API_KEY", raising=False)
    body = dict(VALID_INGEST_BODY, document_id="contract-doc-accept-1")
    resp = client.post("/v1/ingest", json=body)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["chunks_added"] > 0
    assert payload["lineage"]
    for entry in payload["lineage"]:
        assert len(entry["content_hash"]) == 64
        assert entry["ingested_at"]
