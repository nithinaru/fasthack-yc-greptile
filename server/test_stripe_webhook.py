"""Verification without live keys: the signed-webhook path, exercised by
signing payloads exactly the way Stripe does (t=<ts>,v1=HMAC-SHA256("{t}.{body}")).

Run: python3 -m pytest server/test_stripe_webhook.py -q
"""
import hashlib
import hmac
import json
import tempfile
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


def event_bytes(user_id="judge@test.com", credits="100", session_id="cs_live_1",
                event_id="evt_test_1") -> bytes:
    return json.dumps({
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {"object": {"id": session_id,
                            "metadata": {"user_id": user_id, "credits": credits}}},
    }).encode()


@pytest.fixture()
def live_mode(monkeypatch, tmp_path):
    # Fresh SQLite file per test so balances don't leak between tests.
    monkeypatch.setattr(settings, "USE_MOCKS", False)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(settings, "WALLET_DB", str(tmp_path / "wallet.db"))
    wallet._reset_for_tests()
    stripe_pay._reset_events_for_tests()
    yield wallet
    wallet._reset_for_tests()
    stripe_pay._reset_events_for_tests()


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


def test_duplicate_event_not_double_credited(live_mode):
    """Stripe retries deliveries: the same event id must credit exactly once."""
    payload = event_bytes(credits="100", event_id="evt_dup_1")
    stripe_pay.handle_webhook(payload, sign(payload))
    stripe_pay.handle_webhook(payload, sign(payload))  # exact redelivery
    stripe_pay.handle_webhook(payload, sign(payload))  # and again
    assert live_mode.get_credits("judge@test.com") == 100


def test_distinct_events_credit_separately(live_mode):
    """Different event ids are separate purchases and must all credit."""
    p1 = event_bytes(credits="100", event_id="evt_a", session_id="cs_a")
    p2 = event_bytes(credits="55", event_id="evt_b", session_id="cs_b")
    stripe_pay.handle_webhook(p1, sign(p1))
    stripe_pay.handle_webhook(p2, sign(p2))
    assert live_mode.get_credits("judge@test.com") == 155


def test_duplicate_without_event_id_dedups_on_session_id(live_mode):
    """Payloads missing a top-level id (mock/hand-rolled) dedup on session id."""
    raw = json.dumps({
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_no_evt",
                            "metadata": {"user_id": "judge@test.com", "credits": "10"}}},
    }).encode()
    stripe_pay.handle_webhook(raw, sign(raw))
    stripe_pay.handle_webhook(raw, sign(raw))
    assert live_mode.get_credits("judge@test.com") == 10


def test_replayed_bad_signature_still_rejected_after_success(live_mode):
    """A valid delivery must not whitelist the payload for later forgeries."""
    payload = event_bytes(credits="100", event_id="evt_replay")
    stripe_pay.handle_webhook(payload, sign(payload))
    with pytest.raises(ValueError):
        stripe_pay.handle_webhook(payload, sign(payload, secret="whsec_wrong"))
    assert live_mode.get_credits("judge@test.com") == 100


def test_tier_mapping_frozen():
    assert settings.TIERS == {1: 10, 5: 55, 10: 120}
