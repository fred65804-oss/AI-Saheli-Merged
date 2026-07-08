"""Language layer — provider-agnostic, injectable, testable.

Everything that touches ASR/NMT/TTS goes through the ``LanguageProvider``
protocol, mirroring the ``StructuredLLM`` pattern in
``agents/orchestrator/llm.py``:

  - ``transcribe(...)`` → speech-to-text (base64 audio in, text out).
  - ``translate(...)``  → text between languages (2-letter ISO codes).
  - ``synthesize(...)`` → text-to-speech (base64 MP3 audio out).

Two implementations:
  - ``FreeProvider``          — ASR/NMT/TTS via faster-whisper + deep-translator
                                + edge-tts (zero keys, zero cost).
  - ``FakeLanguageProvider``  — scripted/passthrough values for deterministic
                                offline tests (no network, no deps).

The provider is injected at startup via ``get_language_provider()`` and stored
on ``app.state.language``; endpoint handlers never import a concrete class.
"""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable

# Canonical supported-language registry — the single source the API and web UI
# read from (never hardcode language lists downstream). Codes are 2-letter ISO;
# ``native`` is the endonym shown to citizens.
LANGUAGES: list[dict[str, str]] = [
    {"code": "en", "name": "English", "native": "English"},
    {"code": "hi", "name": "Hindi", "native": "हिन्दी"},
    {"code": "bn", "name": "Bengali", "native": "বাংলা"},
    {"code": "ta", "name": "Tamil", "native": "தமிழ்"},
    {"code": "te", "name": "Telugu", "native": "తెలుగు"},
    {"code": "mr", "name": "Marathi", "native": "मराठी"},
    {"code": "gu", "name": "Gujarati", "native": "ગુજરાતી"},
    {"code": "kn", "name": "Kannada", "native": "ಕನ್ನಡ"},
    {"code": "ml", "name": "Malayalam", "native": "മലയാളം"},
    {"code": "pa", "name": "Punjabi", "native": "ਪੰਜਾਬੀ"},
    {"code": "ur", "name": "Urdu", "native": "اردو"},
]


@runtime_checkable
class LanguageProvider(Protocol):
    """The only ASR/NMT/TTS surface the app depends on."""

    async def transcribe(self, audio_base64: str, lang: str) -> str:
        """Return the transcript of base64 audio spoken in ``lang``."""
        ...

    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Return ``text`` translated from ``source_lang`` to ``target_lang``."""
        ...

    async def synthesize(self, text: str, lang: str, gender: str = "female") -> str:
        """Return base64 MP3 audio of ``text`` spoken in ``lang``."""
        ...


# --------------------------------------------------------------------------- #
# Test double / offline fallback
# --------------------------------------------------------------------------- #
TranscribeResponder = Callable[[str, str], str]
TranslateResponder = Callable[[str, str, str], str]
SynthesizeResponder = Callable[[str, str], str]


class FakeLanguageProvider:
    """Scripted LanguageProvider for deterministic tests / offline mode.

    Defaults: ``translate`` is a passthrough (text returned unchanged),
    ``transcribe`` returns a canned string, ``synthesize`` returns "".
    Optional scripted responders override each method individually.
    """

    def __init__(
        self,
        transcribe_responder: TranscribeResponder | None = None,
        translate_responder: TranslateResponder | None = None,
        synthesize_responder: SynthesizeResponder | None = None,
    ) -> None:
        self._transcribe = transcribe_responder
        self._translate = translate_responder
        self._synthesize = synthesize_responder

    async def transcribe(self, audio_base64: str, lang: str) -> str:
        if self._transcribe is not None:
            return self._transcribe(audio_base64, lang)
        return "(offline transcript)"

    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if self._translate is not None:
            return self._translate(text, source_lang, target_lang)
        return text  # passthrough — behaves as English-only

    async def synthesize(self, text: str, lang: str, gender: str = "female") -> str:
        if self._synthesize is not None:
            return self._synthesize(text, lang)
        return ""


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
def get_language_provider() -> LanguageProvider:
    """Return the best available provider.

    Priority:
      1. FreeProvider  — when faster-whisper + deep-translator + edge-tts are
                         installed (``pip install faster-whisper deep-translator edge-tts``).
      2. FakeLanguageProvider — offline passthrough (tests, CI, missing deps).

    Tests bypass this factory entirely by injecting FakeLanguageProvider directly.
    """
    try:
        import deep_translator  # noqa: F401
        import edge_tts          # noqa: F401
        from language.free_provider import FreeProvider
        return FreeProvider()
    except ImportError:
        return FakeLanguageProvider()
