# DevSecOps Pipeline Plan — AI Saheli

## Why this is needed

Right now "deploying" AI Saheli means one person runs
`scripts\start_demo.ps1` on their own laptop. There is no Docker, no CI, and
no automated deployment anywhere in this repo. As the Ministry demo moves
toward real staging and production use, we need a repeatable, secured path
from `git push` to a running instance — on **whatever host ends up hosting
staging/prod** (a cloud VM, an on-prem box, or a government data center; not
decided yet, and the pipeline should not need to change when that's decided).

## Step 0 — you need an actual computer to deploy to (do this first)

This is the part that's easy to miss coming into DevOps fresh: "staging" and
"production" are not things that get created automatically by writing a
pipeline. They are **two real, always-on Linux machines with their own IP
address**, sitting somewhere on the internet, that someone has to go get.
Nothing in this plan works until at least one of those exists.

- **Cheapest way to get one today**: rent one small Linux VM (Ubuntu 22.04)
  from any cloud provider — DigitalOcean, AWS Lightsail, Azure, GCP all sell
  this for roughly $10–25/month. Follow the [Host sizing note](#5-host-sizing-note)
  below (4 vCPU / 8 GB RAM minimum). This becomes **staging** — use it to
  prove the whole pipeline works end-to-end before anyone asks for a
  "real" production server.
- **Production**, for a Ministry-facing citizen app, will likely end up on
  Ministry/government-approved infrastructure (NIC, MeghRaj, or an
  on-prem data center) rather than a public cloud, for data-sovereignty
  reasons — that decision belongs to the Ministry/Uneecops infra team, not
  this repo. The pipeline doesn't care which one it is; it only needs an IP
  address, SSH access, and Docker installed on it.
- Once you (or whoever owns the machine) can `ssh` into it and run
  `docker --version` successfully, that machine is ready to be wired into
  this pipeline as `STAGING_HOST` or `PROD_HOST` (see
  [Environments and secrets](#2-environments-and-secrets)).

## How the pipeline actually works, end-to-end (plain-English walkthrough)

Once Step 0 is done, here's the full journey of one code change, from your
editor to a real user's browser:

1. **You push code to GitHub.** Nothing different from today.
2. **GitHub Actions wakes up** — this is a free robot that GitHub runs on
   your behalf whenever you push. It checks out your code on a fresh machine
   and runs the checks in [Continuous Integration](#3-continuous-integration--runs-on-every-pr-and-every-push-to-main):
   do the tests pass, does the frontend compile, are there any leaked
   secrets or known-vulnerable dependencies. Think of it as an automated
   security guard that has to say "yes" before anything moves further.
3. **If everything passes, the robot builds two Docker images.** A Docker
   image is like a sealed shipping container: it bundles your code together
   with the exact Python/Node versions and libraries it needs, so it behaves
   identically no matter which physical machine eventually runs it — no more
   "works on my laptop, breaks on the server."
4. **The images get pushed to GitHub Container Registry** — a warehouse
   where the sealed containers sit, tagged with the commit they came from,
   waiting to be picked up.
5. **The robot connects to your staging server over SSH** (a secure remote
   login) and runs `docker compose pull && docker compose up -d` — plain
   English: "go get the newest sealed containers from the warehouse and
   restart yourself using them." `docker-compose.yml` is the instruction
   sheet listing which containers to run, what ports they use, and how they
   talk to each other.
6. **Caddy — one of those containers — is the only thing exposed to the
   internet.** It terminates HTTPS (the padlock icon) and forwards traffic
   to the backend or frontend container behind it. Nobody reaches the app
   directly; they always go through Caddy first.
7. **Production works identically, except a human clicks "Approve" in
   GitHub first.** That's the safety gate — nothing reaches real citizens
   without a person signing off, even though the technical steps are
   otherwise the same as staging.
8. **Your user accounts and audit logs are never inside the sealed
   container.** They live in a "volume" — a folder on the server's actual
   disk, outside the container — so step 5's "restart with the new
   container" never wipes out real user data. Only the code and ML models
   get replaced on each deploy; the database and logs persist across every
   single one.

If you take nothing else from this: **the pipeline automates steps 2–7. Step
0 (getting a real machine) is a one-time manual prerequisite, and step 8
(data persistence) is why we use named volumes instead of just copying
`data/` and `logs/` into the image.**

## Facts about this repo that shape the design

- **The app writes live state to relative paths on disk**: the audit trail
  (`logs/interactions.jsonl`), the user-accounts database
  (`data/auth.db`, SQLite), and the knowledge-base vector index
  (`rag/qdrant_db/`, ~23 MB, currently checked into git) — see
  `apps/backend/config.py`. A container that doesn't persist these will
  silently lose user accounts and audit history on every redeploy.
- **The JWT signing secret ships with an insecure default**
  (`JWT_SECRET_KEY=dev-insecure-secret-change-me-not-for-prod` in
  `.env.example`) — every real environment needs its own randomly generated
  value, never the default, never committed.
- **Startup is slow the first time**: `POST /warmup` loads the KB embedder,
  the LLM clients, the faster-whisper speech model (~150 MB on first
  download), and edge-tts — 30–90 seconds. Baking these models into the
  Docker image at build time (rather than downloading them the first time a
  container starts) avoids a slow/flaky first request and avoids needing
  internet access from the production host at all — which matters given this
  project's "sovereign by design" principle.
- **A leftover Vercel serverless entrypoint exists** (`[tool.vercel]` in
  `pyproject.toml`) but doesn't fit this app — Vercel's stateless serverless
  model doesn't work with a local Qdrant index, a SQLite database, large ML
  models, and a 30–90s warmup. This plan replaces that approach; the leftover
  config block is harmless and can be cleaned up later.
- **The test suite is fully offline** — `tests/conftest.py` blanks every API
  key before the app config loads, so `pytest` can run in CI with zero
  secrets configured.
- **The frontend already proxies through one env var** —
  `apps/web/next.config.mjs` sends every API call through `BACKEND_ORIGIN`,
  which is exactly the hook a container (or a remote host) needs — no
  frontend code changes required to point it at a different backend.
- **No Python or Node version is pinned anywhere** in the repo today — the
  Dockerfiles will pin explicit versions so builds are reproducible.

## The approach: containerize once, deploy anywhere, gate on security

Because the hosting target isn't decided yet, the pipeline must not lock
into one cloud's proprietary services. The simplest approach that's still
correct: **Docker images + docker-compose, deployed over SSH, driven by
GitHub Actions** (the code is already on GitHub — no new tool to stand up or
pay for). This runs unchanged on an Azure VM, an AWS EC2 instance, an
on-prem server, or a government data-center machine. "Deploy on any staging
or production environment" becomes: *any Linux host with Docker installed and
an SSH key registered in GitHub Secrets.*

Kubernetes, Terraform, and a service mesh are deliberately **not** part of
this plan — they're real upgrade paths if traffic or multi-host scale ever
demands them, but nothing about this project needs that complexity today.

```
push to main / open a PR
        │
        ▼
CI (GitHub Actions): pytest  →  next build  →  security scans
        │  (all green)
        ▼
Build & tag Docker images (backend, web)  →  push to GitHub Container Registry
        │
        ├──────────────► auto-deploy to STAGING  (SSH: docker compose pull && up -d)
        │
        └──────────────► manual approval gate (GitHub "production" environment)
                                  │
                                  ▼
                         deploy to PRODUCTION (same images, different .env)
```

### 1. Containerize the app

- **`apps/backend/Dockerfile`** — `python:3.11-slim`, built from the repo
  root (the backend imports the top-level `agents/`, `mcp/`, `rag/`,
  `language/` packages, not just its own folder). Installs
  `requirements.txt`, copies the code, then pre-loads the KB embedder and
  faster-whisper models once at build time so their weights bake into the
  image instead of downloading at runtime. Includes the current
  `rag/qdrant_db/` index (it's small and already versioned with the code).
  Does **not** include `data/` or `logs/` — those are live application state,
  not code.
- **`apps/web/Dockerfile`** — multi-stage `node:20-alpine` build using
  Next.js's standalone output mode.
- **`docker-compose.yml`** (repo root) — a `backend` service, a `web`
  service, and a **Caddy** reverse-proxy service in front of both for
  automatic HTTPS (Caddy over nginx+certbot: same result, a fraction of the
  config, no manual certificate renewal to babysit). Named volumes hold
  `data/` and `logs/` so they survive every redeploy. A health check on the
  backend's existing `GET /health` endpoint.
- **`.dockerignore`** — excludes `.venv/`, `.git/`, `data/`, `logs/`,
  `node_modules/`, `.next/`, caches — so secrets and local state never end up
  baked into an image.

### 2. Environments and secrets

- `.env.staging.example` and `.env.production.example` extend the existing
  `.env.example` pattern — templates only, real files never committed.
- Each environment gets its own freshly generated `JWT_SECRET_KEY`
  (`python -c "import secrets; print(secrets.token_urlsafe(64))"`), stored as
  a **GitHub Actions secret**, never as a plaintext file beyond the deployed
  host's own `.env`.
- **GitHub Environments** (`staging`, `production`) hold each environment's
  own secrets (`SSH_HOST`, `SSH_KEY`, `JWT_SECRET_KEY`, LLM API keys).
  `SSH_HOST` and `SSH_KEY` come directly from the machine you provisioned in
  [Step 0](#step-0--you-need-an-actual-computer-to-deploy-to-do-this-first) —
  `SSH_HOST` is that machine's IP/domain, `SSH_KEY` is a private key that can
  log into it. Production is configured to require a human reviewer's
  approval before its deploy job runs. This is the actual mechanism behind
  "deploy to any environment" — the same workflow, pointed at different
  secrets.

### 3. Continuous Integration — runs on every PR and every push to `main`

1. `pytest` — the existing offline backend test suite, no secrets needed.
2. `npm ci && npm run build` — compiles and type-checks the frontend.
3. **Security gates:**
   - `gitleaks` — fails the build if a secret is ever committed.
   - `pip-audit` and `npm audit` — dependency vulnerability scanning.
   - `trivy` — scans the built Docker images for OS/package
     vulnerabilities before anything is pushed to a registry.
   - **Important rollout detail:** run all three scanners in *report-only*
     mode at first. This stack pulls in `torch`/`sentence-transformers`/
     `faster-whisper`, and those dependency trees almost always carry some
     known CVEs — turning scans into hard failures on day one would make CI
     red before a single line of code changes, and teams learn to ignore red
     CI fast. Triage the baseline once, then flip the scanners to fail on
     **critical/high severity only**.
4. **Dependabot** — a weekly automated PR for outdated pip/npm/Docker base
   image versions, so the vulnerability surface doesn't quietly grow stale.

### 4. Continuous Deployment

- A successful CI run on `main` builds the images once, tags them with the
  git commit SHA, and pushes to **GitHub Container Registry** (free, already
  authenticated, no new account to create).
- **Staging** deploys automatically: SSH into `STAGING_HOST`, pull the new
  images, `docker compose up -d`, then poll `/health` to confirm it's alive.
- **Production** runs the identical steps against `PROD_HOST`, but only after
  a human approves it in GitHub's UI (the environment protection rule).
- **Rollback**: keep the previous image tag around; if the post-deploy health
  check fails, redeploy the prior tag. This is a documented manual step for
  now — a demo-stage project doesn't yet need automated rollback tooling.

### 5. Host sizing note

`faster-whisper` and the sentence-embedding model are the two components
that actually need real CPU/RAM (this is also why the KB reranker is off by
default — it measured ~2s per candidate on a demo laptop's CPU). Whoever
provisions the staging/production VM should start at **4 vCPU / 8 GB RAM**
for the backend host to avoid hitting the same kind of slowdown in a real
environment.

### 6. Documentation

- **`DEPLOYMENT.md`** — the practical runbook: how to provision a bare Linux
  host, which secrets to create in GitHub before the first deploy, how
  staging and production differ, how to check logs and health after a
  deploy, and how to roll back. This is the piece that means the next person
  doesn't have to re-figure this out from scratch.

## Explicitly out of scope for now

- **Kubernetes / Terraform / multi-region / autoscaling** — nothing about
  current traffic or host count justifies this; docker-compose upgrades
  cleanly to these later if it's ever actually needed.
- **Migrating Qdrant/SQLite to managed services** (Qdrant Cloud, managed
  Postgres) — today's data is 23 MB and 40 KB respectively; revisit only if
  concurrent multi-instance writes become a real requirement.
- **Log shipping/rotation** for the append-only `logs/interactions.jsonl` —
  flagged in `DEPLOYMENT.md` as a known follow-up rather than building a
  logging stack now.
- **Automated backups** of the auth database and logs volumes — flagged as a
  follow-up once real (non-demo) user accounts exist.

## How we'll know it worked

- `docker compose build` succeeds locally for every service.
- `docker compose up` with a throwaway `.env` serves a working chat
  round-trip end-to-end at `:3000`, exactly like `start_demo.ps1` does today,
  plus HTTPS via Caddy.
- A throwaway test PR proves `ci.yml` runs pytest, the frontend build, and
  all three security scans — and that gitleaks/pip-audit/trivy actually catch
  a deliberately introduced secret or vulnerable dependency.
- The production deploy job visibly pauses for manual approval in GitHub's
  UI before it runs.

## Feature additions identified during review

Two things aren't in place yet, flagged directly during review of this plan.
Noting both here since they interact with the pipeline (secrets, access
control, what gets exposed over HTTPS) even though they're feature work, not
pipeline work.

### A. Role-based access: dashboard = admin-only, chatbot = everyone

**Current state** (checked directly in the code): `apps/backend/auth/models.py`'s
`User` table has no `role` column at all. `apps/backend/main.py:134` mounts
the dashboard router with `dependencies=[Depends(get_current_user)]` — meaning
*any* signed-up user can open the analytics dashboard and tool endpoints
today, not just admins. `/chat` and `/voice` are already open to everyone
with no login required (separate router, no auth dependency at all) — so
the "chatbot for everyone" half of this is already true; only the dashboard
side needs locking down.

**Plan:**
1. Add a `role` column to `User` (`apps/backend/auth/models.py`) —
   default `"citizen"`, with `"admin"` as the only other value for now. No DB
   migration tooling needed yet (no real production users exist): recreate
   `data/auth.db` in dev, or `ALTER TABLE` it once per existing environment.
2. **No public path to becoming admin.** `POST /auth/signup` always creates
   `role="citizen"` — it must never read a role from the request body.
   The first admin account is created manually, once per environment, via a
   small one-off script (`scripts/create_admin.py`) that signs up a user and
   flips their role directly in the DB.
3. Add a `require_admin` dependency next to `get_current_user` in
   `apps/backend/auth/deps.py` — same check, plus `user.role == "admin"`,
   else `403`.
4. In `apps/backend/main.py:134`, swap the dashboard router's dependency
   from `Depends(get_current_user)` to `Depends(require_admin)`. This one
   line is the actual enforcement; everything else here is bookkeeping
   around it.
5. Add `role` to `UserOut` (`apps/backend/auth/schemas.py`) so
   `GET /auth/me` tells the frontend what the logged-in user is allowed to
   see.
6. Frontend (`apps/web/app/dashboard/page.tsx` + nav): read `role` from
   `/auth/me`, hide the dashboard link from non-admins and redirect them
   away if they navigate to `/dashboard` directly. This is a UX nicety, not
   the security boundary — step 4 already 403s a non-admin regardless of
   what the frontend shows or hides.

No pipeline changes needed — this ships inside the same backend/frontend
Docker images as everything else.

### B. WhatsApp channel integration

A detailed zero-cost plan for this **already exists** at
`.claude/dev/whatsapp-integration-plan.md` (Meta's free WhatsApp Cloud API
test mode, a new `apps/backend/whatsapp_webhook.py` reusing the existing
`_translated_turn()` / `run_turn()` / `FreeProvider` pipeline unchanged —
no orchestrator, specialist, or KB code needs to change). Rather than
duplicate it, here's what **changes once this DevSecOps pipeline exists** —
the deployment context that plan was written without:

1. **No more ngrok.** That plan's Phase 2 tunnels through ngrok because
   today there's no public HTTPS endpoint — the backend only runs on a
   laptop. Once [Step 0](#step-0--you-need-an-actual-computer-to-deploy-to-do-this-first)
   and the Caddy reverse proxy exist, the staging server *is* a stable
   public HTTPS URL. Point Meta's webhook at
   `https://<staging-domain>/whatsapp-webhook` directly — no tunnel, no URL
   that changes on every restart.
2. **New secrets, same pattern as everything else here**:
   `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, and a
   `WHATSAPP_VERIFY_TOKEN` (a string you invent yourself — Meta echoes it
   back during webhook setup to prove you own the endpoint). These go in
   `.env.staging` / `.env.production` and the matching GitHub Environment
   secrets, exactly like `JWT_SECRET_KEY` — never committed.
3. **The webhook must ACK fast.** Meta expects `200` within ~5 seconds, but
   a grounded answer (LLM + KB retrieval) takes 5–25s — the existing plan
   already calls this out: acknowledge the webhook immediately, then process
   and send the reply as a *separate* outbound call in the background
   (FastAPI `BackgroundTasks` is enough at this volume — no new queue
   infra needed).
4. **Rollout stays inside Meta's free tier at demo scale**: test mode (5
   verified numbers, unlimited free messages) is enough for an internal
   Ministry review on staging. Going public — messaging citizens who
   haven't messaged first — requires Meta **Business Verification** (free,
   just paperwork) and moves into the 1,000-free-conversations/month tier.
   That's a deliberate later decision, not something this pipeline needs to
   solve now.
5. **One PII note worth flagging now, not later**: `CLAUDE.md`'s "zero real
   PII, synthetic demo personas only" principle stops applying the moment a
   real citizen texts a real phone number — `wa_id` (their phone number)
   becomes the session key. Worth a short conversation with whoever owns
   compliance before this goes past the 5-test-number stage.

No CI/CD changes needed beyond adding the three secrets above — the webhook
route ships inside the same backend image as `/chat`/`/voice`.

**Status: code is built.** `apps/backend/whatsapp_webhook.py` (GET handshake +
POST receive-and-ACK + background reply), `apps/backend/turn.py` (the
translate/run_turn/translate logic extracted out of `main.py` so `/chat`,
`/voice`, and WhatsApp all share one implementation instead of three), the
`WHATSAPP_*` settings in `config.py`/`.env.example`, and
`tests/test_whatsapp_webhook.py` (handshake + payload-parsing tests, all
passing). Text messages work end-to-end once configured; voice notes are
transcribed and answered as text (no audio replies yet — that needs Meta's
separate media-upload flow, deliberately deferred).

What's left is the part only a human can do:
1. Create the free Meta developer account + App + WhatsApp product, get the
   Phone Number ID and access token.
2. Verify up to 5 test phone numbers.
3. Run `ngrok http 8000` (no staging server exists yet) to get a public
   HTTPS URL for local testing.
4. Put the real values into `.env`: `WHATSAPP_ACCESS_TOKEN`,
   `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN` (invent this one
   yourself).
5. In Meta's dashboard, register `https://<ngrok-url>/whatsapp-webhook` as
   the webhook, paste the same verify token, subscribe to the `messages`
   field.
6. Send a message from a verified test number and confirm a reply arrives.

## Next steps

This document describes the plan. Nothing has been built yet — not the
pipeline files (Dockerfiles, `docker-compose.yml`, `.github/workflows/`,
`DEPLOYMENT.md`), not the admin/citizen role split, not the WhatsApp
webhook. Say which piece to start with.
