"""Export EventRecorder pipeline spans to Langfuse when LANGFUSE_* keys are set."""

from __future__ import annotations

import os
import uuid
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


def _level_for_event(name: str) -> str:
    if name in {"rag.answer"}:
        return "system"
    if name.startswith("rag."):
        return "node"
    return "trace"


def export_recorder(
    recorder: EventRecorder,
    *,
    trace_name: str = "rag.answer",
    metadata: dict[str, Any] | None = None,
    eval_scores: dict[str, float | int | bool | str] | None = None,
) -> str:
    """Best-effort Langfuse export. Returns: skipped|exported|failed."""
    if not langfuse_export_enabled():
        return "skipped"
    try:
        from langfuse import Langfuse
    except ImportError:
        return "failed"

    trace_id = uuid.uuid4().hex
    try:
        client = Langfuse(
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            environment=os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "production")),
        )
        trace = client.trace(
            id=trace_id,
            name=trace_name,
            metadata=metadata or {},
        )
        for event in recorder.events:
            attrs = dict(event.get("attributes") or {})
            attrs["level"] = _level_for_event(str(event["name"]))
            trace.span(
                name=str(event["name"]),
                metadata=attrs,
            )
        for name, value in (eval_scores or {}).items():
            numeric: float
            if isinstance(value, bool):
                numeric = 1.0 if value else 0.0
            elif isinstance(value, (int, float)):
                numeric = float(value)
            else:
                continue
            client.score(trace_id=trace_id, name=name, value=numeric)
        client.flush()
        return "exported"
    except Exception:
        return "failed"
