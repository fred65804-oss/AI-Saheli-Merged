"""Build and compile the orchestrator LangGraph.

``build_orchestrator`` wires nodes + conditional edges and compiles with a
checkpointer so per-session state persists across turns. ``default_orchestrator``
assembles real dependencies from settings (LLM, router built from the registry's
cards, JSONL trace sink). ``run_turn`` is the single entry point callers use.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agents.orchestrator.llm import StructuredLLM, get_llm
from agents.orchestrator.nodes import OrchestratorNodes
from agents.orchestrator.router import Router
from agents.orchestrator.state import AgentState, new_turn_defaults
from agents.orchestrator.trace import TraceSink, default_sink
from agents.specialists.registry import routable_cards
from apps.backend.config import Settings, get_settings


# --------------------------------------------------------------------------- #
# Edge selectors
# --------------------------------------------------------------------------- #
def _after_safety(state: AgentState) -> str:
    if state.get("escalation"):
        return "escalate"
    if state.get("awaiting_slot"):
        return "continue_slot"
    return "route"


def _after_route(state: AgentState) -> str:
    return "slot_check" if state.get("intent") else "clarify"


def _after_continue_slot(state: AgentState) -> str:
    # continue_slot decides whether this turn continues slot-filling (answer or
    # topic-switch) or bails out to a clarification when a reply can't be parsed.
    return "clarify" if state.get("_slot_outcome") == "clarify" else "slot_check"


def _after_slot_check(state: AgentState) -> str:
    return "ask_slot" if state.get("pending_ask_spec") else "handoff"


def _after_handoff(state: AgentState) -> str:
    outcome = state.get("_handoff_outcome")
    if outcome == "escalate":
        return "escalate"
    if outcome == "slot_check":
        return "slot_check"
    return "done"


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def build_orchestrator(
    *,
    llm: StructuredLLM,
    settings: Settings,
    sink: TraceSink,
):
    router = Router(llm, routable_cards())
    n = OrchestratorNodes(llm=llm, router=router, settings=settings, sink=sink)

    g = StateGraph(AgentState)
    g.add_node("safety_gate", n.safety_gate)
    g.add_node("continue_slot", n.continue_slot)
    g.add_node("route", n.route)
    g.add_node("slot_check", n.slot_check)
    g.add_node("ask_slot", n.ask_slot)
    g.add_node("clarify", n.clarify)
    g.add_node("handoff", n.handoff)
    g.add_node("escalation", n.escalation)
    g.add_node("finalize", n.finalize)

    g.add_edge(START, "safety_gate")
    g.add_conditional_edges(
        "safety_gate",
        _after_safety,
        {"escalate": "escalation", "continue_slot": "continue_slot", "route": "route"},
    )
    g.add_conditional_edges(
        "continue_slot",
        _after_continue_slot,
        {"slot_check": "slot_check", "clarify": "clarify"},
    )
    g.add_conditional_edges(
        "route", _after_route, {"slot_check": "slot_check", "clarify": "clarify"}
    )
    g.add_conditional_edges(
        "slot_check", _after_slot_check, {"ask_slot": "ask_slot", "handoff": "handoff"}
    )
    g.add_conditional_edges(
        "handoff",
        _after_handoff,
        {"escalate": "escalation", "slot_check": "slot_check", "done": "finalize"},
    )
    g.add_edge("ask_slot", "finalize")
    g.add_edge("clarify", "finalize")
    g.add_edge("escalation", "finalize")
    g.add_edge("finalize", END)

    return g.compile(checkpointer=MemorySaver())


def default_orchestrator():
    settings = get_settings()
    return build_orchestrator(
        llm=get_llm(settings), settings=settings, sink=default_sink()
    )


# --------------------------------------------------------------------------- #
# Turn entry point
# --------------------------------------------------------------------------- #
async def run_turn(
    graph,
    *,
    session_id: str,
    message: str,
    channel: str = "web",
    lang: str = "en",
) -> dict[str, Any]:
    """Run one conversational turn and return the final state dict."""
    payload: dict[str, Any] = {
        **new_turn_defaults(),
        "session_id": session_id,
        "user_message": message,
        "channel": channel,
        "lang": lang,
    }
    config = {"configurable": {"thread_id": session_id}, "recursion_limit": 25}
    return await graph.ainvoke(payload, config=config)
