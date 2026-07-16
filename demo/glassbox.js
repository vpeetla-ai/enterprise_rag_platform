/**
 * Enterprise RAG glass-box — architecture rail (left), pipeline replay (center), product UX (right).
 * Trace replay from POST /v1/answer events (not SSE).
 */
(function (global) {
  const NODE_MAP = {
    "rag.guardrails.input": "guard-in",
    "rag.retrieve": "retrieve",
    "rag.graph_expand": "graph",
    "rag.rerank": "rerank",
    "rag.assemble": "assemble",
    "rag.generate": "generate",
    "rag.guardrails.output": "guard-out",
    "rag.decline": "decline",
  };

  const PILL_STEPS = [
    { id: "access", label: "Access", color: "var(--gb-node-access)" },
    { id: "retrieve", label: "Retrieve", color: "var(--gb-node-retrieve)" },
    { id: "graph", label: "Graph", color: "var(--gb-node-graph)" },
    { id: "rerank", label: "Rerank", color: "var(--gb-node-rerank)" },
    { id: "generate", label: "Generate", color: "var(--gb-node-generate)" },
    { id: "guard-out", label: "Guard", color: "var(--gb-node-guard)" },
  ];

  const DEMO_TRACE = [
    { name: "rag.guardrails.input", attributes: { status: "ok" }, duration_ms: 2 },
    { name: "rag.retrieve", attributes: { mode: "hybrid", status: "ok" }, duration_ms: 18 },
    { name: "rag.rerank", attributes: { status: "ok" }, duration_ms: 12 },
    { name: "rag.assemble", attributes: { hit_count: 3, status: "ok" }, duration_ms: 4 },
    { name: "rag.generate", attributes: { status: "ok" }, duration_ms: 8 },
    { name: "rag.guardrails.output", attributes: { status: "ok" }, duration_ms: 3 },
  ];

  const DEMO_ANSWER = {
    answer:
      "[demo_fallback] The mandatory rotation period for API keys is 90 days. [S1]",
    grounded: true,
    declined: false,
    risk_flags: [],
    citations: [
      {
        title: "Zephyr Cloud Security Policy",
        uri: "upload://zephyr-policy.txt",
      },
    ],
    trace: DEMO_TRACE,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function cfg() {
    return global.ARCHITECT_CONFIG || {};
  }

  function totalMs(trace) {
    if (!trace?.length) return null;
    const sum = trace.reduce((a, e) => a + (Number(e.duration_ms) || 0), 0);
    return sum > 0 ? Math.round(sum) : null;
  }

  function renderArchRail() {
    const stack = $("gbStack");
    if (!stack) return;
    const layers = cfg().layers || [];
    stack.innerHTML = layers
      .map(
        (l) =>
          `<div class="gb-stack-layer">
            <div class="gb-stack-tier">${l.tier}</div>
            <div class="gb-stack-name">${l.name}</div>
            <div class="gb-stack-role">${l.role}</div>
          </div>`
      )
      .join("");

    const trade = $("gbTradeoffs");
    if (trade) {
      const items = (cfg().tradeoffs || []).slice(0, 2);
      trade.innerHTML = items
        .map(
          (t) =>
            `<div class="gb-tradeoff"><strong>${t.decision}</strong><p>${t.gain}</p></div>`
        )
        .join("");
    }

    const links = $("gbAdrLinks");
    if (links) {
      const all = [].concat(cfg().adrLinks || [], cfg().docsLinks || []).slice(0, 4);
      links.innerHTML = all
        .map((l) => `<li><a href="${l.href}" target="_blank" rel="noopener">${l.title} →</a></li>`)
        .join("");
    }
  }

  function normalizeMetrics(data) {
    return {
      total_runs: data.total_runs ?? data.query_count ?? data.sample_size ?? 0,
      success_rate_pct: data.success_rate_pct ?? 100 - (data.failure_rate_pct || 0),
      p95_latency_ms: data.p95_latency_ms ?? data.p95_ms ?? null,
      active_entities: data.active_entities ?? data.indexed_chunks ?? data.chunk_count ?? 0,
    };
  }

  function renderMetrics(data) {
    const slot = $("gbMetrics");
    if (!slot) return;
    const labels = cfg().metricLabels || {};
    const m = normalizeMetrics(data);
    slot.innerHTML = `
      <div class="gb-metric"><span>${labels.runs || "Queries"}</span><strong>${m.total_runs}</strong></div>
      <div class="gb-metric"><span>Success</span><strong>${m.success_rate_pct}%</strong></div>
      <div class="gb-metric"><span>${labels.latency || "P95"}</span><strong>${m.p95_latency_ms != null ? m.p95_latency_ms + "ms" : "—"}</strong></div>
      <div class="gb-metric"><span>${labels.entities || "Chunks"}</span><strong>${m.active_entities}</strong></div>`;
  }

  function renderMetricsFailed() {
    const slot = $("gbMetrics");
    if (!slot) return;
    slot.innerHTML = `<div class="gb-metrics-failed">
      <p class="muted">Metrics waking (~30s cold start)…</p>
      <button type="button" class="secondary" id="gbMetricsRetry">Retry</button>
    </div>`;
    $("gbMetricsRetry")?.addEventListener("click", loadMetrics);
  }

  function loadMetrics() {
    const url = cfg().metricsUrl;
    const slot = $("gbMetrics");
    if (!slot) return;
    if (!url) {
      slot.innerHTML = '<p class="muted">No metrics URL.</p>';
      return;
    }
    slot.innerHTML = '<p class="muted">Loading…</p>';
    fetch(url, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(renderMetrics)
      .catch(renderMetricsFailed);
  }

  function renderPills() {
    const wrap = $("gbPills");
    if (!wrap) return;
    wrap.innerHTML = PILL_STEPS.map(
      (s, i) =>
        `${i ? '<span class="gb-pill-arrow">→</span>' : ""}<span class="gb-pill" id="gb-pill-${s.id}" style="--pill-color:${s.color}">${s.label}</span>`
    ).join("");
  }

  function resetDiagram(strategy) {
    document.querySelectorAll(".gb-node").forEach((n) => {
      n.classList.remove("gb-active", "gb-done", "gb-skipped");
    });
    PILL_STEPS.forEach((s) => {
      const pill = $("gb-pill-" + s.id);
      if (pill) pill.classList.remove("gb-active", "gb-done");
    });
    const graph = $("gb-node-graph");
    const rerank = $("gb-node-rerank");
    if (graph) graph.classList.toggle("gb-skipped", !strategy?.agentic);
    if (rerank) rerank.classList.toggle("gb-skipped", !strategy?.rerank);
    const gate = $("gbGate");
    if (gate) {
      gate.classList.remove("decline");
      gate.textContent = "Access-before-ranking — principal groups filter chunks before hybrid scores.";
    }
    const log = $("gbEventLog");
    if (log) log.textContent = "";
    setSourceBadge(null);
  }

  function setSourceBadge(mode) {
    const el = $("gbSource");
    if (!el) return;
    el.classList.remove("live", "fallback");
    if (mode === "live") {
      el.textContent = "live trace";
      el.classList.add("live");
    } else if (mode === "fallback") {
      el.textContent = "demo_fallback";
      el.classList.add("fallback");
    } else {
      el.textContent = "awaiting run";
    }
  }

  function markNode(nodeId, state) {
    const node = $("gb-node-" + nodeId);
    if (node) {
      node.classList.remove("gb-active", "gb-done");
      if (state) node.classList.add(state);
    }
    const pillId =
      nodeId === "guard-in" || nodeId === "access"
        ? "access"
        : nodeId === "guard-out"
          ? "guard-out"
          : nodeId === "decline"
            ? null
            : nodeId;
    if (pillId) {
      const pill = $("gb-pill-" + pillId);
      if (pill) {
        pill.classList.remove("gb-active", "gb-done");
        if (state) pill.classList.add(state);
      }
    }
  }

  function setGate(text, declined) {
    const gate = $("gbGate");
    if (!gate) return;
    gate.textContent = text;
    gate.classList.toggle("decline", !!declined);
  }

  function appendEvent(ev) {
    const log = $("gbEventLog");
    if (!log) return;
    const ms = ev.duration_ms != null ? ` ${ev.duration_ms}ms` : "";
    const line = document.createElement("div");
    line.className = "ev-live";
    line.textContent = `▸ ${ev.name}${ms}`;
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
  }

  function gateMessage(ev) {
    const attrs = ev.attributes || {};
    if (ev.name === "rag.retrieve") {
      const mode = attrs.mode || "hybrid";
      return `Retrieve (${mode}) — access filter applied before ranking.`;
    }
    if (ev.name === "rag.graph_expand") {
      return `Graph expand — ${attrs.hit_count ?? "?"} seed hits → neighbor chunks.`;
    }
    if (ev.name === "rag.rerank") return "Cross-encoder rerank — reordering authorized hits.";
    if (ev.name === "rag.decline") {
      return `Decline gate — top score ${attrs.top_score ?? "?"} below threshold ${attrs.threshold ?? "?"}.`;
    }
    if (ev.name === "rag.generate") return "Grounded generation from assembled context.";
    if (ev.name === "rag.guardrails.output") return "Output guardrails — citations + risk flags attached.";
    return ev.name.replace("rag.", "");
  }

  function playTrace(trace, strategy, opts) {
    const events = Array.isArray(trace) ? trace : [];
    const stepMs = opts?.stepMs ?? 340;
    let i = 0;

    function step() {
      if (i >= events.length) {
        setOps(events, opts?.data);
        return;
      }
      const ev = events[i];
      const nodeId = NODE_MAP[ev.name];
      if (nodeId) {
        if (i > 0) {
          const prev = NODE_MAP[events[i - 1].name];
          if (prev) markNode(prev, "gb-done");
        }
        markNode(nodeId, "gb-active");
        if (ev.name === "rag.retrieve") markNode("access", "gb-done");
      }
      setGate(gateMessage(ev), ev.name === "rag.decline");
      appendEvent(ev);
      i += 1;
      setTimeout(step, stepMs);
    }

    resetDiagram(strategy);
    if (!events.length) {
      setGate("No trace events in response.", false);
      return;
    }
    step();
  }

  function setOps(trace, data) {
    const el = $("gbOps");
    if (!el) return;
    const ms = totalMs(trace);
    const spans = (trace || []).map((e) => e.name).filter(Boolean);
    el.innerHTML = [
      `<span><strong>spans</strong> ${spans.length}</span>`,
      `<span><strong>latency</strong> ${ms != null ? ms + " ms" : "n/a"}</span>`,
      `<span><strong>grounded</strong> ${data?.grounded ? "yes" : "no"}</span>`,
      data?.declined ? `<span><strong>declined</strong> yes</span>` : "",
    ]
      .filter(Boolean)
      .join("");
  }

  function onAnswer(data, strategy, source) {
    setSourceBadge(source === "fallback" ? "fallback" : "live");
    playTrace(data.trace || [], strategy, { data, stepMs: source === "fallback" ? 280 : 340 });
    loadMetrics();
  }

  function showRunning() {
    setSourceBadge(null);
    resetDiagram(global.GlassBox?.lastStrategy);
    setGate("Calling /v1/answer — pipeline trace will replay when response returns.", false);
    const log = $("gbEventLog");
    if (log) log.textContent = "waiting for API…";
  }

  function init() {
    renderArchRail();
    renderPills();
    loadMetrics();
  }

  global.GlassBox = {
    init,
    resetDiagram,
    onAnswer,
    showRunning,
    demoAnswer: DEMO_ANSWER,
    lastStrategy: null,
    setStrategy(s) {
      this.lastStrategy = s;
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})(window);
