import { API_BASE } from "./utils";
import { authFetch } from "./auth";

export type Citation = {
  source_doc: string;
  source_url?: string;
  section?: string | null;
};

export type ChatResponse = {
  response: string;
  response_en: string;
  intent: string | null;
  confidence: number | null;
  escalation: boolean;
  awaiting_input: boolean;
  citations: Citation[];
  trace_id: string;
  degraded_translation: boolean;
};

export async function postChat(input: {
  session_id: string;
  message: string;
  lang: string;
  channel?: string;
}): Promise<ChatResponse> {
  const r = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ channel: "web", ...input }),
  });
  if (!r.ok) throw new Error(`chat ${r.status}: ${await r.text()}`);
  return r.json();
}

// --------------------------------------------------------------------------- //
// Meta — languages, scheme cards, enums. Nothing about schemes/languages is
// hardcoded in the UI; it all comes from here (same source the orchestrator
// and router use).
// --------------------------------------------------------------------------- //
export type LanguageMeta = { code: string; name: string; native: string };
export type CapabilityCard = {
  scheme: string;
  display_name: string;
  description: string;
  safety_critical: boolean;
  fallback: boolean;
};
export type AppMeta = {
  app: { title: string; contract_version: string };
  llm: { live: boolean; provider: string; model: string; fast_model: string };
  languages: LanguageMeta[];
  cards: CapabilityCard[];
  enums: Record<string, string[]>;
};

export async function getMeta(): Promise<AppMeta> {
  const r = await authFetch(`/meta`, { cache: "no-store" });
  if (!r.ok) throw new Error(`meta ${r.status}`);
  return r.json();
}

// --------------------------------------------------------------------------- //
// Analytics — mirrors apps/backend/dashboard.py exactly (aggregates over the
// live audit trace, logs/interactions.jsonl).
// --------------------------------------------------------------------------- //
export type AnalyticsSummary = {
  window_hours: number | null;
  totals: {
    turns: number;
    sessions: number;
    escalations: number;
    escalation_rate: number;
    answered: number;
    grounding_rate: number;
    avg_citations: number;
    fallbacks: number;
    slot_questions: number;
    avg_latency_ms: number;
    max_latency_ms: number;
  };
  by_intent: Record<string, number>;
  by_lang: Record<string, number>;
  by_channel: Record<string, number>;
  by_district: Record<string, number>;
  escalation_by_category: Record<string, number>;
  safety_sources: Record<string, number>;
  tool_usage: Record<string, number>;
  timeline: { t: string; count: number; escalations: number }[];
};

export async function getAnalyticsSummary(hours?: number): Promise<AnalyticsSummary> {
  const qs = hours ? `?hours=${hours}` : "";
  const r = await authFetch(`/analytics/summary${qs}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`analytics/summary ${r.status}`);
  return r.json();
}

export type RecentTurn = {
  trace_id: string;
  session_id: string;
  created_at: string;
  channel: string;
  lang: string;
  user_message: string;
  intent: string | null;
  confidence: number | null;
  escalation: boolean;
  safety_category: string | null;
  safety_source: string | null;
  agent_used: string | null;
  district: string | null;
  tool_calls: string[];
  citation_count: number;
  awaiting_input: boolean;
  grounding_ok: boolean;
  fallback: boolean;
  total_latency_ms: number;
};

export async function getAnalyticsRecent(opts: {
  limit?: number;
  offset?: number;
  hours?: number;
}): Promise<{ count: number; total: number; offset: number; limit: number; items: RecentTurn[] }> {
  const params = new URLSearchParams();
  if (opts.limit) params.set("limit", String(opts.limit));
  if (opts.offset) params.set("offset", String(opts.offset));
  if (opts.hours) params.set("hours", String(opts.hours));
  const r = await authFetch(`/analytics/recent?${params.toString()}`, {
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`analytics/recent ${r.status}`);
  return r.json();
}
