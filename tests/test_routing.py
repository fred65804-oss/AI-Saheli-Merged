"""Router tests — keyword fallback (deterministic) and LLM path via FakeLLM."""

import pytest

from agents.orchestrator.llm import FakeLLM
from agents.orchestrator.router import UNCLEAR, Router, RouterDecision
from agents.specialists.registry import routable_cards

pytestmark = pytest.mark.asyncio


def _router(parse_responder=None):
    return Router(FakeLLM(parse_responder=parse_responder), routable_cards())


@pytest.mark.parametrize(
    "text,expected",
    [
        ("what should i eat during pregnancy", "poshan"),
        ("am i eligible for pmmvy", "shakti"),
        ("how do i adopt a child", "vatsalya"),
    ],
)
async def test_keyword_fallback_routes_specific_schemes(text, expected):
    d = await _router().route(text)
    assert d.intent == expected


async def test_keyword_fallback_unclear_on_no_signal():
    d = await _router().route("hello there")
    assert d.intent == UNCLEAR


async def test_fallback_agent_excluded_from_keyword_competition():
    # "eligible for pmmvy" must beat the generic 'eligible' fallback word.
    d = await _router().route("am i eligible for pmmvy")
    assert d.intent == "shakti"


async def test_llm_decision_is_used_when_valid():
    def responder(system, user, schema):
        return RouterDecision(
            intent="vatsalya", confidence=0.95, rationale="adoption query",
            extracted_slots={"district": "Lucknow"},
        )

    # The message must carry NO strong keyword signal, otherwise route()'s
    # deterministic fast-path returns before the LLM is ever consulted (see
    # test_confident_keyword_route_skips_the_llm below).
    d = await _router(responder).route("I need some guidance please")
    assert d.intent == "vatsalya"
    assert d.confidence == 0.95
    assert d.extracted_slots["district"] == "Lucknow"


async def test_confident_keyword_route_skips_the_llm():
    """route() short-circuits on a confident keyword match (>=0.7) to save an
    LLM call per turn. Pins that: the responder below would return a different
    intent, so if it ever runs the assertion fails."""
    called = False

    def responder(system, user, schema):
        nonlocal called
        called = True
        return RouterDecision(intent="poshan", confidence=0.99)

    d = await _router(responder).route("how do i adopt a child")
    assert d.intent == "vatsalya"
    assert called is False


async def test_invalid_llm_intent_falls_back_to_keywords():
    def responder(system, user, schema):
        return RouterDecision(intent="not_a_real_scheme", confidence=0.9)

    d = await _router(responder).route("what should i eat during pregnancy")
    assert d.intent == "poshan"  # fell back to keyword route
