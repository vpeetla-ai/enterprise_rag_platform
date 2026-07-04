"""Tests for the RAG_API_KEY gate on /v1/ingest, /v1/retrieve, /v1/answer.

These previously had zero caller authentication — see docs/adr/0004-api-auth-and-principal-trust.md.
Note this gate only restricts who can call the API at all; it does not verify the
Principal (tenant_id/groups/clearance) claimed inside the request body, which remains
client-asserted by design in this reference implementation.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from enterprise_rag.api.app import app

client = TestClient(app)

QUERY_BODY = {
    "query": "What does the security policy say?",
    "tenant_id": "acme",
    "user_id": "u1",
    "groups": ["engineering"],
}

INGEST_BODY = {
    "tenant_id": "acme",
    "document_id": "doc-1",
    "title": "Test doc",
    "body": "Some body text",
    "uri": "https://example.internal/doc-1",
    "owner": "test-owner",
}


def test_retrieve_open_when_no_api_key_set(monkeypatch):
    monkeypatch.delenv("RAG_API_KEY", raising=False)
    resp = client.post("/v1/retrieve", json=QUERY_BODY)
    assert resp.status_code == 200


def test_retrieve_rejects_missing_key_when_required(monkeypatch):
    monkeypatch.setenv("RAG_API_KEY", "secret-key")
    resp = client.post("/v1/retrieve", json=QUERY_BODY)
    assert resp.status_code == 401


def test_retrieve_accepts_correct_key(monkeypatch):
    monkeypatch.setenv("RAG_API_KEY", "secret-key")
    resp = client.post("/v1/retrieve", json=QUERY_BODY, headers={"X-API-Key": "secret-key"})
    assert resp.status_code == 200


def test_retrieve_rejects_wrong_key(monkeypatch):
    monkeypatch.setenv("RAG_API_KEY", "secret-key")
    resp = client.post("/v1/retrieve", json=QUERY_BODY, headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_ingest_rejects_missing_key_when_required(monkeypatch):
    monkeypatch.setenv("RAG_API_KEY", "secret-key")
    resp = client.post("/v1/ingest", json=INGEST_BODY)
    assert resp.status_code == 401


def test_answer_rejects_missing_key_when_required(monkeypatch):
    monkeypatch.setenv("RAG_API_KEY", "secret-key")
    resp = client.post("/v1/answer", json=QUERY_BODY)
    assert resp.status_code == 401


def test_health_stays_open_regardless_of_key(monkeypatch):
    monkeypatch.setenv("RAG_API_KEY", "secret-key")
    resp = client.get("/health")
    assert resp.status_code == 200
