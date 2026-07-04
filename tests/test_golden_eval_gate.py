"""Real merge gate: runs the shared `enterprise_rag_golden_v1` suite from
vpeetla-ai/golden-eval-registry against this repo's real `RagPipeline` (the
same core class the live API wraps, including real guardrail-driven
risk_flags) — closes that registry's own backlog item that fixtures existed
but nothing executed them as a CI gate.

Builds an isolated pipeline seeded only with the suite's own corpus, rather
than reusing the API's module-level singleton — that singleton also seeds
unrelated demo documents (see api/app.py's `_seed_demo_corpus`) which
compete for retrieval ranking against the suite's `policy-001` fixture and
would give false regressions unrelated to this repo's own behavior. This
mirrors the existing tests/test_golden.py's isolated-pipeline pattern.

Skips locally when the sibling registry repo isn't checked out; CI always
checks it out first (see .github/workflows/tests.yml).
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
SUITE_DIR = REGISTRY_PATH / "suites" / "enterprise_rag_golden_v1"


@unittest.skipUnless(
    GOLDEN_EVAL_REGISTRY_AVAILABLE and SUITE_DIR.exists(),
    "golden-eval-registry not available — set GOLDEN_EVAL_REGISTRY_PATH or run in CI",
)
class GoldenEvalGateTests(unittest.TestCase):
    def test_enterprise_rag_golden_v1_suite_passes(self) -> None:
        manifest = parse_manifest(SUITE_DIR / "manifest.json")
        cases = load_jsonl(manifest.cases_path)

        chunks: tuple = ()
        if manifest.corpus_path is not None:
            corpus = json.loads(manifest.corpus_path.read_text(encoding="utf-8"))
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
            chunks = DocumentChunker(max_words=80, overlap_words=10).chunk(document).chunks

        pipeline = RagPipeline(InMemoryHybridRetriever(chunks), reranker=ScoreBoostReranker())

        actual_by_id: dict[str, dict] = {}
        for case in cases:
            payload = case["input"]
            principal_input = payload.get("principal", {})
            principal = Principal(
                user_id="golden-eval-runner",
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
            }

        result = score_suite(manifest, cases, actual_by_id)
        failures = "\n".join(f"{failure.case_id}: {failure.detail}" for failure in result.failures)
        self.assertTrue(result.passed, f"golden eval regressions:\n{failures}")


if __name__ == "__main__":
    unittest.main()
