"""End-to-end graph tests for the 4 demo journeys — offline (FakeLLM)."""

import pytest

from agents.orchestrator.graph import build_orchestrator, run_turn
from agents.orchestrator.llm import FakeLLM
from agents.orchestrator.trace import NullTraceSink
from apps.backend.config import get_settings

pytestmark = pytest.mark.asyncio


def _graph():
    return build_orchestrator(
        llm=FakeLLM(), settings=get_settings(), sink=NullTraceSink()
    )


async def test_journey3_safety_escalation_overrides_routing():
    g = _graph()
    s = await run_turn(g, session_id="t3", message="mera pati mujhe maar raha hai")
    assert s["escalation"] is True
    assert "181" in s["response"] and "112" in s["response"]
    # never routed to a specialist
    assert s.get("intent") is None


async def test_multi_intent_safety_wins():
    g = _graph()
    s = await run_turn(
        g, session_id="tm", message="I am pregnant and my husband hits me"
    )
    assert s["escalation"] is True
    assert s.get("intent") is None  # poshan never reached


async def test_journey4_pmmvy_routes_to_shakti_with_citation():
    """PMMVY needs child_order, then a socio-economic fact, before it can give
    a definitive verdict — each missing fact is asked as a tracked slot
    (awaiting_input=True) rather than answered with a guess."""
    g = _graph()
    sid = "t4"
    s1 = await run_turn(g, session_id=sid, message="am i eligible for pmmvy")
    assert s1["intent"] == "shakti"
    assert s1["escalation"] is False
    assert s1["awaiting_input"] is True  # asks child_order

    s2 = await run_turn(g, session_id=sid, message="first child")
    assert s2["awaiting_input"] is True  # now asks the socio-economic fact

    s3 = await run_turn(g, session_id=sid, message="we are BPL")
    assert s3["awaiting_input"] is False
    assert len(s3["citations"]) >= 1
    assert "PMMVY" in s3["response"]


async def test_pmmvy_second_girl_child_accepts_st_category():
    """Regression: an ST category must resolve PMMVY, not clear the intent."""
    g = _graph()
    sid = "pmmvy-st"
    await run_turn(g, session_id=sid, message="am i eligible for pmmvy")
    s2 = await run_turn(g, session_id=sid, message="Second child. She is a girl")
    assert s2["awaiting_input"] is True
    assert s2["awaiting_slot"] == "pmmvy_qualifier"
    assert s2["collected_facts"]["second_child_is_girl"] == "true"

    s3 = await run_turn(g, session_id=sid, message="Category - ST")
    assert s3["awaiting_input"] is False
    assert s3["intent"] == "shakti"
    assert s3["collected_facts"]["pmmvy_qualifier"] == "st"
    assert "PMMVY" in s3["response"]


async def test_journey1_dynamic_slot_filling_then_answer():
    g = _graph()
    sid = "t1"
    s1 = await run_turn(g, session_id=sid, message="what should i eat during pregnancy")
    assert s1["intent"] == "poshan"
    assert s1["awaiting_input"] is True  # asked beneficiary_type

    s2 = await run_turn(g, session_id=sid, message="I am pregnant")
    assert s2["collected_facts"].get("beneficiary_type") == "pregnant_woman"
    assert s2["awaiting_input"] is True  # specialist asked pregnancy_stage

    s3 = await run_turn(g, session_id=sid, message="6th month")
    assert s3["collected_facts"].get("pregnancy_stage") == "2nd_trimester"
    assert s3["awaiting_input"] is False
    assert len(s3["citations"]) >= 1
    assert "nutrition" in s3["response"].lower() or "ration" in s3["response"].lower()


async def test_topic_change_during_slot_fill_switches_intent():
    """Mid-slot-fill, a new request must abandon the pending question and
    re-route — not be swallowed as the answer. Regression for the stuck loop
    where 'how do I adopt a child' was read as beneficiary_type=child."""
    g = _graph()
    sid = "tc"
    s1 = await run_turn(g, session_id=sid, message="what should i eat during pregnancy")
    assert s1["intent"] == "poshan"
    assert s1["awaiting_input"] is True  # asked beneficiary_type

    s2 = await run_turn(g, session_id=sid, message="how do I adopt a child")
    assert s2["intent"] == "vatsalya"  # switched, not stuck on poshan
    assert "CARA" in s2["response"] or "adopt" in s2["response"].lower()


async def test_unparseable_reply_does_not_loop_forever():
    """An answer we can't parse re-asks at most twice, then clarifies — it must
    never loop on the same slot question indefinitely."""
    g = _graph()
    sid = "loop"
    s1 = await run_turn(g, session_id=sid, message="what should i eat during pregnancy")
    assert s1["awaiting_input"] is True
    q1 = s1["response"]

    s2 = await run_turn(g, session_id=sid, message="zxcvbnm qwerty")
    # first unparseable reply: re-asks the same slot
    assert s2["awaiting_input"] is True

    s3 = await run_turn(g, session_id=sid, message="asdfghjkl")
    # second failure: gives up the slot and clarifies instead of re-asking again
    assert s3["intent"] is None
    assert q1 not in s3["response"] or "nutrition" in s3["response"].lower()


async def test_specialist_timeout_falls_back_gracefully():
    import asyncio

    from agents.orchestrator.capabilities import SHAKTI_CARD
    from agents.specialists import registry
    from agents.specialists.base import AgentResponse, ContextPacket, SpecialistAgent

    class SlowAgent(SpecialistAgent):
        capability_card = SHAKTI_CARD

        async def handle(self, packet: ContextPacket) -> AgentResponse:
            await asyncio.sleep(5)  # always longer than the 0.05s timeout below
            return AgentResponse(answer="too late")

    original = registry.SPECIALISTS["shakti"]
    registry.SPECIALISTS["shakti"] = SlowAgent()
    try:
        settings = get_settings()
        settings.specialist_timeout_seconds = 0.05
        g = build_orchestrator(llm=FakeLLM(), settings=settings, sink=NullTraceSink())
        s = await run_turn(g, session_id="to", message="am i eligible for pmmvy")
        assert s["fallback"] is True
        assert "trouble" in s["response"].lower() or "try again" in s["response"].lower()
    finally:
        registry.SPECIALISTS["shakti"] = original
        get_settings().specialist_timeout_seconds = 20.0
