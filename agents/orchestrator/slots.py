"""Slot-filling — the deterministic core of dynamic questioning.

The mechanism (no fixed decision tree, no LLM guessing *which* fact to ask):
  1. merge_slots: fold the router's extracted_slots (and any specialist `needs`)
     into the running collected_facts.
  2. next_missing_slot: given the chosen agent's card, find the unfilled REQUIRED
     slot with the lowest `priority` number — that is the single most important
     question to ask next.
  3. A node then asks exactly that one question (an LLM only *phrases* it warmly);
     when the reply fills it, we re-check, and hand off once nothing required
     is missing.

Logic decides *which* slot; the model only decides *wording*. That is what makes
dynamic questioning testable and loop-free.
"""

from __future__ import annotations

import re

from agents.guardrails.lexicon import normalize
from agents.specialists.base import AgentCapabilityCard, SlotRequest, SlotSpec


def merge_slots(collected: dict, extracted: dict) -> dict:
    """Return a new dict with extracted values folded in.

    Existing values win over empty/None extractions; non-empty extractions
    update or add. We never overwrite a known fact with a blank.
    """
    out = dict(collected)
    for key, value in (extracted or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        out[key] = value
    return out


def _is_filled(collected: dict, name: str) -> bool:
    val = collected.get(name)
    if val is None:
        return False
    if isinstance(val, str) and not val.strip():
        return False
    return True


def next_missing_slot(
    card: AgentCapabilityCard, collected: dict
) -> SlotSpec | None:
    """The highest-priority unfilled REQUIRED slot for this agent, or None."""
    missing = [
        s for s in card.required_slots if s.required and not _is_filled(collected, s.name)
    ]
    if not missing:
        return None
    return sorted(missing, key=lambda s: s.priority)[0]


# --------------------------------------------------------------------------- #
# Offline slot-value extraction
# --------------------------------------------------------------------------- #
# Domain synonyms for the slots we ask most often, so dynamic questioning works
# even without an LLM (deterministic CLI / tests / no API key). When an LLM is
# present the router usually extracts these directly; this is the safety net.

_BENEFICIARY_SYNONYMS = {
    "pregnant_woman": ["pregnan", "garbh", "expecting", "garbhwati", "pregnency"],
    "lactating_mother": ["lactat", "feeding", "new mother", "doodh", "breastfeed"],
    "child": ["child", "baby", "bachcha", "baccha", "kid", "beta", "beti", "son", "daughter"],
}

_CHILD_ORDER_SYNONYMS = {
    "first": ["first", "1st", "pehla", "ek", "one", "1"],
    "second": ["second", "2nd", "doosra", "dusra", "two", "2"],
    "later": ["later", "third", "3rd", "teesra", "more than"],
}

_INCOME_SYNONYMS = {
    "bpl": ["bpl", "below poverty", "ration card", "nfsa", "garib", "antyodaya"],
    "below_threshold": ["low income", "kam aay"],
    "above_threshold": ["above", "apl", "high income", "zyada aay"],
}

_BOOL_TRUE = ["yes", "haan", "han", "ji haan", "girl", "beti", "true", "crisis",
              "hardship", "died", "death", "illness", "sick", "incapacit"]
_BOOL_FALSE = ["no", "nahi", "nahin", "boy", "beta", "false", "stable", "fine",
               "not in crisis", "no crisis"]


def _match_bool(message_norm: str) -> str | None:
    if any(h in message_norm for h in _BOOL_FALSE):
        return "false"
    if any(h in message_norm for h in _BOOL_TRUE):
        return "true"
    return None


def _match_synonyms(message_norm: str, table: dict[str, list[str]]) -> str | None:
    for value, hints in table.items():
        if any(h in message_norm for h in hints):
            return value
    return None


def _first_int(message: str) -> int | None:
    m = re.search(r"\d+", message)
    return int(m.group()) if m else None


def extract_slot_value(spec: SlotSpec, message: str) -> str | None:
    """Best-effort parse of the citizen's reply into a value for ``spec``.

    Returns a stringified value (state stores facts as strings) or None.
    """
    norm = normalize(message)

    if spec.name == "beneficiary_type":
        return _match_synonyms(norm, _BENEFICIARY_SYNONYMS)

    if spec.name == "pregnancy_stage":
        n = _first_int(message)
        if n is not None and 1 <= n <= 9:
            if n <= 3:
                return "1st_trimester"
            if n <= 6:
                return "2nd_trimester"
            return "3rd_trimester"
        if any(
            w in norm
            for w in [
                "postpartum", "delivered", "after birth", "after delivery",
                "baby born", "is born", "born now", "bachcha ho gaya", "delivery ho",
            ]
        ):
            return "postpartum"
        for stage, hints in {
            "1st_trimester": ["first trimester", "1st trimester", "pehli", "teen mahine"],
            "2nd_trimester": ["second trimester", "2nd trimester", "dusri", "chhata"],
            "3rd_trimester": ["third trimester", "3rd trimester", "teesri", "naumahina"],
        }.items():
            if any(h in norm for h in hints):
                return stage
        return None

    if spec.name == "child_order":
        return _match_synonyms(norm, _CHILD_ORDER_SYNONYMS)

    if spec.name == "income_band":
        return _match_synonyms(norm, _INCOME_SYNONYMS)

    if spec.type == "bool":
        return _match_bool(norm)

    if spec.type == "int":
        n = _first_int(message)
        if n is None:
            return None
        if "year" in norm or "saal" in norm or "varsh" in norm:
            n *= 12
        return str(n)

    if spec.type == "enum" and spec.enum_values:
        for value in spec.enum_values:
            token = value.replace("_", " ")
            if token in norm or value in norm:
                return value
        return None

    # string: accept the trimmed reply if it looks like a real answer
    cleaned = message.strip()
    return cleaned or None


def slot_request_to_spec(req: SlotRequest) -> SlotSpec:
    """Adapt a specialist's `needs` item into a SlotSpec we can ask for."""
    return SlotSpec(
        name=req.name,
        type=req.type,
        required=True,
        priority=5,  # specialist-requested facts are asked first
        ask_prompt=req.reason or f"Could you tell me your {req.name.replace('_', ' ')}?",
        enum_values=req.enum_values,
    )
