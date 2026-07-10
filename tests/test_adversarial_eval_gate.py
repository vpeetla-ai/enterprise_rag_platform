"""CI gate for golden-eval-registry `enterprise_rag_adversarial_v1`.

Runs principal-spoof and prompt-injection / jailbreak cases against a real
isolated `RagPipeline` seeded with the suite corpus (authorized policy +
restricted secret). Scorer kind: `adversarial_security`.
"""

from __future__ import annotations

import json
import os
import unittest
from datetime import UTC, datetime
from pathlib import Path

from enterprise_rag.core.ingestion import DocumentChunker
from enterprise_rag.core.models import Classification, Principal, RetrievalQuery, SourceDocument
from enterprise_rag.core.pipeline import RagPipeline
from enterprise_rag.core.reranker import ScoreBoostReranker
from enterprise_rag.core.retrieval import InMemoryHybridRetriever

try:
    from golden_eval_registry.runner import score_suite
    from golden_eval_registry.schema import parse_manifest
    from golden_eval_registry.validate import load_jsonl

    GOLDEN_EVAL_REGISTRY_AVAILABLE = True
except ImportError:
    GOLDEN_EVAL_REGISTRY_AVAILABLE = False

REGISTRY_PATH = Path(os.getenv("GOLDEN_EVAL_REGISTRY_PATH", "../golden-eval-registry")).resolve()
SUITE_DIR = REGISTRY_PATH / "suites" / "enterprise_rag_adversarial_v1"


def _load_corpus_docs(corpus_path: Path) -> list[dict]:
    if corpus_path.is_dir():
        docs: list[dict] = []
        for path in sorted(corpus_path.glob("*.json")):
            docs.append(json.loads(path.read_text(encoding="utf-8")))
        return docs
    return [json.loads(corpus_path.read_text(encoding="utf-8"))]


@unittest.skipUnless(
    GOLDEN_EVAL_REGISTRY_AVAILABLE and SUITE_DIR.exists(),
    "golden-eval-registry not available — set GOLDEN_EVAL_REGISTRY_PATH or run in CI",
)
class AdversarialEvalGateTests(unittest.TestCase):
    def test_enterprise_rag_adversarial_v1_suite_passes(self) -> None:
        manifest = parse_manifest(SUITE_DIR / "manifest.json")
        cases = load_jsonl(manifest.cases_path)

        chunks: tuple = ()
        if manifest.corpus_path is not None:
            for corpus in _load_corpus_docs(manifest.corpus_path):
                document = SourceDocument(
                    document_id=corpus["document_id"],
                    tenant_id=corpus["tenant_id"],
                    title=corpus["title"],
                    body=corpus["body"],
                    uri=corpus["uri"],
                    owner=corpus["owner"],
                    classification=Classification(corpus.get("classification", "internal")),
                    allowed_groups=frozenset(corpus.get("allowed_groups", ["engineering"])),
                    metadata=corpus.get("metadata", {}),
                    updated_at=datetime.now(UTC),
                )
                chunks = chunks + DocumentChunker(max_words=80, overlap_words=10).chunk(document).chunks

        pipeline = RagPipeline(InMemoryHybridRetriever(chunks), reranker=ScoreBoostReranker())

        actual_by_id: dict[str, dict] = {}
        for case in cases:
            payload = case["input"]
            principal_input = payload.get("principal", {})
            principal = Principal(
                user_id="adversarial-eval-runner",
                tenant_id=payload["tenant_id"],
                groups=frozenset(principal_input.get("groups", ["engineering"])),
                clearance=Classification(principal_input.get("classification", "internal")),
            )
            answer = pipeline.answer(
                RetrievalQuery(query=payload["query"], tenant_id=payload["tenant_id"], principal=principal)
            )
            actual_by_id[str(case["id"])] = {
                "grounded": answer.grounded,
                "risk_flags": list(answer.risk_flags),
                "citations": [{"document_id": citation.document_id} for citation in answer.citations],
                "answer": answer.answer,
            }

        result = score_suite(manifest, cases, actual_by_id)
        failures = "\n".join(f"{failure.case_id}: {failure.detail}" for failure in result.failures)
        self.assertTrue(result.passed, f"adversarial eval regressions:\n{failures}")


if __name__ == "__main__":
    unittest.main()
