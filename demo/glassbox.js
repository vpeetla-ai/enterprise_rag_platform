/**
 * Enterprise RAG glass-box — architecture rail (left), pipeline replay (center), product UX (right).
 * Trace replay from POST /v1/answer events (not SSE).
 *
 * Severity (honest):
 * - Green  gb-done     = live authenticated span completed
 * - Amber  gb-fallback = demo_fallback / degraded replay (not live)
 * - Red    gb-error    = hard failure at this stage (API auth, decline)
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
    "rag.faithfulness": "guard-out",
    "rag.decline": "decline",
  };

  const PILL_STEPS = [
    { id: "api", label: "API", color: "var(--vp-danger)" },
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
    risk_flags: ["demo_fallback"],
    citations: [
      {
        title: "Zephyr Cloud Security Policy",
        uri: "upload://zephyr-policy.txt",
        page: 2,
      },
    ],
    trace: DEMO_TRACE,
  };
  // DEMO_ANSWER must NEVER be used on a successful live /v1/answer path.
  // app.js may use it only when the API is unreachable / unauthorized.

  const NODE_STATES = ["gb-active", "gb-done", "gb-fallback", "gb-error"];

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

  function clearNodeStates(el) {
    if (!el) return;
    NODE_STATES.forEach((c) => el.classList.remove(c));
  }

  function resetDiagram(strategy) {
    document.querySelectorAll(".gb-node").forEach((n) => {
      clearNodeStates(n);
      n.classList.remove("gb-skipped");
    });
    PILL_STEPS.forEach((s) => clearNodeStates($("gb-pill-" + s.id)));
    const graph = $("gb-node-graph");
    const rerank = $("gb-node-rerank");
    if (graph) graph.classList.toggle("gb-skipped", !strategy?.agentic);
    if (rerank) rerank.classList.toggle("gb-skipped", !strategy?.rerank);
    const gate = $("gbGate");
    if (gate) {
      gate.classList.remove("decline", "is-error", "is-fallback");
      gate.textContent = "Access-before-ranking — principal groups filter chunks before hybrid scores.";
    }
    const log = $("gbEventLog");
    if (log) log.textContent = "";
    setSourceBadge(null);
    const center = document.querySelector(".gb-center");
    if (center) center.classList.remove("is-fallback-mode", "is-error-mode");
  }

  function setSourceBadge(mode) {
    const el = $("gbSource");
    if (!el) return;
    el.classList.remove("live", "fallback", "error");
    if (mode === "live") {
      el.textContent = "live trace";
      el.classList.add("live");
    } else if (mode === "fallback") {
      el.textContent = "demo_fallback";
      el.classList.add("fallback");
    } else if (mode === "error") {
      el.textContent = "API failed";
      el.classList.add("error");
    } else {
      el.textContent = "awaiting run";
    }
  }

  function markNode(nodeId, state) {
    const node = $("gb-node-" + nodeId);
    if (node) {
      clearNodeStates(node);
      if (state) node.classList.add(state);
    }
    const pillId =
      nodeId === "api"
        ? "api"
        : nodeId === "guard-in" || nodeId === "access"
          ? "access"
          : nodeId === "guard-out"
            ? "guard-out"
            : nodeId === "decline"
              ? null
              : nodeId;
    if (pillId) {
      const pill = $("gb-pill-" + pillId);
      if (pill) {
        clearNodeStates(pill);
        if (state) pill.classList.add(state);
      }
    }
  }

  /** @param {string} text @param {{declined?:boolean, fallback?:boolean, error?:boolean}} [opts] */
  function setGate(text, opts) {
    const gate = $("gbGate");
    if (!gate) return;
    const o = typeof opts === "boolean" ? { declined: opts } : opts || {};
    gate.textContent = text;
    gate.classList.toggle("decline", !!o.declined);
    gate.classList.toggle("is-error", !!o.error);
    gate.classList.toggle("is-fallback", !!o.fallback && !o.error && !o.declined);
  }

  function appendEvent(ev, tone) {
    const log = $("gbEventLog");
    if (!log) return;
    const ms = ev.duration_ms != null ? ` ${ev.duration_ms}ms` : "";
    const line = document.createElement("div");
    line.className = tone === "fallback" ? "ev-fallback" : tone === "error" ? "ev-error" : "ev-live";
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
    const isFallback = opts?.source === "fallback";
    const doneClass = isFallback ? "gb-fallback" : "gb-done";
    let i = 0;

    function step() {
      if (i >= events.length) {
        // Finalize last active node
        if (events.length) {
          const last = NODE_MAP[events[events.length - 1].name];
          if (last) markNode(last, doneClass);
        }
        if (isFallback) {
          setGate(
            "demo_fallback complete — canned teaching replay, not a live authenticated run. Fix API key / wake Render for live spans.",
            { fallback: true }
          );
        }
        setOps(events, opts?.data, isFallback);
        return;
      }
      const ev = events[i];
      const nodeId = NODE_MAP[ev.name];
      if (nodeId) {
        if (i > 0) {
          const prev = NODE_MAP[events[i - 1].name];
          if (prev) markNode(prev, doneClass);
        }
        markNode(nodeId, "gb-active");
        if (ev.name === "rag.retrieve") markNode("access", doneClass);
      }
      const declined = ev.name === "rag.decline";
      setGate(gateMessage(ev), {
        declined,
        fallback: isFallback && !declined,
      });
      appendEvent(ev, isFallback ? "fallback" : "live");
      i += 1;
      setTimeout(step, stepMs);
    }

    resetDiagram(strategy);
    if (isFallback) {
      // Auth already failed — keep API pill red while amber-replaying the rest
      markNode("api", "gb-error");
      const center = document.querySelector(".gb-center");
      if (center) center.classList.add("is-fallback-mode");
      setSourceBadge("fallback");
      setGate(
        "API auth failed (pre-pipeline) — replaying canned demo_fallback in amber. Green is reserved for live runs.",
        { fallback: true }
      );
      const log = $("gbEventLog");
      if (log) {
        log.innerHTML = "";
        const line = document.createElement("div");
        line.className = "ev-error";
        line.textContent = "▸ api.auth FAILED — using demo_fallback";
        log.appendChild(line);
      }
    } else {
      markNode("api", "gb-done");
    }

    if (!events.length) {
      setGate("No trace events in response.", { error: true });
      return;
    }
    setTimeout(step, isFallback ? 420 : 80);
  }

  function setOps(trace, data, isFallback) {
    const el = $("gbOps");
    if (!el) return;
    const ms = totalMs(trace);
    const spans = (trace || []).map((e) => e.name).filter(Boolean);
    el.innerHTML = [
      `<span><strong>spans</strong> ${spans.length}</span>`,
      `<span><strong>latency</strong> ${ms != null ? ms + " ms" : "n/a"}</span>`,
      `<span><strong>grounded</strong> ${data?.grounded ? "yes" : "no"}</span>`,
      data?.declined ? `<span><strong>declined</strong> yes</span>` : "",
      isFallback ? `<span class="ops-fallback"><strong>mode</strong> demo_fallback</span>` : "",
    ]
      .filter(Boolean)
      .join("");
  }

  function onAnswer(data, strategy, source) {
    const isFallback = source === "fallback";
    setSourceBadge(isFallback ? "fallback" : "live");
    playTrace(data.trace || [], strategy, {
      data,
      source: isFallback ? "fallback" : "live",
      stepMs: isFallback ? 280 : 340,
    });
    if (!isFallback) loadMetrics();
  }

  /** Call before fallback replay — paints API pill red. */
  function showApiFailure(reason) {
    setSourceBadge("error");
    markNode("api", "gb-error");
    const center = document.querySelector(".gb-center");
    if (center) {
      center.classList.add("is-error-mode");
      center.classList.add("is-fallback-mode");
    }
    setGate(
      (reason || "API request failed") +
        " — this is before Access / Retrieve. Pipeline below will replay a canned demo_fallback (amber), not live spans.",
      { error: true }
    );
    const log = $("gbEventLog");
    if (log) {
      log.innerHTML = "";
      const line = document.createElement("div");
      line.className = "ev-error";
      line.textContent = "▸ api.auth / transport FAILED";
      log.appendChild(line);
    }
  }

  function showRunning() {
    setSourceBadge(null);
    resetDiagram(global.GlassBox?.lastStrategy);
    markNode("api", "gb-active");
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
    showApiFailure,
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
