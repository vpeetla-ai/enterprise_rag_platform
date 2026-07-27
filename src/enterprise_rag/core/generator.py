"""Answer generators — extractive (tests) and LLM grounded (ADR dual profile)."""

from __future__ import annotations

import os
from typing import Protocol

from enterprise_rag.core.text import query_terms, tokenize


class Generator(Protocol):
    def generate(self, query: str, context: str) -> str:
        ...


class ExtractiveGenerator:
    """Deterministic generator used for tests and MOCK_LLM demos."""

    def generate(self, query: str, context: str) -> str:
        if not context:
            return "I do not have enough authorized context to answer."
        terms = set(query_terms(query))
        best_section = ""
        best_score = -1.0
        best_citation = "S1"
        for section in context.split("\n\n"):
            if not section.strip():
                continue
            lines = section.split("\n")
            header = lines[0] if lines else ""
            body = "\n".join(lines[2:]) if len(lines) > 2 else lines[-1]
            title_part = header.split("]", 1)[-1].strip() if header.startswith("[") else header
            section_score = len(terms & set(tokenize(f"{title_part} {body}")))
            section_score += len(terms & set(tokenize(title_part))) * 2
            if section_score > best_score:
                best_score = section_score
                best_section = section
                best_citation = header.split("]", 1)[0].lstrip("[") if header.startswith("[") else "S1"
        if not best_section:
            best_section = context.split("\n\n", maxsplit=1)[0]
            best_citation = best_section.split("]", 1)[0].lstrip("[") if best_section.startswith("[") else "S1"
        evidence = best_section.split("\n")[-1]
        return f"{evidence} [{best_citation}]"


class LlmGroundedGenerator:
    """LLM generator that must cite [S#] from provided context only."""

    SYSTEM = (
        "You are an enterprise RAG assistant. Answer ONLY using the provided context. "
        "Every factual sentence must include a citation like [S1]. "
        "If the context is insufficient, reply exactly: "
        "I don't have sufficient evidence in authorized sources to answer confidently."
    )

    def generate(self, query: str, context: str) -> str:
        import httpx

        api_key = os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY") or os.getenv(
            "LLM_GATEWAY_API_KEY", ""
        )
        base = os.getenv("LLM_GATEWAY_URL") or os.getenv(
            "LLM_BASE_URL", "https://api.groq.com/openai/v1"
        )
        model = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")
        if not api_key and "groq" in base:
            # Fall back extractive if no key
            return ExtractiveGenerator().generate(query, context)
        payload = {
            "model": model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": self.SYSTEM},
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer with citations:",
                },
            ],
        }
        resp = httpx.post(
            base.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return str(data["choices"][0]["message"]["content"]).strip()


def build_generator() -> Generator:
    if os.getenv("MOCK_LLM", "").strip().lower() in {"1", "true", "yes", "on"}:
        return ExtractiveGenerator()
    kind = os.getenv("GENERATOR", "extractive").strip().lower()
    if kind == "llm":
        return LlmGroundedGenerator()
    return ExtractiveGenerator()
