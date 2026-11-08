"""Trace tracking for agent runs.

Each resolve() call produces a Trace — a list of steps recording tool calls,
LLM outputs, validation results, and safety flags.  Traces are stored in-memory
and retrievable by trace_id.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class TraceStep:
    kind: str  # tool_call | llm_response | validation | safety_flag | fallback
    data: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Trace:
    """Ordered log of everything that happened during one resolve() call."""

    def __init__(self, trace_id: str | None = None) -> None:
        self.trace_id: str = trace_id or uuid.uuid4().hex[:12]
        self.steps: list[TraceStep] = []

    def add(self, kind: str, data: dict[str, Any]) -> None:
        self.steps.append(TraceStep(kind=kind, data=data))

    def to_dicts(self) -> list[dict]:
        return [{"kind": s.kind, "data": s.data, "timestamp": s.timestamp} for s in self.steps]


# ---------------------------------------------------------------------------
# In-memory trace store
# ---------------------------------------------------------------------------
_TRACES: dict[str, Trace] = {}


def store_trace(trace: Trace) -> None:
    _TRACES[trace.trace_id] = trace


def get_trace(trace_id: str) -> Trace | None:
    return _TRACES.get(trace_id)


def clear_traces() -> None:
    """For test cleanup."""
    _TRACES.clear()
