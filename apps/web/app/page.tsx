"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  BookOpen,
  Baby,
  HeartHandshake,
  Phone,
  Send,
  ShieldAlert,
  Sparkles,
  Utensils,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { postChat, type ChatResponse, type Citation } from "@/lib/api";
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

const LANGS = [
  { code: "en", label: "EN" },
  { code: "hi", label: "हिं" },
  { code: "ta", label: "த" },
  { code: "bn", label: "বাং" },
];

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

export default function ChatPage() {
  const [sessionId, setSessionId] = useState<string>("");
  const [lang, setLang] = useState<string>("en");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setSessionId(newSessionId());
  }, []);

  useEffect(() => {
    scrollerRef.current?.scrollTo({
      top: scrollerRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [turns, busy]);

  const send = async (raw?: string) => {
    const text = (raw ?? input).trim();
    if (!text || busy || !sessionId) return;
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
      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          text: r.response || "(no response)",
          ts: Date.now(),
          intent: r.intent,
          confidence: r.confidence,
          escalation: r.escalation,
          awaiting_input: r.awaiting_input,
          citations: r.citations || [],
          trace_id: r.trace_id,
        },
      ]);
    } catch (e: any) {
      setError(e.message || "Request failed");
    } finally {
      setBusy(false);
    }
  };

  const resetSession = () => {
    setSessionId(newSessionId());
    setTurns([]);
    setError(null);
  };

  const emptyState = turns.length === 0;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <Card className="flex flex-col h-[calc(100vh-11rem)] overflow-hidden p-0">
        <div className="flex items-center justify-between border-b border-white/60 px-5 py-3 bg-gradient-to-r from-white/80 to-ministry-soft/40">
          <div className="flex items-center gap-3">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-70 animate-ping" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
            </span>
            <div className="leading-tight">
              <div className="text-sm font-medium text-foreground">Live orchestrator</div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                {sessionId.slice(-10)}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex rounded-full border bg-white/70 overflow-hidden shadow-sm">
              {LANGS.map((l) => (
                <button
                  key={l.code}
                  onClick={() => setLang(l.code)}
                  className={cn(
                    "px-3 py-1.5 text-xs font-medium transition-all",
                    lang === l.code
                      ? "gradient-ministry text-white shadow-inner"
                      : "text-muted-foreground hover:bg-ministry-soft"
                  )}
                >
                  {l.label}
                </button>
              ))}
            </div>
            <Button variant="outline" size="sm" onClick={resetSession} className="rounded-full">
              New session
            </Button>
          </div>
        </div>

        <div
          ref={scrollerRef}
          className="flex-1 overflow-y-auto scrollbar-thin px-6 py-6 space-y-5"
        >
          {emptyState ? (
            <EmptyState
              onPick={(t, l) => {
                setLang(l);
                send(t);
              }}
            />
          ) : (
            turns.map((t, i) => <Message key={i} turn={t} />)
          )}
          {busy && <TypingBubble />}
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

      <aside className="space-y-4">
        <QuickStarters
          starters={JOURNEY_STARTERS}
          onPick={(t, l) => {
            setLang(l);
            send(t);
          }}
        />
        <InfoCard />
        <HelplineStrip />
      </aside>
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
        <div className="relative mx-auto h-20 w-20">
          <div className="absolute inset-0 rounded-full gradient-ministry blur-2xl opacity-30" />
          <div className="relative h-20 w-20 rounded-full gradient-ministry grid place-items-center shadow-lg">
            <Sparkles className="h-9 w-9 text-white" />
          </div>
        </div>
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

function Message({ turn }: { turn: Turn }) {
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
      <div className="flex-shrink-0 h-9 w-9 rounded-full gradient-ministry grid place-items-center text-white font-semibold text-sm shadow-md">
        स
      </div>
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

function TypingBubble() {
  return (
    <div className="flex gap-2.5">
      <div className="flex-shrink-0 h-9 w-9 rounded-full gradient-ministry grid place-items-center text-white font-semibold text-sm shadow-md">
        स
      </div>
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

function QuickStarters({
  starters,
  onPick,
}: {
  starters: typeof JOURNEY_STARTERS;
  onPick: (text: string, lang: string) => void;
}) {
  return (
    <Card>
      <CardContent className="pt-5">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles className="h-4 w-4 text-ministry" />
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Demo journeys
          </div>
        </div>
        <ul className="space-y-2">
          {starters.map((s) => {
            const Icon = s.icon;
            return (
              <li key={s.text}>
                <button
                  onClick={() => onPick(s.text, s.lang)}
                  className="w-full text-left rounded-lg border border-white/70 bg-white/60 hover:bg-white hover:border-ministry hover:shadow-md px-3 py-2 transition-all group"
                >
                  <div className="flex items-center gap-2.5">
                    <div
                      className={cn(
                        "h-7 w-7 rounded-md grid place-items-center bg-gradient-to-br text-white",
                        s.color
                      )}
                    >
                      <Icon className="h-3.5 w-3.5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium">{s.label}</div>
                      <div className="text-[11px] text-muted-foreground truncate">
                        {s.text}
                      </div>
                    </div>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

function InfoCard() {
  const steps = [
    "Safety gate runs first — non-bypassable",
    "Router picks the right scheme agent",
    "Specialist calls MCP tools + grounded RAG",
    "Every reply carries authoritative citations",
  ];
  return (
    <Card>
      <CardContent className="pt-5">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">
          How it works
        </div>
        <ol className="space-y-2.5">
          {steps.map((s, i) => (
            <li key={s} className="flex gap-2.5 text-sm">
              <span className="flex-shrink-0 h-5 w-5 rounded-full gradient-ministry text-white text-[10px] font-bold grid place-items-center">
                {i + 1}
              </span>
              <span className="text-muted-foreground leading-snug">{s}</span>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}

function HelplineStrip() {
  const lines = [
    { label: "CHILDLINE", num: "1098" },
    { label: "Women Helpline", num: "181" },
    { label: "Emergency", num: "112" },
  ];
  return (
    <div className="rounded-xl bg-gradient-to-br from-accent/90 to-orange-600 text-white p-4 shadow-md">
      <div className="flex items-center gap-2 mb-2">
        <Phone className="h-4 w-4" />
        <div className="text-[11px] font-semibold uppercase tracking-wider">
          In an emergency
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {lines.map((l) => (
          <div key={l.num} className="rounded-lg bg-white/15 backdrop-blur-sm px-2 py-2 text-center">
            <div className="text-lg font-bold leading-none">{l.num}</div>
            <div className="text-[10px] opacity-90 mt-1">{l.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
