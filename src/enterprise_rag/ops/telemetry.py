"""Minimal telemetry + audit facade used by platform boundaries."""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


@dataclass
class EventRecorder:
    events: list[dict[str, object]] = field(default_factory=list)

    def record(self, name: str, **attributes: object) -> None:
        self.events.append({"name": name, "attributes": attributes, "ts": time.time()})

    @contextmanager
    def span(self, name: str, **attributes: object) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
            status = "ok"
        except Exception:
            status = "error"
            raise
        finally:
            self.record(
                name,
                **attributes,
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )

    def to_jsonl(self) -> str:
        return "\n".join(json.dumps(event, sort_keys=True) for event in self.events)


@dataclass
class LatencyTracker:
    samples_ms: list[float] = field(default_factory=list)

    def observe(self, latency_ms: float) -> None:
        self.samples_ms.append(latency_ms)
        # Cap memory
        if len(self.samples_ms) > 5000:
            self.samples_ms = self.samples_ms[-2500:]

    def p95(self) -> float | None:
        if not self.samples_ms:
            return None
        ordered = sorted(self.samples_ms)
        idx = int(round(0.95 * (len(ordered) - 1)))
        return round(ordered[idx], 2)


def append_audit_event(event: dict[str, object]) -> None:
    """Append one audit line (JSONL). Path via RAG_AUDIT_PATH or default under /tmp."""
    path = Path(os.getenv("RAG_AUDIT_PATH", "/tmp/enterprise_rag_audit.jsonl"))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True) + "\n")
    except OSError:
        # Ephemeral FS / permission — never break request path
        pass
