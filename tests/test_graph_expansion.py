from __future__ import annotations

import unittest
from datetime import UTC, datetime

from enterprise_rag.core.entity_extract import extract_entities
from enterprise_rag.core.graph_expander import InMemoryGraphExpander
from enterprise_rag.core.ingestion import DocumentChunker
from enterprise_rag.core.models import Chunk, Classification, Principal, RetrievalQuery, SourceDocument
from enterprise_rag.core.pipeline import RagPipeline
from enterprise_rag.core.retrieval import InMemoryHybridRetriever


def _doc(doc_id: str, body: str) -> SourceDocument:
    return SourceDocument(
        document_id=doc_id,
        tenant_id="acme",
        title=doc_id,
        body=body,
        uri=f"https://docs.example/{doc_id}",
        owner="team",
        classification=Classification.INTERNAL,
        allowed_groups=frozenset({"engineering"}),
        metadata={},
        updated_at=datetime.now(UTC),
    )


class GraphExpansionTests(unittest.TestCase):
    def test_entity_extract_finds_domain_terms(self) -> None:
        entities = extract_entities("Enterprise RAG uses hybrid retrieval and evaluation gates.")
        self.assertIn("hybrid", entities)
        self.assertIn("evaluation", entities)

    def test_graph_expander_adds_neighbor_chunks(self) -> None:
        doc_a = _doc("a", "Hybrid retrieval improves Enterprise RAG quality.")
        doc_b = _doc("b", "Evaluation gates protect Enterprise RAG deployments.")
        chunker = DocumentChunker(max_words=40, overlap_words=3)
        chunks = chunker.chunk(doc_a).chunks + chunker.chunk(doc_b).chunks
        tagged = []
        for chunk in chunks:
            entities = extract_entities(chunk.text)
            metadata = dict(chunk.metadata)
            metadata["entities"] = ",".join(entities)
            tagged.append(
                Chunk(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    tenant_id=chunk.tenant_id,
                    text=chunk.text,
                    source_title=chunk.source_title,
                    source_uri=chunk.source_uri,
                    owner=chunk.owner,
                    classification=chunk.classification,
                    allowed_groups=chunk.allowed_groups,
                    metadata=metadata,
                    updated_at=chunk.updated_at,
                )
            )
        retriever = InMemoryHybridRetriever(tuple(tagged))
        expander = InMemoryGraphExpander(tuple(tagged))
        pipeline = RagPipeline(retriever, graph_expander=expander)
        principal = Principal("u1", "acme", frozenset({"engineering"}), Classification.INTERNAL)
        answer = pipeline.answer(RetrievalQuery("Enterprise RAG evaluation", "acme", principal))
        self.assertTrue(answer.grounded)


if __name__ == "__main__":
    unittest.main()
