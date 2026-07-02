const API = (window.ENTERPRISE_RAG_API || "/api").replace(/\/$/, "");

function strategyFromUi() {
  const choice = document.getElementById("ragMode").value;
  if (choice === "regular") {
    return { mode: "keyword", rerank: false, agentic: false, label: "Regular RAG" };
  }
  if (choice === "agentic") {
    return { mode: "hybrid", rerank: true, agentic: true, label: "Agentic RAG" };
  }
  return { mode: "hybrid", rerank: true, agentic: false, label: "Hybrid RAG" };
}

const payload = (query) => {
  const strategy = strategyFromUi();
  return {
    query,
    tenant_id: "acme",
    user_id: "demo-user",
    groups: ["engineering", "ai-platform"],
    mode: strategy.mode,
    rerank: strategy.rerank,
    agentic: strategy.agentic,
  };
};

async function callAnswer(query) {
  const response = await fetch(`${API}/v1/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload(query)),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function callRetrieve(query) {
  const response = await fetch(`${API}/v1/retrieve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload(query)),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function render(data, mode) {
  document.getElementById("status").textContent = mode;
  document.getElementById("answer").textContent =
    data.answer || JSON.stringify(data.hits?.slice(0, 3), null, 2);
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
    if (!pdfjs) throw new Error("PDF.js not loaded");
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
    return pages.join("\n\n");
  }
  return file.text();
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
  if (!body.trim()) {
    status.textContent = "No text found in file.";
    return;
  }
  const title =
    document.getElementById("docTitle").value.trim() ||
    file.name.replace(/\.[^.]+$/, "");
  const documentId = `upload-${Date.now()}`;
  status.textContent = "Ingesting via API…";
  const response = await fetch(`${API}/v1/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      tenant_id: "acme",
      document_id: documentId,
      title,
      body: body.slice(0, 50000),
      uri: `upload://${file.name}`,
      owner: "demo-user",
      groups: ["engineering", "ai-platform"],
      metadata: { source: "demo-upload", filename: file.name },
    }),
  });
  if (!response.ok) throw new Error(await response.text());
  const data = await response.json();
  status.textContent = `Ingested "${title}" — ${data.chunks_added} chunks added.`;
}

document.getElementById("ask").addEventListener("click", async () => {
  const query = document.getElementById("query").value.trim();
  const strategy = strategyFromUi();
  document.getElementById("status").textContent = `Calling /v1/answer (${strategy.label})…`;
  try {
    const data = await callAnswer(query);
    render(data, `Grounded answer — ${strategy.label}`);
  } catch (error) {
    document.getElementById("status").textContent = `API error: ${error.message}`;
  }
});

document.getElementById("retrieve").addEventListener("click", async () => {
  const query = document.getElementById("query").value.trim();
  const strategy = strategyFromUi();
  document.getElementById("status").textContent = `Calling /v1/retrieve (${strategy.label})…`;
  try {
    const data = await callRetrieve(query);
    render({ hits: data.hits, trace: data }, `Retrieval hits — ${strategy.label}`);
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
