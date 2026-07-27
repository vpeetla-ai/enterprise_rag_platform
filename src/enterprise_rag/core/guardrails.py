"""Input and output guardrails — no citation spoofing; optional faithfulness."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from enterprise_rag.core.models import Answer, AssembledContext


@dataclass(frozen=True)
class GuardrailResult:
    allowed: bool
    flags: tuple[str, ...]
    redacted_text: str


class GuardrailService:
    _EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
    _CREDIT_CARD = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
    _DESTRUCTIVE = re.compile(r"\b(delete|refund|terminate|wire|disable account)\b", re.IGNORECASE)
    _INJECT = re.compile(
        r"(ignore\s+(all\s+)?(previous|prior)\s+instructions|jailbreak|reveal\s+the\s+confidential|"
        r"system\s+prompt|dan\s+mode)",
        re.IGNORECASE,
    )

    def inspect_input(self, text: str) -> GuardrailResult:
        flags: list[str] = []
        redacted = self._EMAIL.sub("[REDACTED_EMAIL]", text)
        redacted = self._CREDIT_CARD.sub("[REDACTED_PAYMENT_TOKEN]", redacted)
        if redacted != text:
            flags.append("sensitive_input_redacted")
        if self._DESTRUCTIVE.search(text):
            flags.append("human_approval_required")
        if self._INJECT.search(text):
            flags.append("prompt_injection_suspected")
        return GuardrailResult(allowed=True, flags=tuple(flags), redacted_text=redacted)

    def validate_output(self, answer: str, context: AssembledContext) -> Answer:
        citation_ids = {citation.citation_id for citation in context.citations}
        mentioned = set(re.findall(r"\[(S\d+)\]", answer))
        flags: list[str] = []
        if not mentioned:
            flags.append("missing_citation")
        if mentioned - citation_ids:
            flags.append("unknown_citation")
        grounded = bool(mentioned) and not (mentioned - citation_ids)
        # ADR top-1%: never fabricate citations[0] when unused
        used_citations = tuple(c for c in context.citations if c.citation_id in mentioned)

        if os.getenv("FAITHFULNESS_GATE", "true").strip().lower() in {"1", "true", "yes", "on"}:
            ok, faith_flags = self._faithfulness_check(answer, context)
            flags.extend(faith_flags)
            if not ok:
                grounded = False

        return Answer(
            answer=answer,
            citations=used_citations,
            grounded=grounded,
            risk_flags=tuple(dict.fromkeys(flags)),
        )

    def _faithfulness_check(
        self, answer: str, context: AssembledContext
    ) -> tuple[bool, list[str]]:
        """Lightweight lexical entailment: content words in answer should appear in cited chunks."""
        cited_text = " ".join(
            c.snippet or ""
            for c in context.citations
            if c.citation_id in set(re.findall(r"\[(S\d+)\]", answer))
        )
        if not cited_text.strip():
            # fall back to full context body for extractive answers
            cited_text = context.context
        stop = {
            "the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "for",
            "and", "or", "on", "at", "by", "with", "as", "that", "this", "it", "be",
            "i", "don't", "have", "sufficient", "evidence", "authorized", "sources",
            "answer", "confidently",
        }
        answer_body = re.sub(r"\[S\d+\]", " ", answer).lower()
        words = [w for w in re.findall(r"[a-z0-9]+", answer_body) if w not in stop and len(w) > 2]
        if not words:
            return True, []
        ctx = cited_text.lower()
        missing = [w for w in words if w not in ctx]
        # Allow small fraction of novel tokens (numbers/dates often reformatted)
        if len(missing) / max(len(words), 1) > 0.45:
            return False, ["faithfulness_failed"]
        return True, []
