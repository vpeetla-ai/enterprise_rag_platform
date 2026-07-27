"""Tests for HITL hard-gate, document replace/delete, and citation-span faithfulness."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from enterprise_rag.api.app import app
from enterprise_rag.api.principal_auth import issue_hs256_token
from enterprise_rag.core.context import AssembledContext
from enterprise_rag.core.guardrails import GuardrailService
from enterprise_rag.core.ingestion import DocumentChunker
from enterprise_rag.core.models import Citation, Classification, SourceDocument
from enterprise_rag.core.retrieval import InMemoryHybridRetriever

client = TestClient(app)


def test_hitl_hard_gate_withholds_answer(monkeypatch):
    monkeypatch.delenv("PRODUCTION_STRICT", raising=False)
    monkeypatch.delenv("RAG_API_KEY", raising=False)
    monkeypatch.setenv("HITL_HARD_GATE", "true")
    monkeypatch.delenv("AEGISAI_API_BASE_URL", raising=False)
    resp = client.post(
        "/v1/answer",
        json={
            "query": "Please delete the customer account immediately",
            "tenant_id": "acme",
            "user_id": "u1",
            "groups": ["engineering"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["pending_approval"] is True
    assert body["answer"] == ""
    assert "hitl_pending" in body["risk_flags"]


def test_document_replace_does_not_duplicate(monkeypatch):
    monkeypatch.delenv("RAG_API_KEY", raising=False)
    monkeypatch.setenv("RAG_RATE_LIMIT_ENABLED", "false")
    doc_id = f"replace-{int(time.time())}"
    payload = {
        "tenant_id": "acme",
        "document_id": doc_id,
        "title": "Replace Me",
        "body": "First version of the document with enough content for the ingest gate to pass.",
        "uri": "https://example.internal/replace",
        "owner": "demo",
        "groups": ["engineering"],
        "metadata": {"effective_date": "2026-01-01"},
    }
    r1 = client.post("/v1/ingest", json=payload)
    assert r1.status_code == 200
    n1 = r1.json()["chunks_added"]
    payload["body"] = (
        "Second version of the document with enough content for the ingest gate to pass cleanly."
    )
    r2 = client.post("/v1/ingest", json=payload)
    assert r2.status_code == 200
    # Replace path should not grow unboundedly vs first ingest
    assert r2.json()["chunks_added"] <= n1 + 2


def test_delete_document_endpoint(monkeypatch):
    monkeypatch.delenv("RAG_API_KEY", raising=False)
    monkeypatch.setenv("RAG_RATE_LIMIT_ENABLED", "false")
    doc_id = f"delete-me-{int(time.time())}"
    ingest = client.post(
        "/v1/ingest",
        json={
            "tenant_id": "acme",
            "document_id": doc_id,
            "title": "Delete Me",
            "body": "Document scheduled for deletion with enough content for ingest validation.",
            "uri": "https://example.internal/delete-me",
            "owner": "demo",
            "groups": ["engineering"],
            "metadata": {"effective_date": "2026-01-01"},
        },
    )
    assert ingest.status_code == 200
    deleted = client.delete(f"/v1/documents/{doc_id}", params={"tenant_id": "acme"})
    assert deleted.status_code == 200
    assert deleted.json()["chunks_removed"] >= 1


def test_memory_delete_document_unit():
    doc = SourceDocument(
        document_id="d1",
        tenant_id="acme",
        title="T",
        body="Enough content here for chunking a single window of text about API keys.",
        uri="u",
        owner="o",
        classification=Classification.INTERNAL,
        allowed_groups=frozenset({"engineering"}),
        metadata={},
        updated_at=datetime.now(UTC),
    )
    chunks = DocumentChunker(max_words=40, overlap_words=5).chunk(doc).chunks
    retriever = InMemoryHybridRetriever(chunks)
    assert len(retriever._chunks) >= 1
    removed = retriever.delete_document(document_id="d1", tenant_id="acme")
    assert removed >= 1
    assert len(retriever._chunks) == 0


def test_citation_span_faithfulness_rejects_unsupported_claim():
    ctx = AssembledContext(
        query="q",
        context="[S1] Policy\nURI: u\nThe mandatory rotation period for API keys is 90 days.",
        citations=(
            Citation(
                citation_id="S1",
                document_id="d1",
                title="Policy",
                uri="u",
                owner="o",
                updated_at=datetime.now(UTC),
                page=2,
                snippet="The mandatory rotation period for API keys is 90 days.",
            ),
        ),
        token_estimate=40,
        retrieval_trace={},
    )
    guard = GuardrailService()
    bad = guard.validate_output(
        "Zephyr will wire one million dollars to offshore accounts tomorrow. [S1]",
        ctx,
    )
    assert "faithfulness_failed" in bad.risk_flags
    assert bad.grounded is False

    good = guard.validate_output(
        "The mandatory rotation period for API keys is 90 days. [S1]",
        ctx,
    )
    assert "faithfulness_failed" not in good.risk_flags
    assert good.grounded is True


def test_strict_hitl_pending_with_jwt(monkeypatch):
    monkeypatch.setenv("PRODUCTION_STRICT", "true")
    monkeypatch.setenv("RAG_JWT_SECRET", "test-secret")
    monkeypatch.setenv("RAG_API_KEY", "test-key")
    monkeypatch.delenv("AEGISAI_API_BASE_URL", raising=False)
    now = int(time.time())
    token = issue_hs256_token(
        {
            "sub": "u1",
            "tenant_id": "acme",
            "groups": ["engineering"],
            "iat": now,
            "exp": now + 900,
        },
        secret="test-secret",
    )
    resp = client.post(
        "/v1/answer",
        json={
            "query": "Please refund the customer and terminate the account",
            "tenant_id": "spoof",
            "user_id": "spoof",
            "groups": ["executives"],
        },
        headers={"Authorization": f"Bearer {token}", "X-API-Key": "test-key"},
    )
    assert resp.status_code == 200
    assert resp.json()["pending_approval"] is True
    assert resp.json()["answer"] == ""
