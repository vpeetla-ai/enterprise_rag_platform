# ADR 0009: Strict ingest principal binding

## Status

Accepted

## Context

ADR-0006 verifies Principal on retrieve/answer under `PRODUCTION_STRICT`. Ingest still accepted body `tenant_id` / `groups`, enabling cross-tenant corpus poisoning.

## Decision

Under `PRODUCTION_STRICT`, `/v1/ingest` and `/v1/ingest/pdf` call `resolve_principal` and derive `tenant_id` (and default groups when body groups omitted) from JWT claims. Body spoof of tenant is ignored.

JWT verification requires `exp` (and rejects expired tokens). Panel mint TTL defaults to ≤1 hour.

## Consequences

- Demo mode unchanged (body Principal).
- Operators must mint JWTs with `exp` for Strict ingest and answer.
