"""Mock specialists — stand-ins until the colleague ships the real agents.

Each mock now exercises the real MCP tool surface the orchestrator depends on,
so a demo conversation drives the actual tools end-to-end:

  - Poshan   → eligibility (THR/SNP) + geo_locator (nearest Anganwadi)
  - Vatsalya → helpline_directory (CHILDLINE 1098) + geo_locator (DCPU) + eligibility (sponsorship/foster)
  - Shakti   → eligibility (PMMVY) + helpline_directory/geo_locator (One Stop Centre)

Grounding note: citations are drawn from the deterministic tool sources (each
carries a source_url), so a specialist stays grounded even if the knowledge_base
retrieval index is unavailable. The knowledge_base is still queried best-effort
for richer narrative citations.

To swap in a real agent: implement ``SpecialistAgent`` against the same card and
re-register it in ``registry.py``. No orchestrator change needed.
"""

from __future__ import annotations

import asyncio

from agents.orchestrator.capabilities import (
    GENERAL_CARD,
    POSHAN_CARD,
    SHAKTI_CARD,
    VATSALYA_CARD,
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
    EligibilityRequest,
    IncomeBand,
    RuleResult,
)
from mcp.eligibility.tool import check_eligibility
from mcp.geo_locator.schemas import LookupRequest as GeoRequest
from mcp.geo_locator.schemas import ServiceType
from mcp.geo_locator.tool import find_facilities
from mcp.helpline_directory.schemas import Category, LookupRequest as HelplineRequest, Scheme
from mcp.helpline_directory.tool import lookup_helplines
from mcp.knowledge_base.schemas import KBQueryRequest
from mcp.knowledge_base.tool import query_knowledge_base


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
# The KB is an *enrichment*, never a dependency: a slow or unavailable retrieval
# index must not consume the specialist's whole time budget and cost it the
# grounded tool citations it already has. Cap the best-effort call tightly.
_KB_CITATION_TIMEOUT_S = 4.0


async def _kb_citations(query: str, scheme: str | None, k: int = 3) -> list[Citation]:
    """Best-effort narrative citations from the KB. Never raises and never blocks
    long — retrieval may be unavailable or cold, in which case the specialist
    still cites its deterministic tool sources."""
    try:
        resp = await asyncio.wait_for(
            query_knowledge_base(KBQueryRequest(query=query, scheme=scheme, k=k)),
            timeout=_KB_CITATION_TIMEOUT_S,
        )
    except (Exception, asyncio.TimeoutError):
        return []
    return [
        Citation(source_doc=c.doc, section=c.heading_path_str or None)
        for c in resp.chunks
    ]


def _cite(result: RuleResult) -> Citation:
    return Citation(source_doc=result.source_doc, source_url=result.source_url)


# Slot-value translations: the orchestrator collects human-friendly enum strings;
# the tools speak typed schema values.
_CHILD_ORDER = {"first": 1, "second": 2, "later": 3}
_INCOME_BAND = {
    "bpl": IncomeBand.BPL,
    "below_threshold": IncomeBand.BPL,
    "above_threshold": IncomeBand.APL,
}


def _pick(results, scheme_contains: str) -> RuleResult | None:
    for r in results:
        if scheme_contains.lower() in r.scheme.lower():
            return r
    return None


# --------------------------------------------------------------------------- #
# Poshan — nutrition (eligibility THR/SNP + nearest Anganwadi)
# --------------------------------------------------------------------------- #
class MockPoshanAgent(SpecialistAgent):
    capability_card = POSHAN_CARD

    async def handle(self, packet: ContextPacket) -> AgentResponse:
        facts = packet.collected_facts

        # Preserve the dynamic-questioning demo: ask trimester once we know it's a
        # pregnant woman but not the stage.
        if facts.get("beneficiary_type") == "pregnant_woman" and not facts.get(
            "pregnancy_stage"
        ):
            return AgentResponse(
                answer="",
                needs=[
                    SlotRequest(
                        name="pregnancy_stage",
                        reason="nutrition advice differs by trimester",
                        type="enum",
                        enum_values=[
                            "1st_trimester",
                            "2nd_trimester",
                            "3rd_trimester",
                            "postpartum",
                        ],
                    )
                ],
                confidence=0.9,
            )

        tool_calls: list[str] = []
        citations: list[Citation] = []

        # 1. Eligibility: which nutrition benefit applies?
        beneficiary = facts.get("beneficiary_type") or "pregnant_woman"
        try:
            btype = BeneficiaryType(beneficiary)
        except ValueError:
            btype = BeneficiaryType.PREGNANT_WOMAN
        elig = await check_eligibility(
            EligibilityRequest(
                beneficiary_type=btype,
                child_age_months=facts.get("child_age_months"),
                is_awc_enrolled=True,
            )
        )
        tool_calls.append("eligibility")
        thr = _pick(elig.eligible, "SNP") or _pick(elig.uncertain, "SNP") or _pick(
            elig.ineligible, "SNP"
        )
        benefit_line = ""
        if thr and thr.eligible:
            benefit_line = f" You are entitled to {thr.amount} — {thr.benefit_summary}"
            citations.append(_cite(thr))

        # 2. Nearest Anganwadi Centre, if we know the district.
        facility_line = ""
        district = facts.get("district")
        if district:
            geo = await find_facilities(
                GeoRequest(service_type=ServiceType.AWC, district=district)
            )
            tool_calls.append("geo_locator")
            if geo.facilities:
                f = geo.facilities[0]
                facility_line = f" Your nearest Anganwadi Centre is {f.name}, {f.address}."
                citations.append(Citation(source_doc=f.source, section=f.name))
            elif geo.note:
                facility_line = f" ({geo.note})"

        # 3. KB narrative citations (best-effort).
        kb = await _kb_citations(packet.user_message, self.scheme)
        if kb:
            tool_calls.append("knowledge_base")
            citations.extend(kb)

        stage = facts.get("pregnancy_stage", "your current stage")
        answer = (
            "For good nutrition, include iron-rich foods (green leafy vegetables, "
            "jaggery, chana), protein (dal, eggs, milk), and take your IFA tablets."
            + benefit_line
            + " Collect your Take-Home Ration through your Anganwadi Centre."
            + facility_line
            + f" (Guidance tailored to {stage}.)"
        )
        return AgentResponse(
            answer=answer,
            citations=citations,
            tool_calls=tool_calls,
            confidence=0.86,
        )


# --------------------------------------------------------------------------- #
# Vatsalya — child protection (CHILDLINE + DCPU + sponsorship/foster)
# --------------------------------------------------------------------------- #
class MockVatsalyaAgent(SpecialistAgent):
    capability_card = VATSALYA_CARD

    async def handle(self, packet: ContextPacket) -> AgentResponse:
        facts = packet.collected_facts
        tool_calls: list[str] = []
        citations: list[Citation] = []

        # 1. CHILDLINE + emergency numbers (grounded via the helpline tool).
        hl = await lookup_helplines(
            HelplineRequest(category=Category.CHILD_PROTECTION, scheme=Scheme.VATSALYA)
        )
        tool_calls.append("helpline_directory")
        childline = hl.primary
        others = ", ".join(e.number for e in hl.secondary if e.number)
        citations.append(
            Citation(source_doc="Mission Vatsalya / CHILDLINE", source_url=childline.source_url)
        )

        # 2. Nearest District Child Protection Unit, if district known.
        facility_line = ""
        district = facts.get("district")
        if district:
            geo = await find_facilities(
                GeoRequest(service_type=ServiceType.DCPU, district=district)
            )
            tool_calls.append("geo_locator")
            if geo.facilities:
                f = geo.facilities[0]
                facility_line = f" Your nearest DCPU is {f.name}, {f.address}."
                citations.append(Citation(source_doc=f.source, section=f.name))
            elif geo.note:
                facility_line = f" ({geo.note})"

        kb = await _kb_citations(packet.user_message, self.scheme)
        if kb:
            tool_calls.append("knowledge_base")
            citations.extend(kb)

        contact = f"call CHILDLINE {childline.number} (free, 24x7)"
        if others:
            contact += f" or {others} in an emergency"
        answer = (
            "Mission Vatsalya supports child welfare and protection. To report a "
            f"child in need of care and protection, {contact}, or contact your "
            "District Child Protection Unit (DCPU)." + facility_line + " To adopt, "
            "register on the CARA portal (cara.wcd.gov.in) through a Specialised "
            "Adoption Agency."
        )
        return AgentResponse(
            answer=answer,
            citations=citations,
            tool_calls=tool_calls,
            confidence=0.82,
        )


# --------------------------------------------------------------------------- #
# Shakti — women safety & PMMVY (eligibility + One Stop Centre)
# --------------------------------------------------------------------------- #
class MockShaktiAgent(SpecialistAgent):
    capability_card = SHAKTI_CARD

    async def handle(self, packet: ContextPacket) -> AgentResponse:
        facts = packet.collected_facts
        msg = packet.user_message.lower()
        tool_calls: list[str] = []
        citations: list[Citation] = []

        # Branch: an active One Stop Centre / safety request vs. a PMMVY scheme query.
        wants_osc = any(k in msg for k in ("one stop", "osc", "sakhi", "unsafe", "helpline"))

        if wants_osc:
            hl = await lookup_helplines(
                HelplineRequest(category=Category.WOMEN_SAFETY, scheme=Scheme.SHAKTI)
            )
            tool_calls.append("helpline_directory")
            citations.append(
                Citation(source_doc="Mission Shakti Guidelines", source_url=hl.primary.source_url)
            )
            facility_line = "You can reach your nearest One Stop Centre for in-person support."
            district = facts.get("district")
            if district:
                geo = await find_facilities(
                    GeoRequest(service_type=ServiceType.OSC, district=district)
                )
                tool_calls.append("geo_locator")
                if geo.facilities:
                    f = geo.facilities[0]
                    facility_line = f"Your nearest One Stop Centre: {f.name}, {f.address}, {f.phone}."
                    citations.append(Citation(source_doc=f.source, section=f.name))
                elif geo.note:
                    facility_line = geo.note
            secondary = ", ".join(e.number for e in hl.secondary if e.number)
            answer = (
                f"Please call Women Helpline {hl.primary.number} (24x7, free)"
                + (f" or {secondary} for immediate danger. " if secondary else ". ")
                + facility_line
            )
            return AgentResponse(
                answer=answer, citations=citations, tool_calls=tool_calls,
                escalation=False, confidence=0.85,
            )

        # PMMVY eligibility path (Journey 4). Personalise if facts are present;
        # otherwise give the grounded general explanation (no forced question).
        child_order = _CHILD_ORDER.get(str(facts.get("child_order", "")).lower())
        income_band = _INCOME_BAND.get(str(facts.get("income_band", "")).lower())
        elig = await check_eligibility(
            EligibilityRequest(
                beneficiary_type=BeneficiaryType.PREGNANT_WOMAN,
                child_order=child_order,
                income_band=income_band,
                second_child_is_girl=facts.get("second_child_is_girl"),
            )
        )
        tool_calls.append("eligibility")
        pmmvy = (
            _pick(elig.eligible, "PMMVY")
            or _pick(elig.ineligible, "PMMVY")
            or _pick(elig.uncertain, "PMMVY")
        )
        citations.append(_cite(pmmvy))

        personalised = ""
        if pmmvy.eligible is True:
            personalised = (
                f" Based on what you've shared, you qualify for {pmmvy.amount} "
                f"({pmmvy.instalments})."
            )
        elif pmmvy.eligible is False:
            personalised = f" Note: {pmmvy.reason}"

        kb = await _kb_citations(packet.user_message, self.scheme)
        if kb:
            tool_calls.append("knowledge_base")
            citations.extend(kb)

        answer = (
            "Under PMMVY (Pradhan Mantri Matru Vandana Yojana), the first living "
            "child brings ₹5,000 in two instalments, and a second child brings "
            "₹6,000 if that child is a girl. Apply at your nearest Anganwadi Centre "
            "or CDPO office with Aadhaar, bank passbook, and MCP card."
            + personalised
        )
        return AgentResponse(
            answer=answer, citations=citations, tool_calls=tool_calls,
            escalation=False, confidence=0.84,
        )


# --------------------------------------------------------------------------- #
# General / fallback
# --------------------------------------------------------------------------- #
class MockGeneralAgent(SpecialistAgent):
    capability_card = GENERAL_CARD

    async def handle(self, packet: ContextPacket) -> AgentResponse:
        citations = await _kb_citations(packet.user_message, None)
        answer = (
            "I can help you discover Ministry of Women & Child Development schemes "
            "for nutrition (Poshan), child protection (Vatsalya), and women's "
            "safety and empowerment (Mission Shakti). Tell me a bit about your "
            "situation and I'll guide you to the right one."
        )
        return AgentResponse(
            answer=answer,
            citations=citations,
            tool_calls=["knowledge_base"] if citations else [],
            confidence=0.7,
        )
