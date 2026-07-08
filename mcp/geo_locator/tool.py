# mcp/geo_locator/tool.py
"""
The geo_locator MCP tool — the callable surface specialist agents use to find
the nearest physical facility (Anganwadi, One Stop Centre, DCPU, CWC) for a
citizen, grounded in a demo-scoped facilities dataset.

Deterministic and offline: no live GPS/GIS API, no LLM. The store is loaded and
validated once per process (see loader.get_store).

Usage (from a specialist's ``handle``):

    from mcp.geo_locator.schemas import LookupRequest, ServiceType
    from mcp.geo_locator.tool import find_facilities

    resp = await find_facilities(
        LookupRequest(service_type=ServiceType.OSC, district="Delhi")
    )
    resp.facilities[0].name       # "One Stop Centre — Rohini"
    resp.facilities[0].address
    resp.note                     # non-None on a state fallback or no-data miss

On a miss the tool degrades gracefully — empty ``facilities`` plus a ``note``
explaining that production resolves this live — rather than raising, so the demo
never dead-ends on an out-of-scope district.
"""

from __future__ import annotations

import time

from mcp.geo_locator.loader import get_store
from mcp.geo_locator.schemas import LookupRequest, LookupResponse


async def find_facilities(request: LookupRequest) -> LookupResponse:
    start = time.perf_counter()
    store = get_store()
    facilities, district_matched, note = store.find(
        service_type=request.service_type,
        district=request.district,
        state=request.state,
        limit=request.limit,
    )
    latency_ms = (time.perf_counter() - start) * 1000
    return LookupResponse(
        facilities=facilities,
        district_matched=district_matched,
        count=len(facilities),
        note=note,
        latency_ms=latency_ms,
    )
