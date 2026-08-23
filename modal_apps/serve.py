"""Repo Radio — Modal app #3: serve. Wraps server/app.py's FastAPI app (the
wallet API, PRD §3.4) + static content (site, episode JSON, MP3s, RSS,
memory.json) from a Modal Volume.

Deploy:   modal deploy modal_apps/serve.py
Dev:      modal serve modal_apps/serve.py
Warm-up:  SERVE_MIN_CONTAINERS=1 modal deploy modal_apps/serve.py   (flip on before
          demo windows so the wallet API + static site never cold-start)

Secrets: expects a Modal Secret named "repo-radio-secrets" holding
STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET / GREPTILE_API_KEY / GITHUB_TOKEN /
MODAL_SCRIPT_URL / MODAL_TTS_URL. modal.Secret.from_name() only resolves at
deploy/run time, so this module still imports fine locally with nothing
deployed (`python3 -c "import modal_apps.serve"` needs no Modal login).

The pipeline (pipeline/publish.py) uploads episodes/audio/feed.xml/memory.json
onto the same Volume this app mounts at /data — that's the sanctioned publish
path; this app itself only serves what's already there plus the wallet API.
"""
from __future__ import annotations

import os
from pathlib import Path

import modal

APP_NAME = "repo-radio-serve"
LOCAL_DIR = Path(__file__).parent
REPO_ROOT = LOCAL_DIR.parent

# Keep-warm knob: flip to 1 before demo windows so the API + static site never
# cold-start during judging.
MIN_CONTAINERS = int(os.environ.get("SERVE_MIN_CONTAINERS", "0"))

app = modal.App(APP_NAME)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements(str(REPO_ROOT / "server" / "requirements.txt"))
    # Bundle server/ (the FastAPI app + its modules) into the image.
    .add_local_dir(REPO_ROOT / "server", remote_path="/root/server")
    # ask.py's live path does `from pipeline import greptile` — bundle it too.
    .add_local_dir(REPO_ROOT / "pipeline", remote_path="/root/pipeline")
    .add_local_dir(REPO_ROOT / "fixtures", remote_path="/root/fixtures")
)

# Wallet DB (SQLite) + all static content (site, episodes, audio, RSS,
# memory.json) live on this Volume so they survive container restarts and are
# shared across warm/cold containers.
data_volume = modal.Volume.from_name("repo-radio-data", create_if_missing=True)

try:
    secrets = [modal.Secret.from_name("repo-radio-secrets")]
except Exception:
    # Import-time safety net: if the secret doesn't exist yet (e.g. first-time
    # local import with no Modal auth), fall back to an empty secret list so
    # `import modal_apps.serve` never fails outside a real deploy.
    secrets = []


@app.function(
    image=image,
    volumes={"/data": data_volume},
    secrets=secrets,
    min_containers=MIN_CONTAINERS,
    scaledown_window=15 * 60,  # generous so back-to-back demos stay warm
    timeout=120,
)
@modal.asgi_app()
def fastapi_app():
    import sys

    sys.path.insert(0, "/root/server")
    sys.path.insert(0, "/root")

    os.environ.setdefault("DATA_DIR", "/data/static")
    os.environ.setdefault("WALLET_DB", "/data/wallet.db")

    # server/app.py builds its FastAPI `app` at import time, reading settings
    # from the environment above.
    import app as server_app  # noqa: E402  (path set up just above)

    # Modal Volumes snapshot at mount time — without an explicit reload this
    # container never sees episodes the pipeline publishes after it boots.
    # Throttled to once per 3s so request latency stays flat.
    import time

    state = {"last": 0.0}

    @server_app.app.middleware("http")
    async def _reload_volume(request, call_next):
        now = time.monotonic()
        if now - state["last"] > 3.0:
            state["last"] = now
            try:
                data_volume.reload()
            except Exception:
                pass  # a failed reload just means slightly stale reads
        return await call_next(request)

    return server_app.app
