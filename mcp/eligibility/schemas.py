# mcp/eligibility/schemas.py
"""
Pydantic schemas for the eligibility MCP tool.
These types are the ONLY contract between the tool and its callers.
Change them here first, everywhere else follows.

Design note — three-valued eligibility:
``RuleResult.eligible`` is Optional[bool]:
  True  -> qualifies
  False -> does not qualify (with a grounded reason)
  None  -> CANNOT be determined from the facts given; ``needs`` lists the
           missing fields. The orchestrator turns ``needs`` into a slot-filling
           question rather than guessing — a wrong eligibility answer to a
           government beneficiary is worse than one more question.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class BeneficiaryType(str, Enum):
    PREGNANT_WOMAN = "pregnant_woman"
    LACTATING_MOTHER = "lactating_mother"
    CHILD = "child"
    ADOLESCENT_GIRL = "adolescent_girl"
    FAMILY = "family"


class IncomeBand(str, Enum):
    BPL = "BPL"
    APL = "APL"


class CasteCategory(str, Enum):
    SC = "SC"
    ST = "ST"
    OBC = "OBC"
    GENERAL = "General"


class EligibilityRequest(BaseModel):
    beneficiary_type: BeneficiaryType

    # Woman / mother facts
    age_years: Optional[int] = None
    pregnancy_week: Optional[int] = None
    months_postpartum: Optional[int] = Field(
        default=None, description="months since delivery, for lactating-mother windows"
    )
    child_order: Optional[int] = Field(
        default=None, description="birth order of THIS child: 1 = first living child"
    )
    second_child_is_girl: Optional[bool] = Field(
        default=None, description="required to price PMMVY for a second child"
    )

    # Child facts
    child_age_months: Optional[int] = None

    # Socio-economic facts (PMMVY casts a wide net; see rules.py)
    is_awc_enrolled: Optional[bool] = None
    income_band: Optional[IncomeBand] = None
    annual_family_income: Optional[int] = Field(
        default=None, description="net annual family income in ₹, for the PMMVY ₹8 lakh test"
    )
    nfsa_member: Optional[bool] = None
    caste_category: Optional[CasteCategory] = None
    is_disabled: Optional[bool] = Field(
        default=None, description="40%+ disability (Divyang) — a PMMVY qualifying category"
    )

    # Child-protection facts (Vatsalya)
    family_in_crisis: Optional[bool] = Field(
        default=None,
        description="parent death / serious illness / incapacity / crisis putting the child at risk",
    )

    # Geo
    district: Optional[str] = None
    is_aspirational_district: Optional[bool] = Field(
        default=None,
        description="Poshan 2.0 Scheme for Adolescent Girls runs only in Aspirational Districts & NER",
    )


class RuleResult(BaseModel):
    scheme: str
    eligible: Optional[bool] = Field(
        description="True / False / None(uncertain — see needs)"
    )
    benefit_summary: str = ""
    amount: Optional[str] = None
    instalments: Optional[str] = None
    reason: str
    needs: list[str] = Field(
        default_factory=list, description="facts required to resolve an uncertain result"
    )
    source_doc: str
    source_url: str = ""


class EligibilityResponse(BaseModel):
    eligible: list[RuleResult] = Field(default_factory=list)
    ineligible: list[RuleResult] = Field(default_factory=list)
    uncertain: list[RuleResult] = Field(default_factory=list)
    checked_schemes: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
