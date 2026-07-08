"""FastAPI app — the orchestrator's HTTP surface.

POST /chat   one conversational turn (session_id threads multi-turn state).
POST /voice  one voice turn: audio → ASR → orchestrator → NMT → TTS → audio.
GET  /health liveness + which LLM / language provider is active.

The compiled graph is built once at startup (default dependencies). State is
carried across turns by the in-memory checkpointer keyed by session_id.

The language layer wraps the orchestrator (which reasons in English only):
inbound messages are translated to English before the graph runs, and the
response — whatever path produced it (specialist answer, slot question,
clarification, or escalation template) — is translated back to the user's
language afterwards.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

# Windows/httpx workaround — uvicorn defaults to ProactorEventLoop on Windows,
# and httpx's async TLS transport intermittently stalls under it (the pool
# awaits a response that never arrives and only surfaces on outer cancellation
# — see https://github.com/encode/httpx/issues/2244). SelectorEventLoop is the
# code path Microsoft maintains for async socket I/O and doesn't exhibit the
# hang. Must be set BEFORE uvicorn spins up its loop, which is why this lives
# at module import time, not in lifespan().
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ai-saheli")

from agents.orchestrator.graph import default_orchestrator, run_turn
from agents.orchestrator.llm import get_llm
from apps.backend.config import get_settings
from apps.backend.dashboard import router as dashboard_router
from language.provider import LanguageProvider, get_language_provider
from mcp.knowledge_base.schemas import KBQueryRequest
from mcp.knowledge_base.tool import query_knowledge_base


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    channel: str = "web"
    lang: str = "en"


class Citation(BaseModel):
    source_doc: str
    source_url: str = ""
    section: str | None = None


class ChatResponse(BaseModel):
    response: str
    response_en: str = ""
    intent: str | None = None
    confidence: float | None = None
    escalation: bool = False
    awaiting_input: bool = False
    citations: list[Citation] = []
    trace_id: str = ""
    degraded_translation: bool = False


class VoiceRequest(BaseModel):
    session_id: str = Field(min_length=1)
    audio_base64: str = Field(min_length=1)  # WAV/MP3 — faster-whisper auto-detects format
    lang: str = "hi"
    channel: str = "voice"


class VoiceResponse(BaseModel):
    transcript: str
    response: str
    response_en: str = ""
    audio_base64: str = ""  # TTS of the localized answer; empty when TTS failed
    intent: str | None = None
    confidence: float | None = None
    escalation: bool = False
    awaiting_input: bool = False
    citations: list[Citation] = []
    trace_id: str = ""
    degraded: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.graph = default_orchestrator()
    app.state.language = get_language_provider()
    # We do NOT warm the KB automatically at startup: the retriever runs the
    # reranker synchronously on the calling coroutine's thread (see
    # mcp/knowledge_base/tool.py — asyncio.to_thread was banned due to a
    # Windows PyTorch/OpenMP crash). Running it during lifespan blocks the
    # event loop and prevents uvicorn from ever finishing startup. Hit
    # POST /warmup once before the demo instead.
    log.info("AI Saheli backend ready. Call POST /warmup once before demo to preload the reranker.")
    yield


app = FastAPI(title="AI Saheli — Orchestrator", version="1.0", lifespan=lifespan)

# CORS — the static web UI is served by this same process, so browsers hit
# /chat, /voice, and dashboard endpoints same-origin. Wide-open here for demo
# convenience (curl/other hosts); lock down origins before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard_router)


def _has_non_ascii(text: str) -> bool:
    """True when the message contains non-ASCII characters (Devanagari, Tamil, etc.).

    Romanized / Hinglish input is pure ASCII and should pass straight to the
    orchestrator so the safety lexicon can match known danger phrases directly.
    """
    return any(ord(c) > 127 for c in text)


async def _translated_turn(
    provider: LanguageProvider,
    graph,
    *,
    session_id: str,
    message: str,
    channel: str,
    lang: str,
) -> tuple[dict, str, bool]:
    """Run one orchestrator turn wrapped in translate-in / translate-out.

    Returns ``(state, localized_response, degraded)``. Any translation failure
    degrades to English passthrough rather than erroring — the demo must never
    500 because translation hiccuped. Safety normally runs on the English
    translation; in degraded mode the original text still hits the safety
    lexicon (which covers Hindi/Devanagari terms), but for other languages
    coverage falls back to the L2 LLM classifier alone.
    """
    english_in, degraded = message, False
    if lang != "en" and _has_non_ascii(message):
        # Only translate when the message actually contains non-ASCII characters
        # (i.e. Devanagari, Tamil, etc.). Romanized/Hinglish input should pass
        # through as-is so the safety lexicon can match it directly in English.
        try:
            english_in = await provider.translate(message, lang, "en")
        except Exception:
            degraded = True

    state = await run_turn(
        graph, session_id=session_id, message=english_in, channel=channel, lang=lang
    )

    localized = state.get("response", "")
    if lang != "en" and not degraded and localized:
        try:
            localized = await provider.translate(localized, "en", lang)
        except Exception:
            degraded = True

    return state, localized, degraded


@app.post("/warmup")
async def warmup() -> dict:
    """Preload the KB reranker + embedder AND pay the first-LLM-call tax.

    This will BLOCK the event loop for ~30-90s while models load — that is
    intentional (see note in lifespan). Subsequent /chat calls are fast.

    Two things get warmed here:
    1. KB retriever — embedder + reranker forward pass on a real query.
    2. LLM SDK — the openai package runs a synchronous ``platform.uname()``
       probe on the first request from any process, which on Windows 11
       shells out to the deprecated ``wmic`` and can hang 30-60s (long
       enough to blow the specialist handoff budget). Firing one throwaway
       completion here forces that probe to run inside warmup, not inside
       the first citizen chat.
    """
    import time
    start = time.perf_counter()
    result: dict = {"status": "warm"}
    try:
        r = await query_knowledge_base(KBQueryRequest(query="warmup", k=1))
        result["kb_chunks_returned"] = len(r.chunks)
    except Exception as e:
        result["kb_error"] = str(e)

    # LLM ping — both fast (router/safety) and main (synthesis) clients.
    # They're separate cached instances inside StructuredLLM, so each has to
    # pay its own openai-SDK first-call platform-probe tax; hitting only one
    # left the synthesis client cold and the first real chat still hung.
    if get_settings().has_llm_key:
        llm = get_llm()
        for fast in (True, False):
            key = "llm_fast" if fast else "llm_main"
            try:
                await llm.complete(
                    "You are a warmup probe.", "Reply with: ok", fast=fast
                )
                result[key] = "ready"
            except Exception as e:
                result[f"{key}_error"] = str(e)
    else:
        result["llm"] = "offline"

    result["took_ms"] = round((time.perf_counter() - start) * 1000, 1)
    return result


@app.get("/health")
async def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "llm": "live" if s.has_llm_key else "offline (keyword + lexicon only)",
        "provider": s.resolved_provider,
        "model": s.resolved_model,
        "language": type(app.state.language).__name__,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    state, localized, degraded = await _translated_turn(
        app.state.language,
        app.state.graph,
        session_id=req.session_id,
        message=req.message,
        channel=req.channel,
        lang=req.lang,
    )
    return ChatResponse(
        response=localized,
        response_en=state.get("response", ""),
        intent=state.get("intent"),
        confidence=state.get("confidence"),
        escalation=bool(state.get("escalation")),
        awaiting_input=bool(state.get("awaiting_input")),
        citations=[Citation(**c) for c in state.get("citations", [])],
        trace_id=state.get("trace_id", ""),
        degraded_translation=degraded,
    )


@app.post("/voice", response_model=VoiceResponse)
async def voice(req: VoiceRequest) -> VoiceResponse:
    provider: LanguageProvider = app.state.language

    # Without a transcript there is nothing to degrade to — fail loudly.
    try:
        transcript = await provider.transcribe(req.audio_base64, req.lang)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Speech recognition failed: {e}")

    # A silent/garbled clip (or the wrong language selected) produces an empty
    # transcript. Running the orchestrator on "" used to silently return the
    # generic "could you tell me more" clarify prompt — indistinguishable from
    # a real misunderstanding. Fail loudly instead so the citizen knows to
    # re-record rather than getting a confusing non-answer.
    if not transcript.strip():
        raise HTTPException(
            status_code=422,
            detail="Could not hear any speech in that recording. Please check "
            "your microphone, make sure the selected language matches what "
            "you're speaking, and try again.",
        )

    state, localized, degraded = await _translated_turn(
        provider,
        app.state.graph,
        session_id=req.session_id,
        message=transcript,
        channel=req.channel,
        lang=req.lang,
    )

    # TTS failure degrades to text-only — the localized answer still goes back.
    audio_out = ""
    if localized:
        try:
            audio_out = await provider.synthesize(localized, req.lang)
        except Exception:
            degraded = True

    return VoiceResponse(
        transcript=transcript,
        response=localized,
        response_en=state.get("response", ""),
        audio_base64=audio_out,
        intent=state.get("intent"),
        confidence=state.get("confidence"),
        escalation=bool(state.get("escalation")),
        awaiting_input=bool(state.get("awaiting_input")),
        citations=[Citation(**c) for c in state.get("citations", [])],
        trace_id=state.get("trace_id", ""),
        degraded=degraded,
    )


