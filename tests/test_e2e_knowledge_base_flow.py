"""One full end-to-end test of the orchestrator wired to the REAL knowledge
base (no mocked retrieval) — proves the orchestrator<->KB gap is closed.

Deliberately a single scripted session/test (not many mini-tests): safety
escalation, slot-filling, Poshan grounding, Shakti grounding, and a direct
call to the knowledge_base tool are all asserted together as one continuous
flow, the same way a real conversation would exercise the system.

Routing/safety use FakeLLM (deterministic, offline) — the thing actually
under test here is retrieval, which runs for real against the local Qdrant
index built in rag/qdrant_db (already indexed, models already cached, so
this runs with no network calls, just slower than the pure-unit tests).
"""

import pytest

from agents.orchestrator.graph import build_orchestrator, run_turn
from agents.orchestrator.llm import FakeLLM
from agents.orchestrator.trace import NullTraceSink
from apps.backend.config import get_settings
from mcp.knowledge_base.schemas import KBQueryRequest
from mcp.knowledge_base.tool import query_knowledge_base

pytestmark = pytest.mark.asyncio


def _graph():
    return build_orchestrator(
        llm=FakeLLM(), settings=get_settings(), sink=NullTraceSink()
    )


async def test_full_conversation_with_real_knowledge_base():
    # Warm the embedding/reranker models once, outside any per-turn specialist
    # timeout — a real deployment loads these at process startup, not inside
    # a request's timeout budget.
    await query_knowledge_base(KBQueryRequest(query="warmup", k=1))

    g = _graph()

    # 1. Safety escalation still short-circuits BEFORE any KB call.
    s_escalate = await run_turn(g, session_id="e2e-1", message="mera pati mujhe maar raha hai")
    assert s_escalate["escalation"] is True
    assert s_escalate.get("intent") is None
    assert s_escalate.get("citations", []) == []

    # 2. Poshan nutrition question -> slot-filling loop -> real grounded answer.
    sid = "e2e-2"
    s1 = await run_turn(g, session_id=sid, message="what should i eat during pregnancy")
    assert s1["intent"] == "poshan"
    assert s1["awaiting_input"] is True  # asked beneficiary_type

    s2 = await run_turn(g, session_id=sid, message="I am pregnant")
    assert s2["collected_facts"].get("beneficiary_type") == "pregnant_woman"
    assert s2["awaiting_input"] is True  # specialist asked pregnancy_stage

    s3 = await run_turn(g, session_id=sid, message="6th month")
    assert s3["awaiting_input"] is False
    # Poshan also calls eligibility/geo_locator; assert the KB specifically
    # ran and contributed a REAL, retrieved citation (not a hardcoded one).
    assert "knowledge_base" in s3["tool_calls"]
    citations = s3["citations"]
    assert len(citations) >= 1
    assert any(c["source_doc"].endswith(".pdf") for c in citations)
    assert all(c["source_doc"] != "Poshan 2.0 Operational Guidelines" for c in citations)

    # 3. PMMVY question -> Shakti. PMMVY needs child_order (then a socio-economic
    # fact) before it can give a definite verdict, so the first turn asks a
    # tracked slot; the grounded answer (with real retrieval) lands once those
    # facts are supplied.
    psid = "e2e-3"
    s_pmmvy1 = await run_turn(g, session_id=psid, message="am i eligible for pmmvy")
    assert s_pmmvy1["intent"] == "shakti"
    assert s_pmmvy1["awaiting_input"] is True  # asks child_order first

    s_pmmvy2 = await run_turn(g, session_id=psid, message="first child")
    assert s_pmmvy2["awaiting_input"] is True  # then the socio-economic fact

    s_pmmvy = await run_turn(g, session_id=psid, message="we are BPL")
    assert s_pmmvy["awaiting_input"] is False
    assert "knowledge_base" in s_pmmvy["tool_calls"]
    pmmvy_citations = s_pmmvy["citations"]
    assert len(pmmvy_citations) >= 1
    assert any(c["source_doc"].endswith(".pdf") for c in pmmvy_citations)

    # 4. Direct call to the knowledge_base tool, standalone (not via a specialist).
    resp = await query_knowledge_base(
        KBQueryRequest(query="child protection helpline 1098", scheme="vatsalya", k=4)
    )
    assert len(resp.chunks) >= 1
    assert resp.latency_ms > 0
    assert all(c.scheme == "vatsalya" for c in resp.chunks)
    assert all(c.citation for c in resp.chunks)
