# mcp/helpline_directory/tool.py
"""
The helpline_directory MCP tool — the callable surface specialist agents use to
get the right helpline(s) for a distress category, grounded in helplines.yaml.

Deterministic and offline: no LLM, no network. The store is loaded and validated
once per process (see loader.get_store).

Usage (from a specialist's ``handle``):

    from mcp.helpline_directory.schemas import Category, LookupRequest
    from mcp.helpline_directory.tool import lookup_helplines

    resp = await lookup_helplines(LookupRequest(category=Category.WOMEN_SAFETY))
    resp.primary.number        # "181"
    resp.secondary             # e.g. [112, ...]
    resp.escalation_note       # combined routing guidance

Note the ANM referral entry has ``number is None`` — it is a routing instruction
("hand the beneficiary to the local ANM"), not a phone number. Callers must check
``primary.number is not None`` before presenting it as something to dial.
"""

from __future__ import annotations

import time

from mcp.helpline_directory.loader import get_store
from mcp.helpline_directory.schemas import LookupRequest, LookupResponse


async def lookup_helplines(request: LookupRequest) -> LookupResponse:
    start = time.perf_counter()
    store = get_store()
    primary, secondary, escalation_note = store.lookup(
        category=request.category,
        lang=request.lang,
        scheme=request.scheme,
    )
    latency_ms = (time.perf_counter() - start) * 1000
    return LookupResponse(
        primary=primary,
        secondary=secondary,
        escalation_note=escalation_note,
        latency_ms=latency_ms,
    )
