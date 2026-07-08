"""One full end-to-end flow of the helpline_directory MCP tool — the callable
surface specialist agents use to escalate distress to the right helpline.

Deliberately a single scripted scenario (not many mini-tests): boot/validation,
the safety-critical women_safety and child_distress routing, the scheme-hint
tie-break (181 leads 112 for a Shakti query), the null-number ANM referral
(a routing instruction, not a phone line), and the full-coverage invariant are
all asserted together — the way a real Journey-3 conversation would exercise it.

Fully offline and deterministic: no LLM, no network, just the YAML-backed store.
"""

import pytest

from mcp.helpline_directory.loader import DEFAULT_YAML_PATH, HelplineStore, get_store
from mcp.helpline_directory.schemas import Category, Language, Scheme, LookupRequest
from mcp.helpline_directory.tool import lookup_helplines

pytestmark = pytest.mark.asyncio


async def test_full_helpline_directory_flow():
    # 0. The store boots and validates every Category has coverage. The previously
    #    truncated ANM row must now parse, or this raises on construction.
    store = HelplineStore(DEFAULT_YAML_PATH)
    assert store.entries, "store loaded no entries"
    covered = {cat for e in store.entries for cat in e.categories}
    assert covered == set(Category), f"uncovered categories: {set(Category) - covered}"
    # tool.py uses a process singleton — same validated data.
    assert get_store().version == store.version

    # 1. Journey 3 — woman-safety distress with a Shakti hint. The scheme-specific
    #    line (181) leads; the generic emergency line (112) rides along as secondary.
    r_women = await lookup_helplines(
        LookupRequest(category=Category.WOMEN_SAFETY, scheme=Scheme.SHAKTI)
    )
    assert r_women.primary.number == "181"
    assert r_women.primary.id == "women_helpline_181"
    assert "112" in {e.number for e in r_women.secondary}
    assert r_women.escalation_note  # combined routing guidance present
    assert r_women.latency_ms > 0

    # 2. No scheme hint on a life-safety category → strict priority wins, 112 (prio 0) leads.
    r_emergency = await lookup_helplines(LookupRequest(category=Category.WOMEN_SAFETY))
    assert r_emergency.primary.number == "112"
    assert r_emergency.primary.priority == 0

    # 3. Child distress → CHILDLINE 1098 leads (112 not in this category).
    r_child = await lookup_helplines(
        LookupRequest(category=Category.CHILD_DISTRESS, scheme=Scheme.VATSALYA)
    )
    assert r_child.primary.number == "1098"
    assert r_child.primary.scheme == Scheme.VATSALYA

    # 4. Poshan medical red-flag → ANM referral. This is a ROUTING INSTRUCTION,
    #    not a dialable number: primary.number is None. Agents must branch on this.
    r_anm = await lookup_helplines(LookupRequest(category=Category.MEDICAL_RED_FLAG))
    assert r_anm.primary.id == "anm_health_referral"
    assert r_anm.primary.number is None
    assert r_anm.primary.source_url  # grounding: every entry carries a source

    # 5. Language is a soft tie-break, never a filter — a Tamil request on a line
    #    that only lists en/hi still returns that life-safety line.
    r_ta = await lookup_helplines(
        LookupRequest(category=Category.EMERGENCY, lang=Language.TA)
    )
    assert r_ta.primary.number == "112"
