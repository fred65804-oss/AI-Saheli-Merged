"""Real Vatsalya specialist — child protection, safety-critical, grounded.

Four deterministic branches (routing logic, not scheme knowledge). A prior
version always answered with the "report a child in need of care" framing —
correct for an active concern, but wrong for "how do I adopt a child?" or
"what is the foster care process?", which got the CHILDLINE-reporting spiel
instead of an actual answer to what was asked:

  A. Foster care  → eligibility tool (Model Foster Care Guidelines, ₹4,000/mo).
  B. Sponsorship  → eligibility tool; "family_in_crisis" unknown becomes a real
                    ``needs`` SlotRequest so the follow-up turn is tracked
                    (the same fix applied to Shakti's PMMVY branch — without
                    it, embedding the question only in prose leaves the
                    orchestrator unaware a slot is pending, and the citizen's
                    next reply gets mis-routed as a fresh message).
  C. Adoption     → CARA/adoption-process info (no eligibility rule applies —
                    adoption is a legal process, not an income/age-gated
                    benefit); nearest CWC when the district is known.
  D. Report/concern (default) → CHILDLINE 1098 + nearest DCPU. This stays the
                    fallback because an unflagged concern about a child at
                    risk ("a child near me is being made to work") must still
                    reach a helpline, not a generic answer.

The orchestrator's safety gate escalates ACTIVE distress before this agent is
ever reached — branch D serves informational "how do I report a concern"
queries, not live emergencies.
"""

from __future__ import annotations

from agents.orchestrator.capabilities import VATSALYA_CARD
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
from mcp.eligibility.schemas import BeneficiaryType, EligibilityRequest
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
_FOSTER_HINTS = ("foster",)
_SPONSOR_HINTS = ("sponsor",)
_ADOPT_HINTS = ("adopt", "god lena", "god le", "cara", "गोद")


async def _nearest_facility_line(
    service_type: ServiceType, district: str | None, label: str
) -> tuple[str, list[str], list[Citation]]:
    """Shared 'nearest X' lookup used by every branch that names a facility.
    Returns (fallback_line, tool_calls, citations)."""
    if not district:
        return "", [], []
    geo = await find_facilities(GeoRequest(service_type=service_type, district=district))
    if geo.facilities:
        f = geo.facilities[0]
        line = f"Your nearest {label}: {f.name}, {f.address}" + (
            f", {f.phone}" if f.phone else ""
        ) + "."
        return line, ["geo_locator"], [Citation(source_doc=f.source, section=f.name)]
    if geo.note:
        return geo.note, ["geo_locator"], []
    return "", ["geo_locator"], []


class RealVatsalyaAgent(SpecialistAgent):
    capability_card = VATSALYA_CARD

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
        if any(k in msg for k in _FOSTER_HINTS):
            return await self._handle_foster(packet)
        if any(k in msg for k in _SPONSOR_HINTS) or facts.get("family_in_crisis"):
            return await self._handle_sponsorship(packet)
        if any(k in msg for k in _ADOPT_HINTS):
            return await self._handle_adoption(packet)
        return await self._handle_report(packet)

    # ------------------------------------------------------ branch A: foster
    async def _handle_foster(self, packet: ContextPacket) -> AgentResponse:
        facts = packet.collected_facts
        elig = await check_eligibility(
            EligibilityRequest(beneficiary_type=BeneficiaryType.CHILD, district=facts.get("district"))
        )
        foster = _pick(elig.eligible, "Foster") or _pick(elig.ineligible, "Foster")
        tool_calls = ["eligibility"]
        citations: list[Citation] = []
        tool_facts: list[str] = []
        fallback_parts: list[str] = []
        if foster is not None:
            citations.append(Citation(source_doc=foster.source_doc, source_url=foster.source_url))
            tool_facts.append(f"Foster care verdict (rules engine): {foster.reason}")
            fallback_parts.append(foster.reason)

        line, extra_calls, extra_cites = await _nearest_facility_line(
            ServiceType.DCPU, facts.get("district"), "DCPU"
        )
        tool_calls += extra_calls
        citations += extra_cites
        if line:
            tool_facts.append(line)
            fallback_parts.append(line)

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
            fallback=" ".join(fallback_parts) or "Foster care is arranged by your District Child Protection Unit (DCPU) under a CWC order.",
        )
        return AgentResponse(answer=answer, citations=citations, tool_calls=tool_calls, confidence=0.86 if synthesized else 0.8)

    # -------------------------------------------------- branch B: sponsorship
    async def _handle_sponsorship(self, packet: ContextPacket) -> AgentResponse:
        facts = packet.collected_facts
        elig = await check_eligibility(
            EligibilityRequest(
                beneficiary_type=BeneficiaryType.FAMILY,
                family_in_crisis=to_bool(facts.get("family_in_crisis")),
                district=facts.get("district"),
            )
        )
        tool_calls = ["eligibility"]
        sponsor = _pick(elig.eligible, "Sponsorship") or _pick(elig.ineligible, "Sponsorship") or _pick(elig.uncertain, "Sponsorship")
        if sponsor is None:
            return AgentResponse(answer="", tool_calls=tool_calls, confidence=0.4)

        # Uncertain → ask family_in_crisis as a real slot (tracked follow-up),
        # not just a question embedded in prose (see module docstring).
        if sponsor.eligible is None and "family_in_crisis" in sponsor.needs:
            req = SlotRequest(name="family_in_crisis", reason=sponsor.reason, type="bool")
            return AgentResponse(answer="", needs=[req], tool_calls=tool_calls, confidence=0.85)

        citations = [Citation(source_doc=sponsor.source_doc, source_url=sponsor.source_url)]
        tool_facts = [f"Sponsorship verdict (rules engine): {sponsor.reason}"]
        fallback_parts = [sponsor.reason]

        line, extra_calls, extra_cites = await _nearest_facility_line(
            ServiceType.DCPU, facts.get("district"), "DCPU"
        )
        tool_calls += extra_calls
        citations += extra_cites
        if line:
            tool_facts.append(line)
            fallback_parts.append(line)

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
        return AgentResponse(answer=answer, citations=citations, tool_calls=tool_calls, confidence=0.86 if synthesized else 0.8)

    # ----------------------------------------------------- branch C: adoption
    async def _handle_adoption(self, packet: ContextPacket) -> AgentResponse:
        facts = packet.collected_facts
        tool_calls: list[str] = []
        # CARA is the named statutory authority for adoption in India — a
        # stable public-portal identifier, not a graded scheme fact (no
        # amount/eligibility rule is being asserted here). Still cited, so
        # this claim never rests on KB retrieval succeeding.
        citations: list[Citation] = [
            Citation(
                source_doc="CARA — Central Adoption Resource Authority",
                source_url="https://cara.wcd.gov.in/",
            )
        ]
        tool_facts = [
            "Adoption in India is governed by CARA (Central Adoption Resource "
            "Authority) via cara.wcd.gov.in, through a Specialised Adoption "
            "Agency (SAA)."
        ]
        fallback_parts = [
            "To adopt, register on the CARA portal (cara.wcd.gov.in) through a "
            "Specialised Adoption Agency (SAA)."
        ]

        line, extra_calls, extra_cites = await _nearest_facility_line(
            ServiceType.CWC, facts.get("district"), "Child Welfare Committee (CWC)"
        )
        tool_calls += extra_calls
        citations += extra_cites
        if line:
            tool_facts.append(line)
            fallback_parts.append(line)

        chunks = await retrieve_passages(packet.user_message, self.scheme)
        if chunks:
            tool_calls.append("knowledge_base")
            citations.extend(chunks_to_citations(chunks))
            fallback_parts.append(citation_hint(chunks))

        answer, synthesized = await synthesize_answer(
            self.llm,
            scheme_display=self.capability_card.display_name,
            user_message=packet.user_message,
            collected_facts=facts,
            tool_facts=tool_facts,
            chunks=chunks,
            fallback=" ".join(fallback_parts),
        )
        return AgentResponse(answer=answer, citations=citations, tool_calls=tool_calls, confidence=0.85 if synthesized else 0.78)

    # ------------------------------------------------- branch D: report (default)
    async def _handle_report(self, packet: ContextPacket) -> AgentResponse:
        facts = packet.collected_facts
        tool_calls: list[str] = []
        citations: list[Citation] = []

        hl = await lookup_helplines(
            HelplineRequest(category=HelplineCategory.CHILD_PROTECTION, scheme=HelplineScheme.VATSALYA)
        )
        tool_calls.append("helpline_directory")
        childline = hl.primary
        tool_facts = [
            f"To report a child in need of care and protection: call "
            f"{childline.name} {childline.number} ({childline.hours}, free)"
        ]
        citations.append(Citation(source_doc=childline.name, source_url=childline.source_url))
        secondary_numbers = ", ".join(f"{e.name} {e.number}" for e in hl.secondary if e.number)
        if secondary_numbers:
            tool_facts.append(f"In an emergency: {secondary_numbers}")
        contact = f"call {childline.name} {childline.number} ({childline.hours}, free)"
        if secondary_numbers:
            contact += f" or {secondary_numbers} in an emergency"
        fallback_parts = [
            f"To report a child in need of care and protection, {contact}, or "
            "contact your District Child Protection Unit (DCPU)."
        ]

        line, extra_calls, extra_cites = await _nearest_facility_line(
            ServiceType.DCPU, facts.get("district"), "DCPU"
        )
        tool_calls += extra_calls
        citations += extra_cites
        if line:
            tool_facts.append(line)
            fallback_parts.append(line)

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
        return AgentResponse(answer=answer, citations=citations, tool_calls=tool_calls, confidence=0.82 if synthesized else 0.78)
