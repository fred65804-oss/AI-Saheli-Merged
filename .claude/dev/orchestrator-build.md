# Orchestrator Build — Phase 1 (Core Engine)

**Status:** Built & verified. Text + voice, mock specialists, in-memory state.
**Engine:** LangGraph `StateGraph` + `MemorySaver` checkpointer (per-session thread).
**LLM:** configurable; default `claude-sonnet-4-6`. Runs offline (keyword + lexicon) with no key.

## What the orchestrator does
Receives a citizen message → runs a **layered safety gate** → if safe, **routes** to a
specialist using declarative capability cards → **collects missing facts** via dynamic
questioning → **hands off** to the specialist (mock today) → returns a grounded, cited
answer → writes a structured **audit trace**.

## Flow (LangGraph)
```
safety_gate ─┬─ escalate ───────────────► escalation ─► finalize
             ├─ continue_slot ─► continue_slot ─► slot_check
             └─ route ─► route ─┬─ clarify ─► finalize
                                └─ slot_check ─┬─ ask_slot ─► finalize
                                               └─ handoff ─┬─ escalation
                                                           ├─ slot_check (needs/reroute)
                                                           └─ finalize (answer)
```
State carried per `session_id` via checkpointer (`MemorySaver` now; Redis/Postgres later).

## File map
| Area | File | Purpose |
|---|---|---|
| Config | `apps/backend/config.py` | env-driven settings (model, thresholds, timeout) |
| API | `apps/backend/main.py` | `POST /chat`, `POST /voice`, `GET /health` |
| Safety L1 | `agents/guardrails/lexicon.py` | bilingual (EN/Hinglish/Devanagari) distress keywords |
| Safety L2 | `agents/guardrails/safety.py` | LLM `SafetyVerdict` + templated escalation response |
| Cards | `agents/orchestrator/capabilities.py` | Poshan/Vatsalya/Shakti/General capability cards |
| Router | `agents/orchestrator/router.py` | structured `RouterDecision` + keyword fallback |
| Slots | `agents/orchestrator/slots.py` | merge, next-missing-slot, offline value extraction |
| LLM | `agents/orchestrator/llm.py` | `StructuredLLM` protocol, `AnthropicLLM`, `FakeLLM` |
| Trace | `agents/orchestrator/trace.py` | `InteractionTrace` + JSONL sink (dashboard feed) |
| State | `agents/orchestrator/state.py` | `AgentState` TypedDict |
| Nodes | `agents/orchestrator/nodes.py` | all graph nodes |
| Graph | `agents/orchestrator/graph.py` | build/compile + `run_turn()` |
| Contract | `agents/specialists/base.py` | the specialist integration spec (v1.0) |
| Grounding core | `agents/specialists/_grounding.py` | shared KB retrieval + LLM synthesis + deterministic fallback |
| Real specialists | `agents/specialists/{poshan,vatsalya,shakti,general}.py` | production agents — MCP tools for facts, KB for narrative, LLM to weave them |
| Mocks | `agents/specialists/mocks.py` | cited stub specialists — kept for tests only |
| Registry | `agents/specialists/registry.py` | intent → real specialist instance; router reads cards from here |
| Eval | `eval/run_routing_eval.py` + `routing_golden.jsonl` | routing accuracy + escalation recall |
| CLI | `scripts/chat_cli.py` | terminal demo REPL |
| Tests | `tests/test_{safety,routing,slots,graph}.py` | 31 deterministic tests (no key needed) |

## Language layer (wired into API)
`language/provider.py` — `LanguageProvider` protocol + `FakeLanguageProvider`
`language/free_provider.py` — `FreeProvider`: faster-whisper ASR + deep-translator NMT + edge-tts TTS

Factory `get_language_provider()` auto-detects: FreeProvider if packages installed, FakeLanguageProvider otherwise.
The `/voice` endpoint: audio_base64 → transcribe → translate-to-EN → orchestrator → translate-back → synthesize → audio_base64.
The `/chat` endpoint: message → translate-to-EN (if non-ASCII) → orchestrator → translate-back.

## MCP tools (all built, called by specialist agents)
| Tool | Module | What it does |
|---|---|---|
| `knowledge_base` | `mcp/knowledge_base/tool.py` | Hybrid Qdrant search + rerank → grounded passages |
| `helpline_directory` | `mcp/helpline_directory/tool.py` | Lookup 1098/181/112/15100 by distress category |
| `geo_locator` | `mcp/geo_locator/tool.py` | Nearest AWC/OSC/DCPU/CWC by district (demo dataset) |
| `eligibility` | `mcp/eligibility/tool.py` | Rule-based scheme eligibility (PMMVY, THR, SNP, SAAN, Sponsorship) |

All tools are async Python functions — no network calls, no LLM, fully deterministic.
`mcp/__init__.py` exports all four for specialist agents to import directly.

## How the real specialists work (implemented — see `agents/specialists/{poshan,vatsalya,shakti,general}.py`)
1. Implement `SpecialistAgent` from `agents/specialists/base.py` (set `capability_card`, implement `async handle()`).
2. Call MCP tools inside `handle()` for VERIFIED FACTS (eligibility amounts, helpline numbers, facility addresses) —
   these are authoritative and reach the citizen unaltered.
3. Retrieve official KB passages once per turn (`agents/specialists/_grounding.py:retrieve_passages`) — the only
   narrative source the LLM may draw on.
4. Call `synthesize_answer()` to have the LLM weave facts + passages into one warm, grounded answer under a strict
   "never invent a number" system prompt. No LLM configured / call fails → deterministic tool-composed fallback text,
   so the demo never hallucinates and never crashes offline.
5. Return `AgentResponse` (answer + citations; or `needs` / `reroute_to` / `escalation`).
6. Registered in `agents/specialists/registry.py`, LLM injected lazily via `get_llm()` (env-resolved provider).
   To add a new scheme: implement the agent + register it — nothing else in the orchestrator changes.

## Run
```bash
pip install -r requirements.txt
pip install faster-whisper deep-translator edge-tts   # language layer (optional, falls back without)
cp .env.example .env           # add ANTHROPIC_API_KEY for live LLM (optional)
pytest                         # 31 tests, no key required
python eval/run_routing_eval.py    # routing accuracy + escalation recall
python scripts/chat_cli.py     # interactive demo
uvicorn apps.backend.main:app --reload   # API on :8000
# then open http://localhost:8000 — web UI (chat + dashboard + tools + system)
# NOTE: startup blocks ~1-15 min on first run while KB embedding/reranker warm up
```

## Verified results (offline, no key)
- 31/31 tests pass.
- Eval: **intent accuracy 100%**, **false-escalation 0%**, **escalation recall 86.7%**
  (the 2 misses are indirect-disclosure distress that needs the L2 LLM — set a key → 100%).
- 4 demo journeys work end-to-end (PMMVY route, Hinglish distress escalation,
  nutrition slot-filling loop, multi-intent safety precedence).
- RAG: recall@6=1.00, MRR=0.933 on 15-question gold set (hybrid+rerank).

## Design principles honoured
- **Safety first & non-bypassable** — gate runs before routing; a crisis clears any in-progress routing/slot state.
- **Topic changes escape a pending question** — a new confident intent mid-slot-fill re-routes instead of being swallowed as the answer; an unparseable reply is bounded (max 2 re-asks) so it never loops.
- **Declarative routing** — add a scheme = add a card + register an agent; no prompt/graph edits.
- **Deterministic dynamic questioning** — logic picks the slot, the LLM only phrases it.
- **Grounding visible** — every answer carries citations.
- **Audited** — every turn → one `InteractionTrace` JSONL line (the dashboard's future feed).
- **Testable offline** — `FakeLLM` + `FakeLanguageProvider` make everything deterministic without any key.

## Known limitations (intentional, next phases)
- Offline indirect-distress recall < 100% until an LLM key enables L2.
- In-memory state (no Redis/Postgres). No WhatsApp.
- Geo: demo dataset covers Varanasi, Madurai, Delhi, Lucknow only.

## Topic-change detection (dynamic questioning, `continue_slot`)
A message that arrives while a slot question is pending is checked for a topic
change BEFORE it is treated as the answer: `continue_slot` runs the router, and
a confident intent different from the one being slot-filled abandons the pending
slot and re-routes (so "how do I adopt a child" during a Poshan question switches
to Vatsalya instead of being mis-read as `beneficiary_type=child`). An answer we
still can't parse is re-asked at most `_MAX_SLOT_ATTEMPTS` (2) times, then the
slot is abandoned and we clarify — a reply is never looped on forever. (Earlier
builds swallowed every mid-slot message as the answer; that was the "same
question no matter what I type" bug.)
