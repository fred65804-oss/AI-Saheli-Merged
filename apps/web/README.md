# AI Saheli — Web (Chat + Dashboard)

Next.js 14 (App Router) + Tailwind + shadcn-style components.
Chat page drives Journeys 1–3, Analytics dashboard drives Journey 4.

## Quickstart
```bash
# in one terminal (from repo root)
uvicorn apps.backend.main:app --reload

# in another
cd apps/web
npm install
npm run dev
# -> http://localhost:3000
```

The web app reads `NEXT_PUBLIC_API_BASE` (default `http://127.0.0.1:8000`).
Override in `.env.local` if the backend runs elsewhere.

## Pages
- `/` — chat UI: text mode + voice-avatar mode (calls `POST /chat` / `POST /voice`, threads state via a per-session id).
- `/dashboard` — admin analytics (calls `GET /analytics/summary` + `GET /analytics/recent`).
- `/tools` — admin tool explorer (KB search, eligibility, geo locator, helplines).
- `/system` — admin system panel (health, LLM config, capability cards, languages).
- `/login`, `/signup`, `/forgot-password` — role-aware auth pages (`forgot-password` is a UI stub, no backend endpoint).

## Routes it depends on (backend)
- `POST /chat`, `POST /voice`
- `GET /meta`, `GET /helplines`, `GET /health`
- `GET /analytics/summary`, `GET /analytics/recent`
- `POST /tools/kb-search`, `POST /tools/eligibility`, `POST /tools/geo`, `POST /tools/helpline`
- `POST /auth/signup`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`
