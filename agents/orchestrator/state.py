"""Orchestrator state (LangGraph) + the citizen profile model.

``AgentState`` is a TypedDict carried across turns by the checkpointer, keyed by
``session_id`` (thread). Per-turn inputs (``user_message``) are supplied on each
invoke; durable facts (``collected_facts``, ``intent``, ``awaiting_slot``)
persist automatically.
"""

from __future__ import annotations

from typing import Any, TypedDict

from pydantic import BaseModel

from agents.orchestrator.request_type import RequestType

class CitizenProfile(BaseModel):
    """Synthetic-only in the demo. Built up from collected slots."""

    lang: str = "en"
    district: str | None = None
    role: str | None = None
    pregnancy_stage: str | None = None
    child_age_months: int | None = None
    income_band: str | None = None


class AgentState(TypedDict, total=False):
    # identity / channel
    session_id: str
    trace_id: str
    channel: str
    lang: str

    # turn input
    user_message: str
    conversation_summary: str

    # accumulated knowledge
    collected_facts: dict[str, Any]
    citizen_profile: dict[str, Any]

    # routing
    intent: str | None
    confidence: float | None
    active_agent: str | None
    reroute_count: int
    request_type: RequestType

    # dynamic questioning
    awaiting_slot: str | None              # slot name we asked for last turn
    awaiting_slot_spec: dict[str, Any] | None
    extra_required_slots: list[dict[str, Any]]  # specialist-requested slots
    pending_ask_spec: dict[str, Any] | None     # slot chosen this turn to ask
    slot_attempts: int                          # consecutive failed re-asks of the pending slot
    _handoff_outcome: str | None                # scratch: handoff edge selector
    _slot_outcome: str | None                   # scratch: continue_slot edge selector

    # safety
    escalation: bool
    safety_source: str | None
    safety_category: str | None

    # output
    response: str
    citations: list[dict[str, Any]]
    awaiting_input: bool
    tool_calls: list[str]
    grounding_ok: bool
    fallback: bool

    # audit
    trace_events: list[dict[str, Any]]


def new_turn_defaults() -> dict[str, Any]:
    """Per-turn output fields reset at the start of each invoke."""
    return {
        "response": "",
        "citations": [],
        "awaiting_input": False,
        "tool_calls": [],
        "grounding_ok": True,
        "fallback": False,
        "trace_events": [],
        "escalation": False,
        "pending_ask_spec": None,
        "_handoff_outcome": None,
        "_slot_outcome": None,
    }
