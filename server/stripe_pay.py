"""Stripe Checkout top-ups + webhook crediting (PRD §5.6, test mode all day).
Mock mode needs no Stripe account: /api/topup credits the wallet immediately and
returns a fake success-redirect URL so Lane C can build the full redirect →
poll-wallet → balance-count-up flow against USE_MOCKS=1."""
import json
import logging
import uuid

import settings
import wallet

log = logging.getLogger("server.stripe")


def create_checkout(user_id: str, tier: int) -> str:
    """Return a Checkout URL for the tier. Raises ValueError on unknown tier."""
    credits = settings.TIERS.get(tier)
    if credits is None:
        raise ValueError(f"unknown tier {tier}; valid: {sorted(settings.TIERS)}")

    if settings.USE_MOCKS:
        ref = f"cs_mock_{uuid.uuid4().hex[:12]}"
        wallet.get_store().credit(user_id, credits, ref)
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
    ref = session.get("id", "cs_unknown")
    wallet.get_store().credit(user_id, credits, ref)
    log.info("webhook credited %s +%d (%s)", user_id, credits, ref)
