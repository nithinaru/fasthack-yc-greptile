# Repo Radio — shared targets (frozen at Gate 0; changes need a SYNC commit)
# Env comes from .env (see .env.example). Load with: set -a; . ./.env; set +a

PYTHON ?= python3
-include .env
export

.PHONY: smoke bake-episode serve-local fixtures publish test-money snapshot demo-local

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

# Headless end-to-end money-loop verifier against the deployed MODAL_SERVE_URL:
# wallet baseline -> topup checkout_url -> hand-signed Stripe webhook -> credit
# -> ask debit -> optional answer poll. Exit 0 iff all non-BLOCKED steps pass.
test-money:
	$(PYTHON) scripts/test_money.py

# Self-contained offline copy of the site for the wifi-off demo fallback.
# demo_backup/site/  — full static site (index.html, config.js, js/, vendor/, all episodes, all audio, memory.json, feed.xml)
# demo_backup/live/  — extra insurance: ep-001 pulled straight from the live public Modal URL
snapshot:
	mkdir -p demo_backup/site/js demo_backup/site/episodes demo_backup/site/audio demo_backup/live/episodes demo_backup/live/audio
	cp web/index.html demo_backup/site/
	cp web/config.js demo_backup/site/
	cp -r web/js/. demo_backup/site/js/
	cp -r web/vendor demo_backup/site/
	cp web/episodes/*.json demo_backup/site/episodes/
	cp web/audio/*.mp3 demo_backup/site/audio/
	cp web/memory.json demo_backup/site/
	cp web/feed.xml demo_backup/site/
	@if [ -z "$(MODAL_SERVE_URL)" ]; then \
		echo "snapshot: MODAL_SERVE_URL not set (.env) — skipping demo_backup/live/ curl insurance"; \
	else \
		curl -fsSL "$(MODAL_SERVE_URL)/episodes/ep-001.json" -o demo_backup/live/episodes/ep-001.json && \
		curl -fsSL "$(MODAL_SERVE_URL)/audio/ep-001.mp3" -o demo_backup/live/audio/ep-001.mp3 && \
		echo "snapshot: pulled live ep-001 into demo_backup/live/"; \
	fi
	@echo "snapshot: demo_backup/site/ and demo_backup/live/ ready"

# Zero-network demo server: serves the self-contained snapshot (falls back to web/ if not baked yet).
demo-local:
	bash scripts/demo_local.sh
