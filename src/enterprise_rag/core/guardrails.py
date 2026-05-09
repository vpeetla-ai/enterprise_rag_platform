"""Input and output guardrails for enterprise RAG workflows."""

from __future__ import annotations

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

    def inspect_input(self, text: str) -> GuardrailResult:
        flags: list[str] = []
        redacted = self._EMAIL.sub("[REDACTED_EMAIL]", text)
        redacted = self._CREDIT_CARD.sub("[REDACTED_PAYMENT_TOKEN]", redacted)
        if redacted != text:
            flags.append("sensitive_input_redacted")
        if self._DESTRUCTIVE.search(text):
            flags.append("human_approval_required")
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
        return Answer(answer=answer, citations=context.citations, grounded=grounded, risk_flags=tuple(flags))
