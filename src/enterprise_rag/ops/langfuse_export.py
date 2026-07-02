"""Export EventRecorder pipeline spans to Langfuse when LANGFUSE_* keys are set."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from enterprise_rag.ops.telemetry import EventRecorder


def langfuse_export_enabled() -> bool:
    public = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret = os.getenv("LANGFUSE_SECRET_KEY", "")
    if not public or not secret:
        return False
    enabled = os.getenv("LANGFUSE_ENABLED", "true").lower() not in {"0", "false", "no"}
    return enabled


def _as_type_for_event(name: str) -> str:
    if name.startswith("rag.retrieve"):
        return "retriever"
    if name.startswith("rag.generate"):
        return "generation"
    return "span"


def export_recorder(
    recorder: EventRecorder,
    *,
    trace_name: str = "rag.answer",
    metadata: dict[str, Any] | None = None,
    eval_scores: dict[str, float | int | bool | str] | None = None,
) -> str:
    """Best-effort Langfuse export (SDK v3). Returns: skipped|exported|failed."""
    if not langfuse_export_enabled():
        return "skipped"
    try:
        from langfuse import Langfuse
    except ImportError:
        return "failed"

    try:
        client = Langfuse(
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            environment=os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "production")),
        )
        trace_id = client.create_trace_id()
        trace_context = {"trace_id": trace_id}

        root = client.start_observation(
            trace_context=trace_context,
            name=trace_name,
            as_type="chain",
            metadata=metadata or {},
        )
        root.end()

        for event in recorder.events:
            attrs = dict(event.get("attributes") or {})
            span = client.start_observation(
                trace_context=trace_context,
                name=str(event["name"]),
                as_type=_as_type_for_event(str(event["name"])),
                metadata=attrs,
            )
            span.end()

        for name, value in (eval_scores or {}).items():
            if isinstance(value, bool):
                client.create_score(
                    trace_id=trace_id,
                    name=name,
                    value=1.0 if value else 0.0,
                    data_type="BOOLEAN",
                )
            elif isinstance(value, (int, float)):
                client.create_score(trace_id=trace_id, name=name, value=float(value))
            elif isinstance(value, str):
                client.create_score(trace_id=trace_id, name=name, value=value, data_type="CATEGORICAL")

        client.flush()
        return "exported"
    except Exception:
        return "failed"
