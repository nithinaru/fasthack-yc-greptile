# Wallet API contract (PRD §6.2) — FastAPI on App Runner (Lane D)

FROZEN at Gate 0. Changes require a `SYNC:` commit approved by the human.

`user_id` = lowercase email, stored in the browser's localStorage.
CORS: allow the CloudFront origin.

## Endpoints

```
POST /api/topup            {user_id, tier: 5|10|20}        → {checkout_url}
POST /api/stripe/webhook   (Stripe signed)                 → 200
GET  /api/wallet/{user_id}                                 → {credits: int}
POST /api/ask              {user_id, episode_id, question} → 402 {error:"no_credits"} | {job_id}
GET  /api/ask/{job_id}                                     → {status:"pending"} | {status:"done", qa_segment: {…}}
```

### POST /api/topup
Request: `{"user_id": "someone@example.com", "tier": 10}` — tier ∈ {5, 10, 20} (USD).
Creates a Stripe Checkout Session with `metadata: {user_id, credits}`.
Credit mapping: **$5 → 45 cr · $10 → 100 cr · $20 → 220 cr**.
Response `200`: `{"checkout_url": "https://checkout.stripe.com/..."}`

### POST /api/stripe/webhook
Stripe `checkout.session.completed`, signature verified with `STRIPE_WEBHOOK_SECRET`.
Reads session metadata → increments DynamoDB `wallets.credits` + appends ledger entry.
Response: `200` (empty body OK).

### GET /api/wallet/{user_id}
Response `200`: `{"credits": 100}` — unknown user returns `{"credits": 0}` (implicit wallet).

### POST /api/ask
Request: `{"user_id": "...", "episode_id": "ep-004", "question": "Is the auth real?"}`
Cost: 1 credit. Debit is an atomic DynamoDB conditional update
(`SET credits = credits - :one` with `ConditionExpression: credits >= :one`).
- Insufficient credits → `402` `{"error": "no_credits"}`
- Accepted → `200` `{"job_id": "<opaque string>"}`

### GET /api/ask/{job_id}
- In flight → `200` `{"status": "pending"}`
- Complete → `200` `{"status": "done", "qa_segment": {…}}` where `qa_segment` matches the
  `qa_segments[]` item shape in `contracts/episode.schema.json`
  (`{question, audio_url, segments[]}`, segments same shape as episode segments).
- Unknown job → `404`.

## DynamoDB `wallets`
PK `user_id` (S). Attributes: `credits` (N), `ledger` (L of `{ts, type, amount, ref}`).
