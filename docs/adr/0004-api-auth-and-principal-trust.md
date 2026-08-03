# ADR 0004: API-Key Gate, and the Untrusted-Principal Gap in ADR-0002

## Status

Accepted (partial — principal verification followed in ADR-0006/0009)

## In one breath (panel)

I'd lock the write/retrieve/answer routes behind an API key first, and I'd say out loud that access-before-ranking still trusted whatever Principal the caller typed — that was the real scar.

## Context

`/v1/ingest`, `/v1/retrieve`, and `/v1/answer` had no caller auth — anyone could poison the corpus or burn a pipeline run. Same hole we'd closed in other org repos.

Deeper scar: ADR-0002 promises unauthorized chunks never enter context. That only holds if `Principal` is trustworthy. Here `tenant_id` / `groups` / `clearance` came from the JSON body — spoof `"clearance": "top_secret"` and enforcement dutifully opens the door. The pattern was real; the identity was theater. Risk register didn't say so.

What I refused: silently shipping a full IdP in the same pass, or leaving the spoof gap undocumented.

## Decision

1. **`RAG_API_KEY` gate** on the three POSTs when set — who may call the API at all.
2. **Document the untrusted-Principal gap** — docstrings + risk-register row. This is a reference pattern repo without a user directory; JWT/OIDC is a separate decision (done under Strict in ADR-0006/0009).

**Demo vs Strict:** Demo = API key optional + body Principal. Strict = verified JWT Principal (later ADRs).

## Consequences

### Positive

- Closes anonymous write/retrieve
- ADR-0002's guarantee is honestly scoped in writing

### Negative

- API key ≠ anti-spoof — authenticated callers could still claim any tenant until Strict JWT
- No production deploy of this pattern should go live on body Principal alone

### Follow-ups

- Done: ADR-0006 / ADR-0009 — JWT Principal under `PRODUCTION_STRICT`

## References

- `src/enterprise_rag/api/app.py::_require_api_key`, `QueryRequest`, `IngestRequest`
- `src/enterprise_rag/core/access.py`
- Same auth-gate pattern: [aegisai ADR-0003](https://github.com/vpeetla-ai/aegisai-enterprise-agent-platform/blob/main/adr/0003-orchestrator-auth-gate.md), [VAP ADR-009](https://github.com/vpeetla-ai/ai-architecture-portfolio/blob/main/adr/ADR-009-vap-auth-gate.md)
