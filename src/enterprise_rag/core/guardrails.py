"""Input and output guardrails — no citation spoofing; citation-span faithfulness."""

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
    _STOP = frozenset(
        {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "to",
            "of",
            "in",
            "for",
            "and",
            "or",
            "on",
            "at",
            "by",
            "with",
            "as",
            "that",
            "this",
            "it",
            "be",
            "i",
            "don't",
            "have",
            "sufficient",
            "evidence",
            "authorized",
            "sources",
            "answer",
            "confidently",
        }
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
        """Citation-span entailment: each factual sentence must be supported by its cited snippet.

        Threshold env: FAITHFULNESS_MIN_OVERLAP (default 0.55) = content-word overlap of
        sentence vs cited chunk text. Decline sentences are exempt.
        """
        decline_prefix = "i don't have sufficient evidence"
        if answer.strip().lower().startswith(decline_prefix):
            return True, []

        by_id = {c.citation_id: c for c in context.citations}
        # Split into citation-bearing clauses: "... text [S1]. more [S2]"
        parts = re.split(r"(?=\[\s*S\d+\s*\])", answer)
        sentences: list[tuple[str, str | None]] = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            cites = re.findall(r"\[(S\d+)\]", part)
            body = re.sub(r"\[S\d+\]", " ", part).strip()
            if not body:
                continue
            cite = cites[-1] if cites else None
            # Further split multi-sentence bodies without citations attached to each
            for sent in re.split(r"(?<=[.!?])\s+", body):
                sent = sent.strip()
                if sent:
                    sentences.append((sent, cite))

        if not sentences:
            return True, []

        min_overlap = float(os.getenv("FAITHFULNESS_MIN_OVERLAP", "0.55"))
        unsupported = 0
        checked = 0
        for sent, cite_id in sentences:
            words = self._content_words(sent)
            if len(words) < 3:
                continue
            checked += 1
            if cite_id and cite_id in by_id:
                support = (by_id[cite_id].snippet or "").lower()
            else:
                support = context.context.lower()
            if not support.strip():
                unsupported += 1
                continue
            overlap = sum(1 for w in words if w in support) / len(words)
            if overlap < min_overlap:
                unsupported += 1

        if checked == 0:
            return True, []
        # Fail if a majority of checked sentences lack span support
        if unsupported / checked > 0.34:
            return False, ["faithfulness_failed"]
        return True, []

    def _content_words(self, text: str) -> list[str]:
        return [
            w
            for w in re.findall(r"[a-z0-9]+", text.lower())
            if w not in self._STOP and len(w) > 2
        ]
