import { API_BASE } from "./utils";

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

export type Bucket = { key: string; value: number };
export type DashboardStats = {
  kpis: {
    total_turns: number;
    unique_sessions: number;
    escalations: number;
    escalation_rate: number;
    awaiting_input: number;
    avg_confidence: number | null;
    avg_latency_ms: number | null;
    grounded_share: number | null;
    fallback_count: number;
  };
  intents: Bucket[];
  languages: Bucket[];
  channels: Bucket[];
  safety_categories: Bucket[];
  top_tools: Bucket[];
  turns_by_day: Bucket[];
  updated_at: string;
};

export async function getStats(): Promise<DashboardStats> {
  const r = await fetch(`${API_BASE}/dashboard/stats`, { cache: "no-store" });
  if (!r.ok) throw new Error(`stats ${r.status}`);
  return r.json();
}

export type RecentTurn = {
  trace_id: string;
  session_id: string;
  created_at: string;
  channel: string;
  lang: string;
  intent: string | null;
  confidence: number | null;
  escalation: boolean;
  awaiting_input: boolean;
  user_message: string;
  agent_used: string | null;
  citation_count: number;
  total_latency_ms: number;
};

export async function getRecent(limit = 30): Promise<{ turns: RecentTurn[] }> {
  const r = await fetch(`${API_BASE}/dashboard/recent?limit=${limit}`, {
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`recent ${r.status}`);
  return r.json();
}
