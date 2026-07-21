"""Real General specialist — cross-scheme discovery & navigation (fallback).

The catch-all for "what schemes can I get?" and anything that doesn't route
cleanly to one scheme. Retrieves across the WHOLE knowledge base (no scheme
filter) and synthesizes a short discovery answer that guides the citizen
toward the right specialist. No deterministic tools apply here, which makes
grounding discipline stricter: no passages → no scheme claims.
"""

from __future__ import annotations

from agents.orchestrator.capabilities import GENERAL_CARD
from agents.orchestrator.llm import StructuredLLM, get_llm
from agents.specialists._grounding import (
    chunks_to_citations,
    retrieve_passages,
    synthesize_answer,
)
from agents.specialists.base import AgentResponse, ContextPacket, SpecialistAgent
from agents.specialists.overview_answer import answer_broad_overview

# Deterministic navigation copy (UX template, not scheme knowledge) — used
# when no LLM is available.
_FALLBACK = (
    "I can help you discover Ministry of Women & Child Development schemes "
    "for nutrition (Poshan), child protection (Vatsalya), and women's "
    "safety and empowerment (Mission Shakti). Tell me a bit about your "
    "situation and I'll guide you to the right one."
)


class RealGeneralAgent(SpecialistAgent):
    capability_card = GENERAL_CARD

    def __init__(self, llm: StructuredLLM | None = None) -> None:
        self._llm = llm

    @property
    def llm(self) -> StructuredLLM:
        if self._llm is None:
            self._llm = get_llm()
        return self._llm

    async def handle(self, packet: ContextPacket) -> AgentResponse:
        if packet.request_type == "overview":
            return await answer_broad_overview(self.llm, packet)

        chunks = await retrieve_passages(packet.user_message, scheme=None)
        citations = chunks_to_citations(chunks)

        answer, synthesized = await synthesize_answer(
            self.llm,
            scheme_display="MoWCD schemes (Poshan, Vatsalya, Mission Shakti)",
            user_message=packet.user_message,
            collected_facts=packet.collected_facts,
            tool_facts=[],
            chunks=chunks,
            fallback=_FALLBACK,
            channel=packet.channel,
        )
        return AgentResponse(
            answer=answer,
            citations=citations,
            tool_calls=["knowledge_base"] if chunks else [],
            confidence=0.75 if synthesized else 0.7,
        )
