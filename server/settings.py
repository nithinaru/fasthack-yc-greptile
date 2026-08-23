"""Lane D configuration. All values come from the environment (.env is loaded by
Make / the entrypoint, never committed). Mock-first: USE_MOCKS=1 is the default."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "fixtures"

USE_MOCKS = os.environ.get("USE_MOCKS", "1") == "1"

AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")
S3_BUCKET = os.environ.get("S3_BUCKET", "repo-radio-live")
WALLETS_TABLE = os.environ.get("WALLETS_TABLE", "wallets")

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

GREPTILE_API_KEY = os.environ.get("GREPTILE_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
MODAL_SCRIPT_URL = os.environ.get("MODAL_SCRIPT_URL", "")
MODAL_TTS_URL = os.environ.get("MODAL_TTS_URL", "")

# CloudFront origin(s) for CORS; "*" until the distro URL is known.
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]

# Frontend URL Stripe Checkout redirects back to after payment.
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000")

# Wallet tiers, frozen by contracts/wallet_api.md: $5→45cr, $10→100cr, $20→220cr.
TIERS = {5: 45, 10: 100, 20: 220}
CREDITS_PER_QUESTION = 1
