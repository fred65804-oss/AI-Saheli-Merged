"""Slot-filling — the deterministic core of dynamic questioning.

The mechanism (no fixed decision tree, no LLM guessing *which* fact to ask):
  1. merge_slots: fold the router's extracted_slots (and any specialist `needs`)
     into the running collected_facts.
  2. slot_check (nodes.py): given the chosen agent's card, find the unfilled
     REQUIRED slot with the lowest `priority` number — that is the single most
     important question to ask next.
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


# --------------------------------------------------------------------------- #
# Offline slot-value extraction
# --------------------------------------------------------------------------- #
# Domain synonyms for the slots we ask most often, so dynamic questioning works
# even without an LLM (deterministic CLI / tests / no API key). When an LLM is
# present the router usually extracts these directly; this is the safety net.

_BENEFICIARY_SYNONYMS = {
    # Order matters: the first table entry whose hint appears wins, so the more
    # specific states (pregnant / lactating) are checked before "child" — a
    # pregnant woman's message often mentions her child too.
    "pregnant_woman": ["pregnan", "garbh", "expecting", "garbhwati", "pregnency"],
    "lactating_mother": [
        "lactat", "breastfeed", "new mother", "new mom", "nursing", "doodh",
        "just delivered", "after delivery",
    ],
    "child": [
        "child", "baby", "bachcha", "baccha", "kid", "beta", "beti", "son",
        "daughter", "infant", "newborn", "toddler", "months old", "month old",
        "year old", "yr old",
    ],
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


def _norm_slots(text: str) -> str:
    """normalize() but with hyphens/slashes as spaces.

    ``normalize`` only lowercases and collapses whitespace, so "14-month-old"
    never matched the "month old" hint — which is Demo Journey 2's exact
    phrasing. Kept local to slot matching rather than changing ``normalize``,
    which the safety lexicon also depends on.
    """
    return normalize(re.sub(r"[-_/]+", " ", text))


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


def extract_slot_value(
    spec: SlotSpec, message: str, *, free_text: bool = False
) -> str | None:
    """Best-effort parse of the citizen's reply into a value for ``spec``.

    Returns a stringified value (state stores facts as strings) or None.

    ``free_text=True`` means this is an unprompted opening message, not an
    answer to a specific question. Inferences that are only safe in reply
    context — chiefly reading a bare number as a pregnancy month — are then
    suppressed, since "a plan for my 5 month old" must not become
    "5th month of pregnancy".
    """
    norm = _norm_slots(message)

    if spec.name == "beneficiary_type":
        return _match_synonyms(norm, _BENEFICIARY_SYNONYMS)

    if spec.name == "pregnancy_stage":
        # Trimester wording is checked BEFORE any bare number: "2nd trimester"
        # must not be read as "month 2" (which would answer 1st_trimester).
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
        # Otherwise a bare 1-9 means the month of pregnancy — but ONLY when this
        # is an answer to "which month are you in?". In free text the same digit
        # is far more likely the child's age ("my 5 month old").
        if free_text:
            return None
        n = _first_int(message)
        if n is not None and 1 <= n <= 9:
            if n <= 3:
                return "1st_trimester"
            if n <= 6:
                return "2nd_trimester"
            return "3rd_trimester"
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


# --------------------------------------------------------------------------- #
# Opening-message extraction (the "don't ask what they already told us" net)
# --------------------------------------------------------------------------- #
def coerce_card_slots(card: AgentCapabilityCard, extracted: dict) -> dict:
    """Keep only slot values the card can actually accept.

    The router's LLM is free-form: it can invent a key, or return an enum value
    outside the allowed set ("infant" for beneficiary_type). An unvalidated
    value counts as *filled*, so a bogus one would silently skip the question
    AND feed the specialist junk. We map near-misses through the synonym tables
    and drop whatever still doesn't fit.
    """
    specs = {s.name: s for s in list(card.required_slots) + list(card.optional_slots)}
    out: dict = {}
    for name, value in (extracted or {}).items():
        spec = specs.get(name)
        if spec is None or value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        if spec.type == "enum" and spec.enum_values:
            if text in spec.enum_values:
                out[name] = text
                continue
            # near-miss ("infant", "a child", "pregnant lady") → synonym match
            mapped = extract_slot_value(spec, text)
            if mapped in spec.enum_values:
                out[name] = mapped
            continue
        out[name] = text
    return out


def extract_stated_slots(card: AgentCapabilityCard, message: str) -> dict:
    """Slot values the citizen plainly stated in their opening message.

    A safety net under the router's LLM extraction, not a replacement. Scope is
    deliberately narrow — **required, enum** slots only:

    * *required* — these are the only slots that BLOCK (slot_check asks about
      them), so they are the only ones that can produce the "you already told
      me that" question this net exists to prevent. Guessing an *optional* fact
      from free text buys nothing and can cost correctness: a bare "1" in "my 1
      year old" would substring-match child_order=first and skew a PMMVY
      amount. Optional facts come from the LLM, validated by coerce_card_slots.
    * *enum* — their synonym tables are a positive signal. The int/bool/string
      branches of ``extract_slot_value`` are reply-parsers and misfire on
      free-form text (the string branch returns the whole message, which would
      land in `district`; the bool branch substring-matches "no" in "nutrition").
    """
    found: dict = {}
    for spec in card.required_slots:
        if not spec.required or spec.type != "enum" or not spec.enum_values:
            continue
        value = extract_slot_value(spec, message, free_text=True)
        if value in spec.enum_values:
            found[spec.name] = value
    return found


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
