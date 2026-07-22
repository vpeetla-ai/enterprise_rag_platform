#!/usr/bin/env python3
"""Mint a short-lived HS256 JWT for Enterprise RAG Strict panel demos (ADR-0006).

Never commit the secret. Set RAG_JWT_SECRET to the same value as the Strict Render service.

Example:
  export RAG_JWT_SECRET='…'
  python3 scripts/mint_panel_jwt.py | tee /tmp/erag_jwt.txt
  TOKEN=$(cat /tmp/erag_jwt.txt)
  curl -sS https://enterprise-rag-api-strict.onrender.com/health | python3 -m json.tool
  curl -sS -X POST https://enterprise-rag-api-strict.onrender.com/v1/answer \\
    -H "Authorization: Bearer $TOKEN" \\
    -H "Content-Type: application/json" \\
    -H "X-API-Key: $RAG_API_KEY" \\
    -d '{"query":"What is the mandatory API key rotation period at Zephyr Corporation?","tenant_id":"spoof","user_id":"spoof","groups":["executives"],"mode":"hybrid"}'
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from enterprise_rag.api.principal_auth import issue_hs256_token  # noqa: E402


def main() -> int:
    secret = os.environ.get("RAG_JWT_SECRET", "").strip()
    if not secret:
        print("Set RAG_JWT_SECRET (must match Strict Render service).", file=sys.stderr)
        return 2
    now = int(time.time())
    claims = {
        "sub": os.environ.get("PANEL_SUB", "panel-reviewer"),
        "tenant_id": os.environ.get("PANEL_TENANT", "acme"),
        "groups": ["engineering", "ai-platform"],
        "clearance": os.environ.get("PANEL_CLEARANCE", "internal"),
        "iat": now,
        "exp": now + int(os.environ.get("PANEL_TTL_SEC", "900")),
    }
    print(issue_hs256_token(claims, secret=secret))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
