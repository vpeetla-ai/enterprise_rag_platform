#!/usr/bin/env python3
"""Smoke-test ingest + all 3 RAG strategies against live API."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

API = "https://enterprise-rag-api-4el1.onrender.com"
QUERY = "What is the mandatory API key rotation period at Zephyr Corporation?"

STRATEGIES = [
    ("Regular RAG", {"mode": "keyword", "rerank": False, "agentic": False}),
    ("Hybrid RAG", {"mode": "hybrid", "rerank": True, "agentic": False}),
    ("Agentic RAG", {"mode": "hybrid", "rerank": True, "agentic": True}),
]


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read())


def main() -> int:
    health = json.loads(urllib.request.urlopen(f"{API}/health", timeout=60).read())
    print("health:", health)

    ingest = post(
        "/v1/ingest",
        {
            "tenant_id": "acme",
            "document_id": "test-zephyr-policy-smoke",
            "title": "Zephyr Cloud Security Policy",
            "body": (
                "Zephyr Corporation requires all production deployments to pass AegisAI gateway approval. "
                "The mandatory rotation period for API keys is 90 days."
            ),
            "uri": "upload://zephyr-policy.txt",
            "owner": "demo-user",
            "groups": ["engineering", "ai-platform"],
        },
    )
    print("ingest:", ingest)

    ok = True
    for label, opts in STRATEGIES:
        data = post(
            "/v1/answer",
            {
                "query": QUERY,
                "tenant_id": "acme",
                "user_id": "demo-user",
                "groups": ["engineering", "ai-platform"],
                **opts,
            },
        )
        cites = [c["title"] for c in data.get("citations", [])]
        spans = [e["name"] for e in data.get("trace", [])]
        has_zephyr = any("Zephyr" in c for c in cites)
        has_90 = "90" in data.get("answer", "")
        passed = has_zephyr and has_90
        ok = ok and passed
        print(f"\n=== {label} ===")
        print("answer:", data.get("answer", "")[:160])
        print("citations:", cites)
        print("trace:", " → ".join(spans))
        print("PASS" if passed else "FAIL")

    return 0 if ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise SystemExit(1)
