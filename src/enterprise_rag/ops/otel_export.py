"""Export EventRecorder spans to OTLP HTTP when configured."""

from __future__ import annotations

import json
import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from enterprise_rag.ops.telemetry import EventRecorder


def otel_export_enabled() -> bool:
    return bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))


def export_recorder(recorder: EventRecorder, *, service_name: str = "enterprise-rag-platform") -> str:
    """Best-effort OTLP/HTTP JSON export. Returns status: skipped|exported|failed."""
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return "skipped"
    try:
        import httpx
    except ImportError:
        return "failed"

    resource_spans = {
        "resourceSpans": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": service_name}}]},
                "scopeSpans": [
                    {
                        "scope": {"name": "enterprise_rag"},
                        "spans": [
                            {
                                "traceId": _fake_trace_id(event),
                                "spanId": _fake_span_id(index),
                                "name": str(event["name"]),
                                "kind": 1,
                                "startTimeUnixNano": int(float(event["ts"]) * 1_000_000_000),
                                "endTimeUnixNano": int(
                                    (float(event["ts"]) + float(attrs.get("duration_ms", 0)) / 1000) * 1_000_000_000
                                ),
                                "attributes": [
                                    {"key": k, "value": {"stringValue": str(v)}}
                                    for k, v in attrs.items()
                                ],
                            }
                            for index, event in enumerate(recorder.events)
                            for attrs in [event.get("attributes") or {}]
                        ],
                    }
                ],
            }
        ]
    }
    url = endpoint.rstrip("/")
    if not url.endswith("/v1/traces"):
        url = f"{url}/v1/traces"
    headers = {"Content-Type": "application/json"}
    if headers_env := os.getenv("OTEL_EXPORTER_OTLP_HEADERS"):
        for part in headers_env.split(","):
            if "=" in part:
                key, value = part.split("=", 1)
                headers[key.strip()] = value.strip()
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, content=json.dumps(resource_spans), headers=headers)
            response.raise_for_status()
        return "exported"
    except Exception:
        return "failed"


def _fake_trace_id(event: dict) -> str:
    seed = str(event.get("name", "rag")) + str(event.get("ts", time.time()))
    return (seed.encode("utf-8").hex() + "0" * 32)[:32]


def _fake_span_id(index: int) -> str:
    return f"{index:016x}"
