"""Safety gate tests — the most important guarantees in the system.

These run deterministically with no API key (L1 lexicon path), and use a
FakeLLM to simulate the L2 classifier catching indirect disclosure.
"""

import pytest

from agents.guardrails import safety
from agents.guardrails.lexicon import DistressCategory
from agents.guardrails.safety import SafetyVerdict
from agents.orchestrator.llm import FakeLLM

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "text,expected_category",
    [
        ("My husband beats me", DistressCategory.WOMEN_VIOLENCE),
        ("mera pati mujhe maarta hai", DistressCategory.WOMEN_VIOLENCE),
        ("मेरा पति मुझे मारता है", DistressCategory.WOMEN_VIOLENCE),
        ("My in-laws harass me for dowry", DistressCategory.WOMEN_VIOLENCE),
        ("bachcha gum ho gaya hai", DistressCategory.CHILD_DANGER),
        ("a child is being trafficked", DistressCategory.CHILD_DANGER),
        ("I want to end my life", DistressCategory.GENERIC_EMERGENCY),
    ],
)
async def test_l1_lexicon_catches_distress(text, expected_category):
    res = await safety.check_safety(text, llm=FakeLLM(), run_llm_layer=False)
    assert res.escalate is True
    assert res.category == expected_category
    assert res.source == "lexicon"


async def test_benign_message_not_escalated_by_lexicon():
    res = await safety.check_safety(
        "What should I eat during pregnancy?", llm=FakeLLM(), run_llm_layer=False
    )
    assert res.escalate is False


async def test_l2_catches_indirect_disclosure_lexicon_misses():
    text = "He gets very angry and I feel unsafe at home"
    # L1 alone misses it:
    l1 = await safety.check_safety(text, llm=FakeLLM(), run_llm_layer=False)
    assert l1.escalate is False

    # L2 (simulated) catches it:
    def responder(system, user, schema):
        return SafetyVerdict(
            is_distress=True, category="women_violence", severity="high",
            rationale="indirect disclosure of domestic violence",
        )

    l2 = await safety.check_safety(
        text, llm=FakeLLM(parse_responder=responder), run_llm_layer=True
    )
    assert l2.escalate is True
    assert l2.category == DistressCategory.WOMEN_VIOLENCE
    assert l2.source == "llm"


async def test_escalation_response_is_templated_with_helplines():
    res = await safety.check_safety("my husband beats me", llm=FakeLLM(), run_llm_layer=False)
    msg = safety.build_escalation_response(res)
    assert "181" in msg and "112" in msg
    assert "confidential" in msg.lower()
