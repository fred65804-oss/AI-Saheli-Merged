"""Specialist contract — THE integration boundary (v1.0).

This module is the single source of truth shared between the orchestrator and
the specialist agents (Poshan / Vatsalya / Shakti) built separately by a
colleague. A specialist is any class that:

  1. exposes a ``capability_card`` (so the orchestrator can route + slot-fill
     without hardcoding scheme knowledge), and
  2. implements ``async def handle(packet: ContextPacket) -> AgentResponse``.

Keep this file STABLE and backwards-compatible. ``contract_version`` is bumped
on breaking changes. Hand this file to the colleague as the spec.

To fetch grounded scheme content, call the ``knowledge_base`` MCP tool —
``mcp/knowledge_base/tool.py:query_knowledge_base`` — rather than hardcoding
answers or citations. See ``agents/specialists/mocks.py`` for example usage.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, Field

from agents.orchestrator.request_type import RequestType

CONTRACT_VERSION = "1.0"

SlotType = Literal["enum", "int", "string", "bool"]


# --------------------------------------------------------------------------- #
# Capability description (drives routing + dynamic questioning)
# --------------------------------------------------------------------------- #
class SlotSpec(BaseModel):
    """A fact an agent needs before it can give a grounded answer.

    The orchestrator collects required slots via dynamic questioning BEFORE
    handing off, so the specialist receives a populated ``collected_facts``.
    """

    name: str = Field(description="machine key, e.g. 'pregnancy_stage'")
    type: SlotType = "string"
    required: bool = True
    priority: int = Field(default=100, description="lower = ask first")
    ask_prompt: str = Field(
        description="canonical question; the orchestrator rephrases it warmly"
    )
    enum_values: list[str] | None = None


class AgentCapabilityCard(BaseModel):
    """Declarative description of one specialist.

    The router prompt, few-shot examples, keyword fast-path, and slot questions
    are all generated from these cards. Adding a scheme = adding a card +
    registering an agent. No orchestrator prompt or graph edits.
    """

    scheme: str = Field(description="stable id: poshan | vatsalya | shakti | general")
    display_name: str
    description: str = Field(description="what this agent handles; used by the router")
    example_utterances: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(
        default_factory=list, description="bilingual hints for the cheap fast-path"
    )
    required_slots: list[SlotSpec] = Field(default_factory=list)
    optional_slots: list[SlotSpec] = Field(default_factory=list)
    safety_critical: bool = False
    fallback: bool = Field(
        default=False,
        description="True for the catch-all agent; excluded from the keyword "
        "fast-path so generic words never beat a specific scheme.",
    )


# --------------------------------------------------------------------------- #
# Handoff payload: orchestrator → specialist
# --------------------------------------------------------------------------- #
class ContextPacket(BaseModel):
    contract_version: str = CONTRACT_VERSION
    session_id: str
    trace_id: str
    intent: str
    user_message: str = Field(description="latest citizen message (normalized)")
    lang: str = "en"
    # Adding 'channel', so that the bot can answer concisely accordingly to the channel
    channel: str = "web"
    citizen_profile: dict = Field(default_factory=dict)
    collected_facts: dict = Field(
        default_factory=dict, description="slot values gathered by the orchestrator"
    )
    conversation_summary: str = ""
    request_type: RequestType = "guidance"


# --------------------------------------------------------------------------- #
# Response: specialist → orchestrator
# --------------------------------------------------------------------------- #
class Citation(BaseModel):
    """A grounding source. Non-negotiable: every factual claim cites one."""

    source_doc: str
    source_url: str = ""
    section: str | None = None


class SlotRequest(BaseModel):
    """A specialist asking the orchestrator to collect one more fact."""

    name: str
    reason: str = ""
    type: SlotType = "string"
    enum_values: list[str] | None = None


class AgentResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    needs: list[SlotRequest] = Field(
        default_factory=list, description="missing facts → triggers slot-filling"
    )
    escalation: bool = Field(
        default=False, description="specialist can also trip the safety path"
    )
    reroute_to: str | None = Field(
        default=None, description="'not mine — send to X' (one hop, orchestrator-bounded)"
    )
    tool_calls: list[str] = Field(default_factory=list)
    confidence: float | None = None


# --------------------------------------------------------------------------- #
# The interface the colleague implements
# --------------------------------------------------------------------------- #
class SpecialistAgent(ABC):
    """Base class for every specialist. Subclass, set ``capability_card``,
    implement ``handle``."""

    capability_card: AgentCapabilityCard

    @property
    def scheme(self) -> str:
        return self.capability_card.scheme

    @abstractmethod
    async def handle(self, packet: ContextPacket) -> AgentResponse:
        """Produce a grounded, cited answer — or return ``needs`` /
        ``reroute_to`` / ``escalation``. Must be safe to call concurrently."""
        raise NotImplementedError

    # Optional streaming hook for a later phase; mocks need not implement it.
    # async def handle_stream(self, packet: ContextPacket) -> AsyncIterator[str]: ...
