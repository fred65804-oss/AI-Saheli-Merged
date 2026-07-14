"use client";

import { useEffect, useState } from "react";
import {
  Activity,
  Bot,
  Cpu,
  Languages,
  RefreshCcw,
  ShieldAlert,
  Workflow,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { getHealth, getMeta, type AppMeta, type HealthInfo } from "@/lib/api";
import { cn } from "@/lib/utils";

const SCHEME_STYLE: Record<string, string> = {
  poshan: "bg-emerald-100 text-emerald-800 border-emerald-200",
  vatsalya: "bg-sky-100 text-sky-800 border-sky-200",
  shakti: "bg-fuchsia-100 text-fuchsia-800 border-fuchsia-200",
  general: "bg-slate-100 text-slate-700 border-slate-200",
};

export default function SystemPage() {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [meta, setMeta] = useState<AppMeta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadedAt, setLoadedAt] = useState<Date | null>(null);

  const load = () => {
    setError(null);
    Promise.all([getHealth(), getMeta()])
      .then(([h, m]) => {
        setHealth(h);
        setMeta(m);
        setLoadedAt(new Date());
      })
      .catch((e) => setError(e.message || "Backend unreachable"));
  };

  useEffect(load, []);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ministry">System panel</h1>
          <p className="text-sm text-muted-foreground">
            Live runtime configuration — everything shown here is read from the backend, nothing is hardcoded.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {loadedAt && (
            <span className="text-xs text-muted-foreground">
              as of {loadedAt.toLocaleTimeString()}
            </span>
          )}
          <Button variant="outline" size="sm" onClick={load} className="gap-1.5 rounded-full">
            <RefreshCcw className="h-3.5 w-3.5" /> Refresh
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error} — is the FastAPI backend running on port 8000?
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatusCard
          icon={Activity}
          label="Backend"
          value={health ? health.status.toUpperCase() : "…"}
          ok={health?.status === "ok"}
          hint="FastAPI orchestrator API"
        />
        <StatusCard
          icon={Cpu}
          label="LLM"
          value={health ? (health.llm === "live" ? "LIVE" : "OFFLINE") : "…"}
          ok={health?.llm === "live"}
          hint={
            health?.llm === "live"
              ? `${health.provider} · ${health.model}`
              : "keyword routing + lexicon safety only"
          }
        />
        <StatusCard
          icon={Languages}
          label="Language layer"
          value={health?.language ?? "…"}
          ok={Boolean(health)}
          hint={`${meta?.languages.length ?? "—"} languages · ASR + NMT + TTS`}
        />
        <StatusCard
          icon={Workflow}
          label="Specialist contract"
          value={meta ? `v${meta.app.contract_version}` : "…"}
          ok={Boolean(meta)}
          hint="agents/specialists/base.py"
        />
      </div>

      {meta && (
        <>
          <Card>
            <CardContent className="pt-5">
              <div className="mb-3 flex items-center gap-2">
                <Cpu className="h-4 w-4 text-ministry" />
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  LLM configuration
                </span>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <KV k="Provider" v={meta.llm.provider || "none"} />
                <KV k="Main model (synthesis)" v={meta.llm.model || "—"} />
                <KV k="Fast model (router / safety)" v={meta.llm.fast_model || "—"} />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-5">
              <div className="mb-3 flex items-center gap-2">
                <Bot className="h-4 w-4 text-ministry" />
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Registered capability cards — routing is declarative, driven by these
                </span>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {meta.cards.map((c) => (
                  <div
                    key={c.scheme}
                    className="rounded-xl border border-white/70 bg-white/70 p-4"
                  >
                    <div className="mb-1.5 flex flex-wrap items-center gap-2">
                      <span
                        className={cn(
                          "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize",
                          SCHEME_STYLE[c.scheme] || SCHEME_STYLE.general
                        )}
                      >
                        {c.scheme}
                      </span>
                      <span className="text-sm font-semibold">{c.display_name}</span>
                      {c.safety_critical && (
                        <Badge variant="destructive" className="gap-1">
                          <ShieldAlert className="h-3 w-3" /> safety-critical
                        </Badge>
                      )}
                      {c.fallback && <Badge variant="muted">fallback</Badge>}
                    </div>
                    <p className="text-sm leading-relaxed text-muted-foreground">{c.description}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-5">
              <div className="mb-3 flex items-center gap-2">
                <Languages className="h-4 w-4 text-ministry" />
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Supported languages ({meta.languages.length})
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                {meta.languages.map((l) => (
                  <span
                    key={l.code}
                    className="rounded-full border border-white/70 bg-white/70 px-3 py-1 text-sm"
                    title={l.name}
                  >
                    {l.native}{" "}
                    <span className="text-xs uppercase text-muted-foreground">{l.code}</span>
                  </span>
                ))}
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function StatusCard({
  icon: Icon,
  label,
  value,
  ok,
  hint,
}: {
  icon: typeof Activity;
  label: string;
  value: string;
  ok: boolean;
  hint: string;
}) {
  return (
    <Card>
      <CardContent className="pt-5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {label}
          </span>
          <Icon className={cn("h-4 w-4", ok ? "text-emerald-600" : "text-muted-foreground")} />
        </div>
        <div className={cn("mt-1.5 text-xl font-semibold", ok ? "text-foreground" : "text-muted-foreground")}>
          {value}
        </div>
        <div className="mt-0.5 truncate text-xs text-muted-foreground" title={hint}>
          {hint}
        </div>
      </CardContent>
    </Card>
  );
}

function KV({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-lg border border-white/70 bg-white/70 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{k}</div>
      <div className="mt-0.5 font-mono text-sm">{v}</div>
    </div>
  );
}
