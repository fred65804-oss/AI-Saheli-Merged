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
  ArrowLeft,
  LoaderCircle,
  MessageCircle,
  Mic,
  Square,
  UserRound,
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

const JOURNEY_STARTERS = [
  {
    lang: "hi",
    label: "Pregnancy nutrition",
    hint: "हिन्दी · Journey 1",
    text: "Pregnancy mein kya khana chahiye?",
    icon: Utensils,
    color: "from-emerald-500 to-teal-600",
  },
  {
    lang: "en",
    label: "Child growth concern",
    hint: "English · Journey 2",
    text: "My 14-month-old is not gaining weight — what should I do?",
    icon: Baby,
    color: "from-sky-500 to-indigo-600",
  },
  {
    lang: "en",
    label: "Women safety · OSC",
    hint: "English · Journey 3",
    text: "I feel unsafe at home, where can I get help?",
    icon: ShieldAlert,
    color: "from-rose-500 to-red-600",
  },
  {
    lang: "en",
    label: "PMMVY eligibility",
    hint: "English · Journey 4",
    text: "Am I eligible for PMMVY for my first child?",
    icon: HeartHandshake,
    color: "from-fuchsia-500 to-purple-600",
  },
];

const INTENT_STYLE: Record<string, string> = {
  poshan: "bg-emerald-100 text-emerald-800 border-emerald-200",
  vatsalya: "bg-sky-100 text-sky-800 border-sky-200",
  shakti: "bg-fuchsia-100 text-fuchsia-800 border-fuchsia-200",
  general: "bg-slate-100 text-slate-700 border-slate-200",
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
  const [mode, setMode] = useState<ChatMode | null>(null);
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

      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
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
  const playReply = (b64: string, turnTs: number) => {
    stopSpeaking();
    const audio = new Audio(`data:audio/mp3;base64,${b64}`);
    replyAudioRef.current = audio;
    audio.onplay = () => setSpeakingTurnTs(turnTs);
    const finish = () => {
      setSpeakingTurnTs(null);
      if (replyAudioRef.current === audio) replyAudioRef.current = null;
      if (shouldAutoListenRef.current) {
        window.setTimeout(() => startRecordingRef.current(), 250);
      }
    };
    audio.onended = finish;
    audio.onerror = finish;
    void audio.play().catch(finish);
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
        playReply(r.audio_base64, responseTs);
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

  const chooseMode = (nextMode: ChatMode) => {
    stopSpeaking();
    setMode(nextMode);
    setSessionId(newSessionId());
    setTurns([]);
    setInput("");
    setError(null);
  };

  const leaveChat = () => {
    stopSpeaking();
    setMode(null);
    setTurns([]);
    setInput("");
    setError(null);
  };

  const emptyState = turns.length === 0;

  if (!mode) {
    return <ModePicker onChoose={chooseMode} />;
  }

  if (mode === "avatar") {
    return (
      <Card className="flex h-[calc(100vh-11rem)] min-h-[560px] flex-col overflow-hidden p-0">
        <div className="flex items-center justify-between border-b border-white/60 bg-white/70 px-4 py-3">
          <Button type="button" variant="ghost" size="sm" onClick={leaveChat} className="gap-2 rounded-full">
            <ArrowLeft className="h-4 w-4" /> Modes
          </Button>
          <LangPicker languages={languages} lang={lang} onSelect={setLang} />
          <Button variant="outline" size="sm" onClick={resetSession} className="rounded-full">
            New session
          </Button>
        </div>

        <div className="dot-pattern flex min-h-0 flex-1 flex-col items-center justify-center gap-5 bg-ministry-soft/20 p-6">
          <SaheliAvatar size="hero" speaking={speakingTurnTs !== null} />
          <div className="min-h-6 text-center text-sm font-medium text-ministry" aria-live="polite">
            {speakingTurnTs !== null ? "Speaking…" : busy ? "Thinking…" : voiceDetail}
          </div>
        </div>

        <div className="border-t border-white/60 bg-white/70 p-4">
          <div className="mx-auto flex max-w-2xl justify-center">
            <Button
              type="button"
              onClick={voiceStatus === "recording" ? stopRecording : startRecording}
              disabled={busy || speakingTurnTs !== null || voiceStatus === "processing"}
              className={cn(
                "h-14 min-w-48 rounded-full px-7 text-base shadow-lg",
                voiceStatus === "recording"
                  ? "bg-rose-600 text-white hover:bg-rose-700"
                  : "gradient-ministry"
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
          {error && <div className="mx-auto mt-2 max-w-2xl text-sm text-destructive">{error}</div>}
        </div>
      </Card>
    );
  }

  return (
    <div className="mx-auto w-full max-w-4xl">
      <Card className="flex flex-col h-[calc(100vh-11rem)] overflow-hidden p-0">
        <div className="flex items-center justify-between border-b border-white/60 px-5 py-3 bg-gradient-to-r from-white/80 to-ministry-soft/40">
          <div className="flex items-center gap-3">
            <Button type="button" variant="ghost" size="sm" onClick={leaveChat} className="gap-2 rounded-full">
              <ArrowLeft className="h-4 w-4" /> Modes
            </Button>
            <div className="leading-tight">
              <div className="text-sm font-medium text-foreground">Text chat</div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                {sessionId.slice(-10)}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <LangPicker languages={languages} lang={lang} onSelect={setLang} />
            <Button variant="outline" size="sm" onClick={resetSession} className="rounded-full">
              New session
            </Button>
          </div>
        </div>

        <div
          ref={scrollerRef}
          className="min-h-0 flex-1 overflow-y-auto scrollbar-thin px-6 py-6 space-y-5"
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
          className="border-t border-white/60 p-3 flex gap-2 bg-white/60"
        >
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              lang === "hi"
                ? "अपनी बात यहाँ लिखें..."
                : "Type in English, Hinglish, or any Indian language..."
            }
            disabled={busy}
            className="rounded-full border-white/80 bg-white shadow-sm"
          />
          <Button
            type="submit"
            disabled={busy || !input.trim()}
            className="rounded-full px-5 gradient-ministry"
          >
            <Send className="h-4 w-4" /> Send
          </Button>
        </form>

        {error && (
          <div className="border-t bg-destructive/10 text-destructive text-sm px-4 py-2">
            {error}
          </div>
        )}
      </Card>
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
    <div className="flex overflow-hidden rounded-full border bg-white/70 shadow-sm">
      {languages.map((l) => (
        <button
          key={l.code}
          onClick={() => onSelect(l.code)}
          className={cn(
            "px-3 py-1.5 text-xs font-medium transition-all",
            lang === l.code
              ? "gradient-ministry text-white shadow-inner"
              : "text-muted-foreground hover:bg-ministry-soft"
          )}
        >
          {l.native}
        </button>
      ))}
    </div>
  );
}

function ModePicker({ onChoose }: { onChoose: (mode: ChatMode) => void }) {
  const modes = [
    {
      id: "text" as const,
      title: "Text chat",
      description: "A standard chat with written questions and answers. No voice or avatar.",
      icon: MessageCircle,
    },
    {
      id: "avatar" as const,
      title: "Voice avatar",
      description: "Speak naturally in your language — AI Saheli listens and answers aloud through the avatar.",
      icon: UserRound,
    },
  ];

  return (
    <div className="grid min-h-[calc(100vh-11rem)] place-items-center py-8">
      <div className="w-full max-w-3xl text-center">
        <div className="mb-8 space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight text-ministry">Choose how to chat</h1>
          <p className="text-sm text-muted-foreground">You can return here and switch modes at any time.</p>
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          {modes.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onChoose(item.id)}
                className="group rounded-3xl border border-white/80 bg-white/75 p-7 text-left shadow-lg backdrop-blur-sm transition-all hover:-translate-y-1 hover:border-ministry/40 hover:shadow-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ministry"
              >
                <div className="mb-6 grid h-14 w-14 place-items-center rounded-2xl gradient-ministry text-white shadow-md transition-transform group-hover:scale-105">
                  <Icon className="h-7 w-7" />
                </div>
                <h2 className="text-xl font-semibold text-foreground">{item.title}</h2>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{item.description}</p>
                <div className="mt-6 text-sm font-semibold text-ministry">Start {item.title.toLowerCase()} →</div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function EmptyState({
  onPick,
}: {
  onPick: (text: string, lang: string) => void;
}) {
  return (
    <div className="h-full grid place-items-center text-center">
      <div className="max-w-lg space-y-6">
        <div className="space-y-2">
          <h2 className="text-2xl font-semibold text-ministry">Namaste 🙏</h2>
          <p className="text-sm text-muted-foreground">
            I am <b>AI Saheli</b>, your assistant for the Ministry’s welfare
            schemes — Poshan 2.0, Mission Vatsalya, and Mission Shakti. Pick a
            starter or type your question in any language.
          </p>
        </div>
        <div className="grid gap-2 sm:grid-cols-2 pt-2">
          {JOURNEY_STARTERS.map((s) => {
            const Icon = s.icon;
            return (
              <button
                key={s.text}
                onClick={() => onPick(s.text, s.lang)}
                className="group text-left rounded-xl border border-white/70 bg-white/70 backdrop-blur-sm px-3 py-3 hover:border-ministry hover:shadow-md transition-all"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={cn(
                      "h-9 w-9 rounded-lg grid place-items-center bg-gradient-to-br text-white shadow-sm",
                      s.color
                    )}
                  >
                    <Icon className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate">{s.label}</div>
                    <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                      {s.hint}
                    </div>
                  </div>
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
        <div className="max-w-[75%] rounded-2xl rounded-tr-md gradient-ministry text-white px-4 py-2.5 text-sm shadow-md">
          {turn.text}
        </div>
        <span className="text-[10px] text-muted-foreground pr-2">{fmtTime(turn.ts)}</span>
      </div>
    );
  }
  const intentClass = turn.intent ? INTENT_STYLE[turn.intent] : "";
  return (
    <div className="flex gap-2.5">
      {showAvatar && <SaheliAvatar speaking={speaking} />}
      <div className="min-w-0 flex-1 space-y-2">
        <div className="max-w-[92%] rounded-2xl rounded-tl-md bg-white border border-white/70 px-4 py-3 text-sm shadow-sm whitespace-pre-wrap leading-relaxed">
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
    <span className="inline-flex items-center gap-1 rounded-full border border-border/60 bg-white/70 px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-ministry-soft hover:text-ministry hover:border-ministry/40 transition-colors">
      <BookOpen className="h-3 w-3" />
      <span className="truncate max-w-[240px]">{label}</span>
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
      <div className="rounded-2xl rounded-tl-md bg-white border border-white/70 px-4 py-3 shadow-sm">
        <div className="flex gap-1">
          <span className="h-2 w-2 rounded-full bg-ministry/70 animate-bounce [animation-delay:-0.2s]" />
          <span className="h-2 w-2 rounded-full bg-ministry/70 animate-bounce [animation-delay:-0.1s]" />
          <span className="h-2 w-2 rounded-full bg-ministry/70 animate-bounce" />
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
