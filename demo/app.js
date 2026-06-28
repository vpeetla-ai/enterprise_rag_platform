const API = window.ENTERPRISE_RAG_API || "/api";

const payload = (query) => ({
  query,
  tenant_id: "acme",
  user_id: "demo-user",
  groups: ["engineering", "ai-platform"],
  rerank: true,
});

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
  document.getElementById("answer").textContent = data.answer || JSON.stringify(data.hits?.slice(0, 3), null, 2);
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

document.getElementById("ask").addEventListener("click", async () => {
  const query = document.getElementById("query").value.trim();
  document.getElementById("status").textContent = "Calling /v1/answer…";
  try {
    const data = await callAnswer(query);
    render(data, "Grounded answer");
  } catch (error) {
    document.getElementById("status").textContent = `API error: ${error.message}`;
  }
});

document.getElementById("retrieve").addEventListener("click", async () => {
  const query = document.getElementById("query").value.trim();
  document.getElementById("status").textContent = "Calling /v1/retrieve…";
  try {
    const data = await callRetrieve(query);
    render({ hits: data.hits, trace: data }, "Retrieval hits");
  } catch (error) {
    document.getElementById("status").textContent = `API error: ${error.message}`;
  }
});
