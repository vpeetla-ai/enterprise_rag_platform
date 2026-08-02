"""Observability status — public compose-plane honesty."""

from __future__ import annotations

from fastapi.testclient import TestClient

from enterprise_rag.api.app import app

client = TestClient(app)


def test_observability_status_shape():
    resp = client.get("/v1/observability/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "source_of_truth" in body
    assert "exporters" in body
    assert "planes" in body
    assert "recommendation" in body
    planes = body["planes"]
    assert planes["access_before_ranking"] is True
    assert planes["retriever_backend"] in {"memory", "qdrant"}
    assert planes["corpus_of_record"] == planes["retriever_backend"]
    names = {e["name"] for e in body["exporters"]}
    assert "OpsMetrics" in names
    assert "Langfuse" in names


def test_observability_status_public_under_strict(monkeypatch):
    monkeypatch.setenv("PRODUCTION_STRICT", "true")
    monkeypatch.setenv("RAG_API_KEY", "test-key")
    assert client.get("/v1/observability/status").status_code == 200
    assert client.get("/v1/ops/metrics").status_code == 401
    assert client.get("/v1/ops/metrics", headers={"X-API-Key": "test-key"}).status_code == 200
