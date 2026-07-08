"""Zero-key language provider — free services, no account needed.

Stack:
  ASR  : faster-whisper  (local OpenAI Whisper, CPU-friendly, great Hindi)
  NMT  : deep-translator (Google Translate free endpoint, all Indian languages)
  TTS  : edge-tts        (Microsoft Edge TTS, near-human Hindi voices, no key)

Install:
    pip install faster-whisper deep-translator edge-tts

Voice used for Hindi TTS: hi-IN-SwaraNeural (female, natural quality).
For male voice swap to: hi-IN-MadhurNeural
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
import tempfile

# Language code → Edge TTS voice name (female default)
_EDGE_VOICES: dict[str, str] = {
    "hi": "hi-IN-SwaraNeural",
    "bn": "bn-IN-TanishaaNeural",
    "ta": "ta-IN-PallaviNeural",
    "te": "te-IN-ShrutiNeural",
    "mr": "mr-IN-AarohiNeural",
    "gu": "gu-IN-DhwaniNeural",
    "kn": "kn-IN-SapnaNeural",
    "ml": "ml-IN-SobhanaNeural",
    "pa": "pa-IN-OjasNeural",
    "ur": "ur-IN-GulNeural",
    "en": "en-IN-NeerjaNeural",
}
_DEFAULT_VOICE = "hi-IN-SwaraNeural"


class FreeProvider:
    """ASR + NMT + TTS using entirely free, key-less libraries."""

    async def transcribe(self, audio_base64: str, lang: str) -> str:
        """ASR via faster-whisper (runs locally, first call downloads ~150 MB model)."""
        from faster_whisper import WhisperModel

        try:
            audio_bytes = base64.b64decode(audio_base64)
        except Exception:
            raise ValueError("audio_base64 is not valid base64 — encode your audio file first")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        def _run() -> str:
            # "base" balances speed/accuracy well on CPU; set compute_type="float32"
            # if int8 causes issues on your CPU.
            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, _ = model.transcribe(
                tmp_path,
                language=lang if lang != "en" else None,
            )
            return " ".join(seg.text for seg in segments).strip()

        try:
            return await asyncio.to_thread(_run)
        finally:
            os.unlink(tmp_path)

    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """NMT via deep-translator (Google Translate, no key, all Indian languages)."""
        if source_lang == target_lang:
            return text
        from deep_translator import GoogleTranslator

        def _run() -> str:
            return GoogleTranslator(source=source_lang, target=target_lang).translate(text)

        return await asyncio.to_thread(_run)

    async def synthesize(self, text: str, lang: str, gender: str = "female") -> str:
        """TTS via edge-tts (Microsoft Edge voices, near-human quality, no key).

        Returns base64-encoded MP3 audio.
        """
        import edge_tts

        voice = _EDGE_VOICES.get(lang.lower(), _DEFAULT_VOICE)
        if gender == "male":
            # Swap to male variants where available
            voice = voice.replace("SwaraNeural", "MadhurNeural") \
                         .replace("TanishaaNeural", "BashkarNeural") \
                         .replace("PallaviNeural", "ValluvarNeural") \
                         .replace("ShrutiNeural", "MohanNeural") \
                         .replace("NeerjaNeural", "PrabhatNeural")

        communicate = edge_tts.Communicate(text=text, voice=voice)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        return base64.b64encode(buf.getvalue()).decode()
