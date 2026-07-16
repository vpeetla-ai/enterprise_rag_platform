window.ARCHITECT_CONFIG = {
  tagline:
    "Glass-box RAG: access-before-ranking stays visible while pipeline spans replay from /v1/answer.",
  metricsUrl: (window.ENTERPRISE_RAG_API || "") + "/v1/ops/metrics",
  metricsPath: "/v1/ops/metrics",
  metricLabels: { runs: "Queries + answers", entities: "Indexed chunks", latency: "P95 latency" },
  layers: [
    { tier: "L1", name: "Experience", role: "Governed Q&A demo", components: ["Static Vercel UI", "Ingest + ask", "Citations panel"] },
    { tier: "L2", name: "RAG pipeline", role: "Hybrid + agentic modes", components: ["Access filter", "Rerank", "Graph expand"] },
    { tier: "L3", name: "Governance bridge", role: "High-risk answer gate", components: ["AegisAI authorize", "Decline threshold", "HITL flags"] },
    { tier: "L4", name: "Ops", role: "Eval + export", components: ["Golden eval CI", "Langfuse export", "/v1/ops/metrics"] },
  ],
  tradeoffs: [
    { decision: "Access-before-ranking", gain: "No leaked chunks across clearance levels", trade: "Extra filter pass vs pure vector search" },
    { decision: "In-memory retriever on Render free tier", gain: "Zero infra cost for portfolio demos", trade: "Corpus resets on cold start — re-ingest" },
    { decision: "Decline below confidence threshold", gain: "Safer answers under uncertainty", trade: "More 'no answer' UX vs always-generate" },
    { decision: "Optional Qdrant backend", gain: "Production-scale vector store path", trade: "Another service to operate vs memory mode" },
  ],
  adrLinks: [
    { title: "ADR-004 — API auth and principal trust", href: "https://github.com/vpeetla-ai/enterprise_rag_platform/blob/main/docs/adr/0004-api-auth-and-principal-trust.md" },
    { title: "Case study — Enterprise RAG", href: "https://github.com/vpeetla-ai/ai-architecture-portfolio/blob/main/case-studies/enterprise-rag-platform.md" },
  ],
  docsLinks: [
    { title: "SLO targets", href: "https://github.com/vpeetla-ai/enterprise_rag_platform/blob/main/docs/SLO.md" },
    { title: "Architecture", href: "https://github.com/vpeetla-ai/enterprise_rag_platform/blob/main/docs/ARCHITECTURE.md" },
  ],
};
