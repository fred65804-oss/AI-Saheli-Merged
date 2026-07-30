# AI Saheli — Future Work

Audit date: **2026-07-30**. Scope: this repo (`AI-Saheli-Merged`) at commit `70e4ee4`
plus uncommitted working-tree changes.

Everything here was verified against the code, the test suite, the runtime log, and
the live demo URL — not inferred from documentation. Where a claim is unverified it
says so.

---

## 0. Deployment status — resolved

**This repo is the product.** `https://ai-saheli-egov-poc.azurewebsites.net` is a
third-party reference deployment (Vite/React SPA + Express, `gpt-4o-mini`) — not ours,
and not a deployment of this codebase. It carries no work we own and is not a migration
target.

The real consequence stands, though, and moves to §3.7: **this repo is not currently
deployed anywhere.** `.github/workflows/cd.yml` builds and pushes images to GHCR
correctly, then no-ops both deploy jobs because `STAGING_HOST` / `PROD_HOST` are unset.
There is no environment where this code runs for an audience, and no record of what
version anyone last saw.

Choosing and provisioning a deployment target is therefore the largest open dependency
in this document — but it blocks none of §1–§2, which are correctness and are worth
landing first regardless.

---

## Progress log

| Date | Item | Result |
|---|---|---|
| 2026-07-30 | §1.3 working-tree triage | All 5 WIP changes reviewed and kept (prompt quality, router topic-change, static greeting UI, PS1 BOM). Work branch `fix/p0-imports-tests-kb` cut from `main`. **Dependabot backlog still open.** |
| 2026-07-30 | §1.1 missing imports | **Done.** Fixed; 6 overview tests green. |
| 2026-07-30 | §1.2 stale tests | **Done.** Suite green, 118 passing. Found and fixed one real latent bug en route (see below). |
| 2026-07-30 | §2.1 KB switched off | **Done.** Enabled and verified: 2,319 points, warm query ~0.14 s. |

Verified during the above, worth recording:

- The Qdrant index holds **2,319** points, not the 2,579 quoted in `.claude/CLAUDE.md`
  (likely post-`clean_chunks.py`). Update that doc when convenient.
- Resolved Azure model is **`gpt-4o-mini`**, not `gpt-41` as the `config.py` comment
  implies. The comment describes what was deployed in the portal; `.env` selects
  `gpt-4o-mini`. Worth a deliberate decision — `gpt-41` is the stronger model for
  grounded synthesis.
- Cold KB retrieval is **~60 s** (model load), warm is **~0.14 s**. This is exactly
  what `POST /warmup` exists for, and it makes running warmup before a demo
  non-optional now that the KB is on.

---

## 1. P0 — Broken right now

### 1.1 `answer_scheme_overview` is not imported in two specialists — ✅ DONE (2026-07-30)

`agents/specialists/poshan.py:79` and `agents/specialists/vatsalya.py:98` call
`answer_scheme_overview(...)`. Neither file imports it. Only
`agents/specialists/shakti.py:63` has the import.

Every scheme-overview question routed to Poshan or Vatsalya raises `NameError` and
falls through to the specialist-failure path. Already observed in production logs:

```
2026-07-28 15:01:07,356 ERROR agents.orchestrator.nodes: specialist handoff failed (intent=poshan)
Traceback (most recent call last):
NameError: name 'answer_scheme_overview' is not defined
```

"What is Poshan 2.0?" and "What is Mission Vatsalya?" are the most probable opening
questions from a Ministry audience. This is a two-line fix.

**Fixed:** added `from agents.specialists.overview_answer import answer_scheme_overview`
to `poshan.py` and `vatsalya.py`. Six failing tests went green; failures 10 → 5.

### 1.2 Test suite is red — 10 of 116 failing — ✅ DONE (2026-07-30)

Run with the project venv (`.venv/Scripts/python -m pytest`); the system Python lacks
`sqlalchemy` and cannot even collect.

| Failing test | Cause |
|---|---|
| `test_specialists_real.py::test_overview_returns_answer_without_slots` (×3) | §1.1 |
| `test_graph.py::test_scheme_overview_never_collects_personal_slots` (×2) | §1.1 |
| `test_e2e_knowledge_base_flow.py::test_full_conversation_with_real_knowledge_base` | §1.1 / KB disabled (§2.1) |
| `test_graph.py::test_pmmvy_second_girl_child_accepts_st_category` | behaviour change, test not updated |
| `test_slots.py::test_next_missing_slot_*` (×2) | `agents.orchestrator.slots.next_missing_slot` no longer exists — renamed without updating callers in tests |
| `test_routing.py::test_llm_decision_is_used_when_valid` | expects `confidence == 0.95`, gets `0.7` |

**Resolution — `pytest` is now fully green at 118 passed.** Each failure was diagnosed
before being touched; three of the four turned out to be genuinely stale, and one was a
real latent bug:

- **`test_slots.py` (×2)** — `slots.next_missing_slot` was deleted in commit `405102e`
  and its logic moved inline into `OrchestratorNodes.slot_check` (`nodes.py:387`). The
  tests also referenced an unimported `POSHAN_CARD`, so they had been dead, not merely
  failing. Rewritten against `slot_check`, which is where the behaviour now lives —
  "ask the lowest-priority required slot first" is principle #5 and deserved to stay
  covered rather than be deleted. Added a third case pinning that an `overview`
  request collects no personal slots.

- **`test_routing.py`** — not a regression. `Router.route()` gained a deterministic
  keyword fast-path that returns before calling the LLM when confidence ≥ 0.7, to save
  an LLM call per turn. The test's input (`"I have a question about child welfare"`)
  scores vatsalya @ 0.7, so the mock responder was never reached. Changed the input to
  one with no keyword signal so the LLM path is genuinely exercised, and **added
  `test_confident_keyword_route_skips_the_llm`** — the fast-path is a real cost
  optimization and had no test at all.

- **`test_graph.py::test_pmmvy_second_girl_child_accepts_st_category`** — **a real
  bug, not a stale assertion.** `_match_bool` (`slots.py:112`) returned `"True"`/
  `"False"` from its three regex branches but `"true"`/`"false"` from its two substring
  branches — two casings out of one function. Harmless *today* only because the single
  consumer (`to_bool`) lowercases before comparing. Any future
  `facts.get("...") == "true"` would silently read false. Fixed at the source
  (normalised all branches to lowercase) rather than by editing the assertion, since
  editing the test would have preserved the trap.

**Lesson worth keeping:** three of these four were "just a stale test", but the fourth
was a live inconsistency that a test edit would have buried. Diagnose before
re-asserting.

### 1.3 Uncommitted work on `main`, plus branch/PR backlog

Working tree carries unreviewed changes to `agents/orchestrator/prompts.py`,
`agents/orchestrator/router.py`, `agents/specialists/_grounding.py`,
`apps/web/app/page.tsx` (−182 lines), `scripts/start_demo.ps1`. Untracked:
`Web-Avatar-LipSync.pdf`.

Also open: three stale `claude/*` local branches and ~19 unmerged dependabot PRs
(Python 3.14 base image, Node 26, tailwind 4.3.3, langgraph, pyjwt, pytest, …).

**Working tree — ✅ triaged (2026-07-30).** All five changes reviewed and **kept**;
every one is deliberate, coherent work:

| File | Change | Verdict |
|---|---|---|
| `agents/orchestrator/prompts.py` | slot questions now explain *why* the fact helps | keep |
| `agents/specialists/_grounding.py` | 8th-grade reading level, acronym expansion, dash-list for 3+ facts, anti-truncation guard on KB passages | keep |
| `agents/orchestrator/router.py` | mixed-topic → act-on-now intent; latest message beats stale summary | keep |
| `apps/web/app/page.tsx` | starter-card empty state → instant static greeting (−149 lines) | keep |
| `scripts/start_demo.ps1` | UTF-8 BOM added | keep — helps PowerShell 5.1 render non-ASCII |

Work since then is on branch **`fix/p0-imports-tests-kb`**, cut from `main` with this
WIP carried across. Note the fix files and the WIP files do not overlap, so the two sets
of changes stay independently reviewable. Nothing has been committed or pushed.

**Dependabot — ⬜ still open.** ~19 PRs. Requires a decision, since merging mutates the
remote: the GitHub Actions and npm bumps are low-risk and mergeable as a batch; the
**Python 3.14 and Node 26 base-image bumps must not be** — this stack pins torch /
ctranslate2 / faster-whisper wheels that lag new Python releases, so those two need a
`docker build` test first and should be closed rather than merged if they fail.

---

## 2. P1 — Claims made to the Ministry that the code does not yet support

The demo email describes capabilities that this repo does not implement as stated.
Each row is either a build item or a wording correction — decide which, but do not
leave the gap unaddressed.

### 2.1 "Grounded, cited answers" — the RAG index is switched off — ✅ DONE (2026-07-30)

`apps/backend/config.py:97` sets `kb_local_models_enabled: bool = False`, and
`KB_LOCAL_MODELS_ENABLED` is **not set in `.env`**. `mcp/knowledge_base/tool.py`
therefore returns `KBQueryResponse(chunks=[], latency_ms=0.0)` before Qdrant is ever
queried.

The 2,579-chunk index built from 23 official MoWCD PDFs is not being consulted.
Answers currently come from the LLM plus deterministic tool facts (eligibility rules,
helpline YAML) — grounded in the sense that amounts are not invented, but **not
sourced from the official guidelines**, and citation counts in the dashboard reflect
that.

This is the highest-value single flag in the codebase: the expensive work is built and
not running.

**Fixed.** Retrieval was verified working *before* the flag was flipped, so this
enabled a known-good path rather than a hopeful one:

- Qdrant index present and populated — **2,319 points** in `saheli_kb`.
- e5 + bm25 assets present; `local_files_only=True` load succeeds (no network).
- Real query returns real cited chunks: `retrieve("what should i eat during
  pregnancy", "poshan")` → 3 chunks citing `Poshan_3.pdf — ROLES AND
  RESPONSIBILITIES — p.1`.
- **Latency: ~60 s cold (model load), ~0.14 s warm.** Warm is far inside the 15 s
  `kb_citation_timeout_seconds` budget. Cold is not — which is why `POST /warmup`
  before a demo is now mandatory, not merely advisable.
- `KB_LOCAL_MODELS_ENABLED=true` set in `.env`, with a comment recording the above.

The `config.py` default stays `False` deliberately — a fresh clone without the model
assets should degrade to "no passages", not block a request on a Hugging Face
download. Enabling is an explicit per-environment act.

`tests/test_e2e_knowledge_base_flow.py` now **skips** when the flag is off instead of
failing. It is the one test needing real local assets, absent in CI; failing there
meant "environment", not "regression", which is exactly the signal that makes a red
suite worth ignoring. It runs and passes locally.

**⬜ Still required:** set `KB_LOCAL_MODELS_ENABLED=true` in whatever deployed
environment §3.7 eventually produces, and confirm `POST /warmup` returns a non-zero
`kb_chunks_returned` there. The Dockerfile already bakes the e5/bm25 assets, so a
container deploy needs only the env var.

### 2.2 "Mobile number + OTP for citizens"

Not implemented. `grep -ri "otp\|mobile"` across `apps/` and `agents/` returns nothing.
Citizen sign-in is **email + password**, identical to the admin form, differentiated
only by the role toggle in `apps/web/components/auth-role-selector.tsx`.

**If OTP is required:** needs an SMS gateway decision first (MSG91 / Gupshup / a
Government-approved sender ID), then a `phone` column on `User`, an OTP table with
expiry + attempt limits, and rate limiting on the send endpoint (§3.3). Estimate: this
is the largest single item in this document. Do not start it before §0 is decided.

**If not:** correct the wording to "role-based login (citizen / Ministry official)".

### 2.3 "Top questions" and "emerging concerns"

The dashboard renders six panels — Scheme distribution, Languages, MCP tools invoked,
Safety categories flagged, Channels, Top districts (`apps/web/app/dashboard/page.tsx`).
There is no question clustering, no trend detection, no "emerging" surface.

`by_intent` (which scheme) is not the same as "top questions" (what citizens actually
ask). Building it properly means embedding + clustering `user_message` from the trace —
which collides directly with the PII issue in §3.5. Sequence PII redaction first.

### 2.4 "Regional hotspots"

`by_district` is a `Counter` over four synthetic districts (Varanasi, Madurai, Delhi,
Lucknow) with 37 illustrative facilities in `mcp/geo_locator/data/facilities.json` —
correctly and explicitly labelled `"demo_data": true` in that file's `_meta`.

Production sources are already named in that same `_meta` block: Poshan Tracker (AWC),
Mission Shakti GIS / Sakhi OSC directory (OSC), CPMS / Mission Vatsalya directory
(DCPU, CWC). Integrating any one of them is a discrete, well-scoped task — but each
needs a Ministry data-access request, so start the paperwork early if this is wanted.

---

## 3. P2 — Production readiness

These are genuine defects for a publicly reachable deployment, listed in the order I
would fix them.

### 3.1 JWT secret is the shipped dev default

`apps/backend/config.py` defaults `jwt_secret_key` to
`"dev-insecure-secret-change-me-not-for-prod"`, and `JWT_SECRET_KEY` is absent from
`.env`. Anyone with repo access can forge an admin access token and read the Ministry
dashboard.

**Fix:** generate a long random value per environment, set it as an App Service
application setting / GitHub Environment secret. Consider making the app refuse to
start if the default value is detected outside development — a silent insecure default
is how this stays broken.

### 3.2 CORS is fully open

`apps/backend/main.py:123` — `allow_origins=["*"]`, `allow_methods=["*"]`,
`allow_headers=["*"]`. The code comment already says "lock down origins before any
real deployment".

**Fix:** an env-driven allowlist containing the deployed web origin (and, during
development, `http://localhost:3000`).

### 3.3 No rate limiting on `/chat` or `/voice`

Both endpoints are intentionally unauthenticated so WhatsApp and voice IVR channels
work without a login wall — that design is fine. But both spend Azure OpenAI tokens
per call, and `/voice` additionally runs ASR and TTS. A public URL with no limit is an
uncapped spend and a trivial denial-of-wallet target.

**Fix:** per-IP and per-`session_id` limits (`slowapi` is the smallest thing that
works). Also worth an Azure OpenAI quota/budget alert as a backstop that does not
depend on application code being correct.

### 3.4 WhatsApp webhook does not verify request signatures

`apps/backend/whatsapp_webhook.py` has no `X-Hub-Signature-256` check — no `hmac`
import at all. Any party who learns the URL can POST a forged inbound message and the
backend will generate an LLM reply and attempt to send it via the Cloud API.

**Fix:** verify the HMAC-SHA256 of the raw request body against the Meta app secret
before processing, and reject on mismatch. Requires capturing the raw body (FastAPI's
parsed model is not sufficient for HMAC).

### 3.5 Raw citizen messages are persisted and displayed

`agents/orchestrator/trace.py:37` stores `user_message` verbatim into
`logs/interactions.jsonl`, and `apps/backend/dashboard.py` returns it in
`/analytics/recent` and `/dashboard/recent`, where the UI renders it.

The file's own docstring acknowledges this: *"a production sink would redact
`user_message`."* Project principle #4 is "Zero real PII". With synthetic demo
personas this is safe; the moment one real citizen types a name, phone number, or
address it is not.

**Fix:** redact at write time in `trace.py` (phone numbers, Aadhaar-shaped digit runs,
email addresses at minimum) rather than at read time — the sink is the trust boundary,
and redacting only in the dashboard leaves the raw data on disk. This is a
prerequisite for §2.3.

### 3.6 All state is ephemeral or single-process

| State | Current store | Failure mode |
|---|---|---|
| Conversation | `MemorySaver` (`agents/orchestrator/graph.py:109`) | lost on restart; breaks with >1 worker |
| WhatsApp language choice | `_wa_lang` dict in module scope | same (already flagged with a `ponytail:` comment) |
| Auth users | SQLite at `data/auth.db` | Azure App Service local disk is ephemeral |
| Analytics | `logs/interactions.jsonl` on local disk | **a restart erases the entire Ministry dashboard** |
| Knowledge base | embedded Qdrant, `QdrantClient(path=...)` | single-process file lock; stale `.lock` survives crashes; cannot scale past one uvicorn worker |

For a demo this is acceptable and was a deliberate trade. For anything the Ministry
returns to a second time, the analytics row is the one that will embarrass you first —
it is the only one whose loss is visible to the audience.

**Suggested order if this becomes a real deployment:** analytics → Postgres; auth →
Postgres (same instance); sessions → Redis; Qdrant → server mode. Not before §0 is
decided.

### 3.7 CD does not deploy to where the app actually lives

`.github/workflows/cd.yml` builds and pushes both images to GHCR (this part works),
then deploys over SSH to a docker-compose host gated on `STAGING_HOST` / `PROD_HOST`
secrets — neither of which is set, so both deploy jobs no-op with a notice. The live
demo is on **Azure App Service**, which this pipeline never touches.

Deployment is therefore manual and untracked: there is no record of which commit is
live, and no way to roll back.

**Fix:** either provision the Linux host `DEVSECOPS_PLAN.md` Step 0 describes, or
replace the SSH deploy jobs with an Azure Web App container deploy
(`azure/webapps-deploy`) pointed at the GHCR tags already being built.

### 3.8 Security scanning is report-only

`pip-audit`, `npm audit`, and both Trivy scans run with `continue-on-error: true`.
`DEVSECOPS_PLAN.md` #3 documents why (the torch / sentence-transformers /
faster-whisper tree always carries known CVEs) and the intent to triage a baseline then
enforce. That triage has not happened.

**Fix:** triage the current findings once, record accepted CVEs, then drop
`continue-on-error` on at least the CRITICAL severity gate.

---

## 4. P3 — Quality and credibility gaps

### 4.1 `rag/eval/gold.jsonl` is missing — retrieval quality is unmeasured

`rag/eval/run.py` exists; its gold set does not. **There is no recall or MRR number for
the knowledge base.**

For a Ministry audience this is the credibility number — "our retrieval surfaces the
correct guideline passage X% of the time" is the claim that separates this from a
chatbot. It cannot currently be made.

**Fix:** author ~50–100 question/expected-source pairs across the three schemes
(realistically half a day, and it is the single highest-credibility-per-hour item in
this document), restore `gold.jsonl`, run the harness, publish the number. Do this
after §2.1, since retrieval is currently disabled and would score zero.

### 4.2 Cross-encoder reranking disabled

`kb_rerank = False` — the bge-reranker-v2-m3 forward pass measured ~2s per candidate on
the demo laptop CPU (104s/query at 50 candidates, blocking the event loop). Correct
call for local hardware. On a GPU or a properly sized server it costs milliseconds and
measurably improves the top-6 passage set.

**Fix:** re-enable on server hardware, and add the reranker bake step to
`apps/backend/Dockerfile` (the existing comment says exactly where and why it was
omitted). Re-measure with §4.1's harness — do not enable it on faith.

### 4.3 Language layer is not the sovereign stack

Current: `faster-whisper` ASR + `deep-translator` NMT + `edge-tts` TTS, 10 languages,
zero keys. Project principle #3 says "Sovereign by design — use Bhashini/VoicERA
(MeitY-approved stack)".

`edge-tts` in particular routes text to a Microsoft consumer endpoint. Expect this
question in the room; have an answer ready even if the migration is not scheduled.
`.claude/dev/api-integrations.md` already scopes the Bhashini integration.

### 4.4 No response streaming

A grounded answer takes 5–25 s (`specialist_timeout_seconds = 60.0`, inner LLM budget
20 s) and arrives as one blocking chunk. On stage this reads as a hang. Token
streaming over SSE would change the perceived latency without changing the pipeline.

Not urgent, high demo impact, moderate cost — schedule it before the next leadership
presentation, not before §1–§2.

### 4.5 Smaller open items

- `/forgot-password` is a UI stub with no backend (the page states this honestly — fine
  for a demo, must not survive a real citizen rollout).
- No synthetic personas directory, despite being referenced in the docs.
- WhatsApp voice notes are transcribed and answered **as text**; no audio replies
  (already flagged with a `ponytail:` comment — needs Meta's resumable media-upload
  flow).
- `apps/backend/dashboard.py` has a duplicated `from apps.backend.config import
  get_settings` import in `mcp/knowledge_base/tool.py` (harmless, one-line cleanup).
- `apps/web/static/` legacy pre-Next.js UI is served by nothing; delete it rather than
  letting it rot as a false reference.

---

## 5. Recommended sequence

Each step is independently shippable. Do not start a later step before the earlier ones
land — the ordering is dependency-driven, not preference.

| # | Item | Ref | Status |
|---|---|---|---|
| 1 | Add the two missing imports | §1.1 | ✅ done |
| 2 | Fix the four stale tests; get the suite green | §1.2 | ✅ done — 118 passing |
| 3 | Triage the working tree | §1.3 | ✅ done — all kept |
| 4 | `KB_LOCAL_MODELS_ENABLED=true`; verify retrieval | §2.1 | ✅ done — verified before enabling |
| 5 | Dependabot backlog | §1.3 | ⬜ needs a call (mutates the remote) |
| 6 | Real `JWT_SECRET_KEY`; CORS allowlist; rate limits | §3.1–3.3 | ⬜ ~half a day |
| 7 | WhatsApp signature verification | §3.4 | ⬜ ~2 hours |
| 8 | PII redaction at the trace sink | §3.5 | ⬜ ~half a day |
| 9 | Author `gold.jsonl`; publish retrieval numbers | §4.1 | ⬜ ~half a day — now unblocked by #4 |
| 10 | Provision a deployment target; point CD at it | §3.7 | ⬜ ~half a day + procurement |

Steps 1–4 are complete and land as one reviewable branch. Step 9 was blocked on step 4
(retrieval was off, so it would have scored zero) and is now the highest
credibility-per-hour item remaining. Steps 6–8 are the security block and are best done
together. Step 10 is the largest external dependency and gates nothing above it.

Deliberately **not** scheduled: Redis/Postgres migration (§3.6), OTP auth (§2.2),
WhatsApp audio replies, additional schemes. None of these block anything above, and
each is cheaper to build after §0 is settled than before.
