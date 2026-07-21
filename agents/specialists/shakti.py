"""Real Shakti specialist — women's safety & empowerment, grounded.

Three deterministic branches (routing logic, not scheme knowledge):

  A. Safety / One Stop Centre request →
       helpline_directory (Women Helpline 181 + 112) + geo_locator (nearest
       OSC). Numbers always verbatim from the directory data.
  B. PMMVY eligibility (Journey 4) — only when the message actually signals
       PMMVY/maternity-benefit interest, or we're mid-way through answering
       PMMVY's own follow-up question →
       eligibility tool (three-valued verdict) + official passages. An
       "uncertain" verdict becomes a real ``needs`` SlotRequest so the
       orchestrator tracks the follow-up turn — a prior version only wrote
       the missing-fact question into the answer text without registering
       it as a pending slot, so the citizen's next reply ("first child")
       was treated as a fresh, unrelated message and mis-routed.
  C. General Mission Shakti info (Sakhi Niwas, Nari Adalat, Beti Bachao Beti
       Padhao, legal rights, or an open "tell me about Mission Shakti") —
       KB synthesis only, no eligibility call. Without this branch every
       non-safety Shakti message fell into B and got interrogated about
       PMMVY child order regardless of what was actually asked.

The orchestrator's safety gate escalates active distress BEFORE this agent —
branch A serves informational safety queries ("what is a One Stop Centre?").
"""

from __future__ import annotations

from agents.orchestrator.capabilities import SHAKTI_CARD
from agents.orchestrator.llm import StructuredLLM, get_llm
from agents.specialists._grounding import (
    chunks_to_citations,
    citation_hint,
    pick_rule as _pick,
    retrieve_passages,
    synthesize_answer,
    to_bool,
)
from agents.specialists.base import (
    AgentResponse,
    Citation,
    ContextPacket,
    SlotRequest,
    SpecialistAgent,
)
from mcp.eligibility.schemas import (
    BeneficiaryType,
    CasteCategory,
    EligibilityRequest,
    IncomeBand,
    RuleResult,
)
from mcp.eligibility.tool import check_eligibility
from mcp.geo_locator.schemas import LookupRequest as GeoRequest, ServiceType
from mcp.geo_locator.tool import find_facilities
from mcp.helpline_directory.schemas import (
    Category as HelplineCategory,
    LookupRequest as HelplineRequest,
    Scheme as HelplineScheme,
)
from mcp.helpline_directory.tool import lookup_helplines

# Branch triggers — deterministic routing heuristics, not scheme knowledge.
_SAFETY_HINTS = ("one stop", "osc", "sakhi centre", "sakhi center", "unsafe", "helpline", "safety")
_PMMVY_HINTS = (
    "pmmvy", "matru vandana", "maternity benefit", "maternity scheme",
    "instalment", "installment", "labh", "5000", "6000", "₹5,000", "₹6,000",
)
# Facts that only exist because THIS agent's PMMVY branch asked for them —
# their presence means we're mid-conversation on PMMVY, even if this turn's
# message ("first child") carries no PMMVY keyword at all.
_PMMVY_CONTINUATION_FACTS = (
    "child_order",
    "income_band",
    "caste_category",
    "pmmvy_qualifier",
    "second_child_is_girl",
)

# Slot-value translations: the orchestrator collects human-friendly enum
# strings; the tools speak typed schema values.
_CHILD_ORDER = {"first": 1, "second": 2, "later": 3}
_INCOME_BAND = {
    "bpl": IncomeBand.BPL,
    "below_threshold": IncomeBand.BPL,
    "above_threshold": IncomeBand.APL,
}
_CASTE_CATEGORY = {"sc": CasteCategory.SC, "st": CasteCategory.ST}
# How to ask for each fact PMMVY's rules engine might report as missing.
# income_band stands in for the socio-economic bucket (income/caste/NFSA) —
# it is the single best question, and it already matches the card's own
# optional-slot enum, so extraction works offline without an LLM.
_NEEDS_SLOT_SPECS: dict[str, dict] = {
    "child_order": {"type": "enum", "enum_values": ["first", "second", "later"]},
    "second_child_is_girl": {"type": "bool", "enum_values": None},
    "income_band": {"type": "enum", "enum_values": ["bpl", "below_threshold", "above_threshold"]},
}
_PMMVY_QUALIFIER_VALUES = [
    "sc", "st", "bpl", "nfsa", "disabled", "below_8_lakh", "above_8_lakh"
]


def _pmmvy_slot_request(pmmvy: RuleResult) -> SlotRequest | None:
    if not pmmvy.needs:
        return None
    socioeconomic_needs = {"annual_family_income", "caste_category", "income_band"}
    if socioeconomic_needs.intersection(pmmvy.needs):
        return SlotRequest(
            name="pmmvy_qualifier",
            reason=pmmvy.reason,
            type="enum",
            enum_values=_PMMVY_QUALIFIER_VALUES,
        )
    name = "income_band" if "income_band" in pmmvy.needs else pmmvy.needs[0]
    spec = _NEEDS_SLOT_SPECS.get(name)
    if spec is None:
        return None
    return SlotRequest(name=name, reason=pmmvy.reason, type=spec["type"], enum_values=spec["enum_values"])


def _pmmvy_socioeconomic_fields(facts: dict) -> dict:
    """Map the broad conversational qualifier to typed PMMVY rule inputs."""
    qualifier = str(facts.get("pmmvy_qualifier", "")).lower()
    raw_caste = str(facts.get("caste_category", "")).lower()
    return {
        "income_band": _INCOME_BAND.get(str(facts.get("income_band", "")).lower())
        or (IncomeBand.BPL if qualifier == "bpl" else None),
        "caste_category": _CASTE_CATEGORY.get(qualifier)
        or _CASTE_CATEGORY.get(raw_caste),
        "nfsa_member": True if qualifier == "nfsa" else None,
        "is_disabled": True if qualifier == "disabled" else None,
        "annual_family_income": (
            799_999 if qualifier == "below_8_lakh"
            else 800_000 if qualifier == "above_8_lakh"
            else None
        ),
    }


class RealShaktiAgent(SpecialistAgent):
    capability_card = SHAKTI_CARD

    def __init__(self, llm: StructuredLLM | None = None) -> None:
        self._llm = llm

    @property
    def llm(self) -> StructuredLLM:
        if self._llm is None:
            self._llm = get_llm()
        return self._llm

    async def handle(self, packet: ContextPacket) -> AgentResponse:
        msg = packet.user_message.lower()
        facts = packet.collected_facts
        if any(k in msg for k in _SAFETY_HINTS):
            return await self._handle_safety(packet)
        is_pmmvy = any(k in msg for k in _PMMVY_HINTS) or any(
            facts.get(f) for f in _PMMVY_CONTINUATION_FACTS
        )
        if is_pmmvy:
            return await self._handle_pmmvy(packet)
        return await self._handle_general_info(packet)

    # ------------------------------------------------------- branch A: safety
    async def _handle_safety(self, packet: ContextPacket) -> AgentResponse:
        facts = packet.collected_facts
        tool_calls: list[str] = []
        citations: list[Citation] = []
        tool_facts: list[str] = []
        fallback_parts: list[str] = []

        hl = await lookup_helplines(
            HelplineRequest(
                category=HelplineCategory.WOMEN_SAFETY, scheme=HelplineScheme.SHAKTI
            )
        )
        tool_calls.append("helpline_directory")
        primary = hl.primary
        tool_facts.append(
            f"{primary.name}: {primary.number} ({primary.hours}, free)"
        )
        citations.append(
            Citation(source_doc=primary.name, source_url=primary.source_url)
        )
        secondary_numbers = ", ".join(
            f"{e.name} {e.number}" for e in hl.secondary if e.number
        )
        if secondary_numbers:
            tool_facts.append(f"For immediate danger: {secondary_numbers}")
        fallback_parts.append(
            f"Please call {primary.name} {primary.number} ({primary.hours}, free)"
            + (f" or {secondary_numbers} for immediate danger." if secondary_numbers else ".")
        )

        district = facts.get("district")
        osc_line = (
            "You can reach your nearest One Stop Centre for in-person support."
        )
        if district:
            geo = await find_facilities(
                GeoRequest(service_type=ServiceType.OSC, district=district)
            )
            tool_calls.append("geo_locator")
            if geo.facilities:
                f = geo.facilities[0]
                osc_line = (
                    f"Your nearest One Stop Centre: {f.name}, {f.address}"
                    + (f", {f.phone}" if f.phone else "")
                    + "."
                )
                tool_facts.append(osc_line)
                citations.append(Citation(source_doc=f.source, section=f.name))
            elif geo.note:
                osc_line = geo.note
        fallback_parts.append(osc_line)

        chunks = await retrieve_passages(packet.user_message, self.scheme)
        if chunks:
            tool_calls.append("knowledge_base")
            citations.extend(chunks_to_citations(chunks))

        answer, synthesized = await synthesize_answer(
            self.llm,
            scheme_display=self.capability_card.display_name,
            user_message=packet.user_message,
            collected_facts=facts,
            tool_facts=tool_facts,
            chunks=chunks,
            fallback=" ".join(fallback_parts),
        )
        return AgentResponse(
            answer=answer,
            citations=citations,
            tool_calls=tool_calls,
            escalation=False,
            confidence=0.88 if synthesized else 0.85,
        )

    # ------------------------------------------------------- branch B: PMMVY
    async def _handle_pmmvy(self, packet: ContextPacket) -> AgentResponse:
        facts = packet.collected_facts
        tool_calls = ["eligibility"]

        child_order = _CHILD_ORDER.get(str(facts.get("child_order", "")).lower())
        socioeconomic = _pmmvy_socioeconomic_fields(facts)
        elig = await check_eligibility(
            EligibilityRequest(
                beneficiary_type=BeneficiaryType.PREGNANT_WOMAN,
                child_order=child_order,
                income_band=socioeconomic["income_band"],
                caste_category=socioeconomic["caste_category"],
                nfsa_member=socioeconomic["nfsa_member"],
                is_disabled=socioeconomic["is_disabled"],
                annual_family_income=socioeconomic["annual_family_income"],
                second_child_is_girl=to_bool(facts.get("second_child_is_girl")),
                district=facts.get("district"),
            )
        )
        pmmvy = (
            _pick(elig.eligible, "PMMVY")
            or _pick(elig.ineligible, "PMMVY")
            or _pick(elig.uncertain, "PMMVY")
        )
        if pmmvy is None:
            return AgentResponse(answer="", tool_calls=tool_calls, confidence=0.4)

        # Uncertain with a mappable missing fact → ask it as a REAL slot
        # (registers with the orchestrator's slot-filling state) rather than
        # only describing the question in prose, so the next reply is
        # correctly captured as the answer instead of mis-routed.
        if pmmvy.eligible is None:
            req = _pmmvy_slot_request(pmmvy)
            if req is not None:
                return AgentResponse(answer="", needs=[req], tool_calls=tool_calls, confidence=0.85)

        citations = [Citation(source_doc=pmmvy.source_doc, source_url=pmmvy.source_url)]
        tool_facts: list[str] = []
        fallback_parts: list[str] = []
        if pmmvy.eligible is True:
            tool_facts.append(
                f"PMMVY verdict (rules engine): ELIGIBLE — {pmmvy.amount} "
                f"({pmmvy.instalments}). {pmmvy.benefit_summary}"
            )
            fallback_parts.append(
                f"Under {pmmvy.scheme}, based on what you've shared, you "
                f"qualify for {pmmvy.amount} ({pmmvy.instalments})."
            )
        elif pmmvy.eligible is False:
            tool_facts.append(
                f"PMMVY verdict (rules engine): NOT ELIGIBLE — {pmmvy.reason}"
            )
            fallback_parts.append(f"Under {pmmvy.scheme}: {pmmvy.reason}")
        else:  # uncertain but unmappable (no slot spec for this need) — explain in prose
            tool_facts.append(f"PMMVY verdict (rules engine): UNCERTAIN — {pmmvy.reason}")
            fallback_parts.append(f"Under {pmmvy.scheme}: {pmmvy.reason}")

        chunks = await retrieve_passages(packet.user_message, self.scheme)
        if chunks:
            tool_calls.append("knowledge_base")
            citations.extend(chunks_to_citations(chunks))
            fallback_parts.append(citation_hint(chunks))
        fallback_parts.append(
            "Your nearest Anganwadi Centre can help you apply and check documents."
        )

        answer, synthesized = await synthesize_answer(
            self.llm,
            scheme_display=self.capability_card.display_name,
            user_message=packet.user_message,
            collected_facts=facts,
            tool_facts=tool_facts,
            chunks=chunks,
            fallback=" ".join(fallback_parts),
        )
        return AgentResponse(
            answer=answer,
            citations=citations,
            tool_calls=tool_calls,
            escalation=False,
            confidence=0.88 if synthesized else 0.84,
        )

    # ----------------------------------------------- branch C: general info
    async def _handle_general_info(self, packet: ContextPacket) -> AgentResponse:
        """Sakhi Niwas, Nari Adalat, Beti Bachao Beti Padhao, legal rights, or
        an open 'tell me about Mission Shakti' — no eligibility call. Forcing
        a PMMVY interrogation onto a non-PMMVY question was the bug this
        branch exists to fix."""
        chunks = await retrieve_passages(packet.user_message, self.scheme)
        citations = chunks_to_citations(chunks)
        tool_calls = ["knowledge_base"] if chunks else []

        fallback = (
            "Mission Shakti supports women's safety and empowerment: the "
            "Women Helpline 181 and One Stop Centres for safety, the PMMVY "
            "maternity benefit, Sakhi Niwas shelters, Nari Adalat for local "
            "dispute resolution, and Beti Bachao Beti Padhao. Tell me more "
            "about what you need and I can go into detail."
        )
        if chunks:
            fallback = f"{fallback} {citation_hint(chunks)}"

        answer, synthesized = await synthesize_answer(
            self.llm,
            scheme_display=self.capability_card.display_name,
            user_message=packet.user_message,
            collected_facts=packet.collected_facts,
            tool_facts=[],
            chunks=chunks,
            fallback=fallback,
        )
        return AgentResponse(
            answer=answer,
            citations=citations,
            tool_calls=tool_calls,
            confidence=0.8 if synthesized else 0.72,
        )
