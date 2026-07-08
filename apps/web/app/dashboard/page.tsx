"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Anchor,
  BarChart3,
  CheckCircle2,
  Clock,
  Languages,
  Layers,
  MessageSquare,
  RefreshCw,
  ShieldCheck,
  Users,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getRecent,
  getStats,
  type Bucket,
  type DashboardStats,
  type RecentTurn,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const INTENT_BAR: Record<string, string> = {
  poshan: "from-emerald-400 to-emerald-600",
  vatsalya: "from-sky-400 to-sky-600",
  shakti: "from-fuchsia-400 to-fuchsia-600",
  general: "from-slate-300 to-slate-500",
};

const INTENT_CHIP: Record<string, string> = {
  poshan: "bg-emerald-100 text-emerald-800 border-emerald-200",
  vatsalya: "bg-sky-100 text-sky-800 border-sky-200",
  shakti: "bg-fuchsia-100 text-fuchsia-800 border-fuchsia-200",
  general: "bg-slate-100 text-slate-700 border-slate-200",
};

const LANG_LABEL: Record<string, string> = {
  en: "English",
  hi: "हिन्दी",
  ta: "தமிழ்",
  bn: "বাংলা",
  te: "తెలుగు",
  mr: "मराठी",
};

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recent, setRecent] = useState<RecentTurn[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, r] = await Promise.all([getStats(), getRecent(30)]);
      setStats(s);
      setRecent(r.turns);
    } catch (e: any) {
      setError(e.message || "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" />
            <span className="text-[11px] uppercase tracking-widest text-muted-foreground font-semibold">
              MoWCD · Live analytics
            </span>
          </div>
          <h1 className="text-3xl font-semibold text-ministry">Ministry Dashboard</h1>
          <p className="text-sm text-muted-foreground max-w-xl">
            Every citizen turn is audited — safe, grounded, and cited. This
            view reads the orchestrator’s audit trace directly.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {stats && (
            <div className="text-right">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Last updated
              </div>
              <div className="text-xs font-medium">
                {new Date(stats.updated_at).toLocaleTimeString()}
              </div>
            </div>
          )}
          <Button variant="outline" onClick={load} disabled={loading} className="rounded-full">
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive flex items-center gap-3">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          <span>{error} — is the backend running on port 8000?</span>
        </div>
      )}

      {stats && (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <Kpi
              icon={<MessageSquare className="h-5 w-5" />}
              label="Total turns"
              value={stats.kpis.total_turns.toLocaleString()}
              hint={`${stats.kpis.unique_sessions} unique sessions`}
              tone="ministry"
            />
            <Kpi
              icon={<AlertTriangle className="h-5 w-5" />}
              label="Safety escalations"
              value={stats.kpis.escalations.toString()}
              hint={`${(stats.kpis.escalation_rate * 100).toFixed(1)}% of turns routed to helplines`}
              tone="destructive"
            />
            <Kpi
              icon={<ShieldCheck className="h-5 w-5" />}
              label="Grounded reply share"
              value={
                stats.kpis.grounded_share !== null
                  ? `${(stats.kpis.grounded_share * 100).toFixed(0)}%`
                  : "—"
              }
              hint={
                stats.kpis.avg_confidence !== null
                  ? `avg confidence ${(stats.kpis.avg_confidence * 100).toFixed(0)}%`
                  : "no confidence data yet"
              }
              tone="success"
            />
            <Kpi
              icon={<Clock className="h-5 w-5" />}
              label="Avg latency"
              value={
                stats.kpis.avg_latency_ms !== null
                  ? `${stats.kpis.avg_latency_ms.toFixed(0)} ms`
                  : "—"
              }
              hint={`${stats.kpis.fallback_count} specialist fallbacks`}
              tone="accent"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <BarCard
              title="Scheme distribution"
              icon={<Layers className="h-4 w-4" />}
              buckets={stats.intents}
              gradientFn={(k) => INTENT_BAR[k] || "from-ministry to-ministry-muted"}
              formatKey={(k) => k}
            />
            <BarCard
              title="Languages"
              icon={<Languages className="h-4 w-4" />}
              buckets={stats.languages}
              gradientFn={() => "from-ministry to-ministry-muted"}
              formatKey={(k) => LANG_LABEL[k] || k}
            />
            <BarCard
              title="MCP tools invoked"
              icon={<Anchor className="h-4 w-4" />}
              buckets={stats.top_tools}
              gradientFn={() => "from-accent to-orange-500"}
              formatKey={(k) => k}
            />
            <BarCard
              title="Safety categories flagged"
              icon={<AlertTriangle className="h-4 w-4" />}
              buckets={stats.safety_categories}
              gradientFn={() => "from-rose-400 to-red-600"}
              emptyLabel="No safety triggers in the trace — every turn passed the gate."
              formatKey={(k) => k}
            />
          </div>

          <TrendCard buckets={stats.turns_by_day} />

          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <CardTitle className="normal-case tracking-normal text-sm font-semibold text-foreground">
                Recent conversations
              </CardTitle>
              <Badge variant="muted">{recent.length} turns</Badge>
            </CardHeader>
            <CardContent className="p-0">
              <RecentTable rows={recent} />
            </CardContent>
          </Card>
        </>
      )}

      {!stats && !error && loading && (
        <div className="grid gap-4 md:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="rounded-xl bg-white/50 animate-pulse h-32" />
          ))}
        </div>
      )}
    </div>
  );
}

type KpiTone = "ministry" | "destructive" | "success" | "accent";

const KPI_TONE: Record<KpiTone, { chip: string; accent: string }> = {
  ministry: {
    chip: "bg-gradient-to-br from-ministry to-ministry-muted text-white",
    accent: "from-ministry/10 to-transparent",
  },
  destructive: {
    chip: "bg-gradient-to-br from-rose-500 to-red-600 text-white",
    accent: "from-rose-500/10 to-transparent",
  },
  success: {
    chip: "bg-gradient-to-br from-emerald-500 to-teal-600 text-white",
    accent: "from-emerald-500/10 to-transparent",
  },
  accent: {
    chip: "bg-gradient-to-br from-accent to-orange-500 text-white",
    accent: "from-accent/10 to-transparent",
  },
};

function Kpi({
  icon,
  label,
  value,
  hint,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint?: string;
  tone: KpiTone;
}) {
  const t = KPI_TONE[tone];
  return (
    <Card className="relative overflow-hidden">
      <div
        className={cn(
          "pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b",
          t.accent
        )}
      />
      <CardContent className="relative pt-5">
        <div className="flex items-start justify-between gap-2">
          <div className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
            {label}
          </div>
          <div className={cn("h-9 w-9 rounded-lg grid place-items-center shadow-md", t.chip)}>
            {icon}
          </div>
        </div>
        <div className="mt-3 text-3xl font-bold tabular-nums text-foreground">{value}</div>
        {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
      </CardContent>
    </Card>
  );
}

function BarCard({
  title,
  icon,
  buckets,
  gradientFn,
  formatKey,
  emptyLabel = "No data yet",
}: {
  title: string;
  icon: React.ReactNode;
  buckets: Bucket[];
  gradientFn: (k: string) => string;
  formatKey: (k: string) => string;
  emptyLabel?: string;
}) {
  const max = Math.max(1, ...buckets.map((b) => b.value));
  const total = buckets.reduce((s, b) => s + b.value, 0);
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2 space-y-0">
        <div className="flex items-center gap-2">
          <span className="text-ministry">{icon}</span>
          <CardTitle className="normal-case tracking-normal text-sm font-semibold text-foreground">
            {title}
          </CardTitle>
        </div>
        {total > 0 && (
          <Badge variant="muted" className="tabular-nums">{total}</Badge>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {buckets.length === 0 ? (
          <div className="text-xs text-muted-foreground py-8 text-center flex flex-col items-center gap-2">
            <CheckCircle2 className="h-6 w-6 text-emerald-500/70" />
            <span>{emptyLabel}</span>
          </div>
        ) : (
          buckets.map((b) => (
            <div key={b.key} className="space-y-1.5">
              <div className="flex justify-between text-xs items-center">
                <span className="font-medium capitalize">
                  {formatKey(b.key).replace(/_/g, " ")}
                </span>
                <span className="text-muted-foreground tabular-nums">
                  {b.value}{" "}
                  <span className="opacity-60">
                    ({((b.value / (total || 1)) * 100).toFixed(0)}%)
                  </span>
                </span>
              </div>
              <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                <div
                  className={cn(
                    "h-full rounded-full bg-gradient-to-r transition-all duration-500",
                    gradientFn(b.key)
                  )}
                  style={{ width: `${(b.value / max) * 100}%` }}
                />
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function TrendCard({ buckets }: { buckets: Bucket[] }) {
  const max = Math.max(1, ...buckets.map((b) => b.value));
  return (
    <Card>
      <CardHeader className="flex-row items-center gap-2 space-y-0">
        <span className="text-ministry">
          <BarChart3 className="h-4 w-4" />
        </span>
        <CardTitle className="normal-case tracking-normal text-sm font-semibold text-foreground">
          Turns per day{" "}
          <span className="text-muted-foreground font-normal">
            · last {buckets.length || 0} days
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {buckets.length === 0 ? (
          <div className="text-xs text-muted-foreground py-10 text-center">
            No traces recorded yet — run a conversation to populate.
          </div>
        ) : (
          <div className="flex items-end gap-2 h-44 px-1">
            {buckets.map((b) => (
              <div
                key={b.key}
                className="flex-1 flex flex-col items-center gap-1.5 group"
                title={`${b.key}: ${b.value}`}
              >
                <div className="text-[10px] font-medium tabular-nums text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
                  {b.value}
                </div>
                <div className="w-full flex-1 flex items-end">
                  <div
                    className="w-full rounded-md bg-gradient-to-t from-ministry to-ministry-muted/70 shadow-sm group-hover:from-accent group-hover:to-orange-500 transition-colors"
                    style={{ height: `${(b.value / max) * 100}%`, minHeight: "4px" }}
                  />
                </div>
                <div className="text-[10px] text-muted-foreground tabular-nums">
                  {b.key.slice(5)}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RecentTable({ rows }: { rows: RecentTurn[] }) {
  if (rows.length === 0) {
    return (
      <div className="p-10 text-sm text-muted-foreground text-center">
        No turns yet — start a chat to see live activity.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-white/60 bg-ministry-soft/40 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">
            <th className="px-4 py-3 text-left">Time</th>
            <th className="px-4 py-3 text-left">Lang</th>
            <th className="px-4 py-3 text-left">Scheme</th>
            <th className="px-4 py-3 text-left">Message</th>
            <th className="px-4 py-3 text-right">Conf</th>
            <th className="px-4 py-3 text-right">Latency</th>
            <th className="px-4 py-3 text-right">Cites</th>
            <th className="px-4 py-3 text-left">Flags</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.trace_id}
              className="border-b border-white/40 last:border-0 hover:bg-ministry-soft/30 transition-colors"
            >
              <td className="px-4 py-2.5 whitespace-nowrap text-xs text-muted-foreground tabular-nums">
                {r.created_at ? new Date(r.created_at).toLocaleTimeString() : "—"}
              </td>
              <td className="px-4 py-2.5 text-xs uppercase font-medium">{r.lang}</td>
              <td className="px-4 py-2.5">
                {r.intent ? (
                  <span
                    className={cn(
                      "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize",
                      INTENT_CHIP[r.intent] || "bg-muted text-muted-foreground border-border"
                    )}
                  >
                    {r.intent}
                  </span>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </td>
              <td className="px-4 py-2.5 max-w-[420px] truncate" title={r.user_message}>
                {r.user_message}
              </td>
              <td className="px-4 py-2.5 text-right text-xs tabular-nums">
                {r.confidence !== null ? `${(r.confidence * 100).toFixed(0)}%` : "—"}
              </td>
              <td className="px-4 py-2.5 text-right text-xs text-muted-foreground tabular-nums">
                {r.total_latency_ms.toFixed(0)} ms
              </td>
              <td className="px-4 py-2.5 text-right text-xs tabular-nums">
                {r.citation_count}
              </td>
              <td className="px-4 py-2.5 space-x-1">
                {r.escalation && <Badge variant="destructive">esc</Badge>}
                {r.awaiting_input && <Badge variant="accent">slot</Badge>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
