"""Real specialist agents — grounding, synthesis, and fallback discipline.

All offline-deterministic: a scripted FakeLLM plays the synthesis model, so we
verify the CONTRACT (verified facts reach the prompt, fallback never
hallucinates, red-flags route to the ANM, follow-up questions register as a
real tracked slot rather than only prose) without any key or network.
"""

import pytest

from agents.orchestrator.llm import FakeLLM
from agents.specialists.base import ContextPacket
from agents.specialists.general import RealGeneralAgent
from agents.specialists.poshan import RealPoshanAgent
from agents.specialists.shakti import RealShaktiAgent
from agents.specialists.vatsalya import RealVatsalyaAgent

pytestmark = pytest.mark.asyncio


def _packet(message: str, intent: str, facts: dict | None = None) -> ContextPacket:
    return ContextPacket(
        session_id="s1",
        trace_id="t1",
        intent=intent,
        user_message=message,
        collected_facts=facts or {},
    )


class PromptCapturingLLM(FakeLLM):
    """Records the synthesis prompt and answers with a marker string."""

    def __init__(self, reply: str = "SYNTHESIZED ANSWER") -> None:
        super().__init__()
        self.system: str | None = None
        self.user: str | None = None
        self._reply = reply

    async def complete(self, system: str, user: str, *, fast: bool = True) -> str:
        self.system = system
        self.user = user
        return self._reply


# --------------------------------------------------------------------------- #
# Synthesis path: verified tool facts must reach the LLM prompt verbatim
# --------------------------------------------------------------------------- #
async def test_poshan_synthesis_prompt_carries_verified_facts():
    llm = PromptCapturingLLM()
    agent = RealPoshanAgent(llm=llm)
    resp = await agent.handle(
        _packet(
            "what should I eat during pregnancy",
            "poshan",
            {"beneficiary_type": "pregnant_woman", "pregnancy_stage": "2nd_trimester"},
        )
    )
    assert resp.answer == "SYNTHESIZED ANSWER"
    assert "eligibility" in resp.tool_calls
    assert llm.user is not None
    # The THR entitlement (rules-engine output) is in the prompt as a verified fact.
    assert "Take-Home Ration" in llm.user
    # Grounding rules are in force.
    assert "VERIFIED FACTS" in llm.user
    assert "never alter" in llm.user.lower() or "never altered" in llm.system.lower()
    assert len(resp.citations) >= 1


async def test_shakti_pmmvy_eligible_verdict_in_prompt_and_citation():
    llm = PromptCapturingLLM()
    agent = RealShaktiAgent(llm=llm)
    resp = await agent.handle(
        _packet(
            "kya mujhe pmmvy ka labh mil sakta hai",
            "shakti",
            {"child_order": "first", "income_band": "bpl"},
        )
    )
    assert resp.answer == "SYNTHESIZED ANSWER"
    assert "eligibility" in resp.tool_calls
    assert "ELIGIBLE" in llm.user  # rules-engine verdict reached the prompt
    assert "₹" in llm.user  # amount comes from the tool, not the model
    assert len(resp.citations) >= 1


async def test_vatsalya_report_branch_surfaces_childline_in_prompt():
    llm = PromptCapturingLLM()
    agent = RealVatsalyaAgent(llm=llm)
    resp = await agent.handle(_packet("I want to report a child who needs help", "vatsalya"))
    assert "1098" in llm.user  # CHILDLINE from the directory, never optional
    assert "helpline_directory" in resp.tool_calls
    assert len(resp.citations) >= 1


async def test_vatsalya_adoption_branch_does_not_lead_with_childline():
    """Regression test: 'how do I adopt' used to get the report/CHILDLINE
    answer regardless of what was asked. It must now hit the adoption branch
    and talk about CARA, not helpline reporting."""
    llm = PromptCapturingLLM()
    agent = RealVatsalyaAgent(llm=llm)
    resp = await agent.handle(_packet("how do I adopt a child", "vatsalya"))
    assert "CARA" in llm.user
    assert "helpline_directory" not in resp.tool_calls
    assert len(resp.citations) >= 1


async def test_vatsalya_foster_branch_uses_eligibility_tool():
    llm = PromptCapturingLLM()
    agent = RealVatsalyaAgent(llm=llm)
    resp = await agent.handle(_packet("what is the foster care process", "vatsalya"))
    assert "eligibility" in resp.tool_calls
    assert "4,000" in llm.user
    assert len(resp.citations) >= 1


# --------------------------------------------------------------------------- #
# Fallback path: no LLM → deterministic tool-composed answer, no invention
# --------------------------------------------------------------------------- #
async def test_poshan_offline_fallback_is_tool_grounded():
    agent = RealPoshanAgent(llm=FakeLLM())  # complete() returns "" → fallback
    resp = await agent.handle(
        _packet(
            "what should I eat during pregnancy",
            "poshan",
            {"beneficiary_type": "pregnant_woman", "pregnancy_stage": "2nd_trimester"},
        )
    )
    assert "Take-Home Ration" in resp.answer  # from the rules engine
    assert "Anganwadi" in resp.answer
    assert len(resp.citations) >= 1


async def test_shakti_safety_branch_surfaces_181_and_osc():
    agent = RealShaktiAgent(llm=FakeLLM())
    resp = await agent.handle(
        _packet("what is a one stop centre", "shakti", {"district": "Delhi"})
    )
    assert "181" in resp.answer
    assert resp.escalation is False
    assert "geo_locator" in resp.tool_calls


async def test_vatsalya_offline_fallback_has_childline_and_dcpu():
    agent = RealVatsalyaAgent(llm=FakeLLM())
    resp = await agent.handle(
        _packet("i want to report a child who needs help", "vatsalya", {"district": "Delhi"})
    )
    assert "1098" in resp.answer
    assert "DCPU" in resp.answer


async def test_general_offline_fallback_navigates():
    agent = RealGeneralAgent(llm=FakeLLM())
    resp = await agent.handle(_packet("what schemes can I get", "general"))
    assert "Poshan" in resp.answer and "Shakti" in resp.answer


# --------------------------------------------------------------------------- #
# Behavior preserved from the contract: dynamic questioning + red flags
# --------------------------------------------------------------------------- #
async def test_poshan_still_asks_trimester_before_answering():
    agent = RealPoshanAgent(llm=PromptCapturingLLM())
    resp = await agent.handle(
        _packet(
            "what should I eat during pregnancy",
            "poshan",
            {"beneficiary_type": "pregnant_woman"},
        )
    )
    assert resp.needs and resp.needs[0].name == "pregnancy_stage"
    assert resp.answer == ""


async def test_poshan_medical_red_flag_routes_to_anm():
    llm = PromptCapturingLLM()
    agent = RealPoshanAgent(llm=llm)
    resp = await agent.handle(
        _packet(
            "I am 6 months pregnant and having bleeding since morning",
            "poshan",
            {"beneficiary_type": "pregnant_woman", "pregnancy_stage": "2nd_trimester"},
        )
    )
    assert "helpline_directory" in resp.tool_calls
    assert "danger sign" in llm.user.lower() or "DANGER SIGN" in llm.user


async def test_synthesis_error_falls_back_not_crashes():
    class ExplodingLLM(FakeLLM):
        async def complete(self, system: str, user: str, *, fast: bool = True) -> str:
            raise RuntimeError("provider down")

    # Facts resolve PMMVY to a definitive verdict so the call actually reaches
    # synthesis (an uncertain verdict short-circuits into a slot question
    # before any LLM call — see test_shakti_pmmvy_uncertain_* below).
    agent = RealShaktiAgent(llm=ExplodingLLM())
    resp = await agent.handle(
        _packet("am i eligible for pmmvy", "shakti", {"child_order": "first", "income_band": "bpl"})
    )
    assert "PMMVY" in resp.answer  # deterministic fallback served
    assert len(resp.citations) >= 1


# --------------------------------------------------------------------------- #
# Regression tests: uncertain verdicts must become a TRACKED slot, not just a
# question written into the answer text with no follow-up state. Without this,
# the orchestrator's awaiting_input stays False and the citizen's next reply
# ("first child") is mis-routed as a brand-new, unrelated message.
# --------------------------------------------------------------------------- #
async def test_shakti_pmmvy_uncertain_asks_child_order_as_tracked_slot():
    agent = RealShaktiAgent(llm=FakeLLM())
    resp = await agent.handle(_packet("am i eligible for pmmvy", "shakti"))
    assert resp.answer == ""
    assert resp.needs and resp.needs[0].name == "child_order"
    assert resp.needs[0].enum_values == ["first", "second", "later"]


async def test_shakti_pmmvy_continuation_without_keyword_still_routes_to_pmmvy():
    """Second turn of the slot-filling dance: the reply ('first child') has no
    PMMVY keyword at all — only the leftover collected_facts signal we're mid
    PMMVY conversation. This is the exact scenario that broke before the fix."""
    llm = PromptCapturingLLM()
    agent = RealShaktiAgent(llm=llm)
    resp = await agent.handle(_packet("first child", "shakti", {"child_order": "first"}))
    assert "eligibility" in resp.tool_calls


async def test_shakti_general_info_branch_skips_eligibility():
    """Regression test: a generic Mission Shakti question must not be dragged
    into a PMMVY child-order interrogation."""
    agent = RealShaktiAgent(llm=FakeLLM())
    resp = await agent.handle(_packet("tell me about mission shakti", "shakti"))
    assert "eligibility" not in resp.tool_calls
    assert resp.answer != ""


async def test_vatsalya_sponsorship_uncertain_asks_family_in_crisis_as_tracked_slot():
    agent = RealVatsalyaAgent(llm=FakeLLM())
    resp = await agent.handle(_packet("how can I sponsor a child's care", "vatsalya"))
    assert resp.answer == ""
    assert resp.needs and resp.needs[0].name == "family_in_crisis"
    assert resp.needs[0].type == "bool"


async def test_vatsalya_sponsorship_with_crisis_fact_gives_grounded_answer():
    agent = RealVatsalyaAgent(llm=FakeLLM())
    resp = await agent.handle(
        _packet("how can I sponsor a child's care", "vatsalya", {"family_in_crisis": "true"})
    )
    assert "4,000" in resp.answer
    assert len(resp.citations) >= 1
