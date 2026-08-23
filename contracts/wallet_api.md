# Wallet API contract (PRD §3.4) — FastAPI, served by Modal (`modal_apps/serve.py`)

FROZEN. Changes require human approval.

`user_id` = lowercase email, stored in the browser's localStorage.
CORS: allow-all is acceptable for the hackathon.

## Endpoints

```
POST /api/topup            {user_id, tier: 1|5|10}         → {checkout_url}
POST /api/stripe/webhook   (Stripe signed)                 → 200
GET  /api/wallet/{user_id}                                 → {credits: int}
POST /api/ask              {user_id, episode_id, question} → 402 {error:"no_credits"} | {job_id}
GET  /api/ask/{job_id}                                     → {status:"pending"} | {status:"done", qa_segment: {…}}
```

### POST /api/topup
Request: `{"user_id": "someone@example.com", "tier": 10}` — tier ∈ {1, 5, 10} (USD).
Mock mode / no `STRIPE_SECRET_KEY`: credits the wallet immediately and returns a
fake success-redirect URL (no Stripe account needed to exercise the UI loop).
Live: creates a Stripe Checkout Session with `metadata: {user_id, credits}`.
Credit mapping (FROZEN): **$1 → 10 cr · $5 → 55 cr · $10 → 120 cr**.
Response `200`: `{"checkout_url": "https://checkout.stripe.com/..."}`

### POST /api/stripe/webhook
Stripe `checkout.session.completed`, signature verified with `STRIPE_WEBHOOK_SECRET`.
Reads session metadata → increments the SQLite wallet's `credits`.
Response: `200` (empty body OK).

### GET /api/wallet/{user_id}
Response `200`: `{"credits": 100}` — unknown user returns `{"credits": 0}` (implicit wallet).

### POST /api/ask
Request: `{"user_id": "...", "episode_id": "ep-004", "question": "Is the auth real?"}`
Cost: 1 credit. Debit is an atomic SQLite update:
`UPDATE wallets SET credits = credits - 1 WHERE user_id = ? AND credits >= 1`.
- Insufficient credits → `402` `{"error": "no_credits"}`
- Accepted → `200` `{"job_id": "<opaque string>"}`

### GET /api/ask/{job_id}
- In flight → `200` `{"status": "pending"}`
- Complete → `200` `{"status": "done", "qa_segment": {…}}` where `qa_segment` matches the
  `qa_segments[]` item shape in `contracts/episode.schema.json`
  (`{question, audio_url, segments[]}`, segments same shape as episode segments).
- Unknown job → `404`.

## Wallet store — SQLite (no AWS)
File path from `WALLET_DB` env (default `DATA_DIR/wallet.db`); on Modal this
lives on a mounted Volume so balances survive container restarts.
Table `wallets(user_id TEXT PRIMARY KEY, credits INTEGER NOT NULL DEFAULT 0)`.
