"""One full end-to-end flow of the geo_locator MCP tool — the callable surface
specialist agents use to find the nearest physical facility for a citizen.

Deliberately a single scripted scenario (not many mini-tests): boot/validation,
the Journey-3 OSC lookup (Shakti), the Journey-1 AWC lookup (Poshan), the
Vatsalya DCPU lookup, case/whitespace-insensitive matching, the state-level
fallback, and the graceful out-of-scope miss are all asserted together — the way
a real conversation would exercise it.

Fully offline and deterministic: no LLM, no GIS/network, just the JSON store.
"""

import pytest

from mcp.geo_locator.loader import DEFAULT_JSON_PATH, FacilityStore, get_store
from mcp.geo_locator.schemas import LookupRequest, ServiceType
from mcp.geo_locator.tool import find_facilities

pytestmark = pytest.mark.asyncio


async def test_full_geo_locator_flow():
    # 0. Store boots, validates every record, and is flagged demo data.
    store = FacilityStore(DEFAULT_JSON_PATH)
    assert store.facilities, "store loaded no facilities"
    assert store.meta.get("demo_data") is True
    assert get_store() is get_store()  # process singleton is stable

    # 1. Journey 3 — Shakti escalation needs the nearest OSC in Delhi.
    r_osc = await find_facilities(
        LookupRequest(service_type=ServiceType.OSC, district="Delhi")
    )
    assert r_osc.count >= 1
    assert r_osc.district_matched == "Delhi"
    assert r_osc.note is None
    assert all(f.type == ServiceType.OSC for f in r_osc.facilities)
    assert all(f.district == "Delhi" for f in r_osc.facilities)
    assert r_osc.facilities[0].address and r_osc.facilities[0].source
    assert r_osc.latency_ms > 0

    # 2. Journey 1 — Poshan needs the nearest Anganwadi in Varanasi. Input is
    #    messy-cased with stray spaces; matching must normalize it.
    r_awc = await find_facilities(
        LookupRequest(service_type=ServiceType.AWC, district="  vARANasi ", limit=2)
    )
    assert r_awc.count == 2  # limit respected
    assert r_awc.district_matched == "Varanasi"
    assert all(f.type == ServiceType.AWC for f in r_awc.facilities)

    # 3. Vatsalya needs a District Child Protection Unit in Lucknow.
    r_dcpu = await find_facilities(
        LookupRequest(service_type=ServiceType.DCPU, district="Lucknow")
    )
    assert r_dcpu.count >= 1
    assert all(f.type == ServiceType.DCPU for f in r_dcpu.facilities)

    # 4. State-level fallback — a district we don't stock, but the state is known.
    #    We widen to the state and SAY SO in the note (no silent wrong answer).
    r_fallback = await find_facilities(
        LookupRequest(
            service_type=ServiceType.OSC, district="Ghaziabad", state="Uttar Pradesh"
        )
    )
    assert r_fallback.count >= 1
    assert all(f.state == "Uttar Pradesh" for f in r_fallback.facilities)
    assert r_fallback.note is not None and "Ghaziabad" in r_fallback.note

    # 5. Graceful out-of-scope miss — the "what about Bhopal?" demo question.
    #    Empty list + explanatory note, NOT a crash.
    r_miss = await find_facilities(
        LookupRequest(service_type=ServiceType.OSC, district="Bhopal")
    )
    assert r_miss.count == 0
    assert r_miss.facilities == []
    assert r_miss.district_matched is None
    assert r_miss.note and "production" in r_miss.note.lower()
