# AI Saheli — Project Intelligence for Claude

## What This Project Is
AI Saheli is a **working demo of an Agentic AI ecosystem** for India's Ministry of Women & Child Development (MoWCD). It is being built to demonstrate to senior Ministry leadership how AI can transform citizen welfare delivery across three flagship schemes: **Poshan 2.0**, **Mission Vatsalya**, and **Mission Shakti**.

Presented by **Uneecops Technologies**. Demo must be leadership-ready — polished, grounded, and safe.

## Current Status
> **Phase 3 IN PROGRESS — real specialist agents live; LLM layer is multi-provider.**
>
> ✅ **Orchestrator** — LangGraph safety gate → capability-card routing → slot-filling (with topic-change detection: a new request mid-question re-routes instead of being swallowed as the answer, and an unparseable reply is bounded to 2 re-asks, never looping) → specialist handoff. 59 tests, all passing.
> ✅ **Knowledge Base** — 2,579 chunks from 23 official PDFs in Qdrant (hybrid dense+BM25, reranker). recall@6=1.00, MRR=0.933.
> ✅ **MCP Tools** — all 4 tools built: `knowledge_base`, `helpline_directory`, `geo_locator`, `eligibility`.
> ✅ **Language Layer** — `FreeProvider`: faster-whisper ASR + deep-translator NMT + edge-tts TTS. 10 Indian languages. Zero keys needed.
> ✅ **Voice + Text API** — FastAPI `/chat`, `/voice`, `/health` all live. Language layer wired: translate-in → orchestrator → translate-out → TTS.
> ✅ **Real specialist agents** — Poshan/Vatsalya/Shakti/General now call MCP tools for VERIFIED FACTS and retrieve official KB passages, then an LLM synthesizes a grounded, cited answer from them (never inventing amounts/rules). No LLM key → deterministic tool-composed fallback (same behaviour as before, demo never breaks). Mocks kept only for tests.
> ✅ **Multi-provider LLM** — `LLM_PROVIDER=auto` resolves Anthropic or OpenAI from whichever key is set in `.env`; model names are env-driven with per-provider defaults (no model name hardcoded in code).
> ✅ **Zero hardcoded escalation data** — the 181/1098/112 safety-gate message now reads its numbers from `mcp/helpline_directory/data/helplines.yaml` (previously a hardcoded dict in `guardrails/safety.py`).
>
> Next: WhatsApp webhook, Web UI + analytics dashboard, Redis/Postgres persistence.

## Non-Negotiable Principles
1. **Grounding over fluency** — every scheme fact must cite an official source. Never invent benefit amounts or eligibility rules.
2. **Safety-first routing** — child protection (Vatsalya) and women's safety (Shakti) queries surface helplines (1098, 181, 112), never autonomous counselling.
3. **Sovereign by design** — use Bhashini/VoicERA for ASR/TTS/NMT (MeitY-approved stack). Open-weight models for production path.
4. **Zero real PII** — synthetic demo personas only. PII guard always active.
5. **Dynamic questioning** — ask the single most informative missing question, never walk a fixed tree.

## Priority Schemes (Demo Scope)
| Agent | Scheme | Safety Level |
|---|---|---|
| Poshan Agent | Poshan 2.0 / Saksham Anganwadi | Medium — flag medical red-flags to ANM |
| Vatsalya Agent | Mission Vatsalya (child protection) | HIGH — distress → 1098 / 112 immediately |
| Shakti Agent | Mission Shakti (women safety) | HIGH — distress → 181 / 112 + nearest OSC |

## 4 Demo Journeys (Script These First)
1. Pregnant woman asks about nutrition in Hindi **by voice** on WhatsApp
2. Parent worried child isn't hitting growth milestones
3. Woman seeking safety/helpline support → routed to 181 + nearest OSC
4. Citizen discovers PMMVY eligibility → Ministry analytics dashboard flip

## Documentation Index
- [`project/context.md`](project/context.md) — Ministry context, stakeholders, vision
- [`project/schemes.md`](project/schemes.md) — Poshan, Vatsalya, Shakti scheme details
- [`architecture/system.md`](architecture/system.md) — Full system architecture & request lifecycle
- [`architecture/agents.md`](architecture/agents.md) — Orchestrator + 3 specialist agent designs
- [`architecture/data-model.md`](architecture/data-model.md) — Data schemas
- [`dev/tech-stack.md`](dev/tech-stack.md) — Technology decisions & rationale
- [`dev/guardrails.md`](dev/guardrails.md) — Safety, grounding, escalation rules
- [`dev/api-integrations.md`](dev/api-integrations.md) — Bhashini, WhatsApp, geo APIs
- [`dev/roadmap.md`](dev/roadmap.md) — Phased build plan
- [`demo/journeys.md`](demo/journeys.md) — Scripted demo scenarios & personas
- [`dev/orchestrator-build.md`](dev/orchestrator-build.md) — **Phase 1 orchestrator build: file map, run, contract**

## Repo Structure (Actual — as built)
```
ai-saheli/
  apps/
    backend/            # FastAPI: /chat ✅ /voice ✅ /health ✅ /meta ✅ /helplines ✅
      main.py           #   /tools/* ✅ /analytics/* ✅ — /whatsapp-webhook ❌
      config.py         # pydantic-settings (env vars, multi-provider LLM)
      dashboard.py      # ✅ dashboard/tools/analytics API (UI is 100% data-driven)
    web/
      static/           # ✅ web UI — chat (text+voice), analytics dashboard, tool
                        #   explorer, system panel. Self-contained HTML/JS/CSS served
                        #   by FastAPI at "/" (no Node/build step — decision: demo
                        #   robustness on a machine without Node; Next.js stays the
                        #   production path)

  agents/
    orchestrator/       # ✅ LangGraph supervisor
      graph.py          # StateGraph + run_turn()
      nodes.py          # safety_gate, route, slot_check, handoff, finalize...
      capabilities.py   # Poshan/Vatsalya/Shakti/General cards
      router.py         # RouterDecision + keyword fast-path
      slots.py          # deterministic slot selection
      llm.py            # AnthropicLLM + OpenAILLM + FakeLLM, provider resolved from Settings (auto/anthropic/openai)
      trace.py          # InteractionTrace → JSONL
      state.py          # AgentState TypedDict
      prompts.py        # card-driven prompts
    guardrails/         # ✅ safety gate
      lexicon.py        # bilingual distress keywords
      safety.py         # L1+L2 check + templated escalation (helplines sourced from mcp/helpline_directory data)
    specialists/        # ✅ real agents (mocks kept for tests only)
      base.py           # ✅ ContextPacket, AgentResponse, SpecialistAgent ABC (the contract)
      _grounding.py     # ✅ shared KB retrieval + LLM synthesis + deterministic fallback
      poshan.py         # ✅ RealPoshanAgent — eligibility + geo(AWC) + KB + medical red-flag→ANM
      vatsalya.py        # ✅ RealVatsalyaAgent — helpline(CHILDLINE) + geo(DCPU) + KB
      shakti.py          # ✅ RealShaktiAgent — helpline(women)/geo(OSC) branch + PMMVY eligibility branch + KB
      general.py         # ✅ RealGeneralAgent — cross-scheme KB synthesis (fallback/discovery)
      mocks.py          # mock Poshan/Vatsalya/Shakti/General agents — used only by tests now
      registry.py       # ✅ intent → real specialist instance (LLM injected via get_llm())

  mcp/                  # ✅ ALL 4 TOOLS BUILT
    knowledge_base/     # hybrid Qdrant RAG → grounded passages
    helpline_directory/ # 1098/181/112/15100 lookup by category (YAML data)
    geo_locator/        # nearest AWC/OSC/DCPU/CWC by district (mock data)
    eligibility/        # PMMVY/THR/SNP/SAAN/Sponsorship rules (pure Python)

  language/             # ✅ language layer
    provider.py         # LanguageProvider protocol + FakeLanguageProvider
    free_provider.py    # FreeProvider: faster-whisper + deep-translator + edge-tts

  rag/                  # ✅ knowledge base
    embed.py            # dense (e5-base) + sparse (bm25) embedding
    index.py            # Qdrant ingest (2,579 points)
    retrieve.py         # hybrid search + RRF + rerank
    chunks/             # chunked JSON per scheme (poshan/shakti/vatsalya)
    qdrant_db/          # local persistent Qdrant storage
    eval/               # gold.jsonl + run.py (recall/MRR harness)

  pdf_chunker/          # ✅ standalone PDF → chunks pipeline
    chunk_pdfs.py       # hybrid auto-detect (text vs OCR) + heading cascade
    ocr.py              # RapidOCR backend + space repair

  tests/                # ✅ 57 tests, all passing (no key needed) — conftest.py blanks LLM keys so the suite is always offline/free
  eval/                 # ✅ routing golden set + accuracy harness
  scripts/              # ✅ chat_cli.py terminal REPL
  personas/             # ❌ synthetic demo personas (not yet)
  infra/                # ❌ docker-compose (not yet)
```

## Key Contacts & Context
- **Client:** Ministry of Women & Child Development (MoWCD), Government of India
- **Presenter:** Uneecops Technologies (CMMi Level 5)
- **Audience:** Senior Ministry leadership
- **Timeline:** Demo must be ready before next leadership presentation
