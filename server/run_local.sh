#!/usr/bin/env bash
# D6 — the local fallback: identical API from the laptop if App Runner misbehaves.
#   Terminal 1: bash server/run_local.sh
#   Terminal 2: stripe listen --forward-to localhost:8080/api/stripe/webhook
#               (copy its whsec_… into .env STRIPE_WEBHOOK_SECRET, restart T1)
#   Terminal 3: cloudflared tunnel --url http://localhost:8080
#               (SYNC the printed https URL into web/config.js)
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] && { set -a; source .env; set +a; }

PY=.venv/bin/python3.14
[ -x "$PY" ] || PY=.venv/bin/python
[ -x "$PY" ] || { echo "no .venv — run: python3 -m venv .venv && .venv/bin/pip install -r server/requirements.txt"; exit 1; }

exec "$PY" -m uvicorn app:app --app-dir server --host 0.0.0.0 --port 8080
