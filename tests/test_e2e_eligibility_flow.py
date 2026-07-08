"""One full end-to-end flow of the eligibility MCP tool — the deterministic,
grounded surface specialist agents use to tell a citizen what they qualify for.

Deliberately a single scripted scenario (not many mini-tests): the PMMVY
first-child grant, the second-girl-child (₹6,000) provision, the second-non-girl
rejection, the slot-filling `needs` loop when a fact is missing, the wide
socio-economic net, THR-vs-HCM by child age, and the Vatsalya sponsorship
pathway are all exercised in sequence — the way a real conversation would.

Fully offline and deterministic: no LLM, no network. Every asserted number is
grounded in the official scheme PDFs (see rules.py SOURCE comments).
"""

import pytest

from mcp.eligibility.schemas import BeneficiaryType, CasteCategory, EligibilityRequest, IncomeBand
from mcp.eligibility.tool import check_eligibility

pytestmark = pytest.mark.asyncio


def _by_scheme(results, name):
    return next(r for r in results if r.scheme == name)


async def test_full_eligibility_flow():
    # 1. Pregnant woman, first child, BPL → PMMVY eligible (₹5,000, two instalments)
    #    AND THR eligible in the same call.
    r1 = await check_eligibility(
        EligibilityRequest(
            beneficiary_type=BeneficiaryType.PREGNANT_WOMAN,
            child_order=1,
            income_band=IncomeBand.BPL,
        )
    )
    pmmvy = _by_scheme(r1.eligible, "PMMVY")
    assert pmmvy.amount == "₹5,000"
    assert "Two instalments" in pmmvy.instalments
    assert pmmvy.source_url.endswith(".pdf")  # grounded citation
    assert any("SNP" in r.scheme for r in r1.eligible)  # THR rides along
    assert r1.latency_ms >= 0
    assert "PMMVY" in r1.checked_schemes

    # 2. Second child, and she is a girl → PMMVY ₹6,000 (the provision the plan missed).
    r2 = await check_eligibility(
        EligibilityRequest(
            beneficiary_type=BeneficiaryType.PREGNANT_WOMAN,
            child_order=2,
            second_child_is_girl=True,
            caste_category=CasteCategory.SC,
        )
    )
    assert _by_scheme(r2.eligible, "PMMVY").amount == "₹6,000"

    # 3. Second child, NOT a girl → PMMVY ineligible, with a clear grounded reason.
    r3 = await check_eligibility(
        EligibilityRequest(
            beneficiary_type=BeneficiaryType.PREGNANT_WOMAN,
            child_order=2,
            second_child_is_girl=False,
            income_band=IncomeBand.BPL,
        )
    )
    pmmvy3 = _by_scheme(r3.ineligible, "PMMVY")
    assert pmmvy3.eligible is False
    assert "girl" in pmmvy3.reason.lower()

    # 4. Slot-filling loop: pregnant woman, child_order unknown → PMMVY UNCERTAIN,
    #    asking exactly for child_order (not a crash, not a guess).
    r4 = await check_eligibility(
        EligibilityRequest(beneficiary_type=BeneficiaryType.PREGNANT_WOMAN)
    )
    pmmvy4 = _by_scheme(r4.uncertain, "PMMVY")
    assert pmmvy4.eligible is None
    assert pmmvy4.needs == ["child_order"]

    # 5. Income above the ₹8 lakh ceiling with no other qualifying category →
    #    PMMVY ineligible on income (the corrected, wide-net rule).
    r5 = await check_eligibility(
        EligibilityRequest(
            beneficiary_type=BeneficiaryType.PREGNANT_WOMAN,
            child_order=1,
            annual_family_income=1_200_000,
            caste_category=CasteCategory.GENERAL,
            income_band=IncomeBand.APL,
            is_disabled=False,
            nfsa_member=False,
        )
    )
    assert _by_scheme(r5.ineligible, "PMMVY").eligible is False

    # 6. Child nutrition by age: 18 months → THR; 4 years → Hot Cooked Meal.
    r_thr = await check_eligibility(
        EligibilityRequest(beneficiary_type=BeneficiaryType.CHILD, child_age_months=18)
    )
    snp_thr = _by_scheme(r_thr.eligible, "Poshan 2.0 SNP (THR/HCM)")
    assert "THR" in snp_thr.amount

    r_hcm = await check_eligibility(
        EligibilityRequest(beneficiary_type=BeneficiaryType.CHILD, child_age_months=48)
    )
    snp_hcm = _by_scheme(r_hcm.eligible, "Poshan 2.0 SNP (THR/HCM)")
    assert "Hot Cooked Meal" in snp_hcm.amount

    # 7. Vatsalya: a family in crisis → Sponsorship at ₹4,000/month (grounded p24/p32).
    r_sponsor = await check_eligibility(
        EligibilityRequest(beneficiary_type=BeneficiaryType.FAMILY, family_in_crisis=True)
    )
    sponsor = _by_scheme(r_sponsor.eligible, "Mission Vatsalya — Sponsorship")
    assert sponsor.amount == "₹4,000/month per child"
    assert "DCPU" in sponsor.reason
