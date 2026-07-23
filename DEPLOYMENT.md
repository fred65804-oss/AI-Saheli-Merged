# Deployment runbook

See `DEVSECOPS_PLAN.md` for the full design and rationale. This is the
practical "how do I actually run it" reference.

## Running locally in Docker (laptop, no host yet)

Prereqs: Docker Desktop running, a `.env` at the repo root (copy from
`.env.example` if you don't have one — the app runs offline with zero keys).

```
make up      # builds images, starts backend+web+caddy, waits for health, warms up models
```

No `make` on Windows? Run the same steps directly:

```
docker compose build
docker compose up -d
curl http://localhost:8000/health          # repeat until it returns 200
curl -X POST http://localhost:8000/warmup  # can take a few minutes on first run
```

Then open **http://localhost** (via Caddy) or **http://localhost:3000**
(web, direct). `make logs` / `docker compose logs -f` to follow logs,
`make down` / `docker compose down` to stop (data/logs volumes persist),
`make clean` / `docker compose down -v` to wipe them too.

### Creating the first admin account

`/auth/signup` always creates a `"citizen"` account — there's no public way
to become admin. Run once per environment:

```
make create-admin EMAIL=admin@example.com NAME="Admin" PASSWORD=a-strong-password
```

Without `make`: `docker compose exec backend python scripts/create_admin.py <email> "<name>" <password>`

## Provisioning a real staging/production host

1. Rent a Linux VM (Ubuntu 22.04, 4 vCPU / 8GB RAM minimum — see
   `DEVSECOPS_PLAN.md` § Host sizing). DigitalOcean/Lightsail/Azure/GCP, ~$10–25/mo.
2. Install Docker + Docker Compose on it, and `git clone` this repo to
   `/opt/ai-saheli` (the path `cd.yml`'s deploy jobs assume).
3. Copy `.env.staging.example` (or `.env.production.example`) to
   `/opt/ai-saheli/.env` on that host and fill in real values — **especially
   a freshly generated `JWT_SECRET_KEY`**
   (`python -c "import secrets; print(secrets.token_urlsafe(64))"`, or
   `make secret`). Never reuse the dev default.
4. In this repo's GitHub Settings → Environments, create a `staging`
   environment (and later `production`, with a required reviewer) holding:
   - `STAGING_HOST` (or `PROD_HOST`) — the VM's IP/domain
   - `STAGING_SSH_USER` / `PROD_SSH_USER` — the SSH login user
   - `STAGING_SSH_KEY` / `PROD_SSH_KEY` — a private key that can log into it
   - Whichever LLM/WhatsApp keys that environment needs (see `.env.*.example`)
5. Push to `main`. `cd.yml` builds+pushes images to GHCR, then SSHes in,
   `git pull`s, `docker compose pull && up -d`, and checks `/health`. Until
   step 4 is done, this job no-ops with a notice instead of failing.

## Rollback

Images are tagged with the git commit SHA in GHCR. To roll back: on the
host, edit `docker-compose.yml` (or set an image tag override) to the prior
SHA, `docker compose up -d`. No automated rollback yet — flagged as a
follow-up once this is a real production system, see
`DEVSECOPS_PLAN.md` § Explicitly out of scope.

## Known follow-ups (not yet built)

- Log rotation for `logs/interactions.jsonl` (append-only today).
- Automated backups of the `data/` volume (auth DB).
- The KB retriever's local dense/sparse models (`KB_LOCAL_MODELS_ENABLED`)
  and cross-encoder reranker (`KB_RERANK`) are baked into the backend image
  but stay off by default, matching current behavior — flip them in `.env`
  once you've decided the CPU-latency tradeoff is worth it (see comments in
  `apps/backend/config.py`).
- `edge-tts` (voice replies) and `deep-translator` (translation) call out to
  free Microsoft/Google endpoints at request time — they need outbound
  internet from wherever the backend runs, unlike everything else baked into
  the image. Worth flagging to whoever owns the "sovereign by design"
  requirement before this goes past a demo.
