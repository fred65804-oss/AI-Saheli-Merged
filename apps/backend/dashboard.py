"""Dashboard & tools API — everything the web UI reads, all data-driven.

Design rule: the UI hardcodes NOTHING. Scheme cards, language lists, enum
choices, form fields, helpline rows, analytics — every value on screen comes
from these endpoints, which in turn read the same sources the orchestrator
uses (registry cards, Pydantic schemas, the helpline YAML store, the JSONL
audit trace). Adding a scheme / language / rule upstream changes the UI with
zero frontend edits.

Endpoints:
  GET  /meta               app metadata: provider/model, languages, cards, enums,
                           tool form schemas (Pydantic model_json_schema)
  GET  /helplines          full validated helpline directory
  POST /tools/kb-search    knowledge_base passthrough
  POST /tools/eligibility  eligibility rules passthrough
  POST /tools/geo          geo_locator passthrough
  POST /tools/helpline     helpline_directory lookup passthrough
  GET  /analytics/summary  aggregates over logs/interactions.jsonl
  GET  /analytics/recent   latest interaction traces (trimmed for the feed)
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from agents.specialists.base import CONTRACT_VERSION
from agents.specialists.registry import routable_cards
from apps.backend.config import get_settings
from language.provider import LANGUAGES
from mcp.eligibility.schemas import EligibilityRequest, EligibilityResponse
from mcp.eligibility.tool import check_eligibility
from mcp.geo_locator.schemas import (
    LookupRequest as GeoLookupRequest,
    LookupResponse as GeoLookupResponse,
    ServiceType,
)
from mcp.geo_locator.tool import find_facilities
from mcp.helpline_directory.loader import get_store as get_helpline_store
from mcp.helpline_directory.schemas import (
    Category as HelplineCategory,
    LookupRequest as HelplineLookupRequest,
    LookupResponse as HelplineLookupResponse,
    Scheme as HelplineScheme,
)
from mcp.helpline_directory.tool import lookup_helplines
from mcp.knowledge_base.schemas import KBQueryRequest, KBQueryResponse, Scheme as KBScheme
from mcp.knowledge_base.tool import query_knowledge_base

router = APIRouter()


# --------------------------------------------------------------------------- #
# Metadata — the UI builds itself from this
# --------------------------------------------------------------------------- #
@router.get("/meta")
async def meta() -> dict:
    s = get_settings()
    return {
        "app": {"title": "AI Saheli", "contract_version": CONTRACT_VERSION},
        "llm": {
            "live": s.has_llm_key,
            "provider": s.resolved_provider,
            "model": s.resolved_model,
            "fast_model": s.resolved_fast_model,
        },
        "languages": LANGUAGES,
        "cards": [c.model_dump() for c in routable_cards()],
        "enums": {
            "kb_schemes": [e.value for e in KBScheme],
            "geo_service_types": [e.value for e in ServiceType],
            "helpline_categories": [e.value for e in HelplineCategory],
            "helpline_schemes": [e.value for e in HelplineScheme],
        },
        # JSON Schema drives the dynamic eligibility form — fields, types and
        # enum choices come from the SAME Pydantic model the rules engine uses.
        "eligibility_schema": EligibilityRequest.model_json_schema(),
    }


@router.get("/helplines")
async def helplines() -> dict:
    store = get_helpline_store()
    return {
        "version": store.version,
        "updated": store.updated,
        "entries": [e.model_dump() for e in store.entries],
    }


# --------------------------------------------------------------------------- #
# Tool passthroughs — the dashboard's live tool explorer
# --------------------------------------------------------------------------- #
@router.post("/tools/kb-search", response_model=KBQueryResponse)
async def kb_search(req: KBQueryRequest) -> KBQueryResponse:
    return await query_knowledge_base(req)


@router.post("/tools/eligibility", response_model=EligibilityResponse)
async def eligibility(req: EligibilityRequest) -> EligibilityResponse:
    return await check_eligibility(req)


@router.post("/tools/geo", response_model=GeoLookupResponse)
async def geo(req: GeoLookupRequest) -> GeoLookupResponse:
    return await find_facilities(req)


@router.post("/tools/helpline", response_model=HelplineLookupResponse)
async def helpline(req: HelplineLookupRequest) -> HelplineLookupResponse:
    return await lookup_helplines(req)


# --------------------------------------------------------------------------- #
# Analytics — aggregates over the audit trace (the dashboard's data feed)
# --------------------------------------------------------------------------- #
def _read_traces(hours: int | None = None) -> list[dict]:
    """Read interactions.jsonl, newest last. Robust to a missing file and to
    corrupt lines (skip, never crash the dashboard)."""
    path = get_settings().trace_sink_path
    if not os.path.exists(path):
        return []
    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=hours) if hours else None
    )
    rows: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if cutoff is not None:
                try:
                    ts = datetime.fromisoformat(row.get("created_at", ""))
                except ValueError:
                    continue
                if ts < cutoff:
                    continue
            rows.append(row)
    return rows


def _bucket_key(ts: datetime, by_day: bool) -> str:
    return ts.strftime("%Y-%m-%d") if by_day else ts.strftime("%Y-%m-%d %H:00")


@router.get("/analytics/summary")
async def analytics_summary(
    hours: int | None = Query(default=None, ge=1, le=24 * 365)
) -> dict:
    rows = _read_traces(hours)
    total = len(rows)
    sessions = len({r.get("session_id") for r in rows if r.get("session_id")})
    escalations = [r for r in rows if r.get("escalation")]
    answered = [
        r for r in rows if not r.get("awaiting_input") and not r.get("escalation")
    ]
    latencies = [r.get("total_latency_ms", 0.0) for r in rows]

    by_intent = Counter(r.get("intent") or "unrouted" for r in rows)
    by_lang = Counter(r.get("lang") or "en" for r in rows)
    by_channel = Counter(r.get("channel") or "web" for r in rows)
    by_district = Counter(r["district"] for r in rows if r.get("district"))
    escalation_by_category = Counter(
        r.get("safety_category") or "generic" for r in escalations
    )
    safety_sources = Counter(
        r.get("safety_source") for r in escalations if r.get("safety_source")
    )
    tool_usage: Counter = Counter()
    for r in rows:
        tool_usage.update(r.get("tool_calls") or [])

    # Timeline: hourly buckets under 48h of span, daily beyond.
    stamps: list[datetime] = []
    for r in rows:
        try:
            stamps.append(datetime.fromisoformat(r.get("created_at", "")))
        except ValueError:
            continue
    timeline: list[dict] = []
    if stamps:
        span_h = (max(stamps) - min(stamps)).total_seconds() / 3600
        by_day = span_h > 48
        buckets: dict[str, dict] = {}
        for r in rows:
            try:
                ts = datetime.fromisoformat(r.get("created_at", ""))
            except ValueError:
                continue
            key = _bucket_key(ts, by_day)
            b = buckets.setdefault(key, {"t": key, "count": 0, "escalations": 0})
            b["count"] += 1
            if r.get("escalation"):
                b["escalations"] += 1
        timeline = [buckets[k] for k in sorted(buckets)]

    grounded = [r for r in answered if r.get("grounding_ok")]
    avg_citations = (
        sum(r.get("citation_count", 0) for r in answered) / len(answered)
        if answered
        else 0.0
    )
    return {
        "window_hours": hours,
        "totals": {
            "turns": total,
            "sessions": sessions,
            "escalations": len(escalations),
            "escalation_rate": round(len(escalations) / total, 4) if total else 0.0,
            "answered": len(answered),
            "grounding_rate": (
                round(len(grounded) / len(answered), 4) if answered else 0.0
            ),
            "avg_citations": round(avg_citations, 2),
            "fallbacks": sum(1 for r in rows if r.get("fallback")),
            "slot_questions": sum(1 for r in rows if r.get("awaiting_input")),
            "avg_latency_ms": (
                round(sum(latencies) / len(latencies), 1) if latencies else 0.0
            ),
            "max_latency_ms": round(max(latencies), 1) if latencies else 0.0,
        },
        "by_intent": dict(by_intent.most_common()),
        "by_lang": dict(by_lang.most_common()),
        "by_channel": dict(by_channel.most_common()),
        "by_district": dict(by_district.most_common(10)),
        "escalation_by_category": dict(escalation_by_category.most_common()),
        "safety_sources": dict(safety_sources.most_common()),
        "tool_usage": dict(tool_usage.most_common()),
        "timeline": timeline,
    }


@router.get("/analytics/recent")
async def analytics_recent(
    limit: int = Query(default=50, ge=1, le=500),
    hours: int | None = Query(default=None, ge=1, le=24 * 365),
) -> dict:
    rows = _read_traces(hours)
    recent = rows[-limit:][::-1]  # newest first
    feed = [
        {
            "created_at": r.get("created_at", ""),
            "trace_id": r.get("trace_id", ""),
            "session_id": r.get("session_id", ""),
            "channel": r.get("channel", "web"),
            "lang": r.get("lang", "en"),
            "user_message": r.get("user_message", ""),
            "intent": r.get("intent"),
            "confidence": r.get("confidence"),
            "escalation": bool(r.get("escalation")),
            "safety_category": r.get("safety_category"),
            "agent_used": r.get("agent_used"),
            "district": r.get("district"),
            "tool_calls": r.get("tool_calls") or [],
            "citation_count": r.get("citation_count", 0),
            "awaiting_input": bool(r.get("awaiting_input")),
            "fallback": bool(r.get("fallback")),
            "total_latency_ms": r.get("total_latency_ms", 0.0),
        }
        for r in recent
    ]
    return {"count": len(feed), "items": feed}
