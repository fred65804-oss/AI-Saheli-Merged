"""LangGraph node implementations.

Each node is an async method that takes the state and returns a partial update.
Conditional edges (see graph.py) read flags these nodes set. Dependencies (LLM,
router, settings, trace sink) are injected via the constructor so the whole
graph is testable with a FakeLLM and no network.

Flow (safety is always first and non-bypassable):

    safety_gate ─┬─ escalate ──────────────► escalation
                 ├─ continue_slot ─► continue_slot ─► slot_check
                 └─ route ─────────► route ─┬─ clarify
                                            └─ slot_check ─┬─ ask_slot
                                                           └─ handoff ─┬─ escalation
                                                                       ├─ slot_check (needs / reroute)
                                                                       └─ done
    (every leaf) ─► finalize ─► END
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from agents.guardrails import safety
from agents.guardrails.lexicon import DistressCategory
from agents.orchestrator import prompts, slots
from agents.orchestrator.llm import StructuredLLM
from agents.orchestrator.request_type import classify_request_type
from agents.orchestrator.router import UNCLEAR, Router
from agents.orchestrator.state import AgentState
from agents.orchestrator.trace import (
    InteractionTrace,
    Stopwatch,
    TraceSink,
    now_iso,
)
from agents.specialists.base import ContextPacket, SlotSpec
from agents.specialists.registry import get_card, get_specialist
from apps.backend.config import Settings

logger = logging.getLogger(__name__)


def _event(node: str, ms: float, **detail) -> dict:
    return {"node": node, "latency_ms": ms, "detail": detail}


def _append_event(state: AgentState, ev: dict) -> list[dict]:
    return list(state.get("trace_events", [])) + [ev]


class OrchestratorNodes:
    def __init__(
        self,
        llm: StructuredLLM,
        router: Router,
        settings: Settings,
        sink: TraceSink,
    ) -> None:
        self.llm = llm
        self.router = router
        self.settings = settings
        self.sink = sink

    # ---------------------------------------------------------------- safety
    async def safety_gate(self, state: AgentState) -> dict:
        text = state.get("user_message", "")
        with Stopwatch() as sw:
            result = await safety.check_safety(
                text,
                llm=self.llm,
                run_llm_layer=self.settings.safety_always_llm_check,
            )
        update: dict = {
            "trace_id": state.get("trace_id") or uuid.uuid4().hex,
            "escalation": result.escalate,
            "safety_source": result.source,
            "safety_category": result.category.value if result.escalate else None,
            "trace_events": _append_event(
                state,
                _event(
                    "safety_gate",
                    sw.ms,
                    source=result.source,
                    escalate=result.escalate,
                    category=result.category.value,
                    matched_phrase = result.matched_phrase,
                    rationale = result.rationale
                ),
            ),
        }
        return update

    # ------------------------------------------------------- continue a slot
    # Max times we re-ask the SAME unfilled slot before giving up and
    # re-clarifying, so an answer we can't parse never loops forever.
    _MAX_SLOT_ATTEMPTS = 2

    async def continue_slot(self, state: AgentState) -> dict:
        """We asked for a slot last turn. This message is usually the answer —
        but it might instead be a TOPIC CHANGE (the citizen changed their mind
        and asked something new). Distinguish the two before treating the text
        as a slot value, otherwise a new request gets swallowed as an answer
        and the conversation can never leave the pending question.

        Order matters:
          1. Topic change? Ask the router. A confident, routable intent that
             differs from the one we're mid-slot-fill on wins — even if a slot
             value could be extracted (e.g. "how do I adopt a child" would
             otherwise be mis-read as beneficiary_type=child).
          2. Otherwise treat the message as the slot answer and extract it.
          3. If we still can't fill it, re-ask — but only up to
             ``_MAX_SLOT_ATTEMPTS`` times, then abandon the slot and clarify so
             an unparseable reply never loops.
        """
        spec_dict = state.get("awaiting_slot_spec") or {}
        spec = SlotSpec(**spec_dict) if spec_dict else None

        collected = dict(state.get("collected_facts", {}))
        message = state.get("user_message", "")
        current_intent = state.get("intent")
        current_type = state.get("request_type", "guidance")

        with Stopwatch() as sw:
            # Fast path: parse the pending answer locally before making an LLM
            # routing call. A deterministic topic/request check still wins so
            # messages such as "how do I adopt a child" are not swallowed as
            # beneficiary_type=child.
            filled = None
            if spec is not None:
                value = slots.extract_slot_value(spec, message)
                if value is not None:
                    collected[spec.name] = value
                    collected.update(
                        slots.extract_companion_slots(spec, value, message)
                    )
                    filled = f"{spec.name}={value}"

            explicit_type = classify_request_type(message)
            request_type_changed = (
                explicit_type is not None and explicit_type != current_type
            )
            keyword_decision = self.router.keyword_route(message)
            keyword_routable = (
                keyword_decision.intent != UNCLEAR
                and keyword_decision.confidence
                >= self.settings.router_confidence_threshold
            )
            intent_changed = (
                keyword_routable
                and keyword_decision.intent != current_intent
            )

            if intent_changed or request_type_changed:
                target_intent = (
                    keyword_decision.intent
                    if keyword_routable
                    else current_intent
                )
                target_type = (
                    explicit_type
                    or keyword_decision.request_type
                    or current_type
                )
                return {
                    "intent": target_intent,
                    "request_type": target_type,
                    "active_agent": target_intent,
                    "confidence": (
                        keyword_decision.confidence
                        if keyword_routable
                        else state.get("confidence")
                    ),
                    "collected_facts": collected,
                    "awaiting_slot": None,
                    "awaiting_slot_spec": None,
                    "extra_required_slots": [],
                    "slot_attempts": 0,
                    "_slot_outcome": "slot_check",
                    "trace_events": _append_event(
                        state,
                        _event(
                            "continue_slot",
                            sw.ms,
                            topic_change_to=target_intent,
                            request_type=target_type,
                            routing="deterministic",
                        ),
                    ),
                }

            if filled is not None:
                return {
                    "collected_facts": collected,
                    "awaiting_slot": None,
                    "awaiting_slot_spec": None,
                    "slot_attempts": 0,
                    "_slot_outcome": "slot_check",
                    "trace_events": _append_event(
                        state,
                        _event(
                            "continue_slot",
                            sw.ms,
                            filled=filled,
                            routing="skipped",
                        ),
                    ),
                }

            # The deterministic slot parser could not resolve the reply. Only
            # this slower path invokes the full router.
            decision = await self.router.route(
                message,
                conversation_summary=state.get("conversation_summary", ""),
            )

            routable = (
                decision.intent != UNCLEAR
                and decision.confidence >= self.settings.router_confidence_threshold
            )

            # Detect a change in what the citizen wants, even when the specialist
            # remains the same. Example: PMMVY eligibility → PMMVY overview.
            explicit_type = classify_request_type(message)
            current_type = state.get("request_type", "guidance")

            request_type_changed = (
                explicit_type is not None and explicit_type != current_type
            )

            topic_changed = (
                routable and (
                    decision.intent != current_intent or request_type_changed
                )
            )

            collected = slots.merge_slots(collected, decision.extracted_slots)

            # 1. Topic/request change → abandon the pending slot.
            if topic_changed:
                return {
                    "intent": decision.intent,
                    "request_type": (
                        decision.request_type
                        or explicit_type
                        or "guidance"
                    ),
                    "active_agent": decision.intent,
                    "confidence": decision.confidence,
                    "collected_facts": collected,
                    "awaiting_slot": None,
                    "awaiting_slot_spec": None,
                    "extra_required_slots": [],
                    "slot_attempts": 0,
                    "_slot_outcome": "slot_check",
                    "trace_events": _append_event(
                        state,
                        _event(
                            "continue_slot",
                            sw.ms,
                            topic_change_to=decision.intent,
                            request_type=(
                                decision.request_type
                                or explicit_type
                                or "guidance"
                            ),
                        ),
                    ),
                }

            # 2. Treat as the slot answer.
            filled = None
            if spec is not None:
                value = slots.extract_slot_value(spec, message)
                if value is not None:
                    collected[spec.name] = value
                    collected.update(slots.extract_companion_slots(spec, value, message))
                    filled = f"{spec.name}={value}"

            if filled is not None:
                return {
                    "collected_facts": collected,
                    "awaiting_slot": None,
                    "awaiting_slot_spec": None,
                    "slot_attempts": 0,
                    "_slot_outcome": "slot_check",
                    "trace_events": _append_event(
                        state, _event("continue_slot", sw.ms, filled=filled)
                    ),
                }

            # 3. Couldn't fill it and it isn't a new topic → bounded re-ask.
            attempts = state.get("slot_attempts", 0) + 1
            if attempts >= self._MAX_SLOT_ATTEMPTS:
                return {
                    "collected_facts": collected,
                    "awaiting_slot": None,
                    "awaiting_slot_spec": None,
                    "intent": None,
                    "active_agent": None,
                    "slot_attempts": 0,
                    "_slot_outcome": "clarify",
                    "trace_events": _append_event(
                        state, _event("continue_slot", sw.ms, gave_up_slot=spec.name if spec else None)
                    ),
                }
            return {
                "collected_facts": collected,
                "awaiting_slot": None,
                "awaiting_slot_spec": None,
                "slot_attempts": attempts,
                "_slot_outcome": "slot_check",
                "trace_events": _append_event(
                    state, _event("continue_slot", sw.ms, reask_attempt=attempts)
                ),
            }

    # ----------------------------------------------------------------- route
    async def route(self, state: AgentState) -> dict:
        message = state.get("user_message", "")
        with Stopwatch() as sw:
            decision = await self.router.route(
                message,
                conversation_summary=state.get("conversation_summary", ""),
            )
        routable = (
            decision.intent != UNCLEAR
            and decision.confidence >= self.settings.router_confidence_threshold
        )

        # Fold in what the citizen ALREADY told us, so slot_check never asks a
        # question the opening message answered ("a plan for my 5-month-old" →
        # beneficiary_type=child). The router's LLM extraction is validated
        # against the card (it can hallucinate keys/enum values), then any
        # required slot it missed is backfilled deterministically.
        extracted = dict(decision.extracted_slots or {})
        card = get_card(decision.intent) if routable else None
        if card is not None:
            extracted = slots.coerce_card_slots(card, extracted)
            for name, value in slots.extract_stated_slots(card, message).items():
                extracted.setdefault(name, value)
        collected = slots.merge_slots(state.get("collected_facts", {}), extracted)
        return {
            "intent": decision.intent if routable else None,
            "request_type": decision.request_type or "guidance",
            "confidence": decision.confidence,
            "active_agent": decision.intent if routable else None,
            "collected_facts": collected,
            "extra_required_slots": [],
            "trace_events": _append_event(
                state,
                _event(
                    "route",
                    sw.ms,
                    intent=decision.intent,
                    confidence=decision.confidence,
                    request_type=decision.request_type,
                    routable=routable,
                    rationale=decision.rationale,
                ),
            ),
        }

    # ------------------------------------------------------------ slot_check
    async def slot_check(self, state: AgentState) -> dict:
        intent = state.get("intent")
        card = get_card(intent) if intent else None
        collected = state.get("collected_facts", {})
        request_type = state.get("request_type", "guidance")

        # Required slots = card's required + any the specialist asked for.
        extra = [SlotSpec(**d) for d in state.get("extra_required_slots", [])]

        # Overview questions must reach the specialist immediately.
        # No personal fields are required for a definition or scheme summary.
        if request_type == "overview":
            required: list[SlotSpec] = []
        else:
            required = (list(card.required_slots) if card else []) + extra
        missing = [
            spec
            for spec in required
            if spec.required and not _is_filled(collected, spec.name)
        ]
        pending = sorted(missing, key=lambda s: s.priority)[0] if missing else None
        return {
            "pending_ask_spec": pending.model_dump() if pending else None,
            "trace_events": _append_event(
                state,
                _event(
                    "slot_check",
                    0.0,
                    request_type=request_type,
                    next_slot=pending.name if pending else None,
                ),
            ),
        }

    # -------------------------------------------------------------- ask_slot
    async def ask_slot(self, state: AgentState) -> dict:
        spec = SlotSpec(**state["pending_ask_spec"])
        
        # The capability-card prompt is already citizen-facing and vetted.
        question = spec.ask_prompt

        return {
            "response": question,
            "awaiting_input": True,
            "awaiting_slot": spec.name,
            "awaiting_slot_spec": spec.model_dump(),
            "pending_ask_spec": None,
            "trace_events": _append_event(
                state, _event("ask_slot", 0.0, slot=spec.name, phrasing = "deterministic")
            ),
        }

    # --------------------------------------------------------------- clarify
    async def clarify(self, state: AgentState) -> dict:   
        question = (
        "Please choose one: nutrition, child protection through "
        "Mission Vatsalya, women's safety through Mission Shakti, "
        "or information about government schemes."
        )
        return {
            "response": question,
            "awaiting_input": True,
            "intent": None,
            "awaiting_slot": None,
            "awaiting_slot_spec": None,
            "trace_events": _append_event(state, _event("clarify", 0.0, phrasing = "deterministic")),
        }

    # --------------------------------------------------------------- handoff
    async def handoff(self, state: AgentState) -> dict:
        intent = state.get("intent")
        specialist = get_specialist(intent) if intent else None
        if specialist is None:
            return {
                "response": "I'm not able to help with that yet. Please contact your "
                "nearest Anganwadi Centre.",
                "fallback": True,
                "_handoff_outcome": "done",
                "trace_events": _append_event(
                    state, _event("handoff", 0.0, error="no specialist")
                ),
            }

        packet = ContextPacket(
            session_id=state.get("session_id", ""),
            trace_id=state.get("trace_id", ""),
            intent=intent,
            request_type=state.get("request_type", "guidance"),
            user_message=state.get("user_message", ""),
            lang=state.get("lang", "en"),
            channel=state.get("channel", "web"),
            citizen_profile=state.get("citizen_profile", {}),
            collected_facts=state.get("collected_facts", {}),
            conversation_summary=state.get("conversation_summary", ""),
        )

        with Stopwatch() as sw:
            try:
                resp = await asyncio.wait_for(
                    specialist.handle(packet),
                    timeout=self.settings.specialist_timeout_seconds,
                )
            except Exception as exc:  # timeout or specialist crash → graceful
                # str(exc) is empty for several common exception types
                # (bare Exception(), CancelledError, some SDK errors) — log the
                # type too, or a production failure leaves zero diagnostic trail.
                logger.exception("specialist handoff failed (intent=%s)", intent)
                return {
                    "response": "I'm having trouble fetching that right now. Please "
                    "try again, or contact your nearest Anganwadi Centre for help.",
                    "fallback": True,
                    "_handoff_outcome": "done",
                    "trace_events": _append_event(
                        state,
                        _event(
                            "handoff",
                            sw.ms,
                            error=f"{type(exc).__name__}: {exc}",
                        ),
                    ),
                }

        # Specialist tripped safety
        if resp.escalation:
            return {
                "escalation": True,
                "safety_category": state.get("safety_category")
                or DistressCategory.GENERIC_EMERGENCY.value,
                "safety_source": "specialist",
                "_handoff_outcome": "escalate",
                "trace_events": _append_event(
                    state, _event("handoff", sw.ms, outcome="escalate")
                ),
            }

        # Specialist says "not mine" → one bounded reroute
        if resp.reroute_to and state.get("reroute_count", 0) < 1:
            return {
                "intent": resp.reroute_to,
                "active_agent": resp.reroute_to,
                "reroute_count": state.get("reroute_count", 0) + 1,
                "extra_required_slots": [],
                "_handoff_outcome": "slot_check",
                "trace_events": _append_event(
                    state, _event("handoff", sw.ms, reroute_to=resp.reroute_to)
                ),
            }

        # Specialist needs more facts → collect them.
        # Guard: if every requested need is ALREADY filled in collected_facts,
        # slot_check will find nothing missing and bounce right back into
        # handoff — the specialist would then re-request the same needs and
        # the graph would spin forever (LangGraph recursion limit blows). This
        # happens when the specialist's rules engine can't map a value the
        # router captured (e.g. child_order stored as "1" vs enum "first").
        # Break the cycle by treating it as "done" with whatever answer /
        # fallback the specialist produced.
        collected = state.get("collected_facts", {})
        unfilled_needs = [n for n in resp.needs if not _is_filled(collected, n.name)]
        if resp.needs and not unfilled_needs:
            logger.warning(
                "handoff: specialist asked for slots already filled — breaking loop (needs=%s)",
                [n.name for n in resp.needs],
            )
            return {
                "response": resp.answer or (
                    "I'm having trouble matching your details to the scheme rules. "
                    "Please contact your nearest Anganwadi Centre for help."
                ),
                "citations": [c.model_dump() for c in resp.citations],
                "tool_calls": resp.tool_calls,
                "grounding_ok": bool(resp.citations),
                "fallback": not resp.answer,
                "_handoff_outcome": "done",
                "trace_events": _append_event(
                    state,
                    _event(
                        "handoff",
                        sw.ms,
                        broke_loop=True,
                        needs=[n.name for n in resp.needs],
                    ),
                ),
            }
        if resp.needs:
            extra = [
                slots.slot_request_to_spec(n).model_dump() for n in unfilled_needs
            ]
            return {
                "extra_required_slots": extra,
                "_handoff_outcome": "slot_check",
                "trace_events": _append_event(
                    state,
                    _event("handoff", sw.ms, needs=[n.name for n in unfilled_needs]),
                ),
            }

        # Grounded answer
        return {
            "response": resp.answer,
            "citations": [c.model_dump() for c in resp.citations],
            "tool_calls": resp.tool_calls,
            "grounding_ok": bool(resp.citations),
            "_handoff_outcome": "done",
            "trace_events": _append_event(
                state,
                _event(
                    "handoff",
                    sw.ms,
                    agent=intent,
                    citations=len(resp.citations),
                    tool_calls=resp.tool_calls,
                ),
            ),
        }

    # ------------------------------------------------------------ escalation
    async def escalation(self, state: AgentState) -> dict:
        cat_raw = state.get("safety_category") or DistressCategory.GENERIC_EMERGENCY.value
        try:
            category = DistressCategory(cat_raw)
        except ValueError:
            category = DistressCategory.GENERIC_EMERGENCY
        result = safety.SafetyResult(escalate=True, category=category, source="gate")
        message = safety.build_escalation_response(result)
        # A crisis interrupts any in-progress routing/slot-fill: clear it so the
        # turn is logged as a pure escalation and the next turn starts clean.
        return {
            "response": message,
            "escalation": True,
            "awaiting_input": False,
            "intent": None,
            "active_agent": None,
            "awaiting_slot": None,
            "awaiting_slot_spec": None,
            "trace_events": _append_event(
                state, _event("escalation", 0.0, category=category.value)
            ),
        }

    # -------------------------------------------------------------- finalize
    async def finalize(self, state: AgentState) -> dict:
        events = state.get("trace_events", [])
        total = round(sum(e.get("latency_ms", 0.0) for e in events), 2)
        trace = InteractionTrace(
            trace_id=state.get("trace_id", ""),
            session_id=state.get("session_id", ""),
            channel=state.get("channel", "web"),
            lang=state.get("lang", "en"),
            user_message=state.get("user_message", ""),
            intent=state.get("intent"),
            request_type=state.get("request_type"),
            confidence=state.get("confidence"),
            safety_source=state.get("safety_source"),
            safety_category=state.get("safety_category"),
            escalation=bool(state.get("escalation")),
            agent_used=state.get("active_agent"),
            district=state.get("collected_facts", {}).get("district"),
            tool_calls=state.get("tool_calls", []),
            citation_count=len(state.get("citations", [])),
            awaiting_input=bool(state.get("awaiting_input")),
            grounding_ok=bool(state.get("grounding_ok", True)),
            fallback=bool(state.get("fallback")),
            events=events,  # type: ignore[arg-type]
            total_latency_ms=total,
            created_at=now_iso(),
        )
        try:
            self.sink.write(trace)
        except Exception:  # never let audit IO break a citizen reply
            pass
        return {}

    # --------------------------------------------------------------- helpers
    async def _phrase(self, system: str, user: str, *, fallback: str) -> str:
        try:
            text = await self.llm.complete(system, user)
            return text.strip() or fallback
        except Exception:
            return fallback


def _is_filled(collected: dict, name: str) -> bool:
    val = collected.get(name)
    if val is None:
        return False
    if isinstance(val, str) and not val.strip():
        return False
    return True
