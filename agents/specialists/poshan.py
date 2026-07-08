"""Real Poshan specialist — maternal & child nutrition, grounded end-to-end.

Pipeline per turn:
  1. Dynamic questioning — ask the trimester once we know it's a pregnant
     woman (the single most informative missing fact).
  2. Deterministic medical red-flag check → route to the local ANM/AWW via the
     helpline directory (Poshan is medium safety: flag, don't counsel).
  3. eligibility tool  → which nutrition benefit applies (THR / HCM / SAG).
  4. geo_locator tool  → nearest Anganwadi Centre when the district is known.
  5. knowledge_base    → official Poshan 2.0 passages (retrieved once, used
     for BOTH synthesis and citations).
  6. LLM synthesis of facts + passages; deterministic tool-only fallback when
     no LLM is available. No scheme fact ever originates in this file.
"""

from __future__ import annotations

from agents.orchestrator.capabilities import POSHAN_CARD
from agents.orchestrator.llm import StructuredLLM, get_llm
from agents.specialists._grounding import (
    chunks_to_citations,
    citation_hint,
    retrieve_passages,
    synthesize_answer,
)
from agents.specialists.base import (
    AgentResponse,
    Citation,
    ContextPacket,
    SlotRequest,
    SpecialistAgent,
)
from mcp.eligibility.schemas import BeneficiaryType, EligibilityRequest, RuleResult
from mcp.eligibility.tool import check_eligibility
from mcp.geo_locator.schemas import LookupRequest as GeoRequest, ServiceType
from mcp.geo_locator.tool import find_facilities
from mcp.helpline_directory.schemas import (
    Category as HelplineCategory,
    LookupRequest as HelplineRequest,
    Scheme as HelplineScheme,
)
from mcp.helpline_directory.tool import lookup_helplines

# Deterministic danger-sign trigger (EN / Hinglish). This is routing logic,
# not medical knowledge: any hit routes the citizen to the ANM/AWW referral
# defined in the helpline directory data. High recall over precision.
_MEDICAL_RED_FLAGS = (
    "bleeding", "khoon aa", "khoon beh", "spotting",
    "high fever", "tez bukhar", "bukhar hai",
    "swelling", "sujan", "swollen",
    "not moving", "no movement", "movement nahi", "hil nahi",
    "seizure", "fits", "behosh", "unconscious", "faint",
    "severe pain", "tez dard", "bahut dard",
    "blurred vision", "dhundhla",
)


def _has_medical_red_flag(text: str) -> bool:
    low = text.lower()
    return any(flag in low for flag in _MEDICAL_RED_FLAGS)


def _pick(results: list[RuleResult], scheme_contains: str) -> RuleResult | None:
    for r in results:
        if scheme_contains.lower() in r.scheme.lower():
            return r
    return None


class RealPoshanAgent(SpecialistAgent):
    capability_card = POSHAN_CARD

    def __init__(self, llm: StructuredLLM | None = None) -> None:
        self._llm = llm

    @property
    def llm(self) -> StructuredLLM:
        # Resolved lazily so importing the registry never forces a provider.
        if self._llm is None:
            self._llm = get_llm()
        return self._llm

    async def handle(self, packet: ContextPacket) -> AgentResponse:
        facts = packet.collected_facts

        # 1. Dynamic questioning: trimester decides the guidance.
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
        tool_facts: list[str] = []
        fallback_parts: list[str] = []

        # 2. Medical red-flag → ANM/AWW referral from the helpline directory.
        if _has_medical_red_flag(packet.user_message):
            hl = await lookup_helplines(
                HelplineRequest(
                    category=HelplineCategory.MEDICAL_RED_FLAG,
                    scheme=HelplineScheme.POSHAN,
                )
            )
            tool_calls.append("helpline_directory")
            referral = hl.primary
            tool_facts.append(
                f"POSSIBLE DANGER SIGN in the question — the citizen must see "
                f"their {referral.name} right away; give no medical advice. "
                f"When to go: {referral.when_to_call}"
            )
            citations.append(
                Citation(source_doc=referral.name, source_url=referral.source_url)
            )
            fallback_parts.append(
                f"What you describe can be a danger sign — please see your "
                f"{referral.name} right away."
            )

        # 3. Eligibility: which nutrition benefit applies?
        beneficiary = facts.get("beneficiary_type") or "pregnant_woman"
        try:
            btype = BeneficiaryType(beneficiary)
        except ValueError:
            btype = BeneficiaryType.PREGNANT_WOMAN
        elig = await check_eligibility(
            EligibilityRequest(
                beneficiary_type=btype,
                pregnancy_week=facts.get("pregnancy_week"),
                child_age_months=facts.get("child_age_months"),
                # Demo assumption: the citizen is (or will be) AWC-enrolled —
                # enrolment itself happens at the centre we point them to.
                is_awc_enrolled=True,
                district=facts.get("district"),
            )
        )
        tool_calls.append("eligibility")
        snp = (
            _pick(elig.eligible, "SNP")
            or _pick(elig.uncertain, "SNP")
            or _pick(elig.ineligible, "SNP")
        )
        if snp is not None:
            citations.append(Citation(source_doc=snp.source_doc, source_url=snp.source_url))
            if snp.eligible:
                tool_facts.append(
                    f"Entitlement ({snp.scheme}): {snp.amount} — {snp.benefit_summary}"
                )
                fallback_parts.append(
                    f"You are entitled to {snp.amount} — {snp.benefit_summary}"
                )
            else:
                tool_facts.append(f"Entitlement check ({snp.scheme}): {snp.reason}")

        # 4. Nearest Anganwadi Centre, if we know the district.
        district = facts.get("district")
        if district:
            geo = await find_facilities(
                GeoRequest(service_type=ServiceType.AWC, district=district)
            )
            tool_calls.append("geo_locator")
            if geo.facilities:
                f = geo.facilities[0]
                tool_facts.append(
                    f"Nearest Anganwadi Centre: {f.name}, {f.address}"
                    + (f", phone {f.phone}" if f.phone else "")
                )
                citations.append(Citation(source_doc=f.source, section=f.name))
                fallback_parts.append(
                    f"Your nearest Anganwadi Centre is {f.name}, {f.address}."
                )
            elif geo.note:
                fallback_parts.append(f"({geo.note})")

        # 5. Official passages — retrieved once, used for synthesis + citations.
        chunks = await retrieve_passages(packet.user_message, self.scheme)
        if chunks:
            tool_calls.append("knowledge_base")
            citations.extend(chunks_to_citations(chunks))
            fallback_parts.append(citation_hint(chunks))
        fallback_parts.append(
            "Your Anganwadi worker can guide you in detail — please visit your "
            "nearest centre."
        )

        # 6. Grounded synthesis (deterministic fallback offline).
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
            confidence=0.9 if synthesized else 0.8,
        )
