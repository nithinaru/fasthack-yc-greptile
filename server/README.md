# server/ — wallet, Stripe, ask-flow (PRD §3.4/§3.5, v2 all-Modal)

## Run

| Mode | Command | Needs |
|---|---|---|
| Mock (default) | `bash server/run_local.sh` | nothing — fixtures only |
| Live local | same, with `.env` populated and `USE_MOCKS=0` | keys, Modal endpoints |
| Modal | `modal deploy modal_apps/serve.py` | Modal account, `repo-radio-secrets` Secret |

Tests: `python3 -m pytest server/ -q` (mock wallet/API, SQLite atomic debit,
Stripe signature verification, live ask-flow with faked network edges + schema
validation — live-key-dependent parts skip automatically when keys are absent).

## Architecture (v2 — no AWS)

- **Wallet store**: SQLite (`server/wallet.py`), file path from `WALLET_DB` env
  (default `DATA_DIR/wallet.db`). On Modal, `DATA_DIR` is a path on a mounted
  Volume so balances survive container restarts. Debit is one atomic
  `UPDATE wallets SET credits = credits - ? WHERE user_id = ? AND credits >= ?`.
- **Static content**: `DATA_DIR` (default `web/`) is served at both `/` (with
  `index.html` fallback — episodes, audio, RSS all live under it) and `/static`.
  On Modal that directory is a mounted Volume the pipeline publishes onto.
- **API**: `server/app.py`, the wallet API from PRD §3.4, unchanged shape from
  v1 aside from the new tiers and SQLite-backed wallet.
- (Honest note) distribution is designed to swap to S3+CloudFront behind an env
  flag; today everything — models, API, static — serves from Modal.

## Mock-mode behaviors (so the frontend isn't surprised)

- Wallet seeds from `fixtures/wallet.json` on first run → `demo@reporadio.fm`
  starts with a balance.
- `POST /api/topup` credits **immediately** (no Stripe) and returns a fake
  success-redirect URL — the redirect → poll-wallet → balance-count-up flow is
  fully drivable keyless.
- `POST /api/stripe/webhook` accepts an unsigned Stripe-shaped event JSON.
- `POST /api/ask` debits for real (402 at zero) and the job completes after a
  short simulated delay with a canned qa_segment citing real ep-000 fixture
  code + the fixture MP3.

## Going live, one integration at a time

1. **Wallet**: SQLite needs no setup — just a writable `WALLET_DB` path.
2. **Stripe**: `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` in `.env`. Locally:
   `stripe listen --forward-to localhost:8000/api/stripe/webhook` and use the
   `whsec_…` it prints. In prod, register the Modal `/serve` URL as the
   webhook endpoint in the Stripe dashboard (test mode).
3. **Ask-flow**: `MODAL_SCRIPT_URL`/`MODAL_TTS_URL` (from deploying
   `modal_apps/script.py` / `modal_apps/tts.py`) + `GREPTILE_API_KEY`/
   `GITHUB_TOKEN`. Live QA audio is written as a WAV file into
   `DATA_DIR/audio/`.
4. **Deploy**: `modal deploy modal_apps/serve.py` — prints the public `/serve`
   URL; put it in `.env` as `MODAL_SERVE_URL` and sync into `web/config.js`.

`USE_MOCKS` is all-or-nothing in server code; leaving `USE_MOCKS=0` with an
integration's keys/URLs unset fails that path fast with a clear error rather
than silently misbehaving.
