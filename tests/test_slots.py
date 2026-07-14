"""Slot-filling tests — deterministic dynamic questioning."""

import pytest

from agents.orchestrator import slots
from agents.orchestrator.capabilities import POSHAN_CARD
from agents.specialists.base import SlotSpec

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


@pytest.mark.parametrize(
    "reply,expected",
    [
        ("ST", "st"),
        ("Category - ST", "st"),
        ("I am from SC category", "sc"),
        ("We have an NFSA ration card", "nfsa"),
        ("BPL", "bpl"),
    ],
)
def test_pmmvy_qualifier_accepts_valid_categories(reply, expected):
    spec = SlotSpec(name="pmmvy_qualifier", type="enum", ask_prompt="qualifier?")
    assert slots.extract_slot_value(spec, reply) == expected


def test_next_missing_slot_picks_lowest_priority_first():
    # Poshan requires beneficiary_type (priority 10). Nothing collected yet.
    nxt = slots.next_missing_slot(POSHAN_CARD, {})
    assert nxt is not None and nxt.name == "beneficiary_type"


def test_next_missing_slot_none_when_required_filled():
    nxt = slots.next_missing_slot(POSHAN_CARD, {"beneficiary_type": "child"})
    assert nxt is None
