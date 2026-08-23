"""D3 verification without live keys: the signed-webhook path, exercised by
signing payloads exactly the way Stripe does (t=<ts>,v1=HMAC-SHA256("{t}.{body}")).

Run: .venv/bin/python3.14 -m pytest server/test_stripe_webhook.py -q
"""
import hashlib
import hmac
import json
import time

import pytest

import server  # noqa: F401  (path shim: makes the flat imports below resolve)
import settings
import stripe_pay
import wallet

SECRET = "whsec_test_fake_secret"


def sign(payload: bytes, secret: str = SECRET, ts: int | None = None) -> str:
    ts = ts or int(time.time())
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256)
    return f"t={ts},v1={mac.hexdigest()}"


def event_bytes(user_id="judge@test.com", credits="100", session_id="cs_live_1") -> bytes:
    return json.dumps({
        "type": "checkout.session.completed",
        "data": {"object": {"id": session_id,
                            "metadata": {"user_id": user_id, "credits": credits}}},
    }).encode()


@pytest.fixture()
def live_mode(monkeypatch):
    monkeypatch.setattr(settings, "USE_MOCKS", False)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", SECRET)
    store = wallet.MockWalletStore()
    monkeypatch.setattr(wallet, "_store", store)
    return store


def test_valid_signature_credits_wallet(live_mode):
    payload = event_bytes(credits="100")
    stripe_pay.handle_webhook(payload, sign(payload))
    assert live_mode.get_credits("judge@test.com") == 100


def test_bad_signature_rejected(live_mode):
    payload = event_bytes()
    with pytest.raises(ValueError):
        stripe_pay.handle_webhook(payload, sign(payload, secret="whsec_wrong"))
    assert live_mode.get_credits("judge@test.com") == 0


def test_missing_signature_rejected(live_mode):
    with pytest.raises(ValueError):
        stripe_pay.handle_webhook(event_bytes(), None)


def test_stale_timestamp_rejected(live_mode):
    payload = event_bytes()
    stale = sign(payload, ts=int(time.time()) - 3600)
    with pytest.raises(ValueError):
        stripe_pay.handle_webhook(payload, stale)


def test_tampered_payload_rejected(live_mode):
    payload = event_bytes(credits="100")
    sig = sign(payload)
    tampered = payload.replace(b'"100"', b'"999"')
    with pytest.raises(ValueError):
        stripe_pay.handle_webhook(tampered, sig)
    assert live_mode.get_credits("judge@test.com") == 0


def test_other_event_types_ignored(live_mode):
    payload = json.dumps({"type": "payment_intent.created", "data": {"object": {}}}).encode()
    stripe_pay.handle_webhook(payload, sign(payload))
    assert live_mode.get_credits("judge@test.com") == 0


def test_tier_mapping_frozen():
    assert settings.TIERS == {5: 45, 10: 100, 20: 220}
