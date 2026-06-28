# Live Demo — Enterprise RAG Platform

| Surface | URL |
|---------|-----|
| **UI (Vercel)** | https://enterprise-rag-platform.vercel.app |
| **API (Render)** | https://enterprise-rag-api.onrender.com |

## Deploy

```bash
# API on Render — apply render.yaml blueprint
# UI on Vercel — from repo root:
npx vercel --prod
```

`vercel.json` rewrites `/api/*` to the Render API. Demo ships with seeded `policy-001` corpus — no vector DB required.

## Try locally

```bash
pip install -e ".[dev]"
uvicorn enterprise_rag.api.app:app --reload --port 8080
cd demo && python3 -m http.server 5173
# open http://localhost:5173 with ENTERPRISE_RAG_API=http://localhost:8080 in console if needed
```
