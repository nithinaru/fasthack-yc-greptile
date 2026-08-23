"""A1 — Trending picker (PRD §5.1).

Picks today's repo by star velocity. Two sources:
  1. pipeline/watchlist.json — the real source on race day (curated, with
     timestamped star samples so velocity works offline / USE_MOCKS=1).
  2. GitHub Search API — the "algorithm" story; refreshes live star counts
     for watchlist repos and can suggest extra candidates.

CLI:  python -m pipeline.trending [--repo owner/name] [--top N]
      --repo forces the pick (demo override), still prints its velocity.
Exit: prints the chosen repo JSON on stdout; full ranking on stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WATCHLIST_PATH = Path(__file__).parent / "watchlist.json"
GITHUB_API = "https://api.github.com"


def _use_mocks() -> bool:
    return os.environ.get("USE_MOCKS", "1") == "1"


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _gh_get(path: str) -> dict:
    req = urllib.request.Request(GITHUB_API + path)
    req.add_header("Accept", "application/vnd.github+json")
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def load_watchlist(path: Path = WATCHLIST_PATH) -> list[dict]:
    data = json.loads(path.read_text())
    return data["repos"]


def refresh_stars(repos: list[dict]) -> list[dict]:
    """Append a fresh star sample per repo from the GitHub API (live mode only)."""
    now = datetime.now(timezone.utc).isoformat()
    for repo in repos:
        try:
            meta = _gh_get(f"/repos/{repo['full_name']}")
        except Exception as e:  # noqa: BLE001 — a dead candidate must not kill the pick
            print(f"warn: could not refresh {repo['full_name']}: {e}", file=sys.stderr)
            continue
        repo["samples"].append({"ts": now, "stars": meta["stargazers_count"]})
        repo["language"] = meta.get("language")
        repo["url"] = meta.get("html_url")
    return repos


def velocity(repo: dict) -> float:
    """Δstars/Δhours between the two most recent samples; 0 if not computable."""
    samples = sorted(repo.get("samples", []), key=lambda s: s["ts"])
    if len(samples) < 2:
        return 0.0
    a, b = samples[-2], samples[-1]
    hours = (_parse_ts(b["ts"]) - _parse_ts(a["ts"])).total_seconds() / 3600
    if hours <= 0:
        return 0.0
    return (b["stars"] - a["stars"]) / hours


def rank(repos: list[dict]) -> list[dict]:
    for repo in repos:
        repo["velocity_per_hr"] = round(velocity(repo), 1)
        repo["stars_at_airtime"] = (
            sorted(repo.get("samples", []), key=lambda s: s["ts"])[-1]["stars"]
            if repo.get("samples")
            else 0
        )
    return sorted(repos, key=lambda r: r["velocity_per_hr"], reverse=True)


def pick(forced_repo: str | None = None) -> dict:
    repos = load_watchlist()
    if not _use_mocks():
        repos = refresh_stars(repos)
    ranking = rank(repos)
    if forced_repo:
        for repo in ranking:
            if repo["full_name"] == forced_repo:
                return repo
        # forced repo not on the watchlist — build a minimal entry
        entry = {"full_name": forced_repo, "samples": [], "velocity_per_hr": 0.0, "stars_at_airtime": 0}
        if not _use_mocks():
            entry = refresh_stars([entry])[0]
            entry.update(velocity_per_hr=0.0, stars_at_airtime=entry["samples"][-1]["stars"])
        return entry
    return ranking[0]


def main() -> None:
    ap = argparse.ArgumentParser(description="pick today's repo by star velocity")
    ap.add_argument("--repo", help="force this owner/name instead of the ranking winner")
    ap.add_argument("--top", type=int, default=5, help="how many ranked rows to print to stderr")
    args = ap.parse_args()

    ranking = rank(load_watchlist() if _use_mocks() else refresh_stars(load_watchlist()))
    for repo in ranking[: args.top]:
        print(f"{repo['velocity_per_hr']:>8.1f}/hr  {repo['stars_at_airtime']:>7}★  {repo['full_name']}", file=sys.stderr)

    chosen = pick(args.repo)
    print(json.dumps(chosen, indent=2))


if __name__ == "__main__":
    main()
