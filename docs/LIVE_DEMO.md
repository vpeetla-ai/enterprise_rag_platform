# Live Demo — Enterprise RAG Platform

**Live demo (vpeetla-ai team):** [enterprise-rag-platform-eta.vercel.app](https://enterprise-rag-platform-eta.vercel.app)

> `enterprise-rag-platform.vercel.app` may point at a stale deployment. The team URL above uses [`demo/config.js`](../demo/config.js) to call Render directly (CORS enabled on API).

| Surface | URL |
|---------|-----|
| **UI (Vercel)** | https://enterprise-rag-platform-eta.vercel.app |
| **API (Render)** | https://enterprise-rag-api-4el1.onrender.com |

## Deploy

```bash
# API on Render — apply render.yaml blueprint
# UI on Vercel — deploy static demo folder (avoids FastAPI auto-detect):
cd demo && npx vercel --prod
npx vercel alias set <deployment-url> enterprise-rag-platform.vercel.app
```

`vercel.json` rewrites `/api/*` to the Render API. Demo ships with seeded `policy-001` corpus — no vector DB required.

> **Note:** If Render assigns a different hostname (e.g. `enterprise-rag-api-4el1.onrender.com`), update `demo/vercel.json` rewrite destination and redeploy the Vercel demo. `GET /` returns 404 by design — use `/health` or `/v1/answer`.

## Observability (Langfuse)

Set in Render dashboard (see `render.yaml`):

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_ENABLED=true
```

After `POST /v1/answer`, check response field `langfuse_export` (`exported` | `skipped` | `failed`) and Langfuse → **Traces** → project `enterprise-rag-platform`.

## Try locally

```bash
pip install -e ".[dev]"
uvicorn enterprise_rag.api.app:app --reload --port 8080
cd demo && python3 -m http.server 5173
# open http://localhost:5173 with ENTERPRISE_RAG_API=http://localhost:8080 in console if needed
```
