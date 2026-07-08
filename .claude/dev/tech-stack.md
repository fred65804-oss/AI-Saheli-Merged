# Technology Stack — AI Saheli

## Stack Decision Summary

| Layer | Demo Choice | Production/Sovereign | Rationale |
|---|---|---|---|
| **LLM** | Multi-provider: Anthropic (claude-sonnet-4-6) or OpenAI (gpt-4.1), `LLM_PROVIDER=auto` picks whichever key is set | Sarvam-M or Llama-Indic on-prem | Best multilingual reasoning + tool use for demo; sovereign model for production |
| **Orchestration** | LangGraph (Python) | Same | Supervisor pattern, stateful graphs, native tool calling, well-tested |
| **Backend** | FastAPI (async Python) | Same on NIC MeghRaj | Async, WebSocket support, Pydantic validation, easy Docker |
| **Frontend** | Self-contained static app (HTML/JS/CSS) served by FastAPI at `/` — no Node/build step | Next.js 14+ + Tailwind | Demo machine has no Node; one server = fewer demo-day moving parts. UI is 100% API-driven (see `/meta`) |
| **Language (ASR/NMT/TTS)** | FreeProvider: faster-whisper + deep-translator + edge-tts | Bhashini/VoicERA self-hosted | Zero keys, zero cost for demo; sovereign stack for production |
| **Vector DB** | Qdrant (local persistent, on-disk) | Qdrant clustered | Fast, Docker-friendly, hybrid search (dense+sparse), good Python SDK |
| **Embeddings** | `intfloat/multilingual-e5-base` (dense) + `Qdrant/bm25` (sparse) | Same or Indic fine-tuned | Hybrid dense+BM25 hits recall@6=1.00 on this corpus |
| **Reranker** | `BAAI/bge-reranker-v2-m3` | Same | Cross-encoder rerank, MRR 0.933 on gold set |
| **Session Store** | In-memory MemorySaver (LangGraph) | Redis | Simple for demo; Redis for production persistence |
| **Database** | JSONL trace log (flat file) | PostgreSQL | Trace written to `logs/interactions.jsonl`; Postgres-ready interface |
| **Analytics Dashboard** | ✅ Built — hand-rolled SVG charts in the static web UI, fed by `/analytics/*` over `logs/interactions.jsonl` | Metabase / Superset | In same repo for demo; dedicated BI for production |
| **WhatsApp** | WhatsApp Cloud API (Meta) — not yet built | Same | Official API, 1,000 conversations/month free |
| **Infrastructure** | Docker Compose | Kubernetes (k8s) | Simple for demo; scalable for production |
| **MCP Tools** | Python modules (direct import) | MCP protocol server | 4 tools built: knowledge_base, helpline_directory, geo_locator, eligibility |

---

## What's built vs what's planned

| Component | Status |
|---|---|
| Orchestrator (LangGraph) | ✅ Built & tested |
| Safety gate (L1 lexicon + L2 LLM) | ✅ Built |
| RAG pipeline (PDF → chunks → Qdrant) | ✅ Built (2,579 points, 23 PDFs) |
| MCP: knowledge_base | ✅ Built |
| MCP: helpline_directory | ✅ Built |
| MCP: geo_locator | ✅ Built (mock dataset: Varanasi/Madurai/Delhi/Lucknow) |
| MCP: eligibility | ✅ Built (PMMVY, THR, SNP, SAAN, Sponsorship rules) |
| Language layer (ASR/NMT/TTS) | ✅ Built (FreeProvider) |
| FastAPI `/chat` + `/voice` | ✅ Built |
| Real specialist agents (Poshan/Vatsalya/Shakti/General) | ✅ Built — MCP tools for verified facts + KB retrieval, LLM synthesis with deterministic offline fallback |
| Multi-provider LLM (Anthropic + OpenAI) | ✅ Built (`LLM_PROVIDER=auto`) |
| WhatsApp webhook (`/whatsapp-webhook`) | ❌ Not built |
| Web UI (chat + voice + tools + system) | ✅ Built (`apps/web/static`, FastAPI-served, zero hardcoding — all data from `/meta` & friends) |
| Analytics dashboard | ✅ Built (KPI tiles, scheme/language/tool/district charts, timeline, live feed) |
| Dashboard/tools API (`/meta`, `/helplines`, `/tools/*`, `/analytics/*`) | ✅ Built (`apps/backend/dashboard.py`) |
| Redis/Postgres persistence | ❌ Not built (in-memory for demo) |

---

## Python Dependencies (Backend)
```
# Core
fastapi>=0.111
uvicorn[standard]
pydantic>=2.0
python-dotenv

# Agents & Orchestration
langgraph>=0.2
langchain-anthropic
langchain-openai
langchain-core

# Language layer (FreeProvider)
faster-whisper        # ASR — local Whisper, CPU, great Hindi
deep-translator       # NMT — Google Translate free endpoint
edge-tts              # TTS — Microsoft Edge Neural voices

# RAG
qdrant-client
sentence-transformers  # multilingual-e5-base + bge-reranker-v2-m3
fastembed              # BM25 sparse embeddings
pypdfium2              # PDF rendering for OCR pipeline
rapidocr-onnxruntime   # OCR for scanned PDFs
wordninja              # space repair for OCR output
msvc-runtime           # Windows: ships MSVC DLLs for onnxruntime

# Utils
pyyaml                # helpline_directory YAML loader
httpx                 # async HTTP (WhatsApp Cloud API later)
```

---

## Language Layer Detail

### FreeProvider (current — zero keys, zero cost)
| Capability | Library | Notes |
|---|---|---|
| ASR (speech→text) | `faster-whisper` | Runs Whisper locally on CPU. ~150 MB model, downloads once. Excellent Hindi. |
| NMT (translation) | `deep-translator` | Google Translate free endpoint. No key. All 22 Indian languages. |
| TTS (text→speech) | `edge-tts` | Microsoft Edge Neural TTS. No key. Near-human quality. |

**Languages supported:** hi, bn, ta, te, mr, gu, kn, ml, pa, ur, en (all with dedicated Neural voices)

**Fallback:** If packages missing → `FakeLanguageProvider` (English passthrough). App never crashes.

### Production path (sovereign)
Bhashini/VoicERA — swap in by implementing `LanguageProvider` protocol in `language/bhashini_provider.py`.
No other code changes needed — provider is injected at startup.

---

## RAG Stack Detail

### Embedding & Retrieval
- **Dense:** `intfloat/multilingual-e5-base` (768-d, cosine). Prefixed `"passage:"` on ingest, `"query:"` on search.
- **Sparse:** `Qdrant/bm25` via fastembed. IDF-weighted keyword matching.
- **Fusion:** Qdrant RRF (Reciprocal Rank Fusion) of dense + sparse prefetch queries.
- **Reranker:** `BAAI/bge-reranker-v2-m3` cross-encoder. Top-50 prefetch → reranked → top-6 returned.
- **Filter:** every query is scheme-scoped (poshan / vatsalya / shakti) via Qdrant payload filter.

### Eval results (15 gold questions, k=6)
| Config | recall@k | MRR |
|---|---|---|
| dense-only | 0.93 | 0.778 |
| hybrid (dense+BM25) | 1.00 | 0.900 |
| hybrid + rerank | 1.00 | **0.933** |

### Corpus
- 23 official PDFs across 3 schemes → 2,579 chunks in `rag/qdrant_db/saheli_kb`
- Poshan: 251 chunks | Shakti: 474 chunks | Vatsalya: 1,854 chunks
- PDF chunker: `pdf_chunker/` — hybrid auto-detect (text vs OCR), heading cascade, semantic chunks with `heading_path`

---

## MCP Tool Layer Detail

All tools are **pure Python async functions** — no network, no LLM, fully deterministic.

### `knowledge_base` (`mcp/knowledge_base/tool.py`)
Input: `{query, scheme, k=5}` → Output: `{chunks: [{text, citation, score}]}`
Wraps `rag/retrieve.py`. Warms embedding + reranker models at startup.

### `helpline_directory` (`mcp/helpline_directory/tool.py`)
Input: `{category, scheme?, lang?}` → Output: `{primary: HelplineEntry, secondary: [], escalation_note}`
Data: `mcp/helpline_directory/data/helplines.yaml` (1098, 181, 112, 15100, ANM referral). Each entry now carries a
human-facing `name` (e.g. "Women Helpline") used both by specialists and by the guardrail escalation template —
this is the single source of truth for helpline numbers; nothing is hardcoded elsewhere.
Fails fast on boot if any category lacks coverage.

### `geo_locator` (`mcp/geo_locator/tool.py`)
Input: `{district, state?, service_type, limit=3}` → Output: `{facilities: [Facility], note?}`
Data: `mcp/geo_locator/data/facilities.json` — mock dataset for Varanasi, Madurai, Delhi, Lucknow.
Service types: AWC, OSC, DCPU, CWC. Graceful miss (empty + note) for out-of-scope districts.

### `eligibility` (`mcp/eligibility/tool.py`)
Input: `EligibilityRequest` (beneficiary_type, age, income_band, child_order, pregnancy_week, etc.)
Output: `{eligible: [], ineligible: [], uncertain: []}` — uncertain = missing facts → triggers slot-filling
Rules: PMMVY, THR, SNP, SAAN, Sponsorship, Foster Care — pure Python if/else, sourced from official scheme docs.

---

## Key Environment Variables
```bash
# LLM — provider resolved automatically from whichever key is set
LLM_PROVIDER=auto           # auto | anthropic | openai
LLM_MODEL=                  # optional override; else provider default (see config.py)
LLM_FAST_MODEL=             # optional override for router/safety hot path
ANTHROPIC_API_KEY=          # optional; offline mode works without it
OPENAI_API_KEY=             # optional; offline mode works without it

# WhatsApp (not built yet)
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_VERIFY_TOKEN=

# Future persistence
POSTGRES_URL=postgresql+asyncpg://...
REDIS_URL=redis://localhost:6379

# Qdrant (local mode — no URL needed)
# DB_PATH = "rag/qdrant_db"  (hardcoded in rag/index.py)
```

---

## Why LangGraph
| Framework | Why Not |
|---|---|
| LangChain (chains) | Linear chains can't handle dynamic routing or conditional handoffs cleanly |
| AutoGen | Microsoft stack, more suited to code-generation tasks |
| CrewAI | Role-based task assignment, less control over state machine |
| **LangGraph** | ✅ Explicit state graph, conditional edges, supervisor pattern, streaming, stateful conversations |

---

## Docker Compose Services (Target — not yet built)
```yaml
services:
  backend:     # FastAPI
  web:         # Next.js
  redis:       # Session store (replaces MemorySaver)
  postgres:    # Relational DB + interaction logs
  # Qdrant runs local on-disk — no Docker needed for demo
```
