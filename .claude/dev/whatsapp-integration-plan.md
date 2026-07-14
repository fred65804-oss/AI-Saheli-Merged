# WhatsApp Integration Plan — Zero Cost

> Status: **planned, not started**. This is a plan to implement later — see
> [`roadmap.md`](roadmap.md) Phase 3 ("WhatsApp channel — entirely unbuilt").
> Payload shapes and code snippets for the webhook already live in
> [`api-integrations.md`](api-integrations.md#2-whatsapp-cloud-api-meta); this
> doc covers the free-tier mechanics, the setup sequence, and how it maps onto
> the existing backend so nothing needs to be re-derived when work starts.

## Why this maps cleanly onto what already exists

`apps/backend/main.py` already contains `_translated_turn()` (translate-in →
`run_turn()` → translate-out) and `FreeProvider.transcribe()` /
`.synthesize()` — the exact logic `/chat` and `/voice` use. WhatsApp becomes a
**third channel** that calls the same internals. No orchestrator, specialist,
or KB changes are needed.

## The free-tier mechanism that makes this $0

Meta's **WhatsApp Cloud API test mode** gives you, with no credit card and no
business verification:
- A free test phone number (Meta-provisioned)
- A free access token
- The ability to message **up to 5 of your own verified phone numbers**,
  unlimited messages, indefinitely

That's enough to demo live to yourself, colleagues, or a small Ministry
review group.

---

## Phase 1 — Meta setup (no code, ~20 min)
1. Create a free account at [developers.facebook.com](https://developers.facebook.com)
2. Create an App → type **Business** → add the **WhatsApp** product
3. Meta auto-assigns a free test number + shows a **Phone Number ID**, a
   **WhatsApp Business Account ID**, and a temporary access token
4. Under "API Setup," add up to 5 real phone numbers as **test recipients** —
   each verifies via an SMS/WhatsApp OTP. These numbers can message the bot
   and receive replies for free, forever, in test mode.

## Phase 2 — Expose the local backend publicly
Meta's webhook requires a public HTTPS URL.
- Use **ngrok free tier** (`ngrok http 8000`) for an instant HTTPS tunnel, $0
- Caveat: the free ngrok URL changes every restart, so the webhook URL in
  Meta's dashboard needs re-pasting each session. Cloudflare Tunnel's free
  tier can give a stable subdomain if that becomes annoying — still $0.

## Phase 3 — Add a webhook endpoint to the backend
Two routes, both thin wrappers around existing logic (request/response JSON
shapes are already documented in
[`api-integrations.md`](api-integrations.md#2-whatsapp-cloud-api-meta)):
- **`GET /whatsapp-webhook`** — Meta's one-time verification handshake
  (echoes back a challenge token)
- **`POST /whatsapp-webhook`** — receives each inbound message. Design
  constraints:
  - Meta expects `200` within ~5 seconds (see the 20s hard timeout noted in
    api-integrations.md), but grounded answers take 5–25s (LLM + KB). So:
    **ACK immediately**, then process the message and send the reply as a
    *separate* outbound API call in the background — not as the webhook's
    response body. This is how WhatsApp bots always work; it is not
    request/response like `/chat`.
  - Text messages → straight into `_translated_turn()`.
  - Voice notes → Meta gives a temporary media URL; download it, pass the
    bytes to `FreeProvider.transcribe()` (same as `/voice` today), then
    continue the same pipeline.

## Phase 4 — Sending replies
`POST https://graph.facebook.com/v21.0/<PHONE_NUMBER_ID>/messages` with the
access token, sending `{"to": <sender>, "type": "text", "text": {"body":
reply}}`. For voice replies, upload the edge-tts MP3 to Meta's media endpoint
first, then reference it as an `"audio"` message. Sending to the 5 test
numbers is free with no volume limit that would matter for a demo.

## Phase 5 — Session identity
WhatsApp gives the sender's phone number (`wa_id`) on every inbound message.
Use that directly as the `session_id` key into the same in-memory
checkpointer `/chat` already uses — multi-turn slot-filling works identically
per WhatsApp contact.

## Phase 6 — Test loop
Send a WhatsApp message from one of the 5 verified numbers to the test number
→ it hits ngrok → FastAPI → orchestrator → Meta send-API → reply lands back
in WhatsApp. Same safety gate, same citations, same everything already
verified on web.

---

## Staying at $0
- Meta's free tier: **1,000 free service conversations/month** per WhatsApp
  Business Account, on top of the unlimited free messaging within the 5 test
  recipients — a demo will never approach either limit.
- Cost only appears if messaging people who *haven't* messaged first, beyond
  the 5 test numbers — that requires **Business Verification** (still free,
  just paperwork) and moves into Meta's per-conversation pricing. That is a
  future, deliberate decision, not something that can happen by accident
  during testing.

## Alternative considered and rejected
Unofficial libraries like `whatsapp-web.js` or Baileys drive a real WhatsApp
Web session via browser automation — fully free, no Meta account at all.
Rejected for this project: violates WhatsApp's Terms of Service and risks the
phone number being banned with no warning — a bad look for something
presented to MoWCD leadership. The official Cloud API path above is also the
credible route this project would go into real production on.

## When picking this up again
Implementation is small — roughly 1 new route file (`whatsapp_webhook.py`
under `apps/backend/`) reusing `_translated_turn()`, `run_turn()`, and
`FreeProvider` as-is. No orchestrator/specialist/KB changes required.
