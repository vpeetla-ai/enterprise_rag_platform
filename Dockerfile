FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# System deps for pymupdf / sentence-transformers light path
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY src ./src
# Full Strict/prod image: pdf + qdrant + rerank + local embeddings
RUN pip install --no-cache-dir ".[full]"
EXPOSE 8080
CMD ["sh", "-c", "uvicorn enterprise_rag.api.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
