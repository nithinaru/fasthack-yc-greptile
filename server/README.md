# server/ — Lane D: wallet, Stripe, ask-flow (contracts/wallet_api.md)

## Run

| Mode | Command | Needs |
|---|---|---|
| Mock (default) | `bash server/run_local.sh` (or `make serve-local` with the venv active) | nothing — fixtures only |
| Live local (D6 fallback) | same, with `.env` populated and `USE_MOCKS=0` | keys + AWS resources |
| App Runner (D5) | `bash server/deploy_apprunner.sh` | Docker, ECR/App Runner roles from `infra/aws_setup.sh` |

Tests: `.venv/bin/python3.14 -m pytest server/ -q` (16 tests: mock API, DynamoDB
atomic debit via moto, Stripe signature verification, live ask-flow with faked
network edges + schema validation).

## Mock-mode behaviors (so Lane C isn't surprised)

- Wallet seeds from `fixtures/wallet.json` → `demo@reporadio.fm` starts at 100.
- `POST /api/topup` credits **immediately** (no Stripe) and returns a fake
  success-redirect URL — the redirect → poll → count-up flow is fully drivable.
- `POST /api/stripe/webhook` accepts an unsigned Stripe-shaped event JSON.
- `POST /api/ask` debits for real (402 at zero) and the job completes instantly
  with a canned qa_segment citing real ep-000 fixture code + the fixture MP3.

## Going live, one integration at a time

1. **DynamoDB** (`USE_MOCKS=0`): needs `wallets` table (`infra/aws_setup.sh`).
2. **Stripe**: `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` in `.env`. Locally:
   `stripe listen --forward-to localhost:8080/api/stripe/webhook` and use the
   `whsec_…` it prints.
3. **Ask-flow**: `MODAL_SCRIPT_URL`/`MODAL_TTS_URL` from `modal_apps/ENDPOINTS.md`
   + `GREPTILE_API_KEY`/`GITHUB_TOKEN`. QA audio is uploaded as WAV to
   `s3://$S3_BUCKET/audio/`.
4. **Deploy** (D5): `bash server/deploy_apprunner.sh`, then `SYNC:` the printed
   base URL into `web/config.js`.

Note: `USE_MOCKS` is all-or-nothing in server code; per-integration flips are
done by keeping `USE_MOCKS=0` and leaving the unready integration's keys/URLs
empty only if you don't exercise that path (ask fails fast with a clear error
if Modal URLs are unset).
