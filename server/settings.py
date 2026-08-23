"""Server configuration. All values come from the environment (.env is loaded by
Make / the entrypoint, never committed). Mock-first: USE_MOCKS=1 is the default.

v2: no AWS. Modal hosts everything — models, the FastAPI API, and static content
(DATA_DIR points at a plain directory locally; on Modal it's a path on a Volume).
"""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "fixtures"

USE_MOCKS = os.environ.get("USE_MOCKS", "1") == "1"

# Static content dir: served at "/" and "/static". Locally this is repo_root/web;
# on Modal it's a path on a mounted Volume (e.g. /data/static).
DATA_DIR = Path(os.environ.get("DATA_DIR", str(REPO_ROOT / "web")))

# claude-mem worker (PRD §5.5), local by default.
CLAUDE_MEM_URL = os.environ.get("CLAUDE_MEM_URL", "http://localhost:37777")

# SQLite wallet DB. Locally this lands under DATA_DIR; on Modal it's on the
# mounted Volume (e.g. /data/wallet.db) so it survives across container restarts.
WALLET_DB = os.environ.get("WALLET_DB", str(DATA_DIR / "wallet.db"))

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

GREPTILE_API_KEY = os.environ.get("GREPTILE_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
MODAL_SCRIPT_URL = os.environ.get("MODAL_SCRIPT_URL", "")
MODAL_TTS_URL = os.environ.get("MODAL_TTS_URL", "")
MODAL_SERVE_URL = os.environ.get("MODAL_SERVE_URL", "")

# CORS: allow-all is acceptable for the hackathon.
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]

# Frontend URL Stripe Checkout redirects back to after payment.
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000")

# Wallet tiers, FROZEN per PRD §1/§3.4: $1 → 10 credits, $5 → 55, $10 → 120.
TIERS = {1: 10, 5: 55, 10: 120}
CREDITS_PER_QUESTION = 1
