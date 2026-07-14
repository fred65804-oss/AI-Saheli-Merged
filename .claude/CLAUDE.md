# AI Saheli — Project Intelligence for Claude

## What This Project Is
AI Saheli is a **working demo of an Agentic AI ecosystem** for India's Ministry of Women & Child Development (MoWCD). It is being built to demonstrate to senior Ministry leadership how AI can transform citizen welfare delivery across three flagship schemes: **Poshan 2.0**, **Mission Vatsalya**, and **Mission Shakti**.

Presented by **Uneecops Technologies**. Demo must be leadership-ready — polished, grounded, and safe.

## Current Status
> **Phase 4 IN PROGRESS — Next.js web app live (chat, voice avatar, analytics, tools, system); voice is fully server-piped.**
>
> ✅ **Orchestrator** — LangGraph safety gate → capability-card routing → slot-filling (with topic-change detection: a new request mid-question re-routes instead of being swallowed as the answer, and an unparseable reply is bounded to 2 re-asks, never looping) → specialist handoff. 79 tests, all passing.
> ✅ **Knowledge Base** — 2,579 chunks from 23 official PDFs in Qdrant (hybrid dense+BM25). Cross-encoder rerank is **OFF by default** (`KB_RERANK=true` to enable): the bge-reranker forward pass measured ~2s/candidate on the demo laptop CPU (104s/query at 50 candidates, blocking the event loop); hybrid RRF alone answers in ~0.3s. ⚠️ `rag/eval/gold.jsonl` is missing — the recall/MRR harness (`rag/eval/run.py`) cannot run until it is restored.
> ✅ **MCP Tools** — all 4 tools built: `knowledge_base`, `helpline_directory`, `geo_locator`, `eligibility`.
> ✅ **Language Layer** — `FreeProvider`: faster-whisper ASR (model cached per-process, `WHISPER_MODEL_SIZE=small` default — "base" garbles Hindi; script-anchoring initial_prompts keep Devanagari output) + deep-translator NMT + edge-tts TTS. 10 Indian languages. Zero keys needed.
> ✅ **Voice + Text API** — FastAPI `/chat`, `/voice`, `/health` live. `/warmup` preloads KB + both LLM clients + ASR + TTS — **always run it before a demo** (start_demo.ps1 does).
> ✅ **Real specialist agents** — Poshan/Vatsalya/Shakti/General call MCP tools for VERIFIED FACTS and retrieve official KB passages, then an LLM synthesizes a grounded, cited answer from them (never inventing amounts/rules). No LLM key → deterministic tool-composed fallback. Mocks kept only for tests.
> ✅ **Multi-provider LLM** — `LLM_PROVIDER=auto` resolves Azure OpenAI, Anthropic or OpenAI from whichever key is set in `.env`; model names are env-driven with per-provider defaults.
> ✅ **Web app (Next.js 14, apps/web)** — chat (text + voice-avatar modes), analytics dashboard, tool explorer, system panel, email/password auth (JWT + refresh rotation). The Next dev server proxies API paths to the backend (next.config.mjs rewrites). Voice avatar records in the browser and round-trips `POST /voice` — ASR/TTS run **server-side**; no in-browser Whisper (that stack was removed: the ~200 MB model download bricked the mic when it failed, and browser speechSynthesis had no Hindi voice on most machines).
> ✅ **One-command demo startup** — `powershell -File scripts\start_demo.ps1` (backend → health-wait → warmup → frontend).
> ✅ **Zero hardcoded escalation data** — the 181/1098/112 safety-gate message reads its numbers from `mcp/helpline_directory/data/helplines.yaml`.
>
> ❌ Not built: WhatsApp webhook (Journeys 1/3 run on web, not WhatsApp) · password-reset backend (`/forgot-password` page is a UI stub that calls nothing) · Redis/Postgres session persistence (MemorySaver + SQLite auth) · WebSocket streaming · synthetic personas · `rag/eval/gold.jsonl`.

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
1. Pregn ant woman asks about nutrition in Hindi **by voice** on WhatsApp
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
- [`dev/whatsapp-integration-plan.md`](dev/whatsapp-integration-plan.md) — **Zero-cost WhatsApp rollout plan (not yet started)**
- [`dev/roadmap.md`](dev/roadmap.md) — Phased build plan
- [`demo/journeys.md`](demo/journeys.md) — Scripted demo scenarios & personas
- [`dev/orchestrator-build.md`](dev/orchestrator-build.md) — **Phase 1 orchestrator build: file map, run, contract**

## Repo Structure (Actual — as built)
```
ai-saheli/
  apps/
    backend/            # FastAPI: /chat ✅ /voice ✅ /health ✅ /warmup ✅ /meta ✅
      main.py           #   /helplines ✅ /tools/* ✅ /analytics/* ✅ /auth/* ✅
      config.py         # pydantic-settings (env vars, multi-provider LLM, KB_RERANK)
      dashboard.py      # ✅ dashboard/tools/analytics API (UI is 100% data-driven)
      auth/             # ✅ email/password JWT auth (signup/login/refresh/logout/me)
    web/                # ✅ Next.js 14 app (THE web UI — port 3000, proxies API → :8000)
      app/page.tsx      #   chat: text mode + voice-avatar mode (records → POST /voice)
      app/dashboard/    #   Ministry analytics dashboard (login-walled)
      app/tools/        #   tool explorer: KB search, eligibility form (generated from
                        #     the backend's Pydantic JSON Schema), geo locator, helplines
      app/system/       #   system panel: health, LLM config, capability cards, languages
      app/login|signup|forgot-password/   # auth pages (forgot-password = UI stub, no backend)
      static/           # ⚠️ LEGACY pre-Next.js static UI — no longer served by anything;
                        #   kept only as reference, do not extend

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
