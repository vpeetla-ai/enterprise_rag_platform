const DEFAULT_API = (window.ENTERPRISE_RAG_API || "/api").replace(/\/$/, "");
const STRICT_PACK =
  "https://github.com/vpeetla-ai/enterprise_rag_platform/blob/main/docs/STRICT_PANEL_PACK.md";

function resolveApiBase() {
  const params = new URLSearchParams(window.location.search);
  const fromQuery = (params.get("api") || params.get("strict_url") || "").trim().replace(/\/$/, "");
  if (fromQuery) {
    try {
      sessionStorage.setItem("erag_api_base", fromQuery);
    } catch {
      /* private mode */
    }
    return fromQuery;
  }
  try {
    const stored = (sessionStorage.getItem("erag_api_base") || "").trim().replace(/\/$/, "");
    if (stored) return stored;
  } catch {
    /* private mode */
  }
  return DEFAULT_API;
}

let API = resolveApiBase();

function setApiBase(url) {
  API = String(url || DEFAULT_API).replace(/\/$/, "");
  try {
    if (!url || API === DEFAULT_API) sessionStorage.removeItem("erag_api_base");
    else sessionStorage.setItem("erag_api_base", API);
  } catch {
    /* private mode */
  }
  const el = document.getElementById("apiUrl");
  if (el) el.textContent = API;
  const hostInput = document.getElementById("strictApiUrl");
  if (hostInput && !hostInput.value) hostInput.placeholder = DEFAULT_API;
}

function authHeaders() {
  const headers = { "Content-Type": "application/json" };
  const apiKey = document.getElementById("apiKey")?.value?.trim();
  const jwt = document.getElementById("strictJwt")?.value?.trim();
  if (apiKey) headers["X-API-Key"] = apiKey;
  if (jwt) headers["Authorization"] = `Bearer ${jwt}`;
  return headers;
}

const SAMPLE_DOC = {
  title: "Zephyr Cloud Security Policy",
  body: `Zephyr Corporation Cloud Security Policy (2026)

All production deployments must pass AegisAI gateway approval before email or Slack notifications are sent.

The mandatory rotation period for API keys is 90 days. Engineering teams must enable hybrid retrieval with citation grounding for all customer-facing answers.

Incident response playbooks require human approval for restricted documents and confidential customer data.`,
  sampleQuery: "What is the mandatory API key rotation period at Zephyr Corporation?",
};

const STRATEGIES = [
  { id: "regular", mode: "keyword", rerank: false, agentic: false, label: "Regular RAG" },
  { id: "hybrid", mode: "hybrid", rerank: true, agentic: false, label: "Hybrid RAG" },
  { id: "agentic", mode: "hybrid", rerank: true, agentic: true, label: "Agentic RAG" },
];

const PIPELINE_STEPS = ["rag.retrieve", "rag.graph_expand", "rag.rerank", "rag.generate"];

function strategyFromUi() {
  const choice = document.getElementById("ragMode").value;
  return STRATEGIES.find((s) => s.id === choice) || STRATEGIES[1];
}

const basePayload = () => ({
  tenant_id: "acme",
  user_id: "demo-user",
  groups: ["engineering", "ai-platform"],
});

const payload = (query, strategy = strategyFromUi()) => ({
  ...basePayload(),
  query,
  mode: strategy.mode,
  rerank: strategy.rerank,
  agentic: strategy.agentic,
});

function showSingleMode() {
  document.getElementById("compareResults").classList.add("hidden");
}

function showCompareMode() {
  document.getElementById("compareResults").classList.remove("hidden");
}

function clearSingleResults() {
  document.getElementById("answer").textContent = "";
  document.getElementById("answer").classList.remove("is-fallback", "is-error");
  const badge = document.getElementById("answerBadge");
  if (badge) {
    badge.className = "answer-badge hidden";
    badge.textContent = "";
  }
  document.getElementById("citations").innerHTML = "";
  document.getElementById("riskFlags").innerHTML = "";
  document.getElementById("activeQuery").classList.add("hidden");
  document.getElementById("activeQuery").textContent = "";
  setStatus("Submit a query to call the live API.", "idle");
}

/** @param {string} text @param {"idle"|"ok"|"warn"|"error"} severity @param {string} [detail] */
function setStatus(text, severity, detail) {
  const el = document.getElementById("status");
  if (!el) return;
  el.className = "status-msg is-" + (severity || "idle");
  el.textContent = text;
  if (detail) {
    const d = document.createElement("span");
    d.className = "status-detail";
    d.textContent = detail;
    el.appendChild(d);
  }
}

function humanizeApiError(raw) {
  const msg = String(raw || "");
  if (/X-API-Key|api[_ ]?key|Invalid or missing/i.test(msg)) {
    return {
      title: "API key required or invalid",
      detail: msg,
      hint: "Open Advanced → paste X-API-Key, or the backend may require RAG_API_KEY.",
    };
  }
  if (/not reachable|waking|Failed to fetch|NetworkError|timeout/i.test(msg)) {
    return {
      title: "API not reachable",
      detail: msg,
      hint: "Render free tier may still be waking (~30–90s). Retry shortly.",
    };
  }
  return { title: "API request failed", detail: msg, hint: null };
}

function setAnswerTone(tone, label) {
  const answer = document.getElementById("answer");
  const badge = document.getElementById("answerBadge");
  answer.classList.remove("is-fallback", "is-error");
  if (tone === "fallback") answer.classList.add("is-fallback");
  if (tone === "error") answer.classList.add("is-error");
  if (badge) {
    if (label) {
      badge.textContent = label;
      badge.className = "answer-badge is-" + (tone === "live" ? "live" : "fallback");
      badge.classList.remove("hidden");
    } else {
      badge.className = "answer-badge hidden";
      badge.textContent = "";
    }
  }
}

function syncGlassBoxStrategy() {
  const strategy = strategyFromUi();
  if (window.GlassBox) {
    window.GlassBox.setStrategy(strategy);
    window.GlassBox.resetDiagram(strategy);
  }
  return strategy;
}

function replayGlassBox(data, source) {
  const strategy = strategyFromUi();
  if (window.GlassBox) {
    window.GlassBox.onAnswer(data, strategy, source);
  }
}

function applyReviewMode(health) {
  const strict = Boolean(health?.production_strict) || health?.review_mode === "strict";
  const badge = document.getElementById("modeBadge");
  const banner = document.getElementById("reviewModeBanner");
  const retrieval = health?.retrieval || {};
  const profileBits = [
    `embed=${retrieval.embedding_provider || "?"}`,
    `rerank=${retrieval.reranker || "?"}`,
    `fusion=${retrieval.fusion || "?"}`,
    `generator=${health?.generator || "?"}`,
    `corpus=${health?.corpus_of_record || health?.retriever_backend || "?"}`,
  ].join(" · ");
  const claimAligned = Boolean(health?.product_bar?.claim_aligned);
  if (badge) {
    badge.textContent = strict ? "Strict mode" : "Demo mode";
    badge.classList.toggle("status-badge--warn", !strict);
    badge.classList.toggle("status-badge--strict", strict);
  }
  if (banner) {
    banner.classList.toggle("review-mode-banner--demo", !strict);
    banner.classList.toggle("review-mode-banner--strict", strict);
    if (strict) {
      banner.innerHTML =
        `<strong>Strict review mode</strong><span>JWT + API key required. HITL hard-gates high-risk answers. Live profile: <code>${profileBits}</code>${
          claimAligned ? "" : " — not yet claim-aligned (Qdrant + local/CE/LLM)."
        }</span>`;
    } else {
      banner.innerHTML =
        `<strong>Demo review mode</strong><span>Client-asserted Principal. Honest live profile: <code>${profileBits}</code> — hash/ScoreBoost/extractive is expected on the cheap Demo. Point this UI at a Strict host via <code>?api=</code> or the Strict panel below (<a href="${STRICT_PACK}" target="_blank" rel="noreferrer">STRICT_PANEL_PACK</a> · <a href="https://github.com/vpeetla-ai/enterprise_rag_platform/blob/main/docs/PROFILES.md" target="_blank" rel="noreferrer">PROFILES</a>).</span>`;
    }
  }
}

async function wakeApi(maxAttempts = 4) {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const res = await fetch(`${API}/health`, { signal: AbortSignal.timeout(45000), cache: "no-store" });
      if (res.ok) {
        try {
          applyReviewMode(await res.json());
        } catch {
          /* keep default Demo banner */
        }
        return true;
      }
    } catch {
      /* Render cold start */
    }
    await new Promise((r) => setTimeout(r, 8000));
  }
  return false;
}

async function apiPost(path, body) {
  const response = await fetch(`${API}${path}`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
    cache: "no-store",
    signal: AbortSignal.timeout(60000),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(text || `HTTP ${response.status}`);
  return JSON.parse(text);
}

async function callAnswer(query, strategy) {
  return apiPost("/v1/answer", payload(query, strategy));
}

async function callRetrieve(query, strategy) {
  return apiPost("/v1/retrieve", payload(query, strategy));
}

function render(data, mode, query) {
  showSingleMode();
  clearSingleResults();
  setStatus(mode, "ok");
  if (query) {
    const qEl = document.getElementById("activeQuery");
    qEl.textContent = `Question: ${query}`;
    qEl.classList.remove("hidden");
  }
  const answer = data.answer || JSON.stringify(data.hits?.slice(0, 3), null, 2);
  document.getElementById("answer").textContent = answer;
  setAnswerTone("live", "live");
  const citations = document.getElementById("citations");
  (data.citations || []).forEach((c) => {
    const li = document.createElement("li");
    const pageLabel = c.page != null ? ` · p.${c.page}` : "";
    const href =
      c.page != null && lastPdfObjectUrl
        ? `${lastPdfObjectUrl}#page=${c.page}`
        : c.uri;
    li.innerHTML = `<strong>${c.title || "Source"}${pageLabel}</strong><br/><a href="${href}" target="_blank" rel="noreferrer">${c.page != null ? "Open PDF at page " + c.page : c.uri}</a>`;
    if (c.page != null && window.pdfViewerGoto) {
      li.querySelector("a")?.addEventListener("click", (ev) => {
        if (lastPdfObjectUrl) {
          ev.preventDefault();
          window.pdfViewerGoto(c.page);
        }
      });
    }
    citations.appendChild(li);
  });
  const flags = document.getElementById("riskFlags");
  (data.risk_flags || []).forEach((flag) => {
    const span = document.createElement("span");
    span.className = "flag";
    span.textContent = flag;
    flags.appendChild(span);
  });
  replayGlassBox(data, "live");
}

function pipelineHtml(trace) {
  const ran = new Set((trace || []).map((e) => e.name));
  return PIPELINE_STEPS.map((step) => {
    const cls = ran.has(step) ? "on" : "off";
    const label = step.replace("rag.", "");
    return `<span class="${cls}">${label}</span>`;
  }).join(" → ");
}

function hitsHtml(hits) {
  if (!hits?.length) return "<em>No retrieval hits</em>";
  return `<ul class="hits">${hits
    .slice(0, 3)
    .map(
      (h) =>
        `<li><strong>${h.title || h.chunk?.source_title || "?"}</strong> — score ${Number(h.score).toFixed(2)}<br/><span>${(h.text || "").slice(0, 90)}…</span></li>`
    )
    .join("")}</ul>`;
}

function strategyMeta(strategy) {
  return `mode=${strategy.mode} · rerank=${strategy.rerank} · graph=${strategy.agentic}`;
}

function buildStrategyCard(strategy, retrieveData, answerData) {
  const card = document.createElement("article");
  card.className = "strategy-card";
  const trace = answerData.trace || [];
  const hits = retrieveData.hits || [];
  const answer = answerData.answer || "(no answer)";
  const source = answerData.citations?.[0]?.title || "—";
  const topHit = hits[0]?.title || "—";
  card.innerHTML = `
    <h3>${strategy.label}</h3>
    <div class="strategy-meta">${strategyMeta(strategy)}</div>
    <div class="pipeline">${pipelineHtml(trace)}</div>
    <div class="strategy-meta">Top hit: <strong>${topHit}</strong> · Answer from: <strong>${source}</strong></div>
    <strong>Top hits</strong>
    ${hitsHtml(hits)}
    <strong>Answer</strong>
    <div class="card-answer">${answer}</div>
  `;
  return card;
}

let lastPdfObjectUrl = null;
let lastPdfDoc = null;

async function extractFileText(file) {
  const name = file.name.toLowerCase();
  if (name.endsWith(".pdf")) {
    // Client extract is preview-only; server /v1/ingest/pdf owns page provenance.
    const pdfjs = window.pdfjsLib;
    if (!pdfjs) throw new Error("PDF.js failed to load — try a .txt file instead");
    pdfjs.GlobalWorkerOptions.workerSrc =
      "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
    const buffer = await file.arrayBuffer();
    if (lastPdfObjectUrl) URL.revokeObjectURL(lastPdfObjectUrl);
    lastPdfObjectUrl = URL.createObjectURL(file);
    const pdf = await pdfjs.getDocument({ data: buffer }).promise;
    lastPdfDoc = pdf;
    window.pdfViewerGoto = async (pageNum) => {
      const host = document.getElementById("pdfViewer");
      if (!host || !lastPdfDoc) return;
      host.classList.remove("hidden");
      const page = await lastPdfDoc.getPage(pageNum);
      const viewport = page.getViewport({ scale: 1.2 });
      let canvas = host.querySelector("canvas");
      if (!canvas) {
        canvas = document.createElement("canvas");
        host.innerHTML = "";
        host.appendChild(canvas);
      }
      canvas.height = viewport.height;
      canvas.width = viewport.width;
      await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
      host.scrollIntoView({ behavior: "smooth", block: "nearest" });
    };
    return { kind: "pdf", file, buffer };
  }
  return { kind: "text", text: await file.text() };
}

async function ingestBody({ title, body, filename = "upload.txt" }) {
  const status = document.getElementById("ingestStatus");
  if (!(await wakeApi())) {
    throw new Error("API not reachable — Render may still be waking up");
  }
  const documentId = `upload-${Date.now()}`;
  const MAX_CHARS = 50000;
  let payloadBody = body;
  let truncNote = "";
  if (body.length > MAX_CHARS) {
    payloadBody = body.slice(0, MAX_CHARS);
    truncNote = ` Truncated to ${MAX_CHARS} chars (flat ingest is non-page mode).`;
  }
  status.textContent = "Ingesting via API…";
  const data = await apiPost("/v1/ingest", {
    ...basePayload(),
    document_id: documentId,
    title,
    body: payloadBody,
    uri: `upload://${filename}`,
    owner: "demo-user",
    metadata: {
      source: "demo-upload",
      filename,
      ...(truncNote ? { truncated: "true" } : {}),
    },
  });
  status.textContent = `Ingested "${title}" — ${data.chunks_added} chunks added.${truncNote}`;
  document.getElementById("query").value = SAMPLE_DOC.sampleQuery;
  return data;
}

async function ingestPdfFile(file, title) {
  const status = document.getElementById("ingestStatus");
  if (!(await wakeApi())) {
    throw new Error("API not reachable — Render may still be waking up");
  }
  const documentId = `upload-${Date.now()}`;
  status.textContent = "Uploading PDF to server (page-aware ingest)…";
  const form = new FormData();
  form.append("file", file);
  form.append("document_id", documentId);
  form.append("title", title);
  form.append("tenant_id", basePayload().tenant_id || "acme");
  form.append("owner", "demo-user");
  form.append("groups", (basePayload().groups || ["engineering"]).join(","));
  const headers = {};
  const apiKey = document.getElementById("apiKey")?.value?.trim();
  const jwt = document.getElementById("strictJwt")?.value?.trim();
  if (apiKey) headers["X-API-Key"] = apiKey;
  if (jwt) headers["Authorization"] = `Bearer ${jwt}`;
  const res = await fetch(`${API}/v1/ingest/pdf`, { method: "POST", headers, body: form });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`PDF ingest failed (${res.status}): ${err.slice(0, 200)}`);
  }
  const data = await res.json();
  status.textContent = `Ingested PDF "${title}" — ${data.chunks_added} chunks · ${data.pdf?.page_count || "?"} pages.`;
  document.getElementById("query").value = SAMPLE_DOC.sampleQuery;
  return data;
}

async function ingestDocument() {
  const fileInput = document.getElementById("docFile");
  const status = document.getElementById("ingestStatus");
  const file = fileInput.files?.[0];
  if (!file) {
    status.textContent = "Choose a PDF or text file first.";
    return;
  }
  status.textContent = "Preparing upload…";
  const title =
    document.getElementById("docTitle").value.trim() || file.name.replace(/\.[^.]+$/, "");
  const extracted = await extractFileText(file);
  if (extracted.kind === "pdf") {
    await ingestPdfFile(file, title);
  } else {
    await ingestBody({ title, body: extracted.text, filename: file.name });
  }
}

async function loadSampleDocument() {
  const status = document.getElementById("ingestStatus");
  status.textContent = "Loading sample document…";
  document.getElementById("docTitle").value = SAMPLE_DOC.title;
  try {
    const res = await fetch("fixtures/zephyr-policy.txt", { cache: "no-store" });
    const body = res.ok ? await res.text() : SAMPLE_DOC.body;
    await ingestBody({ title: SAMPLE_DOC.title, body, filename: "zephyr-policy.txt" });
  } catch {
    await ingestBody({ title: SAMPLE_DOC.title, body: SAMPLE_DOC.body, filename: "zephyr-policy.txt" });
  }
}

async function testAllStrategies() {
  const query = document.getElementById("query").value.trim() || SAMPLE_DOC.sampleQuery;
  showCompareMode();
  clearSingleResults();
  document.getElementById("compareStatus").textContent = "Waking API and testing all 3 strategies…";
  document.getElementById("compareQuery").textContent = `Question: ${query}`;
  document.getElementById("strategyCards").innerHTML = "";

  if (!(await wakeApi())) {
    document.getElementById("compareStatus").textContent = "API not reachable — wait 30s and retry";
    return;
  }

  for (const strategy of STRATEGIES) {
    document.getElementById("compareStatus").textContent = `Testing ${strategy.label}…`;
    try {
      const [retrieveData, answerData] = await Promise.all([
        callRetrieve(query, strategy),
        callAnswer(query, strategy),
      ]);
      document.getElementById("strategyCards").appendChild(
        buildStrategyCard(strategy, retrieveData, answerData)
      );
    } catch (error) {
      const card = document.createElement("article");
      card.className = "strategy-card";
      card.innerHTML = `<h3>${strategy.label}</h3><p class="muted">ERROR: ${error.message}</p>`;
      document.getElementById("strategyCards").appendChild(card);
    }
  }
  document.getElementById("compareStatus").textContent =
    "Compare pipeline steps and hit scores — answer text may match when the same top chunk wins.";
}

document.getElementById("ask").addEventListener("click", async () => {
  const query = document.getElementById("query").value.trim();
  if (!query) {
    setStatus("Enter a question first.", "warn");
    return;
  }
  const strategy = syncGlassBoxStrategy();
  showSingleMode();
  clearSingleResults();
  setStatus(`Calling /v1/answer (${strategy.label})…`, "idle");
  window.GlassBox?.showRunning();
  try {
    if (!(await wakeApi())) throw new Error("API not reachable — Render may still be waking up");
    const data = await callAnswer(query, strategy);
    if (!data.answer?.trim() || data.answer.includes("do not have enough authorized context")) {
      setStatus(
        `No matching chunks — try keywords from your document (${strategy.label})`,
        "warn"
      );
      document.getElementById("activeQuery").textContent = `Question: ${query}`;
      document.getElementById("activeQuery").classList.remove("hidden");
      document.getElementById("answer").textContent =
        "No authorized context found for this query. Re-ingest your document or use terms that appear in it.";
      setAnswerTone("fallback", "no context");
      replayGlassBox({ ...data, trace: data.trace || [] }, "live");
    } else {
      render(data, `Grounded answer — ${strategy.label}`, query);
    }
  } catch (error) {
    const h = humanizeApiError(error.message);
    const unreachable = /not reachable|waking|Failed to fetch|NetworkError|timeout/i.test(
      error.message || ""
    );
    document.getElementById("activeQuery").textContent = `Question: ${query}`;
    document.getElementById("activeQuery").classList.remove("hidden");
    window.GlassBox?.showApiFailure(h.title);
    if (unreachable) {
      setStatus(
        h.title + " — showing demo_fallback (not a live run)",
        "error",
        (h.hint ? h.hint + " · " : "") + h.detail
      );
      const demo = window.GlassBox?.demoAnswer;
      if (demo) {
        document.getElementById("answer").textContent = demo.answer;
        setAnswerTone("fallback", "demo_fallback");
        replayGlassBox(demo, "fallback");
      }
    } else {
      setStatus(h.title, "error", (h.hint ? h.hint + " · " : "") + h.detail);
      document.getElementById("answer").textContent =
        "Live request failed — fix auth/API and retry. demo_fallback is reserved for unreachable API only.";
      setAnswerTone("fallback", "error");
    }
  }
});

document.getElementById("retrieve").addEventListener("click", async () => {
  const query = document.getElementById("query").value.trim();
  if (!query) {
    setStatus("Enter a question first.", "warn");
    return;
  }
  const strategy = syncGlassBoxStrategy();
  showSingleMode();
  clearSingleResults();
  setStatus(`Calling /v1/retrieve (${strategy.label})…`, "idle");
  window.GlassBox?.showRunning();
  try {
    if (!(await wakeApi())) throw new Error("API not reachable — Render may still be waking up");
    const data = await callRetrieve(query, strategy);
    const synth = {
      hits: data.hits,
      trace: [
        { name: "rag.guardrails.input", attributes: { status: "ok" }, duration_ms: 1 },
        { name: "rag.retrieve", attributes: { mode: strategy.mode, status: "ok" }, duration_ms: 14 },
      ],
    };
    render(
      synth,
      `Retrieval hits — ${strategy.label} (${data.hits?.length || 0} hits)`,
      query
    );
  } catch (error) {
    const h = humanizeApiError(error.message);
    setStatus(h.title, "error", h.detail);
    document.getElementById("activeQuery").textContent = `Question: ${query}`;
    document.getElementById("activeQuery").classList.remove("hidden");
    window.GlassBox?.showApiFailure(h.title);
  }
});

document.getElementById("ingest").addEventListener("click", async () => {
  const status = document.getElementById("ingestStatus");
  try {
    await ingestDocument();
  } catch (error) {
    status.textContent = `Ingest failed: ${error.message}`;
  }
});

document.getElementById("loadSample").addEventListener("click", async () => {
  const status = document.getElementById("ingestStatus");
  try {
    await loadSampleDocument();
  } catch (error) {
    status.textContent = `Sample ingest failed: ${error.message}`;
  }
});

document.getElementById("testAll").addEventListener("click", testAllStrategies);

document.getElementById("ragMode")?.addEventListener("change", syncGlassBoxStrategy);
syncGlassBoxStrategy();

document.getElementById("applyStrictApi")?.addEventListener("click", async () => {
  const raw = document.getElementById("strictApiUrl")?.value?.trim();
  if (!raw) {
    setStatus("Paste a Strict host URL first (local Docker or Cloud Run).", "warn");
    return;
  }
  setApiBase(raw);
  setStatus(`Probing Strict host ${API}…`, "idle");
  const ok = await wakeApi(2);
  setStatus(
    ok ? `Connected · review_mode from /health (see banner)` : `Could not reach ${API}`,
    ok ? "ok" : "error"
  );
});

document.getElementById("resetDemoApi")?.addEventListener("click", async () => {
  setApiBase(DEFAULT_API);
  const hostInput = document.getElementById("strictApiUrl");
  if (hostInput) hostInput.value = "";
  setStatus(`Reset to Demo API ${API}`, "idle");
  await wakeApi(2);
});

setApiBase(API);

if (window.pdfjsLib) {
  window.pdfjsLib.GlobalWorkerOptions.workerSrc =
    "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
}
