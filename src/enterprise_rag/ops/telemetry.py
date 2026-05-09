"""Minimal telemetry facade used by platform boundaries."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
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
