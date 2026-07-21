"""Shared one-turn execution: translate-in -> orchestrator -> translate-out.

Extracted from main.py so /chat, /voice, and the WhatsApp webhook all run the
exact same pipeline instead of each re-implementing translation + timing.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, Field

from agents.orchestrator.graph import run_turn
from language.provider import LanguageProvider


class PipelineTimings(BaseModel):
    asr_ms: float = 0.0
    translation_in_ms: float = 0.0
    orchestrator_ms: float = 0.0
    translation_out_ms: float = 0.0
    tts_ms: float = 0.0
    total_request_ms: float = 0.0


def has_non_ascii(text: str) -> bool:
    """True when the message contains non-ASCII characters (Devanagari, Tamil, etc.).

    Romanized / Hinglish input is pure ASCII and should pass straight to the
    orchestrator so the safety lexicon can match known danger phrases directly.
    """
    return any(ord(c) > 127 for c in text)


async def translated_turn(
    provider: LanguageProvider,
    graph,
    *,
    session_id: str,
    message: str,
    channel: str,
    lang: str,
) -> tuple[dict, str, bool, PipelineTimings]:
    """Run one orchestrator turn wrapped in translate-in / translate-out.

    Returns ``(state, localized_response, degraded, timings)``. Any translation
    failure degrades to English passthrough rather than erroring — a channel
    must never hard-fail because translation hiccuped. Safety normally runs on
    the English translation; in degraded mode the original text still hits the
    safety lexicon (which covers Hindi/Devanagari terms), but for other
    languages coverage falls back to the L2 LLM classifier alone.
    """
    timings = PipelineTimings()
    english_in, degraded = message, False
    if lang != "en" and has_non_ascii(message):
        started = time.perf_counter()
        try:
            english_in = await provider.translate(message, lang, "en")
        except Exception:
            degraded = True
        finally:
            timings.translation_in_ms = round((time.perf_counter() - started) * 1000, 2)

    started = time.perf_counter()
    state = await run_turn(graph, session_id=session_id, message=english_in, channel=channel, lang=lang)
    timings.orchestrator_ms = round((time.perf_counter() - started) * 1000, 2)

    localized = state.get("response", "")

    if lang != "en" and not degraded and localized:
        started = time.perf_counter()
        try:
            localized = await provider.translate(localized, "en", lang)
        except Exception:
            degraded = True
        finally:
            timings.translation_out_ms = round((time.perf_counter() - started) * 1000, 2)

    return state, localized, degraded, timings
