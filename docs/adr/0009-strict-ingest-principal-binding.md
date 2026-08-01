# ADR 0009: Strict ingest principal binding

## Status

Accepted

## In one breath (panel)

I'd bind ingest tenant/groups from JWT under Strict — leaving body `tenant_id` writable after verify-on-retrieve was an open door for cross-tenant corpus poisoning.

## Context

ADR-0006 verifies Principal on retrieve/answer under `PRODUCTION_STRICT`. Ingest still took body `tenant_id` / `groups`. That's how you poison another tenant's corpus while looking authenticated.

What I refused: half-Strict — hard on read, soft on write.

## Decision

Under `PRODUCTION_STRICT`, `/v1/ingest` and `/v1/ingest/pdf` call `resolve_principal` and derive `tenant_id` (and default groups when omitted) from JWT claims. Body tenant spoof is ignored.

JWT requires `exp`; expired tokens reject. Panel mint TTL defaults to ≤1 hour.

**Demo:** unchanged body Principal.

## Consequences

- Demo mode unchanged
- Operators must mint JWTs with `exp` for Strict ingest and answer
- Closes the write-side half of the ADR-0004 identity scar
