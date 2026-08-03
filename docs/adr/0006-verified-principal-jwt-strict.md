# ADR 0006: Verified Principal under PRODUCTION_STRICT (HS256 JWT)

## Status

Accepted — 2026-07-09

## In one breath (panel)

I'd derive Principal from a signed JWT under Strict and ignore body identity fields — Demo can keep body Principal as long as we label the lie.

## Context

[ADR-0004](./0004-api-auth-and-principal-trust.md) documented client-asserted Principal. Org ADR-024 defines `PRODUCTION_STRICT` as the fail-closed honesty profile. Portfolio demos still need a path without Auth0/Clerk.

What I refused: claiming access-before-ranking was "done" while still trusting JSON clearance claims on the public demo posture.

## Decision

1. Dependency-light HS256 JWT helpers in `enterprise_rag.api.principal_auth`.
2. When `PRODUCTION_STRICT=true`: require `Authorization: Bearer <jwt>` with `RAG_JWT_SECRET`; derive Principal from claims; **ignore** body identity for access.
3. When unset: keep Demo body-Principal behavior.

| Claim | Principal field |
|-------|-----------------|
| `sub` (or `user_id`) | `user_id` |
| `tenant_id` (or `tid`) | `tenant_id` |
| `groups` / `roles` | `groups` |
| `clearance` | `clearance` |

**Alternatives deferred:** full OIDC/JWKS (external IdP); mTLS service accounts.

## Consequences

- Strict closes Principal spoof on retrieve/answer when secret + JWT are set
- Ingest ACL metadata binding tightened in ADR-0009
- Operators need **both** `PRODUCTION_STRICT` and `RAG_JWT_SECRET` or APIs return 503/401 — no silent fallback to Demo identity under Strict

## Related

- Org [ADR-024](https://github.com/vpeetla-ai/ai-architecture-portfolio/blob/main/adr/ADR-024-production-strict-fail-closed.md)
- `src/enterprise_rag/api/principal_auth.py`
