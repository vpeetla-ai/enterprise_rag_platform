# ADR 0002: Enforce Access Before Ranking

## Status

Accepted

## In one breath (panel)

I'd filter by who the caller is *before* I rank — optimizing recall with unauthorized neighbors is how demos look smart and prod leaks.

## Context

If unauthorized chunks enter retrieval and you only scrub after generation, secrets still hit prompts, logs, traces, and model providers. Post-generation filtering is theater.

What I refused: "retrieve everything, authorize in the prompt" multi-tenant soft isolation.

## Decision

The retrieval layer enforces tenant, group, and classification checks **before** ranking and context assembly.

**Honesty:** this guarantee holds *given* a trustworthy Principal. Early on Principals were client-asserted (ADR-0004 scar). Strict mode binds JWT claims (ADR-0006/0009). Demo still allows body Principal — labeled, not sold as production identity.

## Consequences

- Unauthorized chunks never enter prompt context (when Principal is real)
- Index adapters must support reliable metadata filters or tenant isolation
- Audit must record which access policy applied
