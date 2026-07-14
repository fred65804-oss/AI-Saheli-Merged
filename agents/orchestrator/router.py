"""Hybrid router — capability-card-driven intent classification.

Two paths, by design:
  - LLM path (default when a key is present): a single structured call returns
    intent + confidence + slots extracted from the message, in one pass.
  - Keyword fallback: a deterministic card-keyword heuristic used when the LLM
    returns nothing usable (e.g. offline / no API key / FakeLLM default). This
    keeps the CLI, tests, and demo working without a key.

The router NEVER hardcodes scheme names — it is built entirely from the cards of
registered agents. Add an agent, the router adapts.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.guardrails.lexicon import normalize
from agents.orchestrator.llm import StructuredLLM
from agents.specialists.base import AgentCapabilityCard

UNCLEAR = "unclear"


class RouterDecision(BaseModel):
    """Structured router output (also the LLM's enforced schema)."""

    intent: str = Field(
        default=UNCLEAR,
        description="the scheme id to route to, or 'unclear' if ambiguous",
    )
    confidence: float = Field(default=0.0, description="0.0-1.0")
    rationale: str = Field(default="")
    extracted_slots: dict[str, str] = Field(
        default_factory=dict, description="facts pulled from the message"
    )
    secondary_intents: list[str] = Field(default_factory=list)


def _slot_catalogue(cards: list[AgentCapabilityCard]) -> str:
    """The extractable facts, derived FROM the cards (never hardcoded).

    Without this the router had no idea which slot names the specialists
    actually require, so it never extracted them and the orchestrator asked a
    question the citizen had already answered ("I need a plan for my 5-month-old"
    → "is this for a pregnant woman, a new mother, or a child?").
    """
    lines: list[str] = []
    seen: set[str] = set()
    for c in cards:
        for spec in list(c.required_slots) + list(c.optional_slots):
            if spec.name in seen:
                continue
            seen.add(spec.name)
            detail = f"  - {spec.name} ({spec.type}"
            if spec.enum_values:
                detail += f"; one of: {', '.join(spec.enum_values)}"
            detail += ")"
            if spec.required:
                detail += "  [REQUIRED by " + c.scheme + " — extract it whenever the message implies it]"
            lines.append(detail)
    return "\n".join(lines)


def build_router_system(cards: list[AgentCapabilityCard]) -> str:
    """Generate the router system prompt from the registered cards."""
    blocks = []
    for c in cards:
        examples = "; ".join(c.example_utterances[:5])
        blocks.append(
            f"- intent id: {c.scheme}\n"
            f"  handles: {c.description}\n"
            f"  examples: {examples}"
        )
    catalogue = "\n".join(blocks)
    ids = ", ".join(c.scheme for c in cards)
    return (
        "You are the routing brain of AI Saheli, a Government of India women & "
        "child welfare assistant. Classify the citizen's message into exactly one "
        "specialist intent, or 'unclear' if it is too ambiguous to route.\n\n"
        f"Available intents:\n{catalogue}\n\n"
        f"Return intent as one of: {ids}, unclear.\n\n"
        "Then extract EVERY fact the message already states into extracted_slots, "
        "using exactly these keys and (for enums) exactly these values:\n"
        f"{_slot_catalogue(cards)}\n\n"
        "Extraction rules — these prevent us asking the citizen something they "
        "already told us:\n"
        "  * 'my 5 month old' / 'my baby' / 'my son' → beneficiary_type=child "
        "(and child_age_months=5 when an age is given).\n"
        "  * 'I am pregnant' / 'pregnancy mein' → beneficiary_type=pregnant_woman.\n"
        "  * 'I just delivered' / 'breastfeeding' → beneficiary_type=lactating_mother.\n"
        "  * Only emit a key when the message genuinely supports it — never guess.\n\n"
        "Give a calibrated confidence in [0,1]. If the message mixes topics, pick "
        "the primary one and list others in secondary_intents.\n"
        "Messages may be in Hindi, English, or romanized Hinglish."
    )


def keyword_scores(message: str, cards: list[AgentCapabilityCard]) -> dict[str, int]:
    """Count distinct card keywords present in the message."""
    norm = normalize(message)
    scores: dict[str, int] = {}
    for c in cards:
        if c.fallback:
            # Fallback agent never competes on generic words in the keyword path.
            continue
        hits = {kw for kw in c.keywords if normalize(kw) in norm}
        if hits:
            scores[c.scheme] = len(hits)
    return scores


def _keyword_route(message: str, cards: list[AgentCapabilityCard]) -> RouterDecision:
    """Deterministic fallback when the LLM gives nothing usable."""
    scores = keyword_scores(message, cards)
    if not scores:
        return RouterDecision(
            intent=UNCLEAR, confidence=0.3, rationale="no keyword signal"
        )
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_scheme, top_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0
    if top_score == runner_up:
        # Tie → ambiguous, ask a clarifying question rather than guess.
        return RouterDecision(
            intent=UNCLEAR,
            confidence=0.4,
            rationale=f"keyword tie between {ranked[0][0]} and {ranked[1][0]}",
            secondary_intents=[s for s, _ in ranked[:2]],
        )
    confidence = min(0.6 + 0.1 * (top_score - runner_up), 0.9)
    return RouterDecision(
        intent=top_scheme,
        confidence=confidence,
        rationale=f"keyword match ({top_score} hits)",
        secondary_intents=[s for s, _ in ranked[1:3]],
    )


class Router:
    def __init__(self, llm: StructuredLLM, cards: list[AgentCapabilityCard]) -> None:
        self._llm = llm
        self._cards = cards
        self._allowed = {c.scheme for c in cards} | {UNCLEAR}

    async def route(
        self,
        message: str,
        *,
        conversation_summary: str = "",
    ) -> RouterDecision:
        system = build_router_system(self._cards)
        user = message
        if conversation_summary:
            user = f"[conversation so far: {conversation_summary}]\n{message}"

        try:
            decision = await self._llm.parse(system, user, RouterDecision)
        except Exception:
            decision = RouterDecision()  # force keyword fallback below

        # Validate the LLM's intent; fall back to keywords if it is empty/invalid.
        if decision.intent not in self._allowed or (
            decision.intent == UNCLEAR and decision.confidence == 0.0
        ):
            return _keyword_route(message, self._cards)
        return decision
