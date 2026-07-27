"""PRODUCTION_STRICT Principal JWT anti-spoof tests (ADR-0006/0009)."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from enterprise_rag.api.app import app
from enterprise_rag.api.principal_auth import issue_hs256_token

client = TestClient(app)

QUERY_BODY = {
    "query": "What does the security policy say?",
    "tenant_id": "spoof-tenant",
    "user_id": "spoof-user",
    "groups": ["executives"],
    "clearance": "restricted",
}


def _token(claims: dict, secret: str = "test-secret") -> str:
    now = int(time.time())
    body = {"iat": now, "exp": now + 900, **claims}
    return issue_hs256_token(body, secret=secret)


def test_demo_mode_still_accepts_body_principal(monkeypatch):
    monkeypatch.delenv("PRODUCTION_STRICT", raising=False)
    monkeypatch.delenv("RAG_API_KEY", raising=False)
    resp = client.post("/v1/retrieve", json=QUERY_BODY)
    assert resp.status_code == 200
    assert resp.json().get("principal_source") == "request_body"


def test_health_exposes_review_mode(monkeypatch):
    monkeypatch.delenv("PRODUCTION_STRICT", raising=False)
    health = client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["review_mode"] == "demo"
    assert body["principal_source"] == "request_body"
    assert body["production_strict"] is False
    assert body["retrieval"]["fusion"] == "rrf"

    monkeypatch.setenv("PRODUCTION_STRICT", "true")
    monkeypatch.setenv("RAG_JWT_SECRET", "test-secret")
    strict = client.get("/health").json()
    assert strict["review_mode"] == "strict"
    assert strict["principal_source"] == "jwt"
    assert strict["production_strict"] is True


def test_strict_requires_bearer(monkeypatch):
    monkeypatch.setenv("PRODUCTION_STRICT", "true")
    monkeypatch.setenv("RAG_JWT_SECRET", "test-secret")
    monkeypatch.delenv("RAG_API_KEY", raising=False)
    resp = client.post("/v1/retrieve", json=QUERY_BODY)
    assert resp.status_code == 401


def test_strict_requires_secret(monkeypatch):
    monkeypatch.setenv("PRODUCTION_STRICT", "true")
    monkeypatch.delenv("RAG_JWT_SECRET", raising=False)
    monkeypatch.delenv("RAG_API_KEY", raising=False)
    token = _token(
        {"sub": "u1", "tenant_id": "acme", "groups": ["engineering"], "clearance": "internal"},
        secret="unused",
    )
    resp = client.post(
        "/v1/retrieve",
        json=QUERY_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 503


def test_strict_uses_jwt_not_body_spoof(monkeypatch):
    monkeypatch.setenv("PRODUCTION_STRICT", "true")
    monkeypatch.setenv("RAG_JWT_SECRET", "test-secret")
    monkeypatch.delenv("RAG_API_KEY", raising=False)
    token = _token(
        {
            "sub": "real-user",
            "tenant_id": "acme",
            "groups": ["engineering"],
            "clearance": "internal",
        }
    )
    resp = client.post(
        "/v1/retrieve",
        json=QUERY_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["principal_source"] == "jwt"


def test_strict_rejects_bad_signature(monkeypatch):
    monkeypatch.setenv("PRODUCTION_STRICT", "true")
    monkeypatch.setenv("RAG_JWT_SECRET", "test-secret")
    monkeypatch.delenv("RAG_API_KEY", raising=False)
    token = _token({"sub": "u1", "tenant_id": "acme", "groups": ["engineering"]}, secret="wrong-secret")
    resp = client.post(
        "/v1/retrieve",
        json=QUERY_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


def test_strict_rejects_expired_token(monkeypatch):
    monkeypatch.setenv("PRODUCTION_STRICT", "true")
    monkeypatch.setenv("RAG_JWT_SECRET", "test-secret")
    monkeypatch.delenv("RAG_API_KEY", raising=False)
    now = int(time.time())
    token = issue_hs256_token(
        {
            "sub": "u1",
            "tenant_id": "acme",
            "groups": ["engineering"],
            "iat": now - 3600,
            "exp": now - 10,
        },
        secret="test-secret",
    )
    resp = client.post(
        "/v1/retrieve",
        json=QUERY_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


def test_strict_ingest_binds_tenant(monkeypatch):
    monkeypatch.setenv("PRODUCTION_STRICT", "true")
    monkeypatch.setenv("RAG_JWT_SECRET", "test-secret")
    monkeypatch.delenv("RAG_API_KEY", raising=False)
    token = _token(
        {"sub": "writer", "tenant_id": "acme", "groups": ["engineering"], "clearance": "internal"}
    )
    resp = client.post(
        "/v1/ingest",
        json={
            "tenant_id": "evil-tenant",
            "document_id": f"strict-ingest-{int(time.time())}",
            "title": "Strict Ingest Doc",
            "body": "This document is long enough to pass the low content gate for ingest tests.",
            "uri": "https://example.internal/strict-ingest",
            "owner": "writer",
            "groups": ["engineering"],
            "metadata": {"effective_date": "2026-01-01"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == "acme"
    assert resp.json()["principal_source"] == "jwt"
