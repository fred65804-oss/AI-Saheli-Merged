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
import threading

# faster-whisper model is expensive to construct (and the first-ever call
# downloads ~150 MB). Build it once per process and reuse — previously it was
# rebuilt on EVERY transcription, adding seconds to each voice turn.
_WHISPER_MODEL = None
_WHISPER_LOCK = threading.Lock()


def _get_whisper_model():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        with _WHISPER_LOCK:
            if _WHISPER_MODEL is None:
                from faster_whisper import WhisperModel

                # "small" is the floor for reliable Hindi/Indic transcription —
                # "base" garbles Devanagari badly enough to derail routing.
                # Override via WHISPER_MODEL_SIZE (e.g. "base" on a weak CPU,
                # "medium" when accuracy matters more than latency). Set
                # compute_type="float32" if int8 causes issues on your CPU.
                size = os.getenv("WHISPER_MODEL_SIZE", "small")
                _WHISPER_MODEL = WhisperModel(size, device="cpu", compute_type="int8")
    return _WHISPER_MODEL

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

# Script-anchoring prompts for ASR. whisper-base sometimes emits phonetically
# correct Hindi in Urdu script (same spoken language, wrong writing system);
# a short native-script initial_prompt anchors the decoder to the expected
# script so transcripts render correctly in the UI.
_ASR_PROMPTS: dict[str, str] = {
    "hi": "नमस्ते, यह हिन्दी में बातचीत है।",
    "bn": "নমস্কার, এটি বাংলা কথোপকথন।",
    "ta": "வணக்கம், இது தமிழ் உரையாடல்.",
    "te": "నమస్తే, ఇది తెలుగు సంభాషణ.",
    "mr": "नमस्कार, हे मराठी संभाषण आहे.",
    "gu": "નમસ્તે, આ ગુજરાતી વાતચીત છે.",
    "kn": "ನಮಸ್ತೆ, ಇದು ಕನ್ನಡ ಸಂಭಾಷಣೆ.",
    "ml": "നമസ്തേ, ഇത് മലയാളം സംഭാഷണമാണ്.",
    "pa": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਇਹ ਪੰਜਾਬੀ ਗੱਲਬਾਤ ਹੈ।",
    "ur": "السلام علیکم، یہ اردو گفتگو ہے۔",
}


import logging

_asr_log = logging.getLogger("ai-saheli.asr")


def _describe_wav(audio_bytes: bytes) -> str:
    """Best-effort WAV inspection: duration, peak, RMS. Never raises."""
    try:
        import wave as _wave

        with _wave.open(io.BytesIO(audio_bytes), "rb") as w:
            ch, sw, fr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            frames = w.readframes(n)
        if sw == 2:
            import array

            a = array.array("h")
            a.frombytes(frames)
            samples = list(a)
            if not samples:
                return f"WAV ch={ch} sr={fr} EMPTY (0 frames)"
            peak = max(abs(s) for s in samples) / 32768.0
            rms = (sum(s * s for s in samples) / len(samples)) ** 0.5 / 32768.0
            return (
                f"WAV ch={ch} sr={fr} dur={n/fr:.2f}s frames={n} "
                f"peak={peak:.4f} rms={rms:.4f}"
                + ("  <-- SILENT" if peak < 0.01 else "")
            )
        return f"WAV ch={ch} sw={sw} sr={fr} frames={n} (non-16bit)"
    except Exception as e:
        return f"not a WAV / unreadable ({type(e).__name__}: {e}); {len(audio_bytes)} bytes, head={audio_bytes[:12]!r}"


def _log_incoming_audio(audio_bytes: bytes, tmp_path: str, lang: str) -> None:
    if os.getenv("ASR_DEBUG"):
        _asr_log.info("ASR in [lang=%s] %d bytes | %s", lang, len(audio_bytes), _describe_wav(audio_bytes))


def _dump_failed_audio(audio_bytes: bytes) -> None:
    try:
        os.makedirs("logs", exist_ok=True)
        path = os.path.join("logs", "last_empty_asr.wav")
        with open(path, "wb") as f:
            f.write(audio_bytes)
        _asr_log.warning("Empty transcript — dumped incoming audio to %s for inspection", path)
    except Exception:
        pass


class FreeProvider:
    """ASR + NMT + TTS using entirely free, key-less libraries."""

    async def transcribe(self, audio_base64: str, lang: str) -> str:
        """ASR via faster-whisper (runs locally, first call downloads ~150 MB model)."""
        try:
            audio_bytes = base64.b64decode(audio_base64)
        except Exception:
            raise ValueError("audio_base64 is not valid base64 — encode your audio file first")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        def _run() -> str:
            _log_incoming_audio(audio_bytes, tmp_path, lang)  # ASR_DEBUG diagnostics
            model = _get_whisper_model()
            segments, _ = model.transcribe(
                tmp_path,
                language=lang if lang != "en" else None,
                initial_prompt=_ASR_PROMPTS.get(lang),
                vad_filter=True,  # trim leading/trailing silence from mic recordings
            )
            text = " ".join(seg.text for seg in segments).strip()
            if not text and os.getenv("ASR_DEBUG"):
                _dump_failed_audio(audio_bytes)
            return text

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
