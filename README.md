# AI Saheli — Orchestrator

Agentic AI assistant for India's Ministry of Women & Child Development (MWCD).
Covers **Poshan**, **Mission Vatsalya**, and **Mission Shakti**. This repo currently
contains the **orchestrator** (Phase 1, core engine): it runs safety, intent routing,
dynamic questioning, and specialist handoff.

> Project docs live in [`.claude/`](.claude/CLAUDE.md). Orchestrator build details:
> [`.claude/dev/orchestrator-build.md`](.claude/dev/orchestrator-build.md).

## Quickstart
```bash
pip install -r requirements.txt
cp .env.example .env            # add an LLM key (Azure/Anthropic/OpenAI) for live synthesis (optional)

pytest                          # 79 tests, no API key required (stop the backend first — local Qdrant is single-writer)
python eval/run_routing_eval.py # routing accuracy + escalation recall
python scripts/chat_cli.py      # interactive terminal demo
uvicorn apps.backend.main:app --reload   # REST API on http://127.0.0.1:8000
```

**Demo day (full web app, one command):**
```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1
# backend :8000 → wait for /health → POST /warmup (KB + LLM + ASR + TTS)
# → Next.js web app on http://localhost:3000
```

## What's built
- **Layered safety gate** (keyword lexicon + LLM classifier) — non-bypassable, runs first.
- **Capability-card routing** — declarative; add a scheme without touching prompts/graph.
- **Deterministic dynamic questioning** — slot-filling; the LLM only phrases questions.
- **Specialist contract** (`agents/specialists/base.py`) + **mock specialists** — the
  integration boundary a colleague builds the real agents against.
- **Audit trace** — one structured JSONL record per turn (`logs/interactions.jsonl`).

Runs fully **offline** (keyword routing + lexicon safety) without an API key; set
`ANTHROPIC_API_KEY` to enable LLM routing and the L2 safety classifier.

## API
`POST /chat` — `{session_id, message, channel?, lang?}` →
`{response, intent, confidence, escalation, awaiting_input, citations, trace_id}`
`GET /health`
