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
- `/` — chat UI (calls `POST /chat`, threads state via a per-session id).
- `/dashboard` — analytics (calls `GET /dashboard/stats` + `GET /dashboard/recent`).

## Routes it depends on (backend)
- `POST /chat`
- `GET /dashboard/stats`
- `GET /dashboard/recent`
- `GET /health`
