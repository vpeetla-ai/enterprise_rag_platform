/** Shared architect landing panel for static Vercel demos. */
(function () {
  const cfg = window.ARCHITECT_CONFIG;
  if (!cfg) return;

  function el(tag, cls, html) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }

  function renderLayers(root) {
    const section = el("section", "panel architect-panel");
    section.appendChild(el("p", "eyebrow", "Eagle-eye view"));
    section.appendChild(el("h2", null, "Architecture at a glance"));
    section.appendChild(el("p", "lede", cfg.tagline));

    const stack = el("div", "arch-layers");
    (cfg.layers || []).forEach((layer) => {
      const row = el("div", "arch-layer");
      row.appendChild(el("span", "arch-tier", layer.tier));
      const mid = el("div", "arch-mid");
      mid.appendChild(el("strong", null, layer.name));
      mid.appendChild(el("span", "muted", layer.role));
      row.appendChild(mid);
      const chips = el("div", "arch-chips");
      (layer.components || []).forEach((c) => chips.appendChild(el("span", "arch-chip", c)));
      row.appendChild(chips);
      stack.appendChild(row);
    });
    section.appendChild(stack);
    root.appendChild(section);
  }

  function renderTradeoffs(root) {
    const section = el("section", "panel architect-panel");
    section.appendChild(el("p", "eyebrow", "Principal tradeoffs"));
    section.appendChild(el("h2", null, "Decisions, not defaults"));
    const grid = el("div", "arch-tradeoffs");
    (cfg.tradeoffs || []).forEach((t) => {
      const card = el("div", "arch-tradeoff");
      card.innerHTML =
        "<strong>" +
        t.decision +
        "</strong><p><span class=\"gain\">Gain:</span> " +
        t.gain +
        "</p><p><span class=\"trade\">Trade:</span> " +
        t.trade +
        "</p>";
      grid.appendChild(card);
    });
    section.appendChild(grid);
    root.appendChild(section);
  }

  function renderMetrics(root, data) {
    const section = el("section", "panel architect-panel");
    section.appendChild(el("p", "eyebrow", "Production metrics"));
    section.appendChild(el("h2", null, "Live from the API"));
    const grid = el("div", "arch-metrics");
    const labels = cfg.metricLabels || {};
    const cards = [
      [labels.runs || "Total runs", data.total_runs],
      ["Success rate", data.success_rate_pct + "%"],
      [labels.latency || "P95 latency", data.p95_latency_ms != null ? data.p95_latency_ms + "ms" : "—"],
      [labels.entities || "Active entities", data.active_entities],
    ];
    cards.forEach(([label, value]) => {
      const card = el("div", "arch-metric");
      card.innerHTML = "<span class=\"muted\">" + label + "</span><strong>" + value + "</strong>";
      grid.appendChild(card);
    });
    section.appendChild(grid);
    const foot = el(
      "p",
      "muted api-hint",
      "Live from <code>" +
        (cfg.metricsPath || "/ops/metrics") +
        "</code> · SLO " +
        (data.slo?.success_target_pct || 95) +
        "% success"
    );
    section.appendChild(foot);
    root.appendChild(section);
  }

  function normalize(data) {
    const slo = data.slo || {};
    return {
      total_runs: data.total_runs ?? data.sample_size ?? data.total ?? 0,
      success_rate_pct: data.success_rate_pct ?? 100 - (data.failure_rate_pct || 0),
      p95_latency_ms: data.p95_latency_ms ?? data.p95_node_latency_ms ?? data.p95_ms ?? null,
      active_entities: data.active_entities ?? data.invited_users ?? 0,
      slo: slo,
    };
  }

  function mount() {
    const root = document.getElementById("architect-root");
    if (!root) return;
    renderLayers(root);
    renderTradeoffs(root);
    if (cfg.metricsUrl) {
      fetch(cfg.metricsUrl, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => data && renderMetrics(root, normalize(data)))
        .catch(() => null);
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
