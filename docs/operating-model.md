# Operating Model

## Ownership

| Capability | Primary Owner | Supporting Teams |
| --- | --- | --- |
| Retrieval strategy | AI Platform | Domain SMEs, Search Platform |
| Source quality and lineage | Data Governance | Content Owners |
| Access policy | Security Architecture | IAM, Legal |
| Prompt and context releases | AI Platform | Product, Risk |
| Evaluation datasets | Quality Engineering | Domain SMEs |
| Runtime operations | Platform Operations | SRE, FinOps |

## Release Gates

1. Ingestion changes must pass document quality checks and lineage validation.
2. Retrieval changes must improve or hold retrieval recall on golden datasets.
3. Prompt/context changes must pass grounding and citation regression tests.
4. Model changes must pass safety, latency, and cost budgets.
5. New high-risk workflow actions must include human approval and audit trails.

## Incident Response

- Severity 1: unauthorized data exposure, regulated decision error, or external customer harm.
- Severity 2: material hallucination in business-critical internal workflow.
- Severity 3: degraded retrieval quality, elevated latency, or abnormal cost trend.

Every incident should capture query, principal, retrieval hits, citations, prompt version, model version, guardrail flags, latency, token usage, and user feedback.
