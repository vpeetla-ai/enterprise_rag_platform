# ADR 0002: Enforce Access Before Ranking

## Status

Accepted

## Context

If unauthorized chunks are retrieved and only filtered after generation, sensitive data may leak into prompts, logs, traces, model providers, or generated answers.

## Decision

The retrieval layer enforces tenant, group, and classification checks before ranking and context assembly.

## Consequences

- Unauthorized chunks never enter prompt context.
- Index adapters must support reliable metadata filtering or tenant-level isolation.
- Audit logs must preserve which access policy was applied.
