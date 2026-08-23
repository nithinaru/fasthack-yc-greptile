"""A7 — Host memory: write-after-episode, search-before-script (PRD §3.5).

Two layers, both degrade gracefully:
  1. memory.json (authoritative, always on): web/memory.json — one
     observation per episode finding. publish.py pushes it to the Modal
     Volume alongside episode JSON/MP3 in live mode, and the checked-in
     web/ mirror is always kept current for local serving. This is the
     PRD-sanctioned fallback and the source of `memory_refs`.
  2. claude-mem worker (best-effort): local worker (CLAUDE_MEM_URL, default
     http://localhost:37777) — GET/POST /api/search for top-k notes. The
     worker has no HTTP write endpoint (it indexes transcripts passively),
     so reads come from the worker when it's up; writes always go through
     memory.json. Short timeout (~2s) — a dead worker must never stall or
     kill the pipeline.

API:  write_observations(episode, findings) -> observation
      memory_digest(repo_full_name, tags) -> (digest_text, memory_refs)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEMORY_JSON = ROOT / "web" / "memory.json"
WORKER_URL = os.environ.get("CLAUDE_MEM_URL", "http://localhost:37777")
WORKER_TIMEOUT_S = 2


def _use_mocks() -> bool:
    return os.environ.get("USE_MOCKS", "1") == "1"


def _load() -> dict:
    """Read web/memory.json, tolerating a pre-existing file in a different
    shape (memory.json is uncontracted per web/js/app.js — a UI-lane fixture
    may have seeded it before the pipeline ever wrote to it). Anything
    without our "observations" list is treated as empty; the next
    write_observations() call replaces it with our schema.
    """
    if MEMORY_JSON.exists():
        try:
            data = json.loads(MEMORY_JSON.read_text())
        except json.JSONDecodeError:
            return {"observations": []}
        if isinstance(data, dict) and isinstance(data.get("observations"), list):
            return data
    return {"observations": []}


def _save(mem: dict) -> None:
    MEMORY_JSON.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_JSON.write_text(json.dumps(mem, indent=2) + "\n")
    # publish.py is the sanctioned upload path (Modal Volume + optional S3);
    # this module only ever owns the local web/memory.json write.


def worker_search(query: str, limit: int = 5) -> list[dict]:
    """Best-effort search against the local claude-mem worker's /api/search.

    Tries GET first (query string), falls back to POST with a JSON body —
    either is fine per PRD §3.5, whichever the worker actually implements.
    Any failure (down, timeout, unexpected shape) degrades to memory.json
    alone; this must never raise.
    """
    try:
        url = f"{WORKER_URL}/api/search?q={urllib.parse.quote(query)}"
        with urllib.request.urlopen(url, timeout=WORKER_TIMEOUT_S) as resp:
            hits = json.load(resp)
    except Exception as e_get:  # noqa: BLE001 — memory must never kill the pipeline
        try:
            body = json.dumps({"query": query, "q": query, "limit": limit}).encode()
            req = urllib.request.Request(
                f"{WORKER_URL}/api/search", data=body, method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=WORKER_TIMEOUT_S) as resp:
                hits = json.load(resp)
        except Exception as e_post:  # noqa: BLE001
            print(f"  memory worker unavailable ({e_get}; {e_post}) — memory.json only", file=sys.stderr)
            return []
    if isinstance(hits, dict):
        hits = hits.get("results") or hits.get("hits") or hits.get("notes") or []
    return hits[:limit] if isinstance(hits, list) else []


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
