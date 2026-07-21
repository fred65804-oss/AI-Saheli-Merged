"""WhatsApp Cloud API webhook — a third channel into the same pipeline /chat
and /voice already use (see apps/backend/turn.py).

Two routes:
  GET  /whatsapp-webhook   Meta's one-time verification handshake.
  POST /whatsapp-webhook   inbound message delivery.

Meta expects a 200 within ~5s, but a grounded answer (LLM + KB) can take
5-25s (see specialist_timeout_seconds in config.py) — so POST acks
immediately and the actual reply is generated + sent in a BackgroundTask,
as a separate outbound call, not as the webhook's response body.

Text messages go straight through. Voice notes are transcribed and answered
as text.
# ponytail: no audio replies yet (would need Meta's resumable media-upload
# flow, a second API shape beyond send-text) — add when a demo specifically
# needs voice-in/voice-out on WhatsApp, not before.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response

from apps.backend.config import get_settings
from apps.backend.turn import translated_turn
from language.provider import LanguageProvider

log = logging.getLogger("ai-saheli.whatsapp")

router = APIRouter()

GRAPH_TIMEOUT_SECONDS = 20.0


@dataclass
class InboundMessage:
    wa_id: str
    kind: Literal["text", "audio"]
    text: str | None = None
    media_id: str | None = None


def _extract_inbound(payload: dict) -> InboundMessage | None:
    """Pull the first user message out of a webhook payload, or None.

    Returns None for anything that isn't a fresh inbound message — status
    callbacks (sent/delivered/read receipts) share the same payload shape but
    have no "messages" key, and are the majority of what this webhook
    actually receives in production.
    """
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        messages = value.get("messages")
        if not messages:
            return None
        msg = messages[0]
        wa_id = msg["from"]
        if msg["type"] == "text":
            return InboundMessage(wa_id=wa_id, kind="text", text=msg["text"]["body"])
        if msg["type"] == "audio":
            return InboundMessage(wa_id=wa_id, kind="audio", media_id=msg["audio"]["id"])
        return None
    except (KeyError, IndexError, TypeError):
        return None


@router.get("/whatsapp-webhook")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> Response:
    settings = get_settings()
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verify token mismatch.")


@router.post("/whatsapp-webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    payload = await request.json()
    inbound = _extract_inbound(payload)
    if inbound is not None:
        background_tasks.add_task(_handle_inbound, inbound, request.app.state.graph, request.app.state.language)
    # Ack immediately regardless — Meta retries aggressively on non-200s.
    return {"status": "received"}


async def _handle_inbound(inbound: InboundMessage, graph, provider: LanguageProvider) -> None:
    settings = get_settings()
    if not settings.whatsapp_configured:
        log.warning("Inbound WhatsApp message dropped — WHATSAPP_* env vars not configured.")
        return

    try:
        if inbound.kind == "audio":
            audio_b64 = await _download_media_base64(inbound.media_id, settings)
            text = await provider.transcribe(audio_b64, "hi")
            if not text.strip():
                await _send_text(inbound.wa_id, "Sorry, I couldn't hear that clearly. Could you try again?", settings)
                return
        else:
            text = inbound.text or ""

        _, localized, _, _ = await translated_turn(
            provider, graph, session_id=inbound.wa_id, message=text, channel="whatsapp", lang="hi"
        )
        if localized:
            await _send_text(inbound.wa_id, localized, settings)
    except Exception:
        log.exception("Failed to process inbound WhatsApp message from %s", inbound.wa_id)


async def _send_text(to: str, body: str, settings) -> None:
    url = f"https://graph.facebook.com/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}}
    async with httpx.AsyncClient(timeout=GRAPH_TIMEOUT_SECONDS) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            log.error("WhatsApp send failed (%s): %s", resp.status_code, resp.text)


async def _download_media_base64(media_id: str, settings) -> str:
    """Two-step fetch: media_id -> temporary URL -> raw bytes (both need the bearer token)."""
    import base64

    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    async with httpx.AsyncClient(timeout=GRAPH_TIMEOUT_SECONDS) as client:
        meta_url = f"https://graph.facebook.com/{settings.whatsapp_api_version}/{media_id}"
        meta_resp = await client.get(meta_url, headers=headers)
        meta_resp.raise_for_status()
        media_url = meta_resp.json()["url"]

        media_resp = await client.get(media_url, headers=headers)
        media_resp.raise_for_status()
        return base64.b64encode(media_resp.content).decode()
