"""Audit trace — governance requirement and the dashboard's data feed.

Every turn emits one structured ``InteractionTrace`` (the routing decision, the
safety verdict, per-node latency, the agent used, tool calls, citation count,
escalation/grounding flags). Written as JSONL now via a swappable ``TraceSink``;
the same records will later land in Postgres and power the analytics dashboard.

Designed to hold ZERO raw PII beyond the message text itself (synthetic personas
only in the demo); a production sink would redact ``user_message``.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Protocol

from pydantic import BaseModel, Field

from agents.orchestrator.request_type import RequestType
from apps.backend.config import get_settings


class TraceEvent(BaseModel):
    node: str
    latency_ms: float
    detail: dict = Field(default_factory=dict)


class InteractionTrace(BaseModel):
    trace_id: str
    session_id: str
    channel: str = "web"
    lang: str = "en"
    user_message: str = ""
    intent: str | None = None
    request_type: RequestType | None = None
    confidence: float | None = None
    safety_source: str | None = None       # lexicon | llm | none
    safety_category: str | None = None
    escalation: bool = False
    agent_used: str | None = None
    district: str | None = None             # coarse geo from collected_facts (no PII)
    tool_calls: list[str] = Field(default_factory=list)
    citation_count: int = 0
    awaiting_input: bool = False
    grounding_ok: bool = True
    fallback: bool = False                  # specialist error/timeout fallback
    events: list[TraceEvent] = Field(default_factory=list)
    total_latency_ms: float = 0.0
    created_at: str = ""


# --------------------------------------------------------------------------- #
# Sinks
# --------------------------------------------------------------------------- #
class TraceSink(Protocol):
    def write(self, trace: InteractionTrace) -> None: ...


class JSONLTraceSink:
    """Append one JSON line per interaction. Swap for a Postgres sink later."""

    def __init__(self, path: str) -> None:
        self._path = path
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def write(self, trace: InteractionTrace) -> None:
        with open(self._path, "a", encoding="utf-8") as fh:
            fh.write(trace.model_dump_json() + "\n")


class NullTraceSink:
    def write(self, trace: InteractionTrace) -> None:  # pragma: no cover
        pass


_default_sink: TraceSink | None = None


def default_sink() -> TraceSink:
    global _default_sink
    if _default_sink is None:
        _default_sink = JSONLTraceSink(get_settings().trace_sink_path)
    return _default_sink


# --------------------------------------------------------------------------- #
# Timing helper
# --------------------------------------------------------------------------- #
class Stopwatch:
    """Per-node latency timer: ``with Stopwatch() as sw: ...; sw.ms``.

    ``ms`` computes elapsed time live on access, so it is accurate whether
    read after the ``with`` block exits OR from inside it (e.g. an ``except``
    handler mid-block, before ``__exit__`` has run). A prior version only set
    ``ms`` in ``__exit__`` — reading it from inside the block always returned
    the initial 0.0, silently hiding the true duration of a failed/timed-out
    call from the audit trace (a handoff that timed out at 20s was logged
    with ~0ms latency).
    """

    def __enter__(self) -> "Stopwatch":
        self._start = time.perf_counter()
        self._end: float | None = None
        return self

    def __exit__(self, *exc) -> None:
        self._end = time.perf_counter()

    @property
    def ms(self) -> float:
        end = self._end if self._end is not None else time.perf_counter()
        return round((end - self._start) * 1000, 2)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
