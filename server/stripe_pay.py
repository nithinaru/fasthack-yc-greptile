"""Stripe Checkout top-ups + webhook crediting (PRD §3.4, test mode all day).

Mock mode (USE_MOCKS=1) or no STRIPE_SECRET_KEY: /api/topup credits the wallet
immediately and returns a fake success-redirect URL so the frontend can build
the full redirect -> poll-wallet -> balance-count-up loop with no Stripe
account at all.
"""
import json
import logging
import os
import threading
import uuid

import settings
import wallet

log = logging.getLogger("server.stripe")

# --- Webhook idempotency store -------------------------------------------------
# Stripe retries deliveries, and a replayed event must never double-credit.
# Dedup on the Stripe event id. Inside a Modal container we use a shared
# modal.Dict (SQLite-on-Volume is NOT shared across containers — that bug
# already bit the wallet, see server/wallet.py). Locally/in tests an
# in-process set is fine. Mark-then-credit: acceptable for the demo (worst
# case a crash between mark and credit drops one credit, never doubles).
_events_lock = threading.Lock()
_events_dict = None  # shared modal.Dict when on Modal, else None
_events_local: set[str] = set()  # local/test fallback


def _get_events_dict():
    """Return the shared modal.Dict of seen event ids when running inside a
    Modal container, else None (in-process set). Mirrors wallet._get_dict."""
    global _events_dict
    if _events_dict is not None:
        return _events_dict
    if not os.environ.get("MODAL_TASK_ID"):  # set inside Modal containers only
        return None
    with _events_lock:
        if _events_dict is None:
            import modal

            _events_dict = modal.Dict.from_name(
                "repo-radio-stripe-events", create_if_missing=True
            )
            log.info("stripe event store: modal.Dict 'repo-radio-stripe-events'")
    return _events_dict


def _mark_event_seen(event_id: str) -> bool:
    """Record event_id as processed. Returns True if it was NEW (proceed to
    credit), False if we've already seen it (skip)."""
    d = _get_events_dict()
    if d is not None:
        if d.get(event_id):
            return False
        d[event_id] = True  # mark-then-credit; see module comment above
        return True
    with _events_lock:
        if event_id in _events_local:
            return False
        _events_local.add(event_id)
        return True


def _reset_events_for_tests() -> None:
    """Test helper: forget all seen event ids (local backend only)."""
    global _events_dict
    with _events_lock:
        _events_local.clear()
        _events_dict = None


def _keyless() -> bool:
    return settings.USE_MOCKS or not settings.STRIPE_SECRET_KEY


def create_checkout(user_id: str, tier: int) -> str:
    """Return a Checkout URL for the tier. Raises ValueError on unknown tier."""
    credits = settings.TIERS.get(tier)
    if credits is None:
        raise ValueError(f"unknown tier {tier}; valid: {sorted(settings.TIERS)}")

    if _keyless():
        ref = f"cs_mock_{uuid.uuid4().hex[:12]}"
        if settings.USE_MOCKS:
            # Mock mode only: credit immediately so the UI loop works keyless.
            wallet.credit(user_id, credits)
            log.info("MOCK topup: %s +%d credits (%s)", user_id, credits, ref)
        return f"{settings.SITE_URL}/?topup=success&session={ref}"

    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "unit_amount": tier * 100,
                "product_data": {"name": f"Repo Radio wallet — {credits} credits"},
            },
            "quantity": 1,
        }],
        metadata={"user_id": user_id, "credits": str(credits)},
        success_url=f"{settings.SITE_URL}/?topup=success",
        cancel_url=f"{settings.SITE_URL}/?topup=cancelled",
    )
    return session.url


def handle_webhook(payload: bytes, sig_header: str | None) -> None:
    """Verify + process checkout.session.completed. Raises ValueError on a bad
    signature. Mock mode skips verification and accepts a raw Stripe-shaped
    event JSON (what `stripe trigger` / a hand-rolled curl sends)."""
    if settings.USE_MOCKS:
        event = json.loads(payload)
    else:
        import stripe

        try:
            stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except (ValueError, stripe.error.SignatureVerificationError) as e:
            raise ValueError(f"webhook verification failed: {e}") from e
        # Signature verified; parse the authenticated payload as a plain dict
        # (construct_event returns a StripeObject with different access semantics).
        event = json.loads(payload)

    if event.get("type") != "checkout.session.completed":
        return
    session = event.get("data", {}).get("object", {})
    meta = session.get("metadata") or {}
    user_id = str(meta.get("user_id", "")).lower()
    try:
        credits = int(meta.get("credits", 0))
    except (TypeError, ValueError):
        credits = 0
    if not user_id or credits <= 0:
        log.warning("webhook with missing/invalid metadata: %s", meta)
        return

    # Idempotency: Stripe retries deliveries; the same event must credit once.
    # Real Stripe events always carry a top-level id ("evt_..."); fall back to
    # the checkout session id for hand-rolled/mock payloads that omit it.
    event_id = event.get("id") or session.get("id") or ""
    if event_id and not _mark_event_seen(event_id):
        log.info("webhook duplicate ignored: event=%s user=%s", event_id, user_id)
        return

    balance = wallet.credit(user_id, credits)
    log.info(
        "STRIPE CREDIT: user=%s +%d credits (balance=%d) event=%s",
        user_id, credits, balance, event_id or "unknown",
    )
