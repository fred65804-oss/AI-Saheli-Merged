/* AI Saheli — minimal frontend.
   All data is fetched from the backend (/meta, /analytics/summary,
   /analytics/recent, /chat). Nothing scheme-, language- or KPI-specific is
   hardcoded — the UI shape adapts to what the backend returns. */

const $ = (id) => document.getElementById(id);
const api = (path, opts) => fetch(path, opts).then(async (r) => {
  if (!r.ok) throw new Error(`${path} ${r.status}: ${await r.text().catch(() => "")}`);
  return r.json();
});

const state = {
  sessionId: "web-" + Math.random().toString(36).slice(2, 10),
  lang: "en",
  languages: [{ code: "en", label: "English" }],
};

/* ---------- Tabs ---------- */
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b === btn));
    const target = btn.dataset.tab;
    $("tab-chat").classList.toggle("hidden", target !== "chat");
    $("tab-dashboard").classList.toggle("hidden", target !== "dashboard");
    if (target === "dashboard") loadDashboard();
  });
});

/* ---------- Boot: /meta ---------- */
async function boot() {
  try {
    const meta = await api("/meta");
    if (Array.isArray(meta.languages) && meta.languages.length) {
      state.languages = meta.languages;
    }
    const sel = $("lang");
    sel.innerHTML = "";
    state.languages.forEach((l) => {
      const opt = document.createElement("option");
      opt.value = l.code;
      opt.textContent = l.label || l.code;
      sel.appendChild(opt);
    });
    sel.value = state.lang;
    sel.addEventListener("change", () => (state.lang = sel.value));

    const live = meta?.llm?.live;
    const provider = meta?.llm?.provider || "offline";
    const model = meta?.llm?.model || "";
    $("statusDot").classList.add(live ? "ok" : "warn");
    $("statusText").textContent = live ? `${provider} · ${model}` : "offline mode";

    greeting();
  } catch (e) {
    $("statusDot").classList.add("err");
    $("statusText").textContent = "backend unreachable";
    $("chatLog").innerHTML = `<div class="msg empty">Cannot reach backend. Is the API server running?</div>`;
  }
}

function greeting() {
  const log = $("chatLog");
  log.innerHTML = "";
  const el = document.createElement("div");
  el.className = "msg empty";
  el.textContent = "Namaste. Ask about Poshan 2.0, Mission Vatsalya, or Mission Shakti.";
  log.appendChild(el);
}

/* ---------- Chat ---------- */
$("composer").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const input = $("input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  addMsg("user", text);
  $("sendBtn").disabled = true;
  $("chatHint").textContent = "Thinking…";
  try {
    const res = await api("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.sessionId,
        message: text,
        lang: state.lang,
        channel: "web",
      }),
    });
    addBotMsg(res);
    $("chatHint").textContent = res.trace_id ? `trace ${res.trace_id.slice(0, 8)}` : "";
  } catch (e) {
    addMsg("bot", "Sorry — something went wrong reaching the assistant.");
    $("chatHint").textContent = String(e).slice(0, 120);
  } finally {
    $("sendBtn").disabled = false;
    input.focus();
  }
});

function addMsg(role, text) {
  const log = $("chatLog");
  const empty = log.querySelector(".msg.empty");
  if (empty) empty.remove();
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.textContent = text;
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
  return el;
}

function addBotMsg(res) {
  let cls = "bot";
  if (res.escalation) cls += " escalation";
  else if (res.awaiting_input) cls += " await";
  const log = $("chatLog");
  const empty = log.querySelector(".msg.empty");
  if (empty) empty.remove();
  const el = document.createElement("div");
  el.className = `msg ${cls}`;
  const body = document.createElement("div");
  body.textContent = res.response || "(no response)";
  el.appendChild(body);

  if (Array.isArray(res.citations) && res.citations.length) {
    const cites = document.createElement("div");
    cites.className = "cites";
    cites.innerHTML =
      `<div><strong>Sources</strong></div>` +
      res.citations
        .map((c) => {
          const label = [c.source_doc, c.section].filter(Boolean).join(" — ");
          const safe = escapeHtml(label);
          return c.source_url
            ? `<div class="cite-row">• <a href="${escapeAttr(c.source_url)}" target="_blank" rel="noopener">${safe}</a></div>`
            : `<div class="cite-row">• ${safe}</div>`;
        })
        .join("");
    el.appendChild(cites);
  }
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function escapeAttr(s) { return escapeHtml(s); }

/* ---------- Dashboard ---------- */
$("refreshBtn").addEventListener("click", loadDashboard);

// KPI cards match the fields the backend's /analytics/summary already returns.
const KPI_SPEC = [
  { key: "turns", label: "Turns", tone: "accent" },
  { key: "sessions", label: "Sessions" },
  { key: "escalations", label: "Escalations", tone: "danger",
    sub: (t) => t.turns ? `${(t.escalation_rate * 100).toFixed(1)}% of turns` : "" },
  { key: "answered", label: "Answered", tone: "ok",
    sub: (t) => `${(t.grounding_rate * 100).toFixed(0)}% grounded` },
  { key: "avg_citations", label: "Avg citations", fmt: (v) => v.toFixed(2) },
  { key: "slot_questions", label: "Slot questions" },
  { key: "fallbacks", label: "Fallbacks", tone: "warn" },
  { key: "avg_latency_ms", label: "Avg latency", fmt: (v) => `${Math.round(v)} ms`,
    sub: (t) => t.max_latency_ms ? `max ${Math.round(t.max_latency_ms)} ms` : "" },
];

async function loadDashboard() {
  $("dashUpdated").textContent = "loading…";
  try {
    const [summary, recent] = await Promise.all([
      api("/analytics/summary"),
      api("/analytics/recent?limit=30"),
    ]);
    renderKpis(summary.totals || {});
    renderBars("byIntent", summary.by_intent);
    renderBars("byLang", summary.by_lang);
    renderBars("byChannel", summary.by_channel);
    renderBars("toolUsage", summary.tool_usage);
    renderBars("escByCat", summary.escalation_by_category, "danger");
    renderBars("byDistrict", summary.by_district);
    renderRecent(recent.items || []);
    $("dashUpdated").textContent =
      `${summary.totals?.turns ?? 0} turns · updated ${new Date().toLocaleTimeString()}`;
  } catch (e) {
    $("dashUpdated").textContent = `error: ${String(e).slice(0, 120)}`;
  }
}

function renderKpis(t) {
  const grid = $("kpiGrid");
  grid.innerHTML = "";
  KPI_SPEC.forEach((spec) => {
    const raw = t[spec.key];
    const value = raw == null
      ? "—"
      : spec.fmt
        ? spec.fmt(raw)
        : typeof raw === "number"
          ? raw.toLocaleString()
          : String(raw);
    const sub = spec.sub ? spec.sub(t) : "";
    const el = document.createElement("div");
    el.className = `kpi ${spec.tone || ""}`;
    el.innerHTML =
      `<div class="k-label">${escapeHtml(spec.label)}</div>` +
      `<div class="k-value">${escapeHtml(value)}</div>` +
      (sub ? `<div class="k-sub">${escapeHtml(sub)}</div>` : "");
    grid.appendChild(el);
  });
}

function renderBars(id, obj, tone) {
  const host = $(id);
  host.innerHTML = "";
  const entries = Object.entries(obj || {});
  if (!entries.length) {
    host.innerHTML = `<div class="empty-state">No data yet.</div>`;
    return;
  }
  const max = Math.max(...entries.map(([, v]) => v || 0));
  entries.slice(0, 8).forEach(([label, value]) => {
    const pct = max ? Math.max(3, Math.round((value / max) * 100)) : 0;
    const row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML =
      `<div class="b-label" title="${escapeAttr(label)}">${escapeHtml(label)}</div>` +
      `<div class="b-track"><div class="b-fill ${tone || ""}" style="width:${pct}%"></div></div>` +
      `<div class="b-val">${escapeHtml(String(value))}</div>`;
    host.appendChild(row);
  });
}

function renderRecent(items) {
  const tbody = $("recent").querySelector("tbody");
  tbody.innerHTML = "";
  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty-state">No interactions yet.</td></tr>`;
    return;
  }
  items.forEach((r) => {
    const flags = [];
    if (r.escalation) flags.push(`<span class="pill esc">escalation</span>`);
    if (r.awaiting_input) flags.push(`<span class="pill await">awaiting</span>`);
    if (r.fallback) flags.push(`<span class="pill fb">fallback</span>`);
    const intent = r.intent
      ? `<span class="pill intent">${escapeHtml(r.intent)}</span>`
      : `<span class="muted">—</span>`;
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td>${escapeHtml(fmtTime(r.created_at))}</td>` +
      `<td>${escapeHtml(r.channel || "")}</td>` +
      `<td>${escapeHtml(r.lang || "")}</td>` +
      `<td>${intent}</td>` +
      `<td class="msg-cell" title="${escapeAttr(r.user_message || "")}">${escapeHtml(r.user_message || "")}</td>` +
      `<td>${flags.join(" ") || `<span class="muted">—</span>`}</td>` +
      `<td class="num">${r.citation_count ?? 0}</td>` +
      `<td class="num">${Math.round(r.total_latency_ms || 0)}</td>`;
    tbody.appendChild(tr);
  });
}

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return iso;
  }
}

boot();
