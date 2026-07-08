# mcp/eligibility/rules.py
"""
Deterministic, auditable eligibility rules. NO LLM, NO AI — pure if/else so the
result is testable and defensible to a Ministry auditor.

Every numeric threshold and benefit figure below was verified against the
official scheme PDFs in the project's RAG corpus (rag/data/*). Where a commonly
cited condition could NOT be grounded in those documents, it is deliberately
NOT enforced as a rejection — see the inline SOURCE/NOTE comments. Giving a
beneficiary a wrong "you don't qualify" is the worst failure mode here.

Grounding highlights (vs. the original plan, which was partly outdated):
  * PMMVY 2.0 covers the FIRST TWO children if the second is a girl — first
    child ₹5,000 in two instalments, second (girl) child ₹6,000 in one.
    Eligibility net is wide: family income < ₹8 lakh OR SC/ST OR 40%+ disabled
    OR BPL OR NFSA/PMJAY/e-Shram/MGNREGA etc. Claim window is up to 730 days of
    pregnancy — NOT a 19-week cutoff.
    SOURCE: Mission Shakti Guidelines (Samarthya/PMMVY), p28.
  * The Poshan 2.0 adolescent-girl component is 14–18 yrs in Aspirational
    Districts & NER — NOT the old SABLA "out-of-school/BPL" gate.
    SOURCE: Saksham Anganwadi & Poshan 2.0 Guidelines.
  * Vatsalya non-institutional support (Sponsorship / Foster / After Care) is
    ₹4,000/month per child. SOURCE: Mission Vatsalya Guidelines, p24 & p32.
"""

from __future__ import annotations

from .schemas import BeneficiaryType, CasteCategory, EligibilityRequest, IncomeBand, RuleResult

# --------------------------------------------------------------------------- #
# Grounding sources
# --------------------------------------------------------------------------- #
PMMVY_DOC = "Mission Shakti Guidelines (Samarthya — PMMVY 2.0), MoWCD"
PMMVY_URL = "https://missionshakti.wcd.gov.in/public/documents/whatsnew/Mission_Shakti_Guidelines.pdf"

POSHAN_DOC = "Saksham Anganwadi & Poshan 2.0 Operational Guidelines, MoWCD"
# TODO(source): confirm the exact operational-guideline PDF URL; portal used as placeholder.
POSHAN_URL = "https://poshantracker.in/"

VATSALYA_DOC = "Mission Vatsalya Guidelines, MoWCD"
VATSALYA_URL = "https://wcd.nic.in/schemes/mission-vatsalya"

FOSTER_DOC = "Model Foster Care Guidelines 2024 (Mission Vatsalya), MoWCD"
FOSTER_URL = "https://wcd.nic.in/schemes/mission-vatsalya"

PMMVY_INCOME_CEILING = 800_000  # ₹8 lakh net annual family income (Mission Shakti Guidelines p28)


def _pmmvy_socioeconomic(req: EligibilityRequest) -> bool | None:
    """PMMVY 2.0 qualifying-category test. True / False / None(unknown).

    Wide net (any ONE qualifies): SC/ST, 40%+ disabled, BPL card, NFSA/PMJAY/
    e-Shram/MGNREGA-type membership, OR net family income < ₹8 lakh.
    Only if income is KNOWN to be >= ₹8 lakh and no other positive flag is seen
    do we return False; otherwise, absent any positive signal, we stay unsure.
    """
    positive = (
        (req.caste_category in (CasteCategory.SC, CasteCategory.ST))
        or (req.is_disabled is True)
        or (req.income_band == IncomeBand.BPL)
        or (req.nfsa_member is True)
        or (req.annual_family_income is not None and req.annual_family_income < PMMVY_INCOME_CEILING)
    )
    if positive:
        return True
    if req.annual_family_income is not None and req.annual_family_income >= PMMVY_INCOME_CEILING:
        return False
    return None


def check_pmmvy(req: EligibilityRequest) -> RuleResult:
    base = dict(scheme="PMMVY", source_doc=PMMVY_DOC, source_url=PMMVY_URL)

    if req.beneficiary_type not in (
        BeneficiaryType.PREGNANT_WOMAN,
        BeneficiaryType.LACTATING_MOTHER,
    ):
        return RuleResult(
            **base, eligible=False,
            reason="PMMVY is for pregnant women and lactating mothers.",
        )

    # Birth-order gate first (cheapest determinant of amount + eligibility).
    if req.child_order is None:
        return RuleResult(
            **base, eligible=None, needs=["child_order"],
            reason="Is this your first or second living child? PMMVY covers the "
            "first two children, the second only if she is a girl.",
        )

    if req.child_order >= 3:
        return RuleResult(
            **base, eligible=False,
            reason="PMMVY covers up to two children (the second only if a girl child); "
            "it does not apply to a third or later child.",
        )

    if req.child_order == 2:
        if req.second_child_is_girl is None:
            return RuleResult(
                **base, eligible=None, needs=["second_child_is_girl"],
                reason="For a second child, PMMVY applies only if the child is a girl. "
                "Is your second child a girl?",
            )
        if req.second_child_is_girl is False:
            return RuleResult(
                **base, eligible=False,
                reason="For a second child, PMMVY benefit is available only if that "
                "child is a girl.",
            )
        amount, instalments = "₹6,000", "One instalment after birth (registration during pregnancy is mandatory)."
        benefit = "Additional maternity benefit for a second girl child."
    else:  # child_order == 1
        amount, instalments = "₹5,000", "Two instalments (₹3,000 + ₹2,000 on childbirth registration & the child's first immunisation cycle)."
        benefit = "Maternity benefit for the first living child."

    socio = _pmmvy_socioeconomic(req)
    if socio is None:
        return RuleResult(
            **base, eligible=None,
            needs=["annual_family_income", "caste_category", "income_band"],
            amount=amount, instalments=instalments, benefit_summary=benefit,
            reason="Almost there — PMMVY covers women with net family income under "
            "₹8 lakh, or from SC/ST, BPL, disabled, or NFSA/PMJAY/e-Shram/MGNREGA "
            "households. Can you share family income or category?",
        )
    if socio is False:
        return RuleResult(
            **base, eligible=False, amount=amount, instalments=instalments,
            reason="Net family income is ₹8 lakh or above and no other qualifying "
            "category (SC/ST, BPL, disabled, NFSA/PMJAY/e-Shram/MGNREGA) applies.",
        )
    return RuleResult(
        **base, eligible=True, amount=amount, instalments=instalments,
        benefit_summary=benefit,
        reason="Qualifies: eligible child order and a qualifying socio-economic "
        "category. Claim can be made any time up to 730 days of pregnancy at the "
        "Anganwadi / ASHA with Aadhaar and bank account.",
    )


def check_thr_snp(req: EligibilityRequest) -> RuleResult:
    """Supplementary Nutrition Programme under Poshan 2.0 — Take-Home Ration (THR)
    for 6mo–3yr children and PW&LM; Hot Cooked Meal (HCM) for 3–6yr at the AWC.
    Universal for registered beneficiaries — NOT income-tested.
    """
    base = dict(scheme="Poshan 2.0 SNP (THR/HCM)", source_doc=POSHAN_DOC, source_url=POSHAN_URL)

    if req.beneficiary_type == BeneficiaryType.PREGNANT_WOMAN:
        return RuleResult(
            **base, eligible=True, amount="Take-Home Ration (THR)",
            benefit_summary="Take-Home Ration through your Anganwadi Centre.",
            reason="Pregnant women registered at an Anganwadi Centre receive THR "
            "under Poshan 2.0. This is universal for registered beneficiaries — not "
            "income-tested." + ("" if req.is_awc_enrolled else " Enrol at your AWC to start receiving it."),
        )

    if req.beneficiary_type == BeneficiaryType.LACTATING_MOTHER:
        if req.months_postpartum is None:
            return RuleResult(
                **base, eligible=None, needs=["months_postpartum"],
                reason="How many months since delivery? THR for lactating mothers "
                "runs up to 6 months postpartum.",
            )
        if req.months_postpartum <= 6:
            return RuleResult(
                **base, eligible=True, amount="Take-Home Ration (THR)",
                benefit_summary="Take-Home Ration for the first 6 months postpartum.",
                reason="Lactating mothers receive THR through the AWC up to 6 months "
                "after delivery.",
            )
        return RuleResult(
            **base, eligible=False,
            reason="THR for lactating mothers covers up to 6 months postpartum; "
            "your child may instead qualify for child nutrition (6 months+).",
        )

    if req.beneficiary_type == BeneficiaryType.CHILD:
        if req.child_age_months is None:
            return RuleResult(
                **base, eligible=None, needs=["child_age_months"],
                reason="How old is the child in months? Nutrition support differs by age.",
            )
        m = req.child_age_months
        if m < 6:
            return RuleResult(
                **base, eligible=False,
                reason="Under 6 months, exclusive breastfeeding is advised; SNP food "
                "supplementation begins at 6 months.",
            )
        if m <= 36:
            return RuleResult(
                **base, eligible=True, amount="Take-Home Ration (THR)",
                benefit_summary="Take-Home Ration for children 6 months–3 years.",
                reason="Children aged 6 months to 3 years registered at the AWC receive "
                "THR under Poshan 2.0.",
            )
        if m <= 72:
            return RuleResult(
                **base, eligible=True, amount="Hot Cooked Meal (HCM) at the AWC",
                benefit_summary="Hot Cooked Meal at the Anganwadi for children 3–6 years.",
                reason="Children aged 3–6 years receive a Hot Cooked Meal at the "
                "Anganwadi Centre (not take-home) under Poshan 2.0.",
            )
        return RuleResult(
            **base, eligible=False,
            reason="Poshan 2.0 SNP covers children up to 6 years of age.",
        )

    return RuleResult(
        **base, eligible=False,
        reason="SNP (THR/HCM) is for pregnant/lactating women and children under 6.",
    )


def check_sag(req: EligibilityRequest) -> RuleResult:
    """Scheme for Adolescent Girls under Poshan 2.0 — girls 14–18, in Aspirational
    Districts & NER only. (Corrects the plan's outdated SABLA out-of-school/BPL gate.)
    """
    base = dict(scheme="Poshan 2.0 — Scheme for Adolescent Girls", source_doc=POSHAN_DOC, source_url=POSHAN_URL)

    if req.beneficiary_type != BeneficiaryType.ADOLESCENT_GIRL:
        return RuleResult(**base, eligible=False, reason="This component is for adolescent girls (14–18).")

    if req.age_years is None:
        return RuleResult(
            **base, eligible=None, needs=["age_years"],
            reason="How old is she? The Scheme for Adolescent Girls covers ages 14–18.",
        )
    if not (14 <= req.age_years <= 18):
        return RuleResult(
            **base, eligible=False,
            reason="The Scheme for Adolescent Girls under Poshan 2.0 covers ages 14–18.",
        )

    if req.is_aspirational_district is None:
        return RuleResult(
            **base, eligible=None, needs=["is_aspirational_district"],
            reason="Age qualifies. This scheme runs only in Aspirational Districts & "
            "the North-Eastern Region — is your district one of these?",
        )
    if req.is_aspirational_district is False:
        return RuleResult(
            **base, eligible=False,
            reason="Age qualifies, but the Scheme for Adolescent Girls under Poshan 2.0 "
            "operates only in Aspirational Districts & the North-Eastern Region.",
        )
    return RuleResult(
        **base, eligible=True,
        benefit_summary="Nutrition support + life-skills for out-of-school adolescent girls at the AWC.",
        reason="Qualifies: age 14–18 in an Aspirational District / NER. Enrol at your "
        "Anganwadi Centre.",
    )


def check_sponsorship(req: EligibilityRequest) -> RuleResult:
    """Mission Vatsalya Sponsorship — ₹4,000/month per child, non-institutional
    support for a child living with a family facing a crisis. DCPU recommends /
    CWC or DM approves.
    NOTE: the plan's "income below ₹2 lakh" cutoff was NOT found in the corpus,
    so it is not enforced here — need is assessed by the DCPU.
    """
    base = dict(scheme="Mission Vatsalya — Sponsorship", source_doc=VATSALYA_DOC, source_url=VATSALYA_URL)

    if req.beneficiary_type not in (BeneficiaryType.CHILD, BeneficiaryType.FAMILY):
        return RuleResult(**base, eligible=False, reason="Sponsorship supports children living with their family.")

    if req.family_in_crisis is None:
        return RuleResult(
            **base, eligible=None, needs=["family_in_crisis"],
            reason="Sponsorship supports children whose family faces a crisis — the "
            "death, serious illness, incapacity, or extreme hardship of a parent. "
            "Does that describe the situation?",
        )
    if req.family_in_crisis is False:
        return RuleResult(
            **base, eligible=False,
            reason="Sponsorship targets children in families facing a crisis "
            "(parent death/illness/incapacity/extreme hardship).",
        )
    return RuleResult(
        **base, eligible=True, amount="₹4,000/month per child",
        benefit_summary="Monthly financial support to keep the child with their family.",
        reason="A child in a family facing a crisis can be sponsored at ₹4,000/month. "
        "Apply through the District Child Protection Unit (DCPU); the CWC/DM approves. "
        "The DCPU assesses need on a case-by-case basis.",
    )


def check_foster(req: EligibilityRequest) -> RuleResult:
    """Mission Vatsalya Foster Care (Model Foster Care Guidelines 2024) —
    ₹4,000/month; a child in need of care & protection is placed with an assessed,
    biologically-unrelated family under a CWC order. Final suitability is
    DCPU/CWC-assessed, so this is presented as an available pathway, not an
    auto-grant.
    """
    base = dict(scheme="Mission Vatsalya — Foster Care", source_doc=FOSTER_DOC, source_url=FOSTER_URL)

    if req.beneficiary_type not in (BeneficiaryType.CHILD, BeneficiaryType.FAMILY):
        return RuleResult(**base, eligible=False, reason="Foster care concerns a child in need of care & protection.")

    return RuleResult(
        **base, eligible=True, amount="₹4,000/month per child",
        benefit_summary="A child in need of care & protection is placed with an assessed foster family.",
        reason="Foster care is available for a child in need of care & protection, with "
        "₹4,000/month support. It is arranged by the DCPU under a CWC order; the foster "
        "family is assessed (stable home, no criminal record, capacity to care). Final "
        "suitability is decided by the DCPU/CWC.",
    )


# Dispatch table: which rules run for each beneficiary type.
RULES_BY_TYPE = {
    BeneficiaryType.PREGNANT_WOMAN: [check_pmmvy, check_thr_snp],
    BeneficiaryType.LACTATING_MOTHER: [check_pmmvy, check_thr_snp],
    BeneficiaryType.CHILD: [check_thr_snp, check_sponsorship, check_foster],
    BeneficiaryType.ADOLESCENT_GIRL: [check_sag],
    BeneficiaryType.FAMILY: [check_sponsorship, check_foster],
}
