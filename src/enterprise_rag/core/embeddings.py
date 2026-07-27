"""Embedding providers for dense retrieval (ADR-0008)."""

from __future__ import annotations

import hashlib
import math
import os
from typing import Protocol


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class HashingEmbedder:
    """Deterministic bag-of-ngrams hashing embedder — Demo/CI default (no ML deps)."""

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = text.lower().split()
        for tok in tokens:
            for n in (tok, tok[:3], tok[-3:] if len(tok) > 3 else tok):
                h = int(hashlib.sha256(n.encode()).hexdigest(), 16)
                idx = h % self.dim
                sign = 1.0 if (h >> 8) & 1 else -1.0
                vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class FastEmbedEmbedder:
    """Local MiniLM via fastembed when installed."""

    def __init__(self, model_name: str | None = None) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(
            model_name or os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        )
        # all-MiniLM-L6-v2 dim
        self.dim = int(os.getenv("EMBEDDING_DIM", "384"))

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._model.embed(texts)]


class OpenAICompatEmbedder:
    """OpenAI-compatible embeddings API (openai or gateway)."""

    def __init__(self) -> None:
        import httpx

        self._httpx = httpx
        self.base = os.getenv("EMBEDDING_BASE_URL") or os.getenv(
            "LLM_GATEWAY_URL", "https://api.openai.com/v1"
        )
        self.api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv(
            "LLM_GATEWAY_API_KEY", ""
        )
        self.model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self.dim = int(os.getenv("EMBEDDING_DIM", "1536"))

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise RuntimeError("EMBEDDING_API_KEY / OPENAI_API_KEY required for openai|gateway embedder")
        url = self.base.rstrip("/") + "/embeddings"
        resp = self._httpx.post(
            url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": self.model, "input": texts},
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        data.sort(key=lambda row: row["index"])
        return [row["embedding"] for row in data]


def build_embedder() -> Embedder:
    kind = os.getenv("EMBEDDING_PROVIDER", "hash").strip().lower()
    if kind in {"local", "fastembed"}:
        try:
            return FastEmbedEmbedder()
        except Exception:
            return HashingEmbedder()
    if kind in {"openai", "gateway"}:
        return OpenAICompatEmbedder()
    return HashingEmbedder()


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
