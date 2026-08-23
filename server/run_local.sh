#!/usr/bin/env bash
# Simple local launcher — the same FastAPI app modal_apps/serve.py wraps for Modal.
#   bash server/run_local.sh
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] && { set -a; source .env; set +a; }

PY=.venv/bin/python3
[ -x "$PY" ] || PY=.venv/bin/python
[ -x "$PY" ] || { echo "no .venv — run: python3 -m venv .venv && .venv/bin/pip install -r server/requirements.txt"; exit 1; }

exec "$PY" -m uvicorn app:app --app-dir server --host 0.0.0.0 --port 8000
