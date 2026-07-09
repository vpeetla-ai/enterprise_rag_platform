"""Verified Principal from JWT (ADR-0006 / org ADR-024 PRODUCTION_STRICT).

Demo mode (default): request-body Principal remains allowed (documented spoof risk).
PRODUCTION_STRICT=true: Authorization Bearer JWT is required; body tenant/groups/clearance
are ignored for access decisions.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from typing import Any

from enterprise_rag.core.models import Classification, Principal

try:
    from fastapi import HTTPException
except ImportError:  # pragma: no cover
    HTTPException = Exception  # type: ignore[misc,assignment]


def production_strict() -> bool:
    return os.getenv("PRODUCTION_STRICT", "").strip().lower() in {"1", "true", "yes", "on"}


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def issue_hs256_token(claims: dict[str, Any], *, secret: str) -> str:
    """Test/demo helper — issue a signed HS256 JWT (no third-party dependency)."""
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url_encode(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode()
    sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url_encode(sig)}"


def verify_hs256_token(token: str, *, secret: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("invalid_jwt_format")
    header_b64, payload_b64, sig_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    actual = _b64url_decode(sig_b64)
    if not hmac.compare_digest(expected, actual):
        raise ValueError("invalid_jwt_signature")
    header = json.loads(_b64url_decode(header_b64))
    if header.get("alg") != "HS256":
        raise ValueError("unsupported_jwt_alg")
    return json.loads(_b64url_decode(payload_b64))


def _clearance_from_claim(value: Any) -> Classification:
    if isinstance(value, Classification):
        return value
    raw = str(value or "internal").strip().lower()
    try:
        return Classification(raw)
    except ValueError as exc:
        raise ValueError(f"invalid_clearance:{raw}") from exc


def principal_from_claims(claims: dict[str, Any]) -> Principal:
    user_id = str(claims.get("sub") or claims.get("user_id") or "").strip()
    tenant_id = str(claims.get("tenant_id") or claims.get("tid") or "").strip()
    groups_raw = claims.get("groups") or claims.get("roles") or []
    if isinstance(groups_raw, str):
        groups = frozenset(g.strip() for g in groups_raw.split(",") if g.strip())
    else:
        groups = frozenset(str(g) for g in groups_raw)
    if not user_id or not tenant_id:
        raise ValueError("jwt_missing_sub_or_tenant")
    clearance = _clearance_from_claim(claims.get("clearance", "internal"))
    return Principal(user_id=user_id, tenant_id=tenant_id, groups=groups, clearance=clearance)


def resolve_principal(
    *,
    authorization: str | None,
    body_user_id: str,
    body_tenant_id: str,
    body_groups: list[str],
    body_clearance: Classification,
) -> Principal:
    """Resolve Principal for retrieve/answer.

    - Demo: body fields (client-asserted).
    - PRODUCTION_STRICT: Bearer JWT with RAG_JWT_SECRET; body identity ignored.
    """
    if not production_strict():
        return Principal(
            user_id=body_user_id,
            tenant_id=body_tenant_id,
            groups=frozenset(body_groups),
            clearance=body_clearance,
        )

    secret = os.getenv("RAG_JWT_SECRET", "").strip()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="PRODUCTION_STRICT requires RAG_JWT_SECRET",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer JWT required under PRODUCTION_STRICT")
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = verify_hs256_token(token, secret=secret)
        return principal_from_claims(claims)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=f"invalid_principal_token:{exc}") from exc
