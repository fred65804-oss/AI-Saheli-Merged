"""Slot-filling tests — deterministic dynamic questioning."""

import pytest

from agents.orchestrator import slots
from agents.orchestrator.llm import FakeLLM
from agents.orchestrator.nodes import OrchestratorNodes
from agents.orchestrator.router import Router
from agents.orchestrator.trace import NullTraceSink
from agents.specialists.base import SlotSpec
from agents.specialists.registry import routable_cards
from apps.backend.config import get_settings

PREG = SlotSpec(
    name="pregnancy_stage", type="enum", ask_prompt="stage?",
    enum_values=["1st_trimester", "2nd_trimester", "3rd_trimester", "postpartum"],
)
BEN = SlotSpec(
    name="beneficiary_type", type="enum", ask_prompt="who?",
    enum_values=["pregnant_woman", "lactating_mother", "child"],
)
AGE = SlotSpec(name="child_age_months", type="int", ask_prompt="age?")


@pytest.mark.parametrize(
    "reply,expected",
    [
        ("6th month", "2nd_trimester"),
        ("I am in 8 months", "3rd_trimester"),
        ("first trimester", "1st_trimester"),
        ("baby is born now", "postpartum"),
    ],
)
def test_pregnancy_stage_extraction(reply, expected):
    assert slots.extract_slot_value(PREG, reply) == expected


def test_beneficiary_type_extraction():
    assert slots.extract_slot_value(BEN, "I am pregnant") == "pregnant_woman"
    assert slots.extract_slot_value(BEN, "my child") == "child"


def test_int_extraction_handles_years():
    assert slots.extract_slot_value(AGE, "he is 2 years old") == "24"
    assert slots.extract_slot_value(AGE, "14 months") == "14"


def test_merge_slots_does_not_overwrite_with_blank():
    merged = slots.merge_slots({"district": "Varanasi"}, {"district": "", "lang": "hi"})
    assert merged["district"] == "Varanasi"
    assert merged["lang"] == "hi"


# "Ask the lowest-priority required slot first" used to live in
# slots.next_missing_slot(); it now runs inline in OrchestratorNodes.slot_check
# (nodes.py). These two tests follow it there — the behaviour is the whole point
# of dynamic questioning (principle #5), so it stays covered rather than deleted.
def _nodes() -> OrchestratorNodes:
    llm = FakeLLM()
    return OrchestratorNodes(
        llm=llm,
        router=Router(llm, routable_cards()),
        settings=get_settings(),
        sink=NullTraceSink(),
    )


@pytest.mark.asyncio
async def test_slot_check_picks_lowest_priority_first():
    # Poshan requires beneficiary_type (priority 10). Nothing collected yet.
    out = await _nodes().slot_check({"intent": "poshan", "collected_facts": {}})
    assert out["pending_ask_spec"] is not None
    assert out["pending_ask_spec"]["name"] == "beneficiary_type"


@pytest.mark.asyncio
async def test_slot_check_none_when_required_filled():
    out = await _nodes().slot_check(
        {"intent": "poshan", "collected_facts": {"beneficiary_type": "child"}}
    )
    assert out["pending_ask_spec"] is None


@pytest.mark.asyncio
async def test_slot_check_skips_personal_slots_for_overview():
    """An overview question ("what is Poshan 2.0?") must reach the specialist
    without collecting personal facts first."""
    out = await _nodes().slot_check(
        {"intent": "poshan", "collected_facts": {}, "request_type": "overview"}
    )
    assert out["pending_ask_spec"] is None
