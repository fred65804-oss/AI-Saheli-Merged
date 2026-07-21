"""Specialist registry — the single place agents are wired in.

The orchestrator routes to ``SPECIALISTS[intent]`` and discovers routing
metadata from each agent's ``capability_card`` (it never hardcodes scheme
knowledge). The real agents resolve their LLM lazily from env-driven settings
(``get_llm``): with a key they synthesize grounded answers; without one they
serve deterministic tool-composed fallbacks (offline mode, tests).
"""

from __future__ import annotations

from agents.specialists.base import AgentCapabilityCard, SpecialistAgent
from agents.specialists.general import RealGeneralAgent
from agents.specialists.poshan import RealPoshanAgent
from agents.specialists.shakti import RealShaktiAgent
from agents.specialists.vatsalya import RealVatsalyaAgent

# intent id → specialist instance
SPECIALISTS: dict[str, SpecialistAgent] = {
    "poshan": RealPoshanAgent(),
    "vatsalya": RealVatsalyaAgent(),
    "shakti": RealShaktiAgent(),
    "general": RealGeneralAgent(),
}


def get_specialist(intent: str) -> SpecialistAgent | None:
    return SPECIALISTS.get(intent)


def routable_cards() -> list[AgentCapabilityCard]:
    """Cards of all registered agents — what the router builds its prompt from."""
    return [agent.capability_card for agent in SPECIALISTS.values()]


def get_card(intent: str) -> AgentCapabilityCard | None:
    agent = SPECIALISTS.get(intent)
    return agent.capability_card if agent else None
