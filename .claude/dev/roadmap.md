# Build Roadmap — AI Saheli Demo

## Overview
4 phases to a leadership-ready demo covering Poshan, Vatsalya, Mission Shakti across WhatsApp + Web with voice in Hindi minimum.

---

## Phase 0 — Foundation
**Status: ✅ COMPLETE**

- ✅ Monorepo structure (apps/, agents/, mcp/, rag/, language/, pdf_chunker/)
- ✅ Environment setup (.env.example, config.py, pydantic-settings)
- ✅ Official scheme PDFs collected (23 PDFs across 3 schemes)
- ✅ RAG ingestion pipeline — chunk → embed → upsert Qdrant (2,579 points)
- ✅ `.gitattributes` (LF line endings)

---

## Phase 1 — Core Text Pipeline
**Status: ✅ COMPLETE**

- ✅ FastAPI backend: `/chat` endpoint (text in, text out)
- ✅ Orchestrator (LangGraph supervisor): safety gate → routing → slot-filling → handoff
- ✅ Capability cards (Poshan / Vatsalya / Shakti / General)
- ✅ Mock specialists (Poshan, Vatsalya, Shakti, General) — colleague's real agents slot in here
- ✅ MCP tools: `knowledge_base`, `helpline_directory`, `geo_locator`, `eligibility`
- ✅ Guardrails: L1 lexicon + L2 LLM safety gate, templated escalation
- ✅ Interaction trace → JSONL (future dashboard feed)
- ✅ 31 deterministic tests (no API key needed)
- ✅ Routing eval: 100% intent accuracy, 0% false escalation

---

## Phase 2 — Voice + Language Layer
**Status: ✅ COMPLETE**

- ✅ Language layer: `FreeProvider` — faster-whisper ASR + deep-translator NMT + edge-tts TTS
- ✅ 10 Indian languages (hi, bn, ta, te, mr, gu, kn, ml, pa, ur)
- ✅ FastAPI `/voice` endpoint: audio → ASR → translate → orchestrator → translate → TTS → audio
- ✅ `/chat` multilingual: non-ASCII → translate-in → orchestrator → translate-back
- ✅ Degraded-mode: translation failure → English passthrough (demo never 500s)
- ✅ Model warmup on startup (embedding + reranker loaded before first request)

---

## Phase 3 — Real Specialists + WhatsApp
**Status: 🔄 IN PROGRESS**

### Real specialist agents ✅ DONE
- [x] Poshan Agent — `knowledge_base(scheme=poshan)` + `eligibility` + `geo_locator(AWC)` + medical red-flag → ANM referral (`agents/specialists/poshan.py`)
- [x] Vatsalya Agent — `knowledge_base(scheme=vatsalya)` + `geo_locator(DCPU)` + `helpline_directory(child)` (`agents/specialists/vatsalya.py`)
- [x] Shakti Agent — `knowledge_base(scheme=shakti)` + `eligibility(PMMVY)` + `geo_locator(OSC)` + `helpline_directory(women)`, two branches: safety/OSC vs PMMVY scheme query (`agents/specialists/shakti.py`)
- [x] General Agent (bonus, not originally scoped) — cross-scheme `knowledge_base` synthesis for discovery/fallback queries (`agents/specialists/general.py`)
- [x] Registered in `agents/specialists/registry.py` (mocks replaced; kept only for test doubles)
- [x] Shared grounding core (`agents/specialists/_grounding.py`): retrieves KB passages once per turn, feeds verified tool facts + passages to the LLM with a strict "never invent a number" system prompt, and falls back to a deterministic tool-composed answer when no LLM is configured or the call fails — so the demo never hallucinates and never crashes offline
- [x] Multi-provider LLM (bonus, not originally scoped) — `agents/orchestrator/llm.py` now supports Anthropic **and** OpenAI; `LLM_PROVIDER=auto` in `.env` picks whichever key is present; model names are env-driven, no model hardcoded in code
- [x] De-hardcoded the safety-gate escalation helplines (bonus fix) — `agents/guardrails/safety.py` previously had 181/1098/112 in a Python dict; now reads them from `mcp/helpline_directory/data/helplines.yaml`, the same source of truth the specialists use

### WhatsApp channel
- [ ] FastAPI `POST /whatsapp-webhook` — Meta webhook receiver + send reply
- [ ] Parse inbound (text / voice note) → call `/chat` or `/voice` logic
- [ ] Download OGG voice note → transcoding → ASR pipeline
- [ ] Reply via Meta Cloud API (text or audio)
- [ ] Webhook verification (`GET /whatsapp-webhook`)

### Testing
- [x] Offline unit/contract tests for the real specialists (`tests/test_specialists_real.py`) — grounding-prompt content, tool-fact fidelity, dynamic questioning, medical red-flag routing, synthesis-error fallback
- [ ] End-to-end test all 4 demo journeys in text **with a live LLM key** (only run offline/FakeLLM so far — need to confirm synthesized answers, not just fallback text, read well)
- [ ] End-to-end Journey 1 via voice (Sunita, Hindi, Varanasi)

---

## Phase 4 — Dashboard + Polish
**Status: 🔄 IN PROGRESS — web UI + analytics dashboard BUILT**

> Stack decision: built as a **self-contained static app served by FastAPI at `/`**
> (apps/web/static — no Node/build step; Node isn't installed on the demo machine
> and one server = fewer demo-day moving parts). Next.js remains the production path.
> The UI is 100% data-driven: languages, scheme cards, enum choices, the eligibility
> form (generated from the backend's JSON Schema), helplines and all analytics come
> from APIs — nothing hardcoded in the frontend.

- [x] Analytics dashboard (`/` → Dashboard tab; APIs: `/analytics/summary`, `/analytics/recent`)
  - [x] KPI stat tiles: turns, sessions, escalations + rate, grounding rate, avg latency, slot questions, fallbacks
  - [x] Queries by scheme (intent mix, scheme-fixed colors)
  - [x] Escalations by safety category
  - [x] Language distribution
  - [x] District distribution (trace now logs collected district; heatmap deferred — demo geo data covers 4 districts)
  - [x] Queries-over-time line (hourly/daily buckets) with escalations in tooltip
  - [x] MCP tool-call usage
  - [x] Real-time query feed reading `logs/interactions.jsonl` (auto-refresh, window filter)
  - [x] Table-view twin on every chart (accessibility)
- [x] "AI Saheli" chat UI — text + voice (MediaRecorder → `/voice` → TTS audio replies), language picker (11 languages from `/meta`), citations, escalation banner, intent chips, dynamic-questioning display
- [x] Tool explorer — live KB search, eligibility checker (form generated from Pydantic JSON Schema), helpline directory, facility locator
- [x] System panel — runtime health, provider/model, registered capability cards
- [ ] WebSocket streaming for token-by-token responses in web app
- [ ] Redis session persistence (replace MemorySaver)
- [ ] Load 4 synthetic personas (Sunita, Kavitha, Meena, Rajesh)
- [ ] Full dry-run of 4 demo journeys (twice without errors)
- [ ] Demo script finalized
- [ ] Backup mode: pre-recorded walkthrough if live infra fails

---

## 4 Demo Journeys (Must Work Live)

### Journey 1 — Maternal Nutrition (Voice, Hindi, WhatsApp) 🎤
**Persona:** Sunita Devi, 6 months pregnant, BPL, Varanasi, UP
```
Sunita: [Hindi voice note] "Mujhe pregnancy mein kya khana chahiye?"
AI: [Hindi voice reply] Tailored nutrition advice for 2nd trimester
    + cite Poshan 2.0 guideline + nearest AWC in Varanasi
```
**Status:** Orchestrator + voice endpoint ✅ | Real Poshan agent ✅ | WhatsApp ❌

### Journey 2 — Child Growth Milestone 📊
**Persona:** Kavitha, Tamil-speaking mother, 14-month-old child, Madurai
```
Kavitha: "My child is 14 months and not walking yet, is this normal?"
AI: Growth milestone guidance for 12–18 months + nearest AWC in Madurai
```
**Status:** Orchestrator ✅ | Real Poshan agent ✅

### Journey 3 — Women Safety Escalation 🆘
**Persona:** Meena, Delhi, seeking safety help
```
Meena: "Mujhe help chahiye, ghar mein mujh par violence ho raha hai"
AI: Immediate 181 + 112 + nearest OSC in Delhi — NO counselling, no delay
    (escalation=true fires on dashboard in real-time)
```
**Status:** Safety gate ✅ | Escalation template ✅ (helplines now data-sourced) | geo_locator(OSC, Delhi) ✅ | Real Shakti agent ✅ | WhatsApp ❌

### Journey 4 — PMMVY Eligibility + Dashboard Flip 📈
**Persona:** Sunita, BPL, first child
```
Sunita: "Kya mujhe PMMVY ka labh mil sakta hai?"
AI: Eligibility confirmed → ₹5,000 in 3 instalments → how to apply → CDO office
[Presenter flips to Ministry dashboard showing all 4 journeys' analytics]
```
**Status:** Eligibility rules ✅ | Real Shakti agent ✅ | Dashboard ❌

---

## Open Decisions
1. **LLM for demo day:** RESOLVED for provider choice — the LLM layer now supports both Anthropic and OpenAI (`LLM_PROVIDER=auto` in `.env` picks whichever key is present); an OpenAI key is available and configured. Still open: offline (no key) mode passes routing/eligibility/helplines correctly but serves template-composed answers instead of LLM-synthesized ones — decide whether the demo runs live (needs the key wired into `.env` and a network connection on demo day) or offline-safe as backup.
2. **WhatsApp number:** Meta test number vs dedicated demo number. Test number sufficient for demo.
3. **Demo hosting:** Docker Compose on laptop vs cloud VM. Laptop is fine; bring a hotspot backup.
4. **Dashboard data:** Real traces from dry-run vs pre-seeded synthetic data for the flip moment.
