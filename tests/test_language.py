"""Language layer tests — provider selection, /chat and /voice seams. Offline."""

import pytest
from fastapi.testclient import TestClient

from agents.orchestrator.graph import build_orchestrator
from agents.orchestrator.llm import FakeLLM
from agents.orchestrator.trace import NullTraceSink
from apps.backend.config import get_settings
from apps.backend.main import app
from language.provider import (
    FakeLanguageProvider,
    LanguageProvider,
    get_language_provider,
)


def _graph():
    return build_orchestrator(
        llm=FakeLLM(), settings=get_settings(), sink=NullTraceSink()
    )


def _client(provider) -> TestClient:
    # Lifespan is intentionally not run (no `with` block) — inject deps directly.
    app.state.graph = _graph()
    app.state.language = provider
    return TestClient(app)


class CountingProvider(FakeLanguageProvider):
    """Fake that tags translations and counts calls, to prove the seam fires."""

    def __init__(self):
        super().__init__()
        self.translate_calls = 0

    async def translate(self, text, source_lang, target_lang):
        self.translate_calls += 1
        return f"[{target_lang}]{text}"


class FailingTranslateProvider(FakeLanguageProvider):
    async def translate(self, text, source_lang, target_lang):
        raise RuntimeError("translation service down")


# --------------------------------------------------------------------------- #
# Factory + fake provider
# --------------------------------------------------------------------------- #
def test_factory_returns_a_provider():
    # Factory returns FreeProvider when deps installed, else FakeLanguageProvider.
    # Either way it must satisfy the protocol.
    p = get_language_provider()
    assert isinstance(p, LanguageProvider)


def test_fake_provider_conforms_to_protocol():
    assert isinstance(FakeLanguageProvider(), LanguageProvider)


@pytest.mark.asyncio
async def test_fake_provider_defaults_are_passthrough():
    p = FakeLanguageProvider()
    assert await p.translate("hello", "hi", "en") == "hello"
    assert await p.synthesize("hello", "hi") == ""
    assert await p.transcribe("QUJD", "hi")  # non-empty canned transcript


@pytest.mark.asyncio
async def test_fake_provider_scripted_responders():
    p = FakeLanguageProvider(
        transcribe_responder=lambda audio, lang: f"heard:{lang}",
        translate_responder=lambda text, s, t: f"{s}->{t}:{text}",
        synthesize_responder=lambda text, lang: "AUDIO64",
    )
    assert await p.transcribe("x", "hi") == "heard:hi"
    assert await p.translate("namaste", "hi", "en") == "hi->en:namaste"
    assert await p.synthesize("hello", "hi") == "AUDIO64"


# --------------------------------------------------------------------------- #
# /chat seam
# --------------------------------------------------------------------------- #
def test_chat_english_never_calls_translator():
    provider = CountingProvider()
    client = _client(provider)
    r = client.post(
        "/chat",
        json={"session_id": "en1", "message": "am i eligible for pmmvy", "lang": "en"},
    )
    assert r.status_code == 200
    assert provider.translate_calls == 0
    assert r.json()["degraded_translation"] is False


def test_chat_hindi_translates_in_and_out():
    provider = CountingProvider()
    client = _client(provider)
    # Use Devanagari so the non-ASCII guard triggers translation
    r = client.post(
        "/chat",
        json={"session_id": "hi1", "message": "मैं पीएमएमवीवाई के लिए पात्र हूं?", "lang": "hi"},
    )
    assert r.status_code == 200
    body = r.json()
    assert provider.translate_calls == 2  # in (hi->en) and out (en->hi)
    assert body["response"].startswith("[hi]")
    assert body["response_en"] and not body["response_en"].startswith("[")
    assert body["degraded_translation"] is False


def test_chat_translator_failure_degrades_to_english():
    client = _client(FailingTranslateProvider())
    r = client.post(
        "/chat",
        json={"session_id": "hi2", "message": "am i eligible for pmmvy", "lang": "hi"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["degraded_translation"] is True
    assert body["response"] == body["response_en"]  # English passthrough


def test_chat_escalation_template_is_translated():
    """Escalation/helpline responses surface via state['response'] too — the
    seam must localize them like any other path."""
    provider = CountingProvider()
    client = _client(provider)
    r = client.post(
        "/chat",
        json={
            "session_id": "esc1",
            "message": "mera pati mujhe maar raha hai",
            "lang": "hi",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["escalation"] is True
    assert body["response"].startswith("[hi]")
    assert "181" in body["response"]


# --------------------------------------------------------------------------- #
# /voice endpoint
# --------------------------------------------------------------------------- #
def test_voice_full_pipeline_shape():
    provider = FakeLanguageProvider(
        transcribe_responder=lambda audio, lang: "am i eligible for pmmvy",
        translate_responder=lambda text, s, t: f"[{t}]{text}",
        synthesize_responder=lambda text, lang: "BASE64AUDIO",
    )
    client = _client(provider)
    r = client.post(
        "/voice",
        json={"session_id": "v1", "audio_base64": "QUJD", "lang": "hi"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["transcript"] == "am i eligible for pmmvy"
    assert body["response"].startswith("[hi]")
    assert body["response_en"]
    assert body["audio_base64"] == "BASE64AUDIO"
    assert body["degraded"] is False
    assert body["trace_id"]


def test_voice_asr_failure_returns_422():
    def _boom(audio, lang):
        raise RuntimeError("asr unavailable")

    client = _client(FakeLanguageProvider(transcribe_responder=_boom))
    r = client.post(
        "/voice",
        json={"session_id": "v2", "audio_base64": "QUJD", "lang": "hi"},
    )
    assert r.status_code == 422


def test_voice_tts_failure_degrades_to_text_only():
    def _boom(text, lang):
        raise RuntimeError("tts unavailable")

    provider = FakeLanguageProvider(
        transcribe_responder=lambda audio, lang: "am i eligible for pmmvy",
        translate_responder=lambda text, s, t: f"[{t}]{text}",
        synthesize_responder=_boom,
    )
    client = _client(provider)
    r = client.post(
        "/voice",
        json={"session_id": "v3", "audio_base64": "QUJD", "lang": "hi"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["audio_base64"] == ""
    assert body["degraded"] is True
    assert body["response"].startswith("[hi]")  # text answer still delivered
