"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Languages,
  Layers,
  MapPin,
  MessageSquare,
  RefreshCw,
  Search,
  ShieldCheck,
  Wrench,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { RequireAuth } from "@/components/require-auth";
import {
  getAnalyticsRecent,
  getAnalyticsSummary,
  getMeta,
  type AnalyticsSummary,
  type AppMeta,
  type RecentTurn,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const RANGES: { label: string; hours?: number }[] = [
  { label: "24h", hours: 24 },
  { label: "7d", hours: 24 * 7 },
  { label: "30d", hours: 24 * 30 },
  { label: "All time", hours: undefined },
];

const PAGE_SIZE = 25;
const LIVE_INTERVAL_MS = 15000;

// Deterministic color assignment for any key (scheme, tool, district, ...)
// so a new scheme/tool added on the backend gets a distinct color with zero
// frontend changes — nothing here is keyed to a specific known name.
const PALETTE = [
  { bar: "bg-emerald-500", chip: "bg-emerald-100 text-emerald-800 border-emerald-200" },
  { bar: "bg-sky-500", chip: "bg-sky-100 text-sky-800 border-sky-200" },
  { bar: "bg-fuchsia-500", chip: "bg-fuchsia-100 text-fuchsia-800 border-fuchsia-200" },
  { bar: "bg-amber-500", chip: "bg-amber-100 text-amber-800 border-amber-200" },
  { bar: "bg-violet-500", chip: "bg-violet-100 text-violet-800 border-violet-200" },
  { bar: "bg-rose-500", chip: "bg-rose-100 text-rose-800 border-rose-200" },
  { bar: "bg-cyan-500", chip: "bg-cyan-100 text-cyan-800 border-cyan-200" },
  { bar: "bg-lime-500", chip: "bg-lime-100 text-lime-800 border-lime-200" },
];

function colorFor(key: string) {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

function titleCase(key: string) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function intentLabel(key: string, meta: AppMeta | null) {
  const card = meta?.cards.find((c) => c.scheme === key);
  return card?.display_name || titleCase(key);
}

function langLabel(code: string, meta: AppMeta | null) {
  const l = meta?.languages.find((x) => x.code === code);
  return l ? l.native : code.toUpperCase();
}

function fmtLatency(ms: number) {
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${ms.toFixed(0)} ms`;
}

function fmtTime(iso: string) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function timelineLabel(t: string) {
  const parts = t.split(" ");
  return parts.length === 2 ? parts[1] : t.slice(5);
}

export default function DashboardPage() {
  return (
    <RequireAuth>
      <DashboardContent />
    </RequireAuth>
  );
}

function DashboardContent() {
  const [meta, setMeta] = useState<AppMeta | null>(null);
  const [hours, setHours] = useState<number | undefined>(undefined);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [items, setItems] = useState<RecentTurn[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const [search, setSearch] = useState("");
  const [intentFilter, setIntentFilter] = useState("all");
  const [escalationOnly, setEscalationOnly] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  const itemsCountRef = useRef(0);
  itemsCountRef.current = items.length;

  useEffect(() => {
    getMeta()
      .then(setMeta)
      .catch(() => {
        /* meta is presentation-only (labels/colors) — dashboard still works without it */
      });
  }, []);

  const loadAll = useCallback(
    async (opts: { silent?: boolean } = {}) => {
      if (!opts.silent) setLoading(true);
      setError(null);
      try {
        const wantLimit = Math.min(Math.max(itemsCountRef.current, PAGE_SIZE), 500);
        const [s, r] = await Promise.all([
          getAnalyticsSummary(hours),
          getAnalyticsRecent({ limit: wantLimit, hours }),
        ]);
        setSummary(s);
        setItems(r.items);
        setTotal(r.total);
        setLastUpdated(new Date());
      } catch (e: any) {
        setError(e.message || "Failed to load dashboard");
      } finally {
        setLoading(false);
      }
    },
    [hours]
  );

  useEffect(() => {
    setItems([]);
    itemsCountRef.current = 0;
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hours]);

  useEffect(() => {
    if (!live) return;
    const id = setInterval(() => loadAll({ silent: true }), LIVE_INTERVAL_MS);
    return () => clearInterval(id);
  }, [live, loadAll]);

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const r = await getAnalyticsRecent({
        limit: PAGE_SIZE,
        offset: items.length,
        hours,
      });
      setItems((prev) => [...prev, ...r.items]);
      setTotal(r.total);
    } catch (e: any) {
      setError(e.message || "Failed to load more");
    } finally {
      setLoadingMore(false);
    }
  };

  const filtered = items.filter((it) => {
    if (escalationOnly && !it.escalation) return false;
    if (intentFilter !== "all" && (it.intent || "unrouted") !== intentFilter) return false;
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      if (
        !it.user_message.toLowerCase().includes(q) &&
        !it.trace_id.toLowerCase().includes(q) &&
        !it.session_id.toLowerCase().includes(q)
      ) {
        return false;
      }
    }
    return true;
  });

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                live ? "bg-emerald-500" : "bg-muted-foreground/40"
              )}
            />
            <span className="text-[11px] uppercase tracking-widest text-muted-foreground font-semibold">
              MoWCD · {live ? "Live analytics" : "Analytics"}
            </span>
          </div>
          <h1 className="text-3xl font-semibold text-foreground">Ministry Dashboard</h1>
          <p className="text-sm text-muted-foreground max-w-xl">
            Every citizen turn is audited — safe, grounded, and cited. This view
            reads the orchestrator's audit trace directly, live.
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex rounded-md border border-border overflow-hidden">
            {RANGES.map((r) => (
              <button
                key={r.label}
                onClick={() => setHours(r.hours)}
                className={cn(
                  "px-3 py-1.5 text-xs font-medium transition-colors",
                  hours === r.hours
                    ? "bg-secondary text-foreground"
                    : "text-muted-foreground hover:bg-secondary/60"
                )}
              >
                {r.label}
              </button>
            ))}
          </div>
          <Button
            variant={live ? "default" : "outline"}
            size="sm"
            onClick={() => setLive((v) => !v)}
          >
            {live ? "Live: on" : "Live: off"}
          </Button>
          <Button variant="outline" size="sm" onClick={() => loadAll()} disabled={loading}>
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </div>

      {lastUpdated && (
        <div className="text-[11px] text-muted-foreground -mt-4">
          Last updated {lastUpdated.toLocaleTimeString()}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive flex items-center gap-3">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          <span>{error} — is the backend running on port 8000?</span>
        </div>
      )}

      {summary && summary.totals.turns === 0 && !error && (
        <div className="rounded-lg border border-border p-10 text-center text-sm text-muted-foreground">
          No interactions recorded yet for this window — start a chat to populate live analytics.
        </div>
      )}

      {summary && summary.totals.turns > 0 && (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <Kpi
              icon={<MessageSquare className="h-5 w-5" />}
              label="Total turns"
              value={summary.totals.turns.toLocaleString()}
              hint={`${summary.totals.sessions} unique sessions`}
              tone="neutral"
            />
            <Kpi
              icon={<AlertTriangle className="h-5 w-5" />}
              label="Safety escalations"
              value={summary.totals.escalations.toString()}
              hint={`${(summary.totals.escalation_rate * 100).toFixed(1)}% of turns routed to helplines`}
              tone="destructive"
            />
            <Kpi
              icon={<ShieldCheck className="h-5 w-5" />}
              label="Grounded reply rate"
              value={`${(summary.totals.grounding_rate * 100).toFixed(0)}%`}
              hint={`avg ${summary.totals.avg_citations} citations per reply`}
              tone="success"
            />
            <Kpi
              icon={<Clock className="h-5 w-5" />}
              label="Avg latency"
              value={fmtLatency(summary.totals.avg_latency_ms)}
              hint={`max ${fmtLatency(summary.totals.max_latency_ms)}`}
              tone="accent"
            />
            <Kpi
              icon={<Wrench className="h-5 w-5" />}
              label="Specialist fallbacks"
              value={summary.totals.fallbacks.toString()}
              hint="handoff errors caught safely"
              tone="neutral"
            />
            <Kpi
              icon={<CheckCircle2 className="h-5 w-5" />}
              label="Clarifying questions"
              value={summary.totals.slot_questions.toString()}
              hint="turns awaiting more info"
              tone="neutral"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <BarCard
              title="Scheme distribution"
              icon={<Layers className="h-4 w-4" />}
              data={summary.by_intent}
              labelFn={(k) => intentLabel(k, meta)}
            />
            <BarCard
              title="Languages"
              icon={<Languages className="h-4 w-4" />}
              data={summary.by_lang}
              labelFn={(k) => langLabel(k, meta)}
            />
            <BarCard
              title="MCP tools invoked"
              icon={<Wrench className="h-4 w-4" />}
              data={summary.tool_usage}
              labelFn={titleCase}
              emptyLabel="No tool calls recorded yet."
            />
            <BarCard
              title="Safety categories flagged"
              icon={<AlertTriangle className="h-4 w-4" />}
              data={summary.escalation_by_category}
              labelFn={titleCase}
              emptyLabel="No safety triggers in the trace — every turn passed the gate."
            />
            <BarCard
              title="Channels"
              icon={<MessageSquare className="h-4 w-4" />}
              data={summary.by_channel}
              labelFn={titleCase}
            />
            <BarCard
              title="Top districts"
              icon={<MapPin className="h-4 w-4" />}
              data={summary.by_district}
              labelFn={titleCase}
              emptyLabel="No district signal collected yet."
            />
          </div>

          <TimelineCard timeline={summary.timeline} />

          <Card>
            <CardHeader className="space-y-3">
              <div className="flex-row items-center justify-between space-y-0 flex flex-wrap gap-2">
                <CardTitle className="normal-case tracking-normal text-sm font-semibold text-foreground">
                  Recent conversations
                </CardTitle>
                <Badge variant="muted">
                  {items.length} of {total} loaded
                </Badge>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative flex-1 min-w-[200px]">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                  <Input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search message, trace or session id..."
                    className="pl-8 h-9"
                  />
                </div>
                <select
                  value={intentFilter}
                  onChange={(e) => setIntentFilter(e.target.value)}
                  className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                >
                  <option value="all">All schemes</option>
                  {Object.keys(summary.by_intent).map((k) => (
                    <option key={k} value={k}>
                      {intentLabel(k, meta)}
                    </option>
                  ))}
                </select>
                <label className="flex items-center gap-1.5 text-sm text-muted-foreground px-1">
                  <input
                    type="checkbox"
                    checked={escalationOnly}
                    onChange={(e) => setEscalationOnly(e.target.checked)}
                  />
                  Escalations only
                </label>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <RecentTable
                rows={filtered}
                meta={meta}
                expanded={expanded}
                onToggle={(id) => setExpanded((cur) => (cur === id ? null : id))}
              />
              <div className="flex justify-center p-4 border-t border-border">
                {items.length < total ? (
                  <Button variant="outline" size="sm" onClick={loadMore} disabled={loadingMore}>
                    {loadingMore ? "Loading…" : `Load more (${total - items.length} remaining)`}
                  </Button>
                ) : items.length > 0 ? (
                  <span className="text-xs text-muted-foreground">
                    All {total} interactions in this window are loaded.
                  </span>
                ) : null}
              </div>
            </CardContent>
          </Card>
        </>
      )}

      {!summary && !error && loading && (
        <div className="grid gap-4 md:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="rounded-lg border border-border bg-secondary/40 animate-pulse h-32" />
          ))}
        </div>
      )}
    </div>
  );
}

type KpiTone = "neutral" | "destructive" | "success" | "accent";

const KPI_TONE: Record<KpiTone, string> = {
  neutral: "bg-secondary text-foreground",
  destructive: "bg-rose-50 text-rose-700",
  success: "bg-emerald-50 text-emerald-700",
  accent: "bg-amber-50 text-amber-700",
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
  return (
    <Card>
      <CardContent className="pt-5">
        <div className="flex items-start justify-between gap-2">
          <div className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
            {label}
          </div>
          <div className={cn("h-9 w-9 rounded-lg grid place-items-center", KPI_TONE[tone])}>
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
  data,
  labelFn,
  emptyLabel = "No data yet",
}: {
  title: string;
  icon: React.ReactNode;
  data: Record<string, number>;
  labelFn: (k: string) => string;
  emptyLabel?: string;
}) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  const total = entries.reduce((s, [, v]) => s + v, 0);
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2 space-y-0">
        <div className="flex items-center gap-2">
          <span className="text-foreground">{icon}</span>
          <CardTitle className="normal-case tracking-normal text-sm font-semibold text-foreground">
            {title}
          </CardTitle>
        </div>
        {total > 0 && <Badge variant="muted" className="tabular-nums">{total}</Badge>}
      </CardHeader>
      <CardContent className="space-y-3">
        {entries.length === 0 ? (
          <div className="text-xs text-muted-foreground py-8 text-center flex flex-col items-center gap-2">
            <CheckCircle2 className="h-6 w-6 text-emerald-500/70" />
            <span>{emptyLabel}</span>
          </div>
        ) : (
          entries.map(([k, v]) => (
            <div key={k} className="space-y-1.5">
              <div className="flex justify-between text-xs items-center">
                <span className="font-medium">{labelFn(k)}</span>
                <span className="text-muted-foreground tabular-nums">
                  {v} <span className="opacity-60">({((v / (total || 1)) * 100).toFixed(0)}%)</span>
                </span>
              </div>
              <div className="h-2 rounded-full bg-secondary overflow-hidden">
                <div
                  className={cn("h-full rounded-full transition-all duration-500", colorFor(k).bar)}
                  style={{ width: `${(v / max) * 100}%` }}
                />
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function TimelineCard({ timeline }: { timeline: AnalyticsSummary["timeline"] }) {
  const max = Math.max(1, ...timeline.map((b) => b.count));
  return (
    <Card>
      <CardHeader className="flex-row items-center gap-2 space-y-0">
        <span className="text-foreground">
          <BarChart3 className="h-4 w-4" />
        </span>
        <CardTitle className="normal-case tracking-normal text-sm font-semibold text-foreground">
          Turns over time
          <span className="text-muted-foreground font-normal"> · {timeline.length || 0} buckets</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {timeline.length === 0 ? (
          <div className="text-xs text-muted-foreground py-10 text-center">
            No traces recorded yet — run a conversation to populate.
          </div>
        ) : (
          <div className="flex items-end gap-1.5 h-44 px-1">
            {timeline.map((b) => (
              <div
                key={b.t}
                className="flex-1 flex flex-col items-center gap-1.5 group"
                title={`${b.t}: ${b.count} turns, ${b.escalations} escalations`}
              >
                <div className="text-[10px] font-medium tabular-nums text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
                  {b.count}
                </div>
                <div className="w-full flex-1 flex items-end">
                  <div
                    className="w-full rounded-t-sm bg-primary/80 group-hover:bg-primary transition-colors flex flex-col justify-end overflow-hidden"
                    style={{ height: `${(b.count / max) * 100}%`, minHeight: "4px" }}
                  >
                    {b.escalations > 0 && (
                      <div
                        className="w-full bg-destructive"
                        style={{ height: `${(b.escalations / b.count) * 100}%` }}
                      />
                    )}
                  </div>
                </div>
                <div className="text-[10px] text-muted-foreground tabular-nums">
                  {timelineLabel(b.t)}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RecentTable({
  rows,
  meta,
  expanded,
  onToggle,
}: {
  rows: RecentTurn[];
  meta: AppMeta | null;
  expanded: string | null;
  onToggle: (id: string) => void;
}) {
  if (rows.length === 0) {
    return (
      <div className="p-10 text-sm text-muted-foreground text-center">
        No turns match the current filters.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-secondary/40 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">
            <th className="px-4 py-3 text-left w-8"></th>
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
          {rows.map((r) => {
            const isOpen = expanded === r.trace_id;
            const intentColor = r.intent ? colorFor(r.intent).chip : "";
            return (
              <Fragment key={r.trace_id}>
                <tr
                  onClick={() => onToggle(r.trace_id)}
                  className="border-b border-border last:border-0 hover:bg-secondary/40 transition-colors cursor-pointer"
                >
                  <td className="px-4 py-2.5 text-muted-foreground">
                    {isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                  </td>
                  <td className="px-4 py-2.5 whitespace-nowrap text-xs text-muted-foreground tabular-nums">
                    {fmtTime(r.created_at)}
                  </td>
                  <td className="px-4 py-2.5 text-xs uppercase font-medium">{r.lang}</td>
                  <td className="px-4 py-2.5">
                    {r.intent ? (
                      <span
                        className={cn(
                          "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium",
                          intentColor || "bg-muted text-muted-foreground border-border"
                        )}
                      >
                        {intentLabel(r.intent, meta)}
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
                    {fmtLatency(r.total_latency_ms)}
                  </td>
                  <td className="px-4 py-2.5 text-right text-xs tabular-nums">{r.citation_count}</td>
                  <td className="px-4 py-2.5 space-x-1">
                    {r.escalation && <Badge variant="destructive">esc</Badge>}
                    {r.awaiting_input && <Badge variant="accent">slot</Badge>}
                    {r.fallback && <Badge variant="muted">fallback</Badge>}
                    {!r.grounding_ok && <Badge variant="outline">ungrounded</Badge>}
                  </td>
                </tr>
                {isOpen && (
                  <tr className="bg-secondary/30 border-b border-border">
                    <td colSpan={9} className="px-4 py-3">
                      <div className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2 lg:grid-cols-3 text-xs">
                        <Detail label="Trace ID" value={r.trace_id} mono />
                        <Detail label="Session ID" value={r.session_id} mono />
                        <Detail label="Channel" value={titleCase(r.channel)} />
                        <Detail label="Agent used" value={r.agent_used ? titleCase(r.agent_used) : "—"} />
                        <Detail label="District" value={r.district || "—"} />
                        <Detail label="Safety source" value={r.safety_source || "—"} />
                        <Detail label="Safety category" value={r.safety_category || "—"} />
                        <Detail
                          label="Tool calls"
                          value={r.tool_calls.length ? r.tool_calls.map(titleCase).join(", ") : "—"}
                        />
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Detail({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex gap-2">
      <span className="text-muted-foreground shrink-0">{label}:</span>
      <span className={cn("text-foreground truncate", mono && "font-mono text-[11px]")}>{value}</span>
    </div>
  );
}
