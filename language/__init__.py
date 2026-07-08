"""Language layer — free ASR/NMT/TTS (faster-whisper + deep-translator + edge-tts)."""

from language.provider import (
    FakeLanguageProvider,
    LanguageProvider,
    get_language_provider,
)

__all__ = ["LanguageProvider", "FakeLanguageProvider", "get_language_provider"]
