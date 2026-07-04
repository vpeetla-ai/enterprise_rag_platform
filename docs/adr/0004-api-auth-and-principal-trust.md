# ADR 0004: API-Key Gate, and the Untrusted-Principal Gap in ADR-0002

## Status

Accepted (partial — principal verification is a follow-up)

## Context

`/v1/ingest`, `/v1/retrieve`, and `/v1/answer` (`src/enterprise_rag/api/app.py`) had no caller
authentication at all — anyone could write documents into the corpus or trigger a retrieval/
answer pipeline run. This matches a pattern found and fixed in 4 other org repos this session.

But this repo's finding goes a layer deeper. ADR-0002 ("Enforce Access Before Ranking")
guarantees that "unauthorized chunks never enter prompt context" — that guarantee only holds
if the `Principal` (`tenant_id`, `user_id`, `groups`, `clearance`) it enforces against is
itself trustworthy. Today it isn't: `QueryRequest` and `IngestRequest` take these fields
directly from the request body with no signature, session, or token behind them. A caller can
set `"clearance": "top_secret", "groups": ["executives"]` in plain JSON and
`core/access.py`'s enforcement will grant access accordingly — the access-before-ranking
architecture is real and correctly implemented, but the identity it's checking is whatever the
caller says it is. This wasn't disclosed anywhere (checked `docs/risk-register.md`, `README.md`,
`docs/ARCHITECTURE.md` — the risk register's "Unauthorized content retrieved into prompt" row
lists "pre-ranking tenant, group, and classification enforcement" as the mitigation without
noting that enforcement currently trusts an unverified identity).

## Decision

1. **`RAG_API_KEY` gate** on all three POST routes (`_require_api_key` in `api/app.py`),
   enforced only when set — restricts who can call the API at all, same pattern as the other
   4 fixes this session.
2. **Document the untrusted-principal gap explicitly** rather than silently building a full
   identity-verification layer: `QueryRequest`/`IngestRequest` now carry docstrings stating
   these fields are client-asserted, and a new risk-register row makes the gap visible where
   ADR-0002's guarantee is stated. This is a reference implementation demonstrating the access-
   before-ranking *pattern* — it has no existing user directory or session system to hook a
   real JWT/OIDC verification layer into, so building one is a distinct, larger follow-up
   decision (which identity provider, how tenants map to it), not a same-pass fix.

## Consequences

### Positive
- Closes the "anyone can write to the corpus or run retrieval for free" gap.
- ADR-0002's guarantee is now honestly scoped in writing: it holds *given* a trustworthy
  Principal, and today nothing supplies one.
- Risk register accurately reflects the org's own documentation-honesty standard instead of
  silently overstating the access-control story.

### Negative
- `RAG_API_KEY` does not solve principal-spoofing — an authenticated caller (anyone with the
  API key) can still claim to be any tenant/user/clearance level. This is the more significant
  residual risk of the two.
- No production deployment of this reference architecture should go live without adding real
  identity verification (JWT/OIDC claims → Principal), which this ADR does not implement.

### Follow-ups
- ADR-0005 (proposed): derive `Principal` from verified JWT/OIDC claims instead of the request
  body — needs a decision on identity provider and tenant-claim mapping before implementation.

## References
- `src/enterprise_rag/api/app.py::_require_api_key`, `QueryRequest`, `IngestRequest`
- `src/enterprise_rag/core/access.py` (the enforcement this ADR does not change)
- Same auth-gate pattern: [loop-engine-agent-platform ADR-002](https://github.com/vpeetla-ai/loop-engine-agent-platform/blob/main/docs/ADR-002-repo-fix-auth-and-isolation.md), [sentinel-brief ADR-0002](https://github.com/vpeetla-ai/sentinel-brief/blob/main/docs/adr/0002-runs-auth-and-llm-synthesis.md), [aegisai ADR-0003](https://github.com/vpeetla-ai/aegisai-enterprise-agent-platform/blob/main/adr/0003-orchestrator-auth-gate.md), [VAP ADR-009](https://github.com/vpeetla-ai/ai-architecture-portfolio/blob/main/adr/ADR-009-vap-auth-gate.md)
