"""HTTP contract tests for PDF ingest + rate limit (Top-1% Phase 1/4)."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from enterprise_rag.api.app import app
from enterprise_rag.api.rate_limit import SlidingWindowRateLimiter

client = TestClient(app)


def test_rate_limiter_blocks_after_limit():
    lim = SlidingWindowRateLimiter(limit=2, window_seconds=60.0)
    assert lim.allow("a")
    assert lim.allow("a")
    assert not lim.allow("a")


def test_ingest_pdf_text_layer(monkeypatch):
    pytest.importorskip("fitz")
    monkeypatch.delenv("RAG_API_KEY", raising=False)
    monkeypatch.setenv("RAG_RATE_LIMIT_ENABLED", "false")
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "The mandatory rotation period for API keys is 90 days.")
    data = doc.tobytes()
    doc.close()
    resp = client.post(
        "/v1/ingest/pdf",
        files={"file": ("policy.pdf", io.BytesIO(data), "application/pdf")},
        data={
            "document_id": "pdf-http-1",
            "title": "Policy",
            "tenant_id": "acme",
            "owner": "demo",
            "groups": "engineering",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chunks_added"] >= 1
    assert body["pdf"]["page_count"] >= 1
    assert any(row.get("page_start") == 1 for row in body["lineage"])


def test_ingest_pdf_empty_returns_ocr_required(monkeypatch):
    pytest.importorskip("fitz")
    monkeypatch.delenv("RAG_API_KEY", raising=False)
    monkeypatch.setenv("RAG_RATE_LIMIT_ENABLED", "false")
    monkeypatch.delenv("RAG_OCR_ENABLED", raising=False)
    import fitz

    doc = fitz.open()
    doc.new_page()  # blank — no text
    data = doc.tobytes()
    doc.close()
    resp = client.post(
        "/v1/ingest/pdf",
        files={"file": ("blank.pdf", io.BytesIO(data), "application/pdf")},
        data={
            "document_id": "pdf-blank-1",
            "title": "Blank",
            "tenant_id": "acme",
            "owner": "demo",
            "groups": "engineering",
        },
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    codes = {d.get("code") for d in detail} if isinstance(detail, list) else set()
    assert "ocr_required" in codes


def test_answer_rate_limit_429(monkeypatch):
    monkeypatch.delenv("RAG_API_KEY", raising=False)
    monkeypatch.setenv("RAG_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RAG_RATE_LIMIT_PER_MIN", "2")
    import enterprise_rag.api.rate_limit as rl

    rl._limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60.0)
    body = {
        "query": "What is hybrid retrieval?",
        "tenant_id": "acme",
        "user_id": "rate-limit-user",
        "groups": ["engineering"],
    }
    assert client.post("/v1/answer", json=body).status_code == 200
    assert client.post("/v1/answer", json=body).status_code == 200
    assert client.post("/v1/answer", json=body).status_code == 429
