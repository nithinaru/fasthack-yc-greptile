"""A2 — Greptile: index + poll-until-ready + the 5-query interrogation battery (PRD §5.2).

USE_MOCKS=1 (default): returns fixtures/greptile_response.json, no network.
Live mode needs GREPTILE_API_KEY + GITHUB_TOKEN in the environment (.env).

Raw responses are persisted to runs/<UTC-stamp>/ for debugging and re-runs.

CLI:  python -m pipeline.greptile --repo owner/name [--branch main] [--skip-index]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "fixtures" / "greptile_response.json"
RUNS_DIR = ROOT / "runs"
API = "https://api.greptile.com/v2"

# PRD §5.2 — the interrogation battery, verbatim.
BATTERY = [
    "In 3 sentences: what does this repo actually do, architecturally? Name the 2–3 core modules and what each owns.",
    "Is the core functionality implemented in this codebase, or mostly delegated to external APIs/SDKs? Name the specific files that prove it.",
    "List claims the README makes that are NOT fully supported by the code (stubbed, TODO, missing). Cite files and lines.",
    "What is the single most technically interesting or novel file/function here, and why? Cite it.",
    "What are the sketchiest parts — untested, TODO-ridden, hardcoded, or security-questionable? Cite files and lines.",
]

READY_STATUSES = {"ready", "completed", "COMPLETED"}


def _use_mocks() -> bool:
    return os.environ.get("USE_MOCKS", "1") == "1"


def _headers() -> dict:
    key = os.environ.get("GREPTILE_API_KEY")
    pat = os.environ.get("GITHUB_TOKEN")
    if not key or not pat:
        raise RuntimeError("GREPTILE_API_KEY and GITHUB_TOKEN must be set for live Greptile calls (.env)")
    return {
        "Authorization": f"Bearer {key}",
        "X-GitHub-Token": pat,
        "Content-Type": "application/json",
    }


def _request(method: str, url: str, body: dict | None = None, timeout: int = 120) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=_headers())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _run_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    d = RUNS_DIR / stamp
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_indexed(repo: str, branch: str = "main", poll_s: int = 10, timeout_s: int = 900) -> str:
    """Submit repo for indexing and poll until ready. Returns final status."""
    if _use_mocks():
        return "completed (mock)"
    try:
        _request("POST", f"{API}/repositories", {"remote": "github", "repository": repo, "branch": branch})
    except urllib.error.HTTPError as e:
        # 4xx here usually means "already submitted" — polling below is the source of truth
        print(f"index submit: HTTP {e.code} ({e.read(200)!r}), continuing to poll", file=sys.stderr)
    repo_id = urllib.parse.quote(f"github:{branch}:{repo}", safe="")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        info = _request("GET", f"{API}/repositories/{repo_id}")
        status = info.get("status", "unknown")
        print(f"  greptile index status: {status}", file=sys.stderr)
        if status in READY_STATUSES:
            return status
        if status in {"failed", "FAILED"}:
            raise RuntimeError(f"Greptile indexing failed for {repo}: {info}")
        time.sleep(poll_s)
    raise TimeoutError(f"Greptile indexing of {repo} not ready after {timeout_s}s")


def query(repo: str, question: str, branch: str = "main", genius: bool = True) -> dict:
    """One /query call → {'query', 'message', 'sources'}."""
    resp = _request(
        "POST",
        f"{API}/query",
        {
            "messages": [{"role": "user", "content": question}],
            "repositories": [{"remote": "github", "repository": repo, "branch": branch}],
            "genius": genius,
        },
        timeout=180,
    )
    return {"query": question, "message": resp.get("message", ""), "sources": resp.get("sources", [])}


def run_battery(repo: str, branch: str = "main", skip_index: bool = False) -> dict:
    """Index (unless skipped) then run the 5-query battery. Persists raw output to runs/."""
    if _use_mocks():
        findings = json.loads(FIXTURE.read_text())
    else:
        if not skip_index:
            ensure_indexed(repo, branch)
        findings = {"repository": repo, "branch": branch, "battery": []}
        for i, q in enumerate(BATTERY, 1):
            print(f"  battery {i}/5 (genius=True)…", file=sys.stderr)
            findings["battery"].append(query(repo, q, branch, genius=True))
    out = _run_dir() / "greptile.json"
    out.write_text(json.dumps(findings, indent=2))
    print(f"  greptile findings → {out}", file=sys.stderr)
    return findings


def main() -> None:
    ap = argparse.ArgumentParser(description="Greptile interrogation battery")
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--skip-index", action="store_true", help="assume repo already indexed")
    args = ap.parse_args()
    findings = run_battery(args.repo, args.branch, args.skip_index)
    json.dump(findings, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
