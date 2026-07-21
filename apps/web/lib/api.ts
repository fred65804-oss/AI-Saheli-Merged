import { API_BASE } from "./utils";
import { authFetch } from "./auth";

export type PipelineTimings = {
  asr_ms: number;
  translation_in_ms: number;
  orchestrator_ms: number;
  translation_out_ms: number;
  tts_ms: number;
  total_request_ms: number;
}

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
  timings: PipelineTimings;
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
// Voice — one full voice turn through the backend pipeline:
// audio → faster-whisper ASR → orchestrator → NMT → edge-tts → audio.
// The browser only records and plays; all speech models run server-side
// (no in-browser model downloads, near-human Hindi TTS via edge-tts).
// --------------------------------------------------------------------------- //
export type VoiceResponse = {
  transcript: string;
  response: string;
  response_en: string;
  audio_base64: string;
  intent: string | null;
  confidence: number | null;
  escalation: boolean;
  awaiting_input: boolean;
  citations: Citation[];
  trace_id: string;
  degraded: boolean;
  timings: PipelineTimings;
};

export async function postVoice(input: {
  session_id: string;
  audio_base64: string;
  lang: string;
  channel?: string;
}): Promise<VoiceResponse> {
  const r = await fetch(`${API_BASE}/voice`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ channel: "voice", ...input }),
  });
  if (!r.ok) {
    // FastAPI errors carry {"detail": "..."} — surface the human-readable
    // message (e.g. "Could not hear any speech in that recording…").
    let detail = "";
    try {
      detail = (await r.json())?.detail ?? "";
    } catch {
      /* non-JSON body */
    }
    throw new Error(detail || `voice ${r.status}`);
  }
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
  // Pydantic model_json_schema() of EligibilityRequest — drives the dynamic
  // eligibility form (fields, types, enum choices come from the SAME model
  // the rules engine validates against).
  eligibility_schema: Record<string, unknown>;
};

export async function getMeta(): Promise<AppMeta> {
  const r = await authFetch(`/meta`, { cache: "no-store" });
  if (!r.ok) throw new Error(`meta ${r.status}`);
  return r.json();
}

export type HealthInfo = {
  status: string;
  llm: string;
  provider: string;
  model: string;
  language: string;
};

export async function getHealth(): Promise<HealthInfo> {
  const r = await fetch(`${API_BASE}/health`, { cache: "no-store" });
  if (!r.ok) throw new Error(`health ${r.status}`);
  return r.json();
}

// --------------------------------------------------------------------------- //
// Tool passthroughs — the Ministry-internal tool explorer. All of these are
// login-walled on the backend (mounted behind get_current_user), hence
// authFetch. Shapes mirror the mcp/* Pydantic schemas exactly.
// --------------------------------------------------------------------------- //
export type KBChunk = {
  text: string;
  scheme: string;
  doc: string;
  heading_path_str: string;
  page_start: number | null;
  page_end: number | null;
  chunk_id: string | null;
  score: number;
  citation: string;
};

export async function toolKbSearch(input: {
  query: string;
  scheme?: string | null;
  k?: number;
}): Promise<{ chunks: KBChunk[]; latency_ms: number }> {
  const r = await authFetch(`/tools/kb-search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!r.ok) throw new Error(`kb-search ${r.status}: ${await r.text()}`);
  return r.json();
}

export type RuleResult = {
  scheme: string;
  eligible: boolean | null;
  benefit_summary: string;
  amount: string | null;
  instalments: string | null;
  reason: string;
  needs: string[];
  source_doc: string;
  source_url: string;
};

export type EligibilityResult = {
  eligible: RuleResult[];
  ineligible: RuleResult[];
  uncertain: RuleResult[];
  checked_schemes: string[];
  latency_ms: number;
};

export async function toolEligibility(
  body: Record<string, unknown>
): Promise<EligibilityResult> {
  const r = await authFetch(`/tools/eligibility`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`eligibility ${r.status}: ${await r.text()}`);
  return r.json();
}

export type Facility = {
  id: string;
  name: string;
  type: string;
  district: string;
  state: string;
  address: string;
  phone: string | null;
  hours: string | null;
  source: string;
};

export async function toolGeo(input: {
  service_type: string;
  district: string;
  state?: string | null;
  limit?: number;
}): Promise<{
  facilities: Facility[];
  district_matched: string | null;
  count: number;
  note: string | null;
  latency_ms: number;
}> {
  const r = await authFetch(`/tools/geo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!r.ok) throw new Error(`geo ${r.status}: ${await r.text()}`);
  return r.json();
}

export type HelplineEntry = {
  id: string;
  name: string;
  number: string | null;
  categories: string[];
  when_to_call: string;
  hours: string | null;
  languages: string[];
  scheme: string | null;
  priority: number;
  source_url: string;
  escalation_note: string | null;
};

export async function toolHelpline(input: {
  category: string;
  lang?: string;
  scheme?: string | null;
}): Promise<{
  primary: HelplineEntry;
  secondary: HelplineEntry[];
  escalation_note: string | null;
  latency_ms: number;
}> {
  const r = await authFetch(`/tools/helpline`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!r.ok) throw new Error(`helpline ${r.status}: ${await r.text()}`);
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
