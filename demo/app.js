const API = (window.ENTERPRISE_RAG_API || "/api").replace(/\/$/, "");

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

async function wakeApi(maxAttempts = 4) {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const res = await fetch(`${API}/health`, { signal: AbortSignal.timeout(45000) });
      if (res.ok) return true;
    } catch {
      /* Render cold start */
    }
    await new Promise((r) => setTimeout(r, 8000));
  }
  return false;
}

async function callAnswer(query, strategy) {
  const response = await fetch(`${API}/v1/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload(query, strategy)),
    signal: AbortSignal.timeout(60000),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(text || `HTTP ${response.status}`);
  return JSON.parse(text);
}

async function callRetrieve(query, strategy) {
  const response = await fetch(`${API}/v1/retrieve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload(query, strategy)),
    signal: AbortSignal.timeout(60000),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(text || `HTTP ${response.status}`);
  return JSON.parse(text);
}

function render(data, mode) {
  document.getElementById("status").textContent = mode;
  const answer = data.answer || JSON.stringify(data.hits?.slice(0, 3), null, 2);
  document.getElementById("answer").textContent = answer;
  const citations = document.getElementById("citations");
  citations.innerHTML = "";
  (data.citations || []).forEach((c) => {
    const li = document.createElement("li");
    li.innerHTML = `<strong>${c.title}</strong><br/><a href="${c.uri}" target="_blank" rel="noreferrer">${c.uri}</a>`;
    citations.appendChild(li);
  });
  const flags = document.getElementById("riskFlags");
  flags.innerHTML = "";
  (data.risk_flags || []).forEach((flag) => {
    const span = document.createElement("span");
    span.className = "flag";
    span.textContent = flag;
    flags.appendChild(span);
  });
  document.getElementById("trace").textContent = JSON.stringify(data.trace || data, null, 2);
}

async function extractFileText(file) {
  const name = file.name.toLowerCase();
  if (name.endsWith(".pdf")) {
    const pdfjs = window.pdfjsLib;
    if (!pdfjs) throw new Error("PDF.js failed to load — try a .txt file instead");
    pdfjs.GlobalWorkerOptions.workerSrc =
      "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
    const buffer = await file.arrayBuffer();
    const pdf = await pdfjs.getDocument({ data: buffer }).promise;
    const pages = [];
    for (let i = 1; i <= pdf.numPages; i++) {
      const page = await pdf.getPage(i);
      const content = await page.getTextContent();
      pages.push(content.items.map((item) => item.str).join(" "));
    }
    const text = pages.join("\n\n").trim();
    if (!text) {
      throw new Error(
        "No extractable text in PDF (scanned image PDFs are not supported — use .txt or paste text)"
      );
    }
    return text;
  }
  return file.text();
}

async function ingestBody({ title, body, filename = "upload.txt" }) {
  const status = document.getElementById("ingestStatus");
  if (!(await wakeApi())) {
    throw new Error("API not reachable — Render may still be waking up");
  }
  const documentId = `upload-${Date.now()}`;
  status.textContent = "Ingesting via API…";
  const response = await fetch(`${API}/v1/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...basePayload(),
      document_id: documentId,
      title,
      body: body.slice(0, 50000),
      uri: `upload://${filename}`,
      owner: "demo-user",
      metadata: { source: "demo-upload", filename },
    }),
    signal: AbortSignal.timeout(60000),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(text || `HTTP ${response.status}`);
  const data = JSON.parse(text);
  status.textContent = `Ingested "${title}" — ${data.chunks_added} chunks added.`;
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
  status.textContent = "Extracting text…";
  const body = await extractFileText(file);
  const title =
    document.getElementById("docTitle").value.trim() || file.name.replace(/\.[^.]+$/, "");
  await ingestBody({ title, body, filename: file.name });
}

async function loadSampleDocument() {
  const status = document.getElementById("ingestStatus");
  status.textContent = "Loading sample document…";
  document.getElementById("docTitle").value = SAMPLE_DOC.title;
  try {
    const res = await fetch("fixtures/zephyr-policy.txt");
    const body = res.ok ? await res.text() : SAMPLE_DOC.body;
    await ingestBody({ title: SAMPLE_DOC.title, body, filename: "zephyr-policy.txt" });
  } catch (error) {
    await ingestBody({ title: SAMPLE_DOC.title, body: SAMPLE_DOC.body, filename: "zephyr-policy.txt" });
  }
}

async function testAllStrategies() {
  const query = document.getElementById("query").value.trim() || SAMPLE_DOC.sampleQuery;
  document.getElementById("query").value = query;
  const status = document.getElementById("status");
  status.textContent = "Waking API and testing all 3 strategies…";
  if (!(await wakeApi())) {
    status.textContent = "API not reachable — wait 30s and retry";
    return;
  }
  const results = [];
  for (const strategy of STRATEGIES) {
    status.textContent = `Testing ${strategy.label}…`;
    try {
      const data = await callAnswer(query, strategy);
      const cites = (data.citations || []).map((c) => c.title).join(", ") || "none";
      const spans = (data.trace || []).map((e) => e.name).join(" → ");
      results.push(
        `【${strategy.label}】\n${data.answer}\nCitations: ${cites}\nTrace: ${spans}\n`
      );
    } catch (error) {
      results.push(`【${strategy.label}】 ERROR: ${error.message}\n`);
    }
  }
  document.getElementById("answer").textContent = results.join("\n");
  document.getElementById("status").textContent = "All 3 strategies tested — see combined results below";
  document.getElementById("citations").innerHTML = "";
  document.getElementById("riskFlags").innerHTML = "";
  document.getElementById("trace").textContent = `API: ${API}\nQuery: ${query}`;
}

document.getElementById("ask").addEventListener("click", async () => {
  const query = document.getElementById("query").value.trim();
  const strategy = strategyFromUi();
  document.getElementById("status").textContent = `Calling /v1/answer (${strategy.label})…`;
  try {
    if (!(await wakeApi())) throw new Error("API not reachable — Render may still be waking up");
    const data = await callAnswer(query, strategy);
    if (!data.answer?.trim() || data.answer.includes("do not have enough authorized context")) {
      document.getElementById("status").textContent =
        `No matching chunks for your query — try the sample question or re-ingest your document (${strategy.label})`;
    } else {
      render(data, `Grounded answer — ${strategy.label}`);
    }
  } catch (error) {
    document.getElementById("status").textContent = `API error: ${error.message}`;
  }
});

document.getElementById("retrieve").addEventListener("click", async () => {
  const query = document.getElementById("query").value.trim();
  const strategy = strategyFromUi();
  document.getElementById("status").textContent = `Calling /v1/retrieve (${strategy.label})…`;
  try {
    if (!(await wakeApi())) throw new Error("API not reachable — Render may still be waking up");
    const data = await callRetrieve(query, strategy);
    render({ hits: data.hits, trace: data }, `Retrieval hits — ${strategy.label} (${data.hits?.length || 0} hits)`);
  } catch (error) {
    document.getElementById("status").textContent = `API error: ${error.message}`;
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

if (window.pdfjsLib) {
  window.pdfjsLib.GlobalWorkerOptions.workerSrc =
    "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
}
