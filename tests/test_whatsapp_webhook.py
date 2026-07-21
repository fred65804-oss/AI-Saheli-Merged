"""WhatsApp webhook: verification handshake + inbound payload parsing.

Doesn't exercise _handle_inbound (that hits the real Graph API / ASR) — just
the two things that break silently and quietly if changed: the handshake
Meta uses to confirm you own the endpoint, and the payload parser that must
ignore status callbacks (delivered/read receipts) rather than crash on them.
"""

from fastapi.testclient import TestClient

from apps.backend.main import app
from apps.backend.whatsapp_webhook import _extract_inbound

client = TestClient(app)

TEXT_PAYLOAD = {
    "entry": [{"changes": [{"value": {"messages": [
        {"from": "919999999999", "type": "text", "text": {"body": "hello"}}
    ]}}]}]
}

STATUS_CALLBACK_PAYLOAD = {
    "entry": [{"changes": [{"value": {"statuses": [{"id": "abc", "status": "delivered"}]}}]}]
}

AUDIO_PAYLOAD = {
    "entry": [{"changes": [{"value": {"messages": [
        {"from": "919999999999", "type": "audio", "audio": {"id": "media123"}}
    ]}}]}]
}


def test_verify_webhook_returns_challenge_on_matching_token(monkeypatch):
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "my-secret-token")
    from apps.backend.config import get_settings
    get_settings.cache_clear()
    try:
        r = client.get(
            "/whatsapp-webhook",
            params={"hub.mode": "subscribe", "hub.verify_token": "my-secret-token", "hub.challenge": "12345"},
        )
        assert r.status_code == 200
        assert r.text == "12345"
    finally:
        get_settings.cache_clear()


def test_verify_webhook_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "my-secret-token")
    from apps.backend.config import get_settings
    get_settings.cache_clear()
    try:
        r = client.get(
            "/whatsapp-webhook",
            params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "12345"},
        )
        assert r.status_code == 403
    finally:
        get_settings.cache_clear()


def test_extract_inbound_parses_text_message():
    inbound = _extract_inbound(TEXT_PAYLOAD)
    assert inbound is not None
    assert inbound.kind == "text"
    assert inbound.wa_id == "919999999999"
    assert inbound.text == "hello"


def test_extract_inbound_parses_audio_message():
    inbound = _extract_inbound(AUDIO_PAYLOAD)
    assert inbound is not None
    assert inbound.kind == "audio"
    assert inbound.media_id == "media123"


def test_extract_inbound_ignores_status_callbacks():
    assert _extract_inbound(STATUS_CALLBACK_PAYLOAD) is None


def test_extract_inbound_handles_malformed_payload():
    assert _extract_inbound({}) is None
    assert _extract_inbound({"entry": []}) is None
