"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  BookOpen,
  Baby,
  HeartHandshake,
  Send,
  ShieldAlert,
  Utensils,
  LoaderCircle,
  MessageCircle,
  Mic,
  Square,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  getMeta,
  postChat,
  postVoice,
  type ChatResponse,
  type Citation,
  type LanguageMeta,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type Turn =
  | { role: "user"; text: string; ts: number }
  | {
      role: "assistant";
      text: string;
      ts: number;
      intent: string | null;
      confidence: number | null;
      escalation: boolean;
      awaiting_input: boolean;
      citations: Citation[];
      trace_id: string;
    };

type ChatMode = "text" | "avatar";
// "processing" covers the full backend round trip: ASR → orchestrator → TTS.
type VoiceStatus = "ready" | "recording" | "processing" | "error";

// Fallback shown while /meta loads (or if it's unreachable) — English only,
// never the source of truth. The real list (all Indian languages the
// language layer supports) always comes from the backend.
const FALLBACK_LANGS: LanguageMeta[] = [{ code: "en", name: "English", native: "English" }];

const STARTERS = [
  {
    lang: "hi",
    title: "Nutrition during pregnancy",
    text: "Pregnancy mein kya khana chahiye?",
    icon: Utensils,
  },
  {
    lang: "en",
    title: "My child's growth",
    text: "My 14-month-old is not gaining weight — what should I do?",
    icon: Baby,
  },
  {
    lang: "en",
    title: "Safety and support",
    text: "I feel unsafe at home, where can I get help?",
    icon: ShieldAlert,
  },
  {
    lang: "en",
    title: "Maternity benefit (PMMVY)",
    text: "Am I eligible for PMMVY for my first child?",
    icon: HeartHandshake,
  },
];

const INTENT_STYLE: Record<string, string> = {
  poshan: "bg-emerald-50 text-emerald-700 border-emerald-200",
  vatsalya: "bg-sky-50 text-sky-700 border-sky-200",
  shakti: "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200",
  general: "bg-slate-50 text-slate-600 border-slate-200",
};

function newSessionId() {
  return `web-${Math.random().toString(36).slice(2, 10)}-${Date.now()}`;
}

function fmtTime(ts: number) {
  return new Date(ts).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

// Base64-encode the raw recorded blob as-is (webm/opus straight from
// MediaRecorder). The backend hands the bytes to faster-whisper, which
// decodes any container/codec via ffmpeg — so we do NOT decode, resample,
// or re-encode in the browser. That old client-side pipeline
// (decodeAudioData → OfflineAudioContext → manual WAV) was fragile and
// could emit silent audio on some browsers; sending the original recording
// is both simpler and what actually made speech reach Whisper.
async function blobToBase64(blob: Blob): Promise<string> {
  const dataUrl: string = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
  // strip the "data:audio/webm;base64," prefix
  return dataUrl.slice(dataUrl.indexOf(",") + 1);
}

export default function ChatPage() {
  const [mode, setMode] = useState<ChatMode>("text");
  const [sessionId, setSessionId] = useState<string>("");
  const [lang, setLang] = useState<string>("en");
  const [languages, setLanguages] = useState<LanguageMeta[]>(FALLBACK_LANGS);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [speakingTurnTs, setSpeakingTurnTs] = useState<number | null>(null);
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>("ready");
  const [voiceDetail, setVoiceDetail] = useState("Tap the microphone and start speaking");
  const scrollerRef = useRef<HTMLDivElement>(null);
  const replyAudioRef = useRef<HTMLAudioElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const captureContextRef = useRef<AudioContext | null>(null);
  const vadFrameRef = useRef<number | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const shouldAutoListenRef = useRef(false);
  const startRecordingRef = useRef<() => void>(() => undefined);

  useEffect(() => {
    setSessionId(newSessionId());
  }, []);

  useEffect(() => {
    getMeta()
      .then((m) => setLanguages(m.languages))
      .catch(() => {
        /* keep the English-only fallback — chat still works, just without the full picker */
      });
  }, []);

  useEffect(() => {
    scrollerRef.current?.scrollTo({
      top: scrollerRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [turns, busy]);

  useEffect(() => {
    return () => window.speechSynthesis?.cancel();
  }, []);

  const stopSpeaking = () => {
    window.speechSynthesis?.cancel();
    replyAudioRef.current?.pause();
    replyAudioRef.current = null;
    setSpeakingTurnTs(null);
  };

  const stopRecording = () => {
    if (vadFrameRef.current !== null) {
      cancelAnimationFrame(vadFrameRef.current);
      vadFrameRef.current = null;
    }
    void captureContextRef.current?.close();
    captureContextRef.current = null;

    const recorder = mediaRecorderRef.current;
    if (recorder?.state === "recording") {
      setVoiceStatus("processing");
      setVoiceDetail("Understanding what you said…");
      recorder.stop();
    }
  };

  const startRecording = async () => {
    if (
      mode !== "avatar" ||
      busy ||
      speakingTurnTs !== null ||
      // "error" is retryable — a denied mic prompt must not brick the button.
      (voiceStatus !== "ready" && voiceStatus !== "error")
    ) {
      return;
    }

    try {
      const stream =
        mediaStreamRef.current ||
        (await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        }));
      mediaStreamRef.current = stream;
      shouldAutoListenRef.current = true;
      audioChunksRef.current = [];

      // Pick a mimeType the browser actually supports. Default-codec pick
      // fails on some Chrome/Edge builds on Windows with "There was an error
      // starting the MediaRecorder" — explicit probing avoids that.
      const preferredMimes = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/ogg;codecs=opus",
        "audio/mp4",
      ];
      const supportedMime = preferredMimes.find(
        (m) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(m)
      );
      const recorder = supportedMime
        ? new MediaRecorder(stream, { mimeType: supportedMime })
        : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      recorder.onerror = (event) => {
        const err = (event as unknown as { error?: DOMException }).error;
        console.error("MediaRecorder error:", err);
        setVoiceStatus("error");
        setVoiceDetail(
          err ? `${err.name}: ${err.message}` : "Recorder failed mid-capture"
        );
      };
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        try {
          const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType });
          if (blob.size < 1200) {
            // Nothing meaningful captured (mic muted / stopped instantly).
            setVoiceStatus("ready");
            setVoiceDetail("I didn't catch any audio — tap the microphone and speak.");
            return;
          }
          await sendVoice(await blobToBase64(blob));
        } catch (cause) {
          setVoiceStatus("ready");
          setVoiceDetail(
            cause instanceof Error
              ? cause.message
              : "Could not process microphone audio — tap the mic to try again"
          );
        }
      };
      recorder.start(250);
      setVoiceStatus("recording");
      setVoiceDetail("Listening… speak naturally");

      const captureContext = new AudioContext();
      captureContextRef.current = captureContext;
      const source = captureContext.createMediaStreamSource(stream);
      const analyser = captureContext.createAnalyser();
      analyser.fftSize = 1024;
      source.connect(analyser);
      const samples = new Uint8Array(analyser.fftSize);
      const startedAt = performance.now();
      let speechStarted = false;
      let lastSpeechAt = startedAt;

      const detectSilence = () => {
        analyser.getByteTimeDomainData(samples);
        let energy = 0;
        for (const sample of samples) {
          const normalized = (sample - 128) / 128;
          energy += normalized * normalized;
        }
        const rms = Math.sqrt(energy / samples.length);
        const now = performance.now();

        if (rms > 0.018) {
          speechStarted = true;
          lastSpeechAt = now;
        }

        if (
          (speechStarted && now - lastSpeechAt > 1200) ||
          (!speechStarted && now - startedAt > 10_000) ||
          now - startedAt > 30_000
        ) {
          stopRecording();
          return;
        }
        vadFrameRef.current = requestAnimationFrame(detectSilence);
      };
      vadFrameRef.current = requestAnimationFrame(detectSilence);
    } catch (cause) {
      setVoiceStatus("error");
      setVoiceDetail(
        cause instanceof Error
          ? cause.message
          : "Microphone access is required for voice mode"
      );
    }
  };
  startRecordingRef.current = () => {
    void startRecording();
  };

  const speakResponse = (text: string, turnTs: number) => {
    if (mode !== "avatar" || !("speechSynthesis" in window)) return;

    stopSpeaking();
    const cleanText = text
      .replace(/https?:\/\/\S+/g, "")
      .replace(/[*_#`]/g, "")
      .trim();
    if (!cleanText) return;

    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang =
      ({ en: "en-IN", hi: "hi-IN", ta: "ta-IN", bn: "bn-IN" } as Record<string, string>)[
        lang
      ] || lang;
    utterance.rate = 0.95;
    utterance.pitch = 1.05;
    utterance.onstart = () => setSpeakingTurnTs(turnTs);
    utterance.onend = () => {
      setSpeakingTurnTs(null);
      if (shouldAutoListenRef.current) {
        window.setTimeout(() => startRecordingRef.current(), 250);
      }
    };
    utterance.onerror = () => setSpeakingTurnTs(null);
    window.speechSynthesis.speak(utterance);
  };

  // Play the edge-tts MP3 the backend returned (near-human Indian-language
  // voices, rendered server-side — no dependency on browser voice packs).
  // Falls back to browser speechSynthesis when audio.play() is blocked
  // (autoplay policy, unsupported codec, decode error).
  const playReply = (b64: string, turnTs: number, fallbackText: string) => {
    stopSpeaking();
    // Blob URL is more reliable than a data: URL — some browsers throttle or
    // reject large data URLs, and .decode()/.play() errors are cleaner.
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const blob = new Blob([bytes], { type: "audio/mpeg" });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    replyAudioRef.current = audio;
    audio.onplay = () => setSpeakingTurnTs(turnTs);
    const finish = () => {
      setSpeakingTurnTs(null);
      if (replyAudioRef.current === audio) replyAudioRef.current = null;
      URL.revokeObjectURL(url);
      if (shouldAutoListenRef.current) {
        window.setTimeout(() => startRecordingRef.current(), 250);
      }
    };
    audio.onended = finish;
    audio.onerror = (event) => {
      console.error("reply audio decode/playback error:", event, audio.error);
      URL.revokeObjectURL(url);
      speakResponse(fallbackText, turnTs);
    };
    void audio.play().catch((err) => {
      console.error("audio.play() rejected:", err);
      setVoiceDetail(
        `Audio blocked (${err?.name || err}); using browser voice.`
      );
      URL.revokeObjectURL(url);
      speakResponse(fallbackText, turnTs);
    });
  };

  // One full voice turn through the backend: WAV → faster-whisper ASR →
  // orchestrator → NMT → edge-tts → MP3 reply. The browser only records
  // and plays audio; no speech model ever downloads into the page.
  const sendVoice = async (audioBase64: string) => {
    if (!sessionId) return;
    stopSpeaking();
    setError(null);
    setBusy(true);
    setVoiceStatus("processing");
    setVoiceDetail("Understanding what you said…");
    try {
      const r = await postVoice({
        session_id: sessionId,
        audio_base64: audioBase64,
        lang,
      });
      const now = Date.now();
      const responseTs = now + 1;
      setTurns((t) => [
        ...t,
        { role: "user", text: r.transcript, ts: now },
        {
          role: "assistant",
          text: r.response || "(no response)",
          ts: responseTs,
          intent: r.intent,
          confidence: r.confidence,
          escalation: r.escalation,
          awaiting_input: r.awaiting_input,
          citations: r.citations || [],
          trace_id: r.trace_id,
        },
      ]);
      setVoiceStatus("ready");
      setVoiceDetail("Tap the microphone and start speaking");
      if (r.audio_base64) {
        playReply(r.audio_base64, responseTs, r.response);
      } else {
        // Server TTS degraded — browser voice keeps the avatar speaking.
        speakResponse(r.response, responseTs);
      }
    } catch (e) {
      // 422 = "couldn't hear speech" — the backend message is user-facing.
      setVoiceStatus("ready");
      setVoiceDetail(
        e instanceof Error && e.message
          ? e.message
          : "Something went wrong — tap the microphone to try again."
      );
    } finally {
      setBusy(false);
    }
  };

  const send = async (raw?: string) => {
    const text = (raw ?? input).trim();
    if (!text || busy || !sessionId) return;
    stopSpeaking();
    setError(null);
    setInput("");
    setTurns((t) => [...t, { role: "user", text, ts: Date.now() }]);
    setBusy(true);
    try {
      const r: ChatResponse = await postChat({
        session_id: sessionId,
        message: text,
        lang,
      });
      const responseText = r.response || "(no response)";
      const responseTs = Date.now();
      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          text: responseText,
          ts: responseTs,
          intent: r.intent,
          confidence: r.confidence,
          escalation: r.escalation,
          awaiting_input: r.awaiting_input,
          citations: r.citations || [],
          trace_id: r.trace_id,
        },
      ]);
      speakResponse(responseText, responseTs);
    } catch (e: any) {
      setError(e.message || "Request failed");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (mode !== "avatar") return;

    // Speech recognition + TTS run server-side (/voice) — nothing to
    // download here; the mic is ready immediately.
    setVoiceStatus("ready");
    setVoiceDetail("Tap the microphone and start speaking");

    return () => {
      if (vadFrameRef.current !== null) cancelAnimationFrame(vadFrameRef.current);
      void captureContextRef.current?.close();
      captureContextRef.current = null;
      if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop();
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
      shouldAutoListenRef.current = false;
      replyAudioRef.current?.pause();
      replyAudioRef.current = null;
    };
  }, [mode]);

  const resetSession = () => {
    stopSpeaking();
    setSessionId(newSessionId());
    setTurns([]);
    setError(null);
  };

  // Switching mode keeps the session and conversation — the toggle changes
  // how you talk to Saheli, not who you're talking to.
  const switchMode = (next: ChatMode) => {
    if (next === mode) return;
    stopSpeaking();
    setError(null);
    setMode(next);
  };

  const emptyState = turns.length === 0;

  return (
    <div className="mx-auto w-full max-w-4xl">
      <Card className="flex h-[calc(100vh-11rem)] min-h-[560px] flex-col overflow-hidden p-0 shadow-sm">
        {/* Header: identity · mode toggle · language / session controls */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-white px-5 py-3">
          <div className="flex items-center gap-3">
            <SaheliAvatar speaking={speakingTurnTs !== null} />
            <div className="leading-tight">
              <div className="text-sm font-semibold text-foreground">AI Saheli</div>
              <div className="text-[11px] text-muted-foreground">
                Poshan 2.0 · Mission Vatsalya · Mission Shakti
              </div>
            </div>
          </div>

          <ModeToggle mode={mode} onSwitch={switchMode} />

          <div className="flex items-center gap-2">
            <LangPicker languages={languages} lang={lang} onSelect={setLang} />
            <Button variant="outline" size="sm" onClick={resetSession}>
              New chat
            </Button>
          </div>
        </div>

        {mode === "avatar" ? (
          <>
            <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-6 bg-white p-6">
              <SaheliAvatar size="hero" speaking={speakingTurnTs !== null} />
              <div className="min-h-6 text-center text-sm text-muted-foreground" aria-live="polite">
                {speakingTurnTs !== null ? "Speaking…" : busy ? "Thinking…" : voiceDetail}
              </div>
              <Button
                type="button"
                onClick={voiceStatus === "recording" ? stopRecording : startRecording}
                disabled={busy || speakingTurnTs !== null || voiceStatus === "processing"}
                className={cn(
                  "h-12 min-w-44 rounded-full px-7 text-base",
                  voiceStatus === "recording"
                    ? "bg-rose-600 text-white hover:bg-rose-700"
                    : "bg-ministry text-white hover:bg-ministry-muted"
                )}
              >
                {voiceStatus === "processing" ? (
                  <LoaderCircle className="h-5 w-5 animate-spin" />
                ) : voiceStatus === "recording" ? (
                  <Square className="h-4 w-4 fill-current" />
                ) : (
                  <Mic className="h-5 w-5" />
                )}
                {voiceStatus === "processing"
                  ? "Understanding"
                  : voiceStatus === "recording"
                    ? "Stop speaking"
                    : voiceStatus === "error"
                      ? "Try again"
                      : "Start speaking"}
              </Button>
            </div>
            {error && (
              <div className="border-t border-border bg-destructive/10 px-4 py-2 text-sm text-destructive">
                {error}
              </div>
            )}
          </>
        ) : (
          <>
            <div
              ref={scrollerRef}
              className="min-h-0 flex-1 space-y-5 overflow-y-auto bg-white px-6 py-6 scrollbar-thin"
            >
              {emptyState ? (
                <EmptyState
                  onPick={(t, l) => {
                    setLang(l);
                    send(t);
                  }}
                />
              ) : (
                turns.map((t, i) => (
                  <Message
                    key={i}
                    turn={t}
                    speaking={t.role === "assistant" && t.ts === speakingTurnTs}
                    showAvatar={false}
                  />
                ))
              )}
              {busy && <TypingBubble showAvatar={false} />}
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                send();
              }}
              className="flex gap-2 border-t border-border bg-white p-3"
            >
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  lang === "hi"
                    ? "अपनी बात यहाँ लिखें..."
                    : "Type your question in any language…"
                }
                disabled={busy}
                className="rounded-full"
              />
              <Button
                type="submit"
                disabled={busy || !input.trim()}
                className="rounded-full bg-ministry px-5 text-white hover:bg-ministry-muted"
              >
                <Send className="h-4 w-4" /> Send
              </Button>
            </form>

            {error && (
              <div className="border-t border-border bg-destructive/10 px-4 py-2 text-sm text-destructive">
                {error}
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}

function ModeToggle({
  mode,
  onSwitch,
}: {
  mode: ChatMode;
  onSwitch: (mode: ChatMode) => void;
}) {
  const options = [
    { id: "text" as const, label: "Chat", icon: MessageCircle },
    { id: "avatar" as const, label: "Voice", icon: Mic },
  ];
  return (
    <div
      role="tablist"
      aria-label="Conversation mode"
      className="flex rounded-full border border-border bg-muted p-0.5"
    >
      {options.map((o) => {
        const Icon = o.icon;
        const active = mode === o.id;
        return (
          <button
            key={o.id}
            role="tab"
            aria-selected={active}
            onClick={() => onSwitch(o.id)}
            className={cn(
              "flex items-center gap-1.5 rounded-full px-4 py-1.5 text-sm font-medium transition-colors",
              active
                ? "bg-white text-ministry shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function LangPicker({
  languages,
  lang,
  onSelect,
}: {
  languages: LanguageMeta[];
  lang: string;
  onSelect: (code: string) => void;
}) {
  return (
    <div className="flex overflow-hidden rounded-full border border-border bg-white">
      {languages.map((l) => (
        <button
          key={l.code}
          onClick={() => onSelect(l.code)}
          className={cn(
            "px-3 py-1.5 text-xs font-medium transition-colors",
            lang === l.code
              ? "bg-ministry text-white"
              : "text-muted-foreground hover:bg-muted"
          )}
        >
          {l.native}
        </button>
      ))}
    </div>
  );
}

function EmptyState({
  onPick,
}: {
  onPick: (text: string, lang: string) => void;
}) {
  return (
    <div className="grid h-full place-items-center text-center">
      <div className="w-full max-w-xl space-y-8">
        <div className="space-y-3">
          <h2 className="text-2xl font-semibold tracking-tight text-foreground">
            How can I help you today?
          </h2>
          <p className="mx-auto max-w-md text-sm leading-relaxed text-muted-foreground">
            Ask me about nutrition, child care, women&apos;s safety, or any
            government scheme — in English, हिन्दी, or your own language.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {STARTERS.map((s) => {
            const Icon = s.icon;
            return (
              <button
                key={s.text}
                onClick={() => onPick(s.text, s.lang)}
                className="group rounded-xl border border-border bg-white p-4 text-left transition-colors hover:border-ministry/50 hover:bg-ministry-soft/50"
              >
                <Icon className="mb-2.5 h-4 w-4 text-ministry" />
                <div className="text-sm font-medium text-foreground">{s.title}</div>
                <div className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                  {s.text}
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function Message({
  turn,
  speaking,
  showAvatar = true,
}: {
  turn: Turn;
  speaking: boolean;
  showAvatar?: boolean;
}) {
  if (turn.role === "user") {
    return (
      <div className="flex flex-col items-end gap-1">
        <div className="max-w-[75%] rounded-2xl rounded-tr-md bg-ministry px-4 py-2.5 text-sm text-white">
          {turn.text}
        </div>
        <span className="pr-2 text-[10px] text-muted-foreground">{fmtTime(turn.ts)}</span>
      </div>
    );
  }
  const intentClass = turn.intent ? INTENT_STYLE[turn.intent] : "";
  return (
    <div className="flex gap-2.5">
      {showAvatar && <SaheliAvatar speaking={speaking} />}
      <div className="min-w-0 flex-1 space-y-2">
        <div className="max-w-[92%] whitespace-pre-wrap rounded-2xl rounded-tl-md border border-border bg-muted/50 px-4 py-3 text-sm leading-relaxed">
          {turn.text}
        </div>
        <div className="flex flex-wrap items-center gap-1.5 pl-1">
          <span className="text-[10px] text-muted-foreground">{fmtTime(turn.ts)}</span>
          {turn.escalation && (
            <Badge variant="destructive" className="gap-1">
              <AlertTriangle className="h-3 w-3" /> Escalated
            </Badge>
          )}
          {turn.awaiting_input && <Badge variant="accent">Awaiting input</Badge>}
          {turn.intent && (
            <span
              className={cn(
                "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize",
                intentClass || "bg-muted text-muted-foreground border-border"
              )}
            >
              {turn.intent}
            </span>
          )}
          {typeof turn.confidence === "number" && (
            <Badge variant="muted">conf {(turn.confidence * 100).toFixed(0)}%</Badge>
          )}
          {turn.citations.slice(0, 3).map((c, i) => (
            <CitationChip key={i} c={c} />
          ))}
        </div>
      </div>
    </div>
  );
}

function CitationChip({ c }: { c: Citation }) {
  const label = c.section ? `${c.source_doc} — ${c.section}` : c.source_doc;
  const chip = (
    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-white px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:border-ministry/40 hover:bg-ministry-soft hover:text-ministry">
      <BookOpen className="h-3 w-3" />
      <span className="max-w-[240px] truncate">{label}</span>
    </span>
  );
  if (!c.source_url) return chip;
  return (
    <a href={c.source_url} target="_blank" rel="noreferrer" title={label}>
      {chip}
    </a>
  );
}

function TypingBubble({ showAvatar = true }: { showAvatar?: boolean }) {
  return (
    <div className="flex gap-2.5">
      {showAvatar && <SaheliAvatar />}
      <div className="rounded-2xl rounded-tl-md border border-border bg-muted/50 px-4 py-3">
        <div className="flex gap-1">
          <span className="h-2 w-2 animate-bounce rounded-full bg-ministry/70 [animation-delay:-0.2s]" />
          <span className="h-2 w-2 animate-bounce rounded-full bg-ministry/70 [animation-delay:-0.1s]" />
          <span className="h-2 w-2 animate-bounce rounded-full bg-ministry/70" />
        </div>
      </div>
    </div>
  );
}

function SaheliAvatar({
  speaking = false,
  size = "message",
}: {
  speaking?: boolean;
  size?: "message" | "stage" | "hero";
}) {
  return (
    <div
      className={cn(
        "relative flex-shrink-0 overflow-hidden rounded-full border-2 border-white bg-ministry-soft shadow-md ring-1 ring-ministry/15",
        size === "hero"
          ? "h-56 w-56 sm:h-72 sm:w-72"
          : size === "stage"
            ? "h-24 w-24 sm:h-32 sm:w-32"
            : "h-10 w-10",
        speaking && "avatar-speaking"
      )}
      aria-label={speaking ? "AI Saheli is speaking" : "AI Saheli"}
    >
      <Image
        src="/ai-saheli-avatar.png"
        alt=""
        fill
        priority={size !== "message"}
        sizes={
          size === "hero"
            ? "(min-width: 640px) 288px, 224px"
            : size === "stage"
              ? "(min-width: 640px) 128px, 96px"
              : "40px"
        }
        className="avatar-face object-cover"
      />
      <Image
        src="/ai-saheli-avatar-speaking.png"
        alt=""
        fill
        priority={size !== "message"}
        sizes={
          size === "hero"
            ? "(min-width: 640px) 288px, 224px"
            : size === "stage"
              ? "(min-width: 640px) 128px, 96px"
              : "40px"
        }
        className={cn(
          "avatar-face object-cover opacity-0",
          speaking && "avatar-speaking-frame"
        )}
      />
    </div>
  );
}
