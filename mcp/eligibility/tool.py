# mcp/eligibility/tool.py
"""
The eligibility MCP tool — the callable surface specialist agents use to check,
deterministically and with citations, which schemes a citizen qualifies for.

No LLM, no network: pure rule evaluation (see rules.py), so every answer is
auditable and reproducible. Results are bucketed into eligible / ineligible /
uncertain. An ``uncertain`` result carries ``needs`` (the missing facts); the
orchestrator turns those into slot-filling questions rather than guessing.

Usage (from a specialist's ``handle``):

    from mcp.eligibility.schemas import BeneficiaryType, EligibilityRequest
    from mcp.eligibility.tool import check_eligibility

    resp = await check_eligibility(EligibilityRequest(
        beneficiary_type=BeneficiaryType.PREGNANT_WOMAN, child_order=1, income_band="BPL",
    ))
    resp.eligible      # -> [RuleResult(scheme="PMMVY", ...), RuleResult(scheme="Poshan 2.0 SNP...", ...)]
    resp.uncertain     # -> rules that need one more fact (see .needs)
"""

from __future__ import annotations

import time

from mcp.eligibility.rules import RULES_BY_TYPE
from mcp.eligibility.schemas import EligibilityRequest, EligibilityResponse


async def check_eligibility(request: EligibilityRequest) -> EligibilityResponse:
    start = time.perf_counter()

    rules = RULES_BY_TYPE.get(request.beneficiary_type, [])
    results = [rule(request) for rule in rules]

    eligible = [r for r in results if r.eligible is True]
    ineligible = [r for r in results if r.eligible is False]
    uncertain = [r for r in results if r.eligible is None]

    latency_ms = (time.perf_counter() - start) * 1000
    return EligibilityResponse(
        eligible=eligible,
        ineligible=ineligible,
        uncertain=uncertain,
        checked_schemes=[r.scheme for r in results],
        latency_ms=latency_ms,
    )
