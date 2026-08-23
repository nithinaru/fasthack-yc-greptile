# Repo Radio — shared targets (frozen at Gate 0; changes need a SYNC commit)
# Env comes from .env (see .env.example). Load with: set -a; . ./.env; set +a

PYTHON ?= python3
-include .env
export

.PHONY: smoke bake-episode serve-local fixtures publish

smoke:
	$(PYTHON) scripts/smoke.py

# Full pipeline: repo in → published episode out. Usage: make bake-episode REPO=owner/name
bake-episode:
	$(PYTHON) -m pipeline.bake --repo "$(REPO)"

# Local FastAPI dev server. Run from repo root so DATA_DIR default (web/) resolves.
# Pair with: stripe listen --forward-to localhost:8080/api/stripe/webhook
serve-local:
	uvicorn server.app:app --port 8080 --reload

# Regenerate ep-000 fixture from fixtures/src
fixtures:
	$(PYTHON) fixtures/generate_ep000.py

# Deploy all three Modal apps: /script, /tts, /serve. Record the resulting
# URLs in .env (MODAL_SCRIPT_URL / MODAL_TTS_URL / MODAL_SERVE_URL) and in
# ENDPOINTS.md.
publish:
	modal deploy modal_apps/script.py
	modal deploy modal_apps/tts.py
	modal deploy modal_apps/serve.py
