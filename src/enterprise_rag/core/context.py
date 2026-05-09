"""Context engineering layer for prompt-ready grounded evidence."""

from __future__ import annotations

from enterprise_rag.core.models import AssembledContext, Citation, RetrievalHit


class ContextAssembler:
    def __init__(self, max_context_tokens: int = 1200) -> None:
        self.max_context_tokens = max_context_tokens

    def assemble(self, query: str, hits: tuple[RetrievalHit, ...]) -> AssembledContext:
        seen_text: set[str] = set()
        citations: list[Citation] = []
        sections: list[str] = []
        token_estimate = 0

        for index, hit in enumerate(hits, start=1):
            compressed = self._compress(hit.chunk.text)
            if compressed in seen_text:
                continue
            next_tokens = self._estimate_tokens(compressed)
            if token_estimate + next_tokens > self.max_context_tokens:
                break
            citation_id = f"S{index}"
            seen_text.add(compressed)
            token_estimate += next_tokens
            sections.append(
                f"[{citation_id}] {hit.chunk.source_title}\n"
                f"Owner: {hit.chunk.owner}; Updated: {hit.chunk.updated_at.date().isoformat()}\n"
                f"{compressed}"
            )
            citations.append(
                Citation(
                    citation_id=citation_id,
                    document_id=hit.chunk.document_id,
                    title=hit.chunk.source_title,
                    uri=hit.chunk.source_uri,
                    owner=hit.chunk.owner,
                    updated_at=hit.chunk.updated_at,
                )
            )

        return AssembledContext(
            query=query,
            context="\n\n".join(sections),
            citations=tuple(citations),
            token_estimate=token_estimate,
            retrieval_trace={
                "hit_count": len(hits),
                "used_citation_count": len(citations),
                "max_context_tokens": self.max_context_tokens,
            },
        )

    @staticmethod
    def _compress(text: str) -> str:
        sentences = [part.strip() for part in text.replace("\n", " ").split(".") if part.strip()]
        return ". ".join(sentences[:5]) + ("." if sentences else "")

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text.split()) * 4 // 3)
