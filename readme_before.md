# AI Saheli — Technical Design & Roadmap

**Project:** Agentic AI assistant for MWCD (demo for senior leadership)
**Priority schemes:** Poshan 2.0 · Mission Vatsalya · Mission Shakti
**Status:** Pre-build design (no code yet)

---

## 0. Scope decision (read this first)

We are building a **working vertical slice**, not the full national ecosystem. The slice must:

- Run **end-to-end** for 4 scripted-but-live citizen journeys.
- Cover **3 schemes** through 3 specialist agents + 1 orchestrator.
- Support **voice + text** in **English + Hindi** minimum (2–3 more languages if time allows).
- Run on **2 channels**: a branded web/mobile chat and **WhatsApp**.
- Be **grounded** (every scheme fact traceable to an official source) and **safe** (sensitive cases route to human helplines, never autonomous advice).

Everything below is sized to that slice, with the production/sovereign path noted where it differs.

---

## 1. Component inventory — what gets built, how, and with what

Each component lists: **what it is → how it's made → tech**.

### 1.1 Channels

| Component | What it is | How it's made | Tech |
|---|---|---|---|
| Web/mobile chat | Branded "AI Saheli" chat UI with mic button, language picker, message list | Single-page app calling the backend over REST/WebSocket; mic records audio, streams to backend | Next.js/React + Tailwind; Web Audio API for mic capture (record as WAV/PCM, not WebM — Bhashini needs WAV) |
| WhatsApp | Same agent reachable on WhatsApp | Webhook receiver for inbound messages + send API for replies; voice notes downloaded, transcoded, sent to ASR | WhatsApp Cloud API (Meta) → backend webhook endpoint |

> WhatsApp is the single biggest credibility multiplier for a rural-citizen story. Include it.

### 1.2 Backend / API gateway

- **What:** the single entry point that receives every channel request and coordinates the pipeline.
- **How:** an async API service exposing `/chat` (text) and `/voice` (audio); manages sessions, calls the language layer, invokes the orchestrator, streams the reply back.
- **Tech:** FastAPI (Python, async) or Node/Express. WebSocket for streaming token output to the web app; plain HTTP for WhatsApp.

### 1.3 Language layer (Bhashini)

Official MeitY sovereign stack — correct optics for a government demo, free for PoC, 22+ voice languages.

| Sub-component | Function | How connected |
|---|---|---|
| Language detect | identify the user's language from text/audio | first step on inbound, sets `session.lang` |
| ASR (speech→text) | transcribe voice note to text in source language | inbound voice only |
| NMT (translate) | source language ⇄ English (the agents reason in English) | inbound: source→EN; outbound: EN→source |
| TTS (text→speech) | render the reply as audio in the user's language | outbound voice only |

- **How it's made:** a thin `BhashiniClient` wrapper. Flow: **Pipeline Config call** (get pipeline/service IDs + auth) → **Compute call** (run ASR / NMT / TTS or a chained `ASR+NMT` task). Cache the config response; audio is base64 WAV.
- **Tech:** Bhashini ULCA REST APIs. Keep a provider interface so Sarvam AI (Indic models) can be swapped in for the production/on-prem path.

### 1.4 Orchestrator agent (the agentic core)

- **What:** a supervisor LLM that, per turn, resolves **intent + user context** and decides: answer directly, ask the next best question, route to a specialist agent, or escalate to a helpline.
- **How it's made:** an LLM with a router system prompt + tool-calling. Maintains conversation state (language, location, pregnancy stage, child age, active agent). Implements **dynamic questioning** — it asks the single most informative missing question rather than walking a fixed tree (no hardcoded flows).
- **Routing signals:** keywords + embeddings + the LLM's own classification → one of `poshan | vatsalya | shakti | general | escalate`.
- **Handoff protocol:** orchestrator passes a compact `context` object (profile + summarized history + detected intent) to the specialist; specialist returns either a grounded answer or `needs: <missing fact>`, which the orchestrator turns into the next question.
- **Tech:** LangGraph (supervisor + agent nodes) **or** a clean custom router; PydanticAI / CrewAI are alternatives. Model = a strong Hindi/Indic-capable frontier model for the demo; open-weight (Sarvam-M, Llama-Indic) noted for sovereign deployment.

### 1.5 Specialist agents

All three share the same skeleton (system prompt + RAG + tools + guardrails); they differ in knowledge base partition, tools, and escalation rules.

**Poshan agent** (Mission Saksham Anganwadi & Poshan 2.0)
- Handles: maternal & child nutrition, the "first 1,000 days," child growth-milestone guidance, supplementary nutrition / Take-Home-Ration awareness, immunization, nearest Anganwadi.
- Tools: knowledge base, eligibility, geo-locator.
- Note: nutrition *guidance*, not clinical diagnosis — flag medical red-flags to ANM/health centre.

**Vatsalya agent** (Mission Vatsalya — child protection)
- Handles: how to report a child in need of care, adoption/foster/sponsorship info, missing-child support, routing to DCPU/CWC.
- Tools: knowledge base, geo-locator, **helpline directory (CHILDLINE 1098)**.
- Safety-critical: **never** counsel or collect abuse details — detect distress → surface 1098 / 112 + nearest authority immediately.

**Shakti agent** (Mission Shakti — women safety & empowerment)
- Handles: 181 helpline, One Stop Centres, domestic-violence support, scheme discovery, PMMVY maternity benefit, Sakhi Niwas, Nari Adalat.
- Tools: knowledge base, eligibility, geo-locator, **helpline directory (181 / 112)**.
- Safety-critical: distress/emergency → surface 181 / 112 + nearest One Stop Centre; do not act as counsellor.

### 1.6 MCP tool layer

Tools are exposed as **MCP servers** (reusable across all agents, consistent with the Udyami-Saarthi pattern). Conceptual contracts:

| Tool | Input → Output | How it's made |
|---|---|---|
| `knowledge_base` (RAG) | `query, scheme` → grounded passages + source IDs | retriever over the vector DB, partitioned by scheme |
| `eligibility` | `profile` (income, district, pregnancy/child status, age) → eligible schemes + reasons | rule engine over a structured scheme-rules table |
| `geo_locator` | `lat/lng or district, service_type` → nearest Anganwadi / OSC / CHC / vaccination centre | Places API, **or** a curated mock dataset for the demo |
| `helpline_directory` | `category` → number + when to call + escalation note | static, authoritative table (181, 1098, 112, NALSA) |
| `profile_session` | get/set citizen profile + session state | read/write to the session store |

### 1.7 RAG knowledge base + ingestion pipeline

- **What:** the grounding source. Official scheme guidelines, FAQs, benefit amounts, eligibility rules — chunked, embedded, retrievable, **partitioned per scheme**.
- **Ingestion (offline, run once + on update):** collect official PDFs/pages → clean/normalize → chunk (≈300–500 tokens, heading-aware) → embed → upsert to vector DB with metadata `{scheme, source_url, section, language}`.
- **Retrieval (online):** embed query → top-k within the scheme partition → optional rerank → pass passages **with source IDs** so answers can cite.
- **Tech:** embeddings (multilingual model, e.g. `intfloat/multilingual-e5` or an Indic-tuned embedder); vector DB = Qdrant or pgvector; ingestion in a standalone Python script.

### 1.8 Data stores

- **Vector DB:** scheme knowledge (Qdrant / pgvector).
- **Profile / session store:** per-user profile + conversation state (Redis for session, Postgres for durable profile). **Synthetic personas only in the demo — zero real PII.**
- **Interaction log:** every turn logged (intent, scheme, language, latency, escalation flag) — feeds analytics. Stored in Postgres.

### 1.9 Guardrails / safety layer

A middleware that wraps agent output before it reaches the user:
- **Grounding check:** answer must be supported by retrieved passages; otherwise return the human-handoff fallback.
- **Escalation classifier:** detects distress/emergency on Vatsalya/Shakti paths → forces helpline response.
- **Scope guard:** refuses legal/medical/financial *advice*; gives information + routes to the right authority.
- **PII guard:** strips/blocks attempts to store real personal data in the demo.

### 1.10 Analytics dashboard (the Ministry-facing view)

- **What:** real-time insight into citizen interactions — top intents, regional pain points, scheme-awareness gaps, demand by scheme, emerging concerns.
- **How:** aggregate the interaction log; render charts + a query table.
- **Tech:** a lightweight dashboard (Next.js + Recharts, or Streamlit/Metabase for speed) reading from Postgres.

### 1.11 Observability

- Structured logging + tracing across the pipeline (latency per stage: ASR → NMT → orchestrator → agent → tools → TTS), so the demo can show "where time goes" and so failures are debuggable. Tech: OpenTelemetry or simple structured logs to start.

---

## 2. How it all connects — request lifecycle

### 2.1 Voice request (the headline demo path)

1. Citizen sends a **voice note** (e.g. Hindi) on WhatsApp / web mic.
2. **Backend** receives audio → **Bhashini ASR** → Hindi text → **NMT** → English text.
3. **Orchestrator** loads session + profile, classifies intent, picks the agent (or asks the next question, or escalates).
4. **Specialist agent** calls **MCP tools** (knowledge_base, eligibility, geo_locator, helpline) and composes a grounded English answer.
5. **Guardrails** validate grounding + safety.
6. **NMT** English→Hindi → **TTS** → Hindi **audio** → back to the channel.
7. Turn is **logged** → analytics.

### 2.2 Text request

Same as above minus ASR/TTS: text in → language detect → (NMT if non-English) → orchestrator → agent → tools → guardrails → (NMT back) → text out → log.

### 2.3 Escalation path (Vatsalya / Shakti)

Inbound → orchestrator/agent **escalation classifier** fires on distress/emergency → response is the **helpline + nearest authority** (181 / 1098 / 112 + nearest OSC/DCPU via geo_locator), *not* an LLM-generated counselling answer → logged with `escalation=true`.

---

## 3. Data model (demo)

```
CitizenProfile   { id, lang, district, lat, lng,
                   role(woman|mother|parent|caregiver),
                   pregnancy_stage?, child_age_months?, income_band? }   # synthetic only

Session          { session_id, citizen_id, active_agent, turn_count,
                   collected_facts{}, last_intent }

MessageLog       { id, session_id, ts, channel, lang, direction,
                   intent, scheme, tool_calls[], latency_ms, escalation:bool }

KBChunk          { id, scheme, text, embedding, source_url, section, language }

SchemeRule       { scheme, benefit, eligibility_predicate, amount, source_url }
```

---

## 4. Agent design details

- **System prompts** are scheme-specific, encode tone (warm, simple, local-language-friendly), and **hard rules** (cite sources, never diagnose, escalate on distress).
- **Dynamic questioning:** the orchestrator computes which profile fact most reduces uncertainty for the current intent and asks *only that* — e.g. pregnancy stage before nutrition advice, child age before milestone guidance, district before locating services.
- **Tool-calling loop:** agent → (call tool) → observe → (call again or answer). Cap iterations to avoid loops.
- **Grounding contract:** every factual claim maps to a retrieved passage; unsupported → fallback. This is non-negotiable for a government demo.

---

## 5. Safety & guardrails (what wins leadership)

1. **Grounding over fluency** — never invent a benefit amount or eligibility rule.
2. **Safety-first routing** — child protection & women's safety surface helplines, don't counsel.
3. **Zero real PII** — synthetic personas; PII guard active.
4. **Responsible-AI framing** — show the restraint deliberately in the demo; it *is* the story.

---

## 6. Tech stack summary

| Layer | Demo choice | Production / sovereign note |
|---|---|---|
| Channels | Next.js web + WhatsApp Cloud API | + IVR/voice, kiosk |
| Backend | FastAPI (async) | same, on NIC MeghRaj / gov cloud |
| Language | Bhashini ULCA APIs | Bhashini self-hosted / Sarvam on-prem |
| Orchestration | LangGraph or custom supervisor | same |
| LLM | Indic-capable frontier model | open-weight (Sarvam-M / Llama-Indic) on-prem |
| Tools | MCP servers | same |
| Vector DB | Qdrant / pgvector | same |
| Session/profile | Redis + Postgres | same |
| Dashboard | Next.js + Recharts / Metabase | same |
| Deploy | Docker Compose | Kubernetes, sovereign cloud |

---

## 7. Roadmap (build phases for the demo)

Each phase has a **technical milestone** and an **exit criterion** (what "done" means).

### Phase 0 — Scope & content · ~3–4 days
- Lock the 4 demo journeys + synthetic personas.
- Build the **scheme knowledge base**: collect official guideline docs for Poshan 2.0, Vatsalya, Shakti → ingestion pipeline → vector DB.
- Stand up repo, env, secrets, Docker Compose skeleton.
- **Exit:** RAG returns correct, cited passages for 20 test questions across the 3 schemes.

### Phase 1 — Core works in text · ~1 week
- Backend `/chat`; orchestrator + router; **Poshan agent** wired to knowledge_base + eligibility + geo_locator.
- Dynamic questioning working (asks for pregnancy stage / child age / district).
- English + Hindi text (via NMT).
- **Exit:** a Hindi text conversation about nutrition gives a grounded, cited answer and finds the nearest Anganwadi.

### Phase 2 — All three agents + safety · ~1 week
- Add **Vatsalya** + **Shakti** agents, helpline_directory tool, escalation classifier, guardrail middleware.
- Agent handoff via orchestrator.
- **Exit:** a women-safety query routes to 181 + nearest OSC; a child-protection distress query routes to 1098 — both with `escalation=true`, no autonomous advice.

### Phase 3 — Voice + WhatsApp + multilingual · ~1 week
- Bhashini **ASR + TTS**; voice on web mic and WhatsApp voice notes.
- WhatsApp Cloud API channel live.
- Add 2–3 more languages.
- **Exit:** end-to-end **voice** journey on WhatsApp in a regional language works for all 3 schemes.

### Phase 4 — Dashboard + polish · ~3–5 days
- Analytics dashboard over the interaction log.
- Branded UI, latency tuning, rehearse the 4 journeys + the Ministry dashboard persona.
- **Exit:** full dry-run of the leadership demo passes cleanly twice.

**The 4 journeys to script (run live):**
1. Pregnant woman asks about nutrition in Hindi **by voice**.
2. Parent worried a child isn't hitting growth milestones.
3. Woman seeking safety/helpline support → routed to 181 + nearest OSC.
4. Citizen discovers PMMVY eligibility → then flip to the **Ministry dashboard** view.

---

## 8. Open decisions to confirm before Phase 0

1. **Sovereign-from-day-one** (Bhashini + open model — stronger optics, more setup) **vs hosted frontier model first** (faster to a working demo, swap later)?
2. Which **3–4 languages** to target?
3. **geo_locator**: live Places API vs curated mock dataset for the demo?
4. Hosting for the demo: laptop/Docker Compose vs a cloud VM for the live presentation?

---

## 9. Suggested repo structure

```
ai-saheli/
  apps/
    web/                 # Next.js chat UI + dashboard
    backend/             # FastAPI: /chat, /voice, /whatsapp-webhook
  agents/
    orchestrator/        # router + state + dynamic questioning
    poshan/  vatsalya/  shakti/
  mcp/
    knowledge_base/  eligibility/  geo_locator/  helplines/  profile_session/
  language/
    bhashini_client.py   # ASR / NMT / TTS wrapper (provider-swappable)
  rag/
    ingest.py            # offline ingestion pipeline
    data/                # official scheme docs
  guardrails/            # grounding + escalation + scope + PII
  infra/
    docker-compose.yml
  personas/              # synthetic demo profiles
```