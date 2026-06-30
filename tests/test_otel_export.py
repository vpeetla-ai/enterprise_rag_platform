"""Tests for OTLP export helper."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from enterprise_rag.ops.otel_export import export_recorder, otel_export_enabled
from enterprise_rag.ops.telemetry import EventRecorder


class OtelExportTests(unittest.TestCase):
    def test_disabled_without_endpoint(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(otel_export_enabled())
            rec = EventRecorder()
            rec.record("retrieve", duration_ms=5)
            self.assertEqual(export_recorder(rec), "skipped")

    @patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.example"})
    @patch("httpx.Client")
    def test_export_success(self, mock_client_cls: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client_cls.return_value.__enter__.return_value.post.return_value = mock_response

        rec = EventRecorder()
        rec.record("pipeline.answer", duration_ms=12, tenant="acme")
        status = export_recorder(rec, service_name="test-rag")
        self.assertEqual(status, "exported")
        call_args = mock_client_cls.return_value.__enter__.return_value.post.call_args
        self.assertIn("/v1/traces", call_args[0][0])

    @patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.example"})
    @patch("httpx.Client")
    def test_export_failed_on_http_error(self, mock_client_cls: MagicMock) -> None:
        mock_client_cls.return_value.__enter__.return_value.post.side_effect = RuntimeError("network")

        rec = EventRecorder()
        rec.record("pipeline.answer")
        self.assertEqual(export_recorder(rec), "failed")


if __name__ == "__main__":
    unittest.main()
