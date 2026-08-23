"""A3 — Scriptwriter call: POST Modal /script (Qwen-vLLM) per PRD §5.3.

USE_MOCKS=1 (default): returns fixtures/script_response.json.
Live mode needs MODAL_SCRIPT_URL in the environment (Lane B publishes it in
modal_apps/ENDPOINTS.md → .env).

The response is validated strictly against the frozen shape:
  { title, verdict: HYPE|REAL|MIXED,
    segments: [ {text, citation: null | {file, start_line, end_line}} ] }
Parse/validation failure retries the call up to 2 times (PRD: guided decoding
plus retry-on-parse-fail), then falls back to the last good response cached in
runs/last_good_script.json if one exists.

CLI:  python -m pipeline.script --repo owner/name  (feeds fixture findings in mock mode)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "fixtures" / "script_response.json"
LAST_GOOD = ROOT / "runs" / "last_good_script.json"

VERDICTS = {"HYPE", "REAL", "MIXED"}
MAX_RETRIES = 2


class ScriptValidationError(ValueError):
    pass


def _use_mocks() -> bool:
    return os.environ.get("USE_MOCKS", "1") == "1"


def validate_script(data: dict) -> dict:
    """Raise ScriptValidationError unless data matches the frozen script shape."""
    if not isinstance(data, dict):
        raise ScriptValidationError("response is not a JSON object")
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        raise ScriptValidationError("missing/empty title")
    if data.get("verdict") not in VERDICTS:
        raise ScriptValidationError(f"bad verdict: {data.get('verdict')!r}")
    segs = data.get("segments")
    if not isinstance(segs, list) or not segs:
        raise ScriptValidationError("segments missing or empty")
    for i, seg in enumerate(segs):
        if not isinstance(seg.get("text"), str) or not seg["text"].strip():
            raise ScriptValidationError(f"segment {i}: missing text")
        cit = seg.get("citation", "MISSING")
        if cit == "MISSING":
            raise ScriptValidationError(f"segment {i}: citation key absent")
        if cit is not None:
            if not isinstance(cit, dict) or not isinstance(cit.get("file"), str):
                raise ScriptValidationError(f"segment {i}: bad citation.file")
            for k in ("start_line", "end_line"):
                if not isinstance(cit.get(k), int) or cit[k] < 1:
                    raise ScriptValidationError(f"segment {i}: bad citation.{k}")
    return data


def _call_modal(payload: dict) -> dict:
    url = os.environ.get("MODAL_SCRIPT_URL")
    if not url:
        raise RuntimeError("MODAL_SCRIPT_URL unset — Lane B's ENDPOINTS.md not wired into .env yet")
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def write_script(repo_meta: dict, greptile_findings: list, memory_digest: str = "") -> dict:
    """repo_meta + 5 findings + memory digest → validated script dict."""
    if _use_mocks():
        return validate_script(json.loads(FIXTURE.read_text()))

    payload = {
        "repo_meta": repo_meta,
        "greptile_findings": greptile_findings,
        "memory_digest": memory_digest,
    }
    last_err: Exception | None = None
    for attempt in range(1 + MAX_RETRIES):
        try:
            script = validate_script(_call_modal(payload))
            LAST_GOOD.parent.mkdir(parents=True, exist_ok=True)
            LAST_GOOD.write_text(json.dumps(script, indent=2))
            return script
        except (ScriptValidationError, json.JSONDecodeError) as e:
            last_err = e
            print(f"  script attempt {attempt + 1} invalid: {e}", file=sys.stderr)
    if LAST_GOOD.exists():
        print("  all retries failed — using runs/last_good_script.json", file=sys.stderr)
        return validate_script(json.loads(LAST_GOOD.read_text()))
    raise RuntimeError(f"script generation failed after {1 + MAX_RETRIES} attempts: {last_err}")


def main() -> None:
    ap = argparse.ArgumentParser(description="generate the episode script")
    ap.add_argument("--repo", required=True, help="owner/name")
    args = ap.parse_args()

    from pipeline import greptile  # local import keeps CLI startup cheap

    findings = greptile.run_battery(args.repo)
    script = write_script({"full_name": args.repo}, findings.get("battery", []))
    json.dump(script, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
