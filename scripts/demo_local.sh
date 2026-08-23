#!/usr/bin/env bash
# Zero-network demo server (Repo Radio, M6 "venue wifi dies" fallback).
#
# Serves demo_backup/site/ (the self-contained snapshot baked by `make snapshot`)
# on localhost, falling back to web/ if the snapshot doesn't exist yet.
# No CDN dependencies are required to run this — everything served must be
# local (fonts, tailwind, wavesurfer). We verify that before starting.
#
# Usage: bash scripts/demo_local.sh [port]

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-8090}"

SITE_DIR="$ROOT_DIR/demo_backup/site"
if [ ! -f "$SITE_DIR/index.html" ]; then
  echo "demo_local: demo_backup/site/ missing or incomplete (run 'make snapshot' first) — falling back to web/"
  SITE_DIR="$ROOT_DIR/web"
fi

if [ ! -f "$SITE_DIR/index.html" ]; then
  echo "demo_local: no index.html found in $SITE_DIR — nothing to serve" >&2
  exit 1
fi

# --- Verify local vendor assets are present ---
MISSING=0
for f in vendor/tailwind.js vendor/wavesurfer.esm.js vendor/fonts/fonts.css; do
  if [ ! -f "$SITE_DIR/$f" ]; then
    echo "demo_local: WARNING missing local vendor asset: $f" >&2
    MISSING=1
  fi
done
if [ "$MISSING" -eq 1 ]; then
  echo "demo_local: vendor/ is incomplete — page will likely try to hit the network. Not editing web/ (out of scope); report this to the owner." >&2
fi

# --- Verify index.html references only local vendor paths (no external CDN tags) ---
if grep -Eo '(src|href)="https?://[^"]+"' "$SITE_DIR/index.html" >/tmp/demo_local_cdn_refs.$$ 2>/dev/null; then
  if [ -s /tmp/demo_local_cdn_refs.$$ ]; then
    echo "demo_local: LOUD WARNING — index.html references external URL(s), demo will NOT be wifi-safe:" >&2
    cat /tmp/demo_local_cdn_refs.$$ >&2
  fi
fi
rm -f /tmp/demo_local_cdn_refs.$$

echo "demo_local: serving $SITE_DIR"
echo "demo_local: open http://localhost:$PORT/index.html"
cd "$SITE_DIR"
exec python3 -m http.server "$PORT"
