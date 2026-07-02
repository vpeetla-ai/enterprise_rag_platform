"""Tests for Langfuse export helper."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from enterprise_rag.ops.langfuse_export import export_recorder, langfuse_export_enabled
from enterprise_rag.ops.telemetry import EventRecorder


class LangfuseExportTests(unittest.TestCase):
    def test_disabled_without_keys(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(langfuse_export_enabled())
            rec = EventRecorder()
            rec.record("rag.retrieve", duration_ms=5)
            self.assertEqual(export_recorder(rec), "skipped")

    @patch.dict(
        os.environ,
        {
            "LANGFUSE_PUBLIC_KEY": "pk-test",
            "LANGFUSE_SECRET_KEY": "sk-test",
            "LANGFUSE_HOST": "https://cloud.langfuse.com",
        },
    )
    @patch("langfuse.Langfuse")
    def test_export_success(self, mock_langfuse_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_langfuse_cls.return_value = mock_client
        mock_client.trace.return_value = mock_trace

        rec = EventRecorder()
        rec.record("rag.retrieve", duration_ms=12, tenant="acme")
        status = export_recorder(
            rec,
            metadata={"tenant_id": "acme"},
            eval_scores={"grounded": True, "citation_count": 3},
        )
        self.assertEqual(status, "exported")
        mock_client.trace.assert_called_once()
        mock_trace.span.assert_called()
        mock_client.score.assert_called()
        mock_client.flush.assert_called_once()

    @patch.dict(
        os.environ,
        {"LANGFUSE_PUBLIC_KEY": "pk-test", "LANGFUSE_SECRET_KEY": "sk-test"},
    )
    @patch("langfuse.Langfuse", side_effect=RuntimeError("boom"))
    def test_export_failed_on_error(self, _mock_langfuse_cls: MagicMock) -> None:
        rec = EventRecorder()
        rec.record("rag.answer")
        self.assertEqual(export_recorder(rec), "failed")


if __name__ == "__main__":
    unittest.main()
