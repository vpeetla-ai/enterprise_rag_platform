"""AegisAI governance gateway bridge for high-risk RAG actions."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]


@dataclass(frozen=True)
class GatewayDecision:
    decision: str
    allowed: bool
    requires_approval: bool
    blocked: bool
    case_id: str
    reason: str
    raw: dict[str, Any] | None = None


def _bool_env(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def gateway_enabled() -> bool:
    return bool(os.getenv("AEGISAI_API_BASE_URL")) and _bool_env("AEGISAI_GATEWAY_ENABLED", "true")


def request_gateway(
    *,
    tool_name: str,
    action_type: str,
    target_system: str,
    case_id: str,
    customer_impact: bool = False,
    safety_score: float = 0.7,
) -> GatewayDecision:
    """Call AegisAI gateway before side-effecting or high-risk RAG operations."""
    if not gateway_enabled():
        return GatewayDecision(
            decision="allow",
            allowed=True,
            requires_approval=False,
            blocked=False,
            case_id=case_id,
            reason="gateway_disabled",
        )
    if httpx is None:
        if _bool_env("AEGISAI_GATEWAY_FAIL_OPEN", "true"):
            return GatewayDecision(
                decision="allow",
                allowed=True,
                requires_approval=False,
                blocked=False,
                case_id=case_id,
                reason="httpx_missing_fail_open",
            )
        return GatewayDecision(
            decision="block",
            allowed=False,
            requires_approval=False,
            blocked=True,
            case_id=case_id,
            reason="httpx_missing",
        )

    base = os.environ["AEGISAI_API_BASE_URL"].rstrip("/")
    payload = {
        "tenant_id": os.getenv("AEGISAI_TENANT_ID", "bank-demo"),
        "agent_id": os.getenv("AEGISAI_AGENT_ID", "enterprise-rag-platform"),
        "principal_id": os.getenv("AEGISAI_PRINCIPAL_ID", "enterprise-rag-principal"),
        "tool_name": tool_name,
        "action_type": action_type,
        "target_system": target_system,
        "amount_usd": 0.0,
        "data_classification": "internal",
        "reversible": True,
        "customer_impact": customer_impact,
        "grounding_score": 0.9,
        "safety_score": safety_score,
        "policy_compliance_score": 0.85,
        "case_id": case_id,
        "proposal_id": case_id,
    }
    headers = {"Content-Type": "application/json"}
    if bearer := os.getenv("AEGISAI_AUTH_BEARER"):
        headers["Authorization"] = f"Bearer {bearer}"
    if principal := os.getenv("AEGISAI_PRINCIPAL_ID", "enterprise-rag-principal"):
        headers["X-AegisAI-Principal"] = principal
    if tenant := os.getenv("AEGISAI_TENANT_ID", "bank-demo"):
        headers["X-AegisAI-Tenant"] = tenant
    headers["X-AegisAI-Roles"] = os.getenv("AEGISAI_ROLES", "workflow_owner,execution_broker")

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{base}/api/gateway/tool-request", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:  # noqa: BLE001
        if _bool_env("AEGISAI_GATEWAY_FAIL_OPEN", "true"):
            return GatewayDecision(
                decision="allow",
                allowed=True,
                requires_approval=False,
                blocked=False,
                case_id=case_id,
                reason=f"gateway_error_fail_open:{exc}",
            )
        return GatewayDecision(
            decision="block",
            allowed=False,
            requires_approval=False,
            blocked=True,
            case_id=case_id,
            reason=f"gateway_error:{exc}",
        )

    decision = str(data.get("gateway_decision", "block"))
    token = data.get("execution_token")
    allowed = decision == "allow" and bool(token)
    requires_approval = decision == "approval_required"
    blocked = decision in {"block", "deny", "frozen"}
    return GatewayDecision(
        decision=decision,
        allowed=allowed,
        requires_approval=requires_approval,
        blocked=blocked,
        case_id=str(data.get("case_id") or case_id),
        reason=str(data.get("business_explanation", decision)),
        raw=data,
    )


def authorize_high_risk_answer(*, case_id: str, risk_flags: tuple[str, ...]) -> GatewayDecision:
    if "human_approval_required" not in risk_flags:
        return GatewayDecision(
            decision="allow",
            allowed=True,
            requires_approval=False,
            blocked=False,
            case_id=case_id,
            reason="no_hitl_flag",
        )
    return request_gateway(
        tool_name="rag.high_risk_answer",
        action_type="deliver_answer",
        target_system="enterprise_rag",
        case_id=case_id,
        safety_score=0.55,
    )


def authorize_ingest(*, case_id: str, document_id: str) -> GatewayDecision:
    return request_gateway(
        tool_name="rag.ingest_document",
        action_type="ingest",
        target_system=document_id,
        case_id=case_id,
    )
