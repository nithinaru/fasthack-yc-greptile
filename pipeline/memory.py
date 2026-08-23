"""A7 — Host memory: write-after-episode, search-before-script (PRD §5.7).

Two layers, both degrade gracefully:
  1. memory.json (authoritative, always on): runs/site/memory.json — one
     observation per episode finding. Uploaded to S3 in live mode so the UI
     panel and the App Runner ask-flow can read it. This is the PRD-sanctioned
     fallback and the source of `memory_refs`.
  2. claude-mem worker (best-effort): local worker (CLAUDE_MEM_URL, default
     http://localhost:37777) exposes GET /api/search?q= over indexed sessions.
     Probed at 20:57 on race-day-eve: search works, there is no HTTP write
     endpoint — the worker indexes transcripts on its own. So reads come from
     the worker when it's up; writes go through memory.json.

API:  write_observations(episode, findings) -> observation
      memory_digest(repo_full_name, tags) -> (digest_text, memory_refs)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEMORY_JSON = ROOT / "runs" / "site" / "memory.json"
WORKER_URL = os.environ.get("CLAUDE_MEM_URL", "http://localhost:37777")


def _use_mocks() -> bool:
    return os.environ.get("USE_MOCKS", "1") == "1"


def _load() -> dict:
    if MEMORY_JSON.exists():
        return json.loads(MEMORY_JSON.read_text())
    return {"observations": []}


def _save(mem: dict) -> None:
    MEMORY_JSON.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_JSON.write_text(json.dumps(mem, indent=2) + "\n")
    if not _use_mocks():
        bucket = os.environ.get("S3_BUCKET")
        if bucket:
            subprocess.run(
                ["aws", "s3", "cp", str(MEMORY_JSON), f"s3://{bucket}/memory.json",
                 "--region", os.environ.get("AWS_REGION", "us-west-2"),
                 "--content-type", "application/json"],
                check=True,
            )


def worker_search(query: str, limit: int = 5) -> list[dict]:
    """Best-effort search against the local claude-mem/cavemem worker."""
    try:
        url = f"{WORKER_URL}/api/search?q={urllib.parse.quote(query)}"
        with urllib.request.urlopen(url, timeout=3) as resp:
            hits = json.load(resp)
        return hits[:limit] if isinstance(hits, list) else []
    except Exception as e:  # noqa: BLE001 — memory must never kill the pipeline
        print(f"  memory worker unavailable ({e}) — memory.json only", file=sys.stderr)
        return []


def write_observations(episode: dict, findings: list[dict] | None = None) -> dict:
    """Append one observation for a finished episode to memory.json."""
    cited = sorted({s["citation"]["file"] for s in episode["segments"] if s["citation"]})
    claims = [b["message"][:200] for b in (findings or [])]
    obs = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "episode_id": episode["id"],
        "repo": episode["repo"]["full_name"],
        "author": episode["repo"]["full_name"].split("/")[0],
        "title": episode["title"],
        "verdict": episode["verdict"],
        "stars_at_airtime": episode["repo"]["stars_at_airtime"],
        "cited_files": cited,
        "claims_checked": claims,
        "tags": _tags_for(episode),
    }
    mem = _load()
    mem["observations"] = [o for o in mem["observations"] if o["episode_id"] != episode["id"]]
    mem["observations"].append(obs)
    _save(mem)
    print(f"  memory: wrote observation for {episode['id']} ({episode['repo']['full_name']})", file=sys.stderr)
    return obs


def _tags_for(episode: dict) -> list[str]:
    text = " ".join(s["text"].lower() for s in episode["segments"])
    tags = []
    for tag, needles in {
        "agent-framework": ("agent", "runtime", "tool registry"),
        "sdk-wrapper": ("wrapper", "wrapping", "api call", "phone call"),
        "memory": ("memory", "persistent"),
        "scheduler": ("scheduler", "priority queue"),
        "dev-tool": ("cli", "developer tool"),
    }.items():
        if any(n in text for n in needles):
            tags.append(tag)
    return tags


def memory_digest(repo_full_name: str, tags: list[str] | None = None) -> tuple[str, list[dict]]:
    """Prior-coverage digest for the script prompt + memory_refs for the episode JSON.

    Matches memory.json observations on repo, author, or shared tags; enriches
    with worker search snippets when the worker is up.
    """
    author = repo_full_name.split("/")[0]
    tags = tags or []
    bullets, refs = [], []

    for o in _load()["observations"]:
        if o["repo"] == repo_full_name:
            match = "same repo"
        elif o["author"] == author:
            match = "same author"
        elif set(o["tags"]) & set(tags):
            match = f"related category ({', '.join(set(o['tags']) & set(tags))})"
        else:
            continue
        note = f"{o['repo']} — verdict {o['verdict']} at {o['stars_at_airtime']}★"
        bullets.append(f"- [{o['episode_id']}, {match}] {note}; cited {', '.join(o['cited_files'][:3])}")
        refs.append({"episode_id": o["episode_id"], "note": note})

    for hit in worker_search(repo_full_name, limit=2):
        snippet = (hit.get("snippet") or "").replace("\n", " ")[:160]
        if snippet:
            bullets.append(f"- [worker recall] …{snippet}…")

    return ("\n".join(bullets), refs)


if __name__ == "__main__":
    # self-check: write an observation from the fixture episode, then digest it back
    ep = json.loads((ROOT / "fixtures" / "ep-000.json").read_text())
    write_observations(ep)
    digest, refs = memory_digest("cavemanlabs/other-repo", tags=["agent-framework"])
    print("digest:\n" + digest)
    print("refs:", json.dumps(refs))
    assert refs and refs[0]["episode_id"] == "ep-000"
    print("memory self-check OK")
