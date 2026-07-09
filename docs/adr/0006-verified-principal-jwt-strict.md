# ADR 0006: Verified Principal under PRODUCTION_STRICT (HS256 JWT)

## Status

Accepted — 2026-07-09

## Context

[ADR-0004](./0004-api-auth-and-principal-trust.md) documented that `Principal` fields on
`/v1/retrieve` and `/v1/answer` are client-asserted. Org ADR-024 introduces
`PRODUCTION_STRICT` as the honesty profile for fail-closed behavior.

## Decision

1. Add `enterprise_rag.api.principal_auth` with dependency-free **HS256 JWT** verify/issue helpers.
2. When `PRODUCTION_STRICT=true`:
   - Require `Authorization: Bearer <jwt>` signed with `RAG_JWT_SECRET`
   - Derive `Principal` from claims (`sub`, `tenant_id`, `groups`, `clearance`)
   - **Ignore** body identity fields for access decisions (anti-spoof)
3. When `PRODUCTION_STRICT` is unset: keep demo body-Principal behavior (unchanged).

Claim mapping:

| Claim | Principal field |
|-------|-----------------|
| `sub` (or `user_id`) | `user_id` |
| `tenant_id` (or `tid`) | `tenant_id` |
| `groups` / `roles` | `groups` |
| `clearance` | `clearance` (Classification enum) |

## Alternatives

- Full OIDC / JWKS against Auth0/Clerk — deferred; portfolio demos need zero external IdP.
- mTLS service accounts — out of scope for the demo API.

## Consequences

- Strict mode closes Principal spoof for retrieve/answer when secret + JWT are configured.
- Ingest still uses body tenant/groups for document ACL metadata (separate trust boundary;
  future ADR may require JWT for ingest writers too).
- Operators must set **both** `PRODUCTION_STRICT` and `RAG_JWT_SECRET` or APIs return 503/401.

## Related

- Org [ADR-024](https://github.com/vpeetla-ai/ai-architecture-portfolio/blob/main/adr/ADR-024-production-strict-fail-closed.md)
- Risk register Principal row
- `src/enterprise_rag/api/principal_auth.py`
