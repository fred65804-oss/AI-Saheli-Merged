# System Architecture — AI Saheli

## Architecture Pattern
**Supervisor + Specialist Agents with RAG Grounding**
Chosen for: clear agent boundaries, testable routing, grounding auditability, safety control points.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CHANNELS                                  │
│  WhatsApp Cloud API ❌   Web UI ✅ (FastAPI-served)  (future: IVR)│
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                    GATEWAY / API LAYER  ✅                        │
│  FastAPI (async) — /chat ✅ /voice ✅ /health ✅ /meta ✅         │
│  /helplines ✅  /tools/* ✅ (kb-search, eligibility, geo,        │
│  helpline)  /analytics/* ✅ (summary, recent)                    │
│  /whatsapp-webhook ❌ (not yet)                                   │
│  Serves the web UI at "/" (apps/web/static, no build step)       │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│               LANGUAGE LAYER  ✅                                  │
│   FreeProvider: faster-whisper ASR + deep-translator NMT         │
│                + edge-tts TTS                                    │
│   Inbound: translate to English (if non-ASCII)                   │
│   Outbound: translate back + TTS                                 │
│   Provider interface: swappable for Bhashini/VoicERA             │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│              ORCHESTRATOR AGENT (LangGraph)  ✅                   │
│  • Layered safety gate (L1 lexicon + L2 LLM)                    │
│  • Capability-card routing → {poshan|vatsalya|shakti|general}   │
│  • Deterministic slot-filling (logic picks, LLM phrases)        │
│  • Handoff to specialist via ContextPacket                       │
│  • Audit trace → logs/interactions.jsonl                         │
└──────┬──────────────────┬──────────────────┬────────────────────┘
       ↓                  ↓                  ↓
┌──────────────┐  ┌───────────────┐  ┌──────────────────┐
│ POSHAN AGENT │  │VATSALYA AGENT │  │  SHAKTI AGENT    │
│ ✅ REAL      │  │ ✅ REAL       │  │ ✅ REAL          │
│ tools+KB+LLM │  │ tools+KB+LLM  │  │ tools+KB+LLM     │
│ synthesis    │  │ synthesis     │  │ synthesis        │
└──────┬───────┘  └───────┬───────┘  └──────┬───────────┘
       └──────────────────┼──────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│                    MCP TOOL LAYER  ✅ ALL BUILT                   │
│  knowledge_base ✅  ·  eligibility ✅  ·  geo_locator ✅          │
│  helpline_directory ✅  ·  profile_session ❌ (not needed yet)    │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                    GUARDRAILS LAYER  ✅                           │
│  L1 lexicon (bilingual) · L2 LLM safety classifier              │
│  Templated escalation · Grounding citations                      │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                    DATA & STORAGE LAYER                          │
│  Qdrant ✅ (local, 2,579 pts)  ·  Redis ❌  ·  PostgreSQL ❌     │
│  JSONL trace log ✅  ·  Facility mock data ✅  ·  Helpline YAML ✅│
└─────────────────────────────────────────────────────────────────┘
```

---

## Request Lifecycle

### Voice Request (Headline Demo Path)
```
1. Citizen sends Hindi voice note on WhatsApp                    ← WhatsApp not built yet
2. Backend POST /voice receives base64 audio
3. FreeProvider.transcribe() → faster-whisper → Hindi text       ✅
4. Hindi text → FreeProvider.translate(hi→en) → English          ✅
5. Orchestrator: safety gate → route → slot → handoff            ✅
6. Specialist agent calls MCP tools (knowledge_base, geo, etc.)  ✅ tools built; ⏳ real agents
7. Agent composes grounded English answer with citations
8. English → FreeProvider.translate(en→hi) → Hindi               ✅
9. Hindi → FreeProvider.synthesize() → edge-tts → Hindi audio   ✅
10. Audio sent back as base64                                     ✅ /voice returns this
11. Turn logged to logs/interactions.jsonl                        ✅
```

### Text Request
```
1. POST /chat with {session_id, message, lang}
2. If lang != "en" and non-ASCII → translate to English           ✅
3. Orchestrator turn → response in English                        ✅
4. Translate back to user's language                              ✅
5. Return ChatResponse (response, intent, confidence, escalation, citations, trace_id)
```

### Escalation Path (Safety)
```
Inbound → safety_gate L1 lexicon fires (or L2 LLM)
→ templated response = helpline + geo_locator result
→ escalation=true logged
→ NO LLM counselling, NO autonomous advice
```

---

## Component Status

### API Endpoints
| Endpoint | Status | Notes |
|---|---|---|
| `POST /chat` | ✅ | Text, multilingual, multi-turn |
| `POST /voice` | ✅ | ASR → orchestrator → NMT → TTS |
| `GET /health` | ✅ | LLM (provider/model) + language provider status |
| `GET /meta` | ✅ | App metadata: languages, capability cards, enums, eligibility JSON Schema — the web UI builds itself from this (zero hardcoding) |
| `GET /helplines` | ✅ | Full validated helpline directory |
| `POST /tools/kb-search` | ✅ | knowledge_base passthrough (dashboard tool explorer) |
| `POST /tools/eligibility` | ✅ | eligibility rules passthrough |
| `POST /tools/geo` | ✅ | geo_locator passthrough |
| `POST /tools/helpline` | ✅ | helpline_directory lookup passthrough |
| `GET /analytics/summary` | ✅ | Aggregates over `logs/interactions.jsonl` (window filter) |
| `GET /analytics/recent` | ✅ | Latest interaction traces for the live feed |
| `GET /` | ✅ | Web UI — chat + dashboard + tools + system (static, no build step) |
| `POST /whatsapp-webhook` | ❌ | Next phase |

### MCP Tools
| Tool | Status | Used by |
|---|---|---|
| `knowledge_base` | ✅ | All 3 specialist agents |
| `helpline_directory` | ✅ | Shakti, Vatsalya, Poshan (medical) |
| `geo_locator` | ✅ | All 3 (AWC/OSC/DCPU/CWC) |
| `eligibility` | ✅ | Poshan (THR/SNP/SAAN), Shakti (PMMVY), Vatsalya (sponsorship) |
| `profile_session` | ❌ | Future — when Redis/Postgres added |

### Specialist Agents (all REAL — `agents/specialists/{poshan,vatsalya,shakti,general}.py`)
| Agent | Status | Notes |
|---|---|---|
| Poshan | ✅ Real | eligibility + geo(AWC) + KB synthesis + medical red-flag → ANM |
| Vatsalya | ✅ Real | helpline(CHILDLINE) + geo(DCPU) + KB synthesis |
| Shakti | ✅ Real | safety/OSC branch + PMMVY eligibility branch + KB synthesis |
| General | ✅ Real | cross-scheme KB synthesis (discovery/fallback) |

All four use `_grounding.py`: MCP tools give VERIFIED FACTS, the KB gives official
passages, the LLM only weaves them (strict no-invention prompt). No key → deterministic
tool-composed fallback.

### Storage
| Store | Status | Notes |
|---|---|---|
| Qdrant (vector DB) | ✅ | Local on-disk, 2,579 points |
| JSONL trace log | ✅ | `logs/interactions.jsonl` |
| Redis | ❌ | Using MemorySaver in-process |
| PostgreSQL | ❌ | Not needed for demo |

---

## LLM Selection
| Context | Model | Reason |
|---|---|---|
| Demo | Multi-provider (`LLM_PROVIDER=auto`): Anthropic claude-sonnet-4-6 or OpenAI gpt-4.1 — whichever key is in `.env` | Strong reasoning, tool use, multilingual, safe; provider/model fully env-driven |
| Offline / No key | Keyword + lexicon routing, deterministic tool-composed answers | Runs without key; routing works, answers grounded but templated |
| Production / Sovereign | Sarvam-M or Llama-Indic on-prem | Sovereign deployment on NIC MeghRaj |

---

## Deployment
| Stage | Option |
|---|---|
| Demo | Single machine — `uvicorn apps.backend.main:app` + Qdrant on-disk |
| Demo (WhatsApp) | + ngrok tunnel to expose localhost to Meta webhook |
| Production | Docker Compose → Kubernetes on NIC MeghRaj / Government Cloud |
