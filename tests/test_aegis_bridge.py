from __future__ import annotations

import unittest
from unittest.mock import patch

from enterprise_rag.integrations.aegis_bridge import (
    authorize_high_risk_answer,
    gateway_enabled,
    request_gateway,
)


class AegisBridgeTests(unittest.TestCase):
    def test_gateway_disabled_allows_by_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(gateway_enabled())
            decision = authorize_high_risk_answer(
                case_id="case-1",
                risk_flags=("human_approval_required",),
            )
            self.assertTrue(decision.allowed)
            self.assertEqual(decision.decision, "allow")

    def test_high_risk_calls_gateway_when_enabled(self) -> None:
        env = {
            "AEGISAI_API_BASE_URL": "http://aegisai.test",
            "AEGISAI_GATEWAY_ENABLED": "true",
            "AEGISAI_GATEWAY_FAIL_OPEN": "false",
        }
        mock_response = unittest.mock.Mock()
        mock_response.raise_for_status = unittest.mock.Mock()
        mock_response.json.return_value = {
            "gateway_decision": "approval_required",
            "business_explanation": "High-risk RAG answer requires review.",
            "case_id": "case-1",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("enterprise_rag.integrations.aegis_bridge.httpx.Client") as client_cls:
                client_cls.return_value.__enter__.return_value.post.return_value = mock_response
                decision = request_gateway(
                    tool_name="rag.high_risk_answer",
                    action_type="deliver_answer",
                    target_system="enterprise_rag",
                    case_id="case-1",
                )
        self.assertTrue(decision.requires_approval)
        self.assertEqual(decision.decision, "approval_required")


if __name__ == "__main__":
    unittest.main()
