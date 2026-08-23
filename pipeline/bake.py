"""A8 — Bake: the full pipeline, repo in → published episode out.

    make bake-episode REPO=owner/name        (Makefile target → this module)
    python -m pipeline.bake --repo owner/name [--ep-id ep-001] [--branch main]

Stages (each mockable via USE_MOCKS=1):
  A1 trending pick → A7 memory digest (search-before) → A2 greptile battery
  → A3 script → A5 citations/code_html → A4 voice+timeline+peaks
  → A6 assemble+publish → A7 memory write-after.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_EPISODES = ROOT / "runs" / "site" / "episodes"


def next_ep_id() -> str:
    nums = [int(m.group(1)) for p in SITE_EPISODES.glob("ep-*.json")
            if (m := re.match(r"ep-(\d{3})\.json$", p.name))]
    return f"ep-{(max(nums) + 1 if nums else 0):03d}"


def bake(repo: str | None, ep_id: str | None = None, branch: str = "main") -> dict:
    from pipeline import greptile, memory, publish, render, script, trending, voice

    ep_id = ep_id or next_ep_id()
    print(f"=== baking {ep_id} (USE_MOCKS={os.environ.get('USE_MOCKS', '1')}) ===", file=sys.stderr)

    print("[1/7] trending pick", file=sys.stderr)
    pick = trending.pick(repo)
    full_name = pick["full_name"]
    print(f"      → {full_name} ({pick.get('velocity_per_hr', 0)}★/hr)", file=sys.stderr)

    print("[2/7] memory: search-before", file=sys.stderr)
    digest, memory_refs = memory.memory_digest(full_name, tags=["agent-framework", "sdk-wrapper", "dev-tool"])
    if digest:
        print(f"      digest:\n{digest}", file=sys.stderr)

    print("[3/7] greptile battery", file=sys.stderr)
    findings = greptile.run_battery(full_name, branch)

    print("[4/7] script", file=sys.stderr)
    ep_script = script.write_script(
        {"full_name": full_name, "stars_at_airtime": pick.get("stars_at_airtime"),
         "velocity_per_hr": pick.get("velocity_per_hr")},
        findings.get("battery", []),
        memory_digest=digest,
    )
    print(f"      → \"{ep_script['title']}\" verdict {ep_script['verdict']}, "
          f"{len(ep_script['segments'])} segments", file=sys.stderr)

    print("[5/7] citations → code_html", file=sys.stderr)
    cited = render.attach_citations(ep_script["segments"], full_name, branch)

    print("[6/7] voice + timeline + peaks", file=sys.stderr)
    mp3_path = ROOT / "runs" / "site" / "audio" / f"{ep_id}.mp3"
    voice_meta = voice.synthesize([s["text"] for s in cited], mp3_path)
    print(f"      → {voice_meta['duration_s']}s audio", file=sys.stderr)

    print("[7/7] assemble + publish + memory write-after", file=sys.stderr)
    episode = publish.assemble_episode(ep_id, pick, ep_script, voice_meta, cited, memory_refs)
    urls = publish.publish_episode(episode, mp3_path)
    memory.write_observations(episode, findings.get("battery", []))

    print(f"=== {ep_id} published: {urls} ===", file=sys.stderr)
    return episode


def main() -> None:
    ap = argparse.ArgumentParser(description="bake one episode end-to-end")
    ap.add_argument("--repo", default=None, help="owner/name (default: trending winner)")
    ap.add_argument("--ep-id", default=None, help="episode id, e.g. ep-001 (default: next)")
    ap.add_argument("--branch", default="main")
    args = ap.parse_args()
    repo = args.repo or None  # Makefile passes REPO="" when unset
    episode = bake(repo if repo else None, args.ep_id, args.branch)
    json.dump({"id": episode["id"], "title": episode["title"], "verdict": episode["verdict"],
               "segments": len(episode["segments"]), "duration_s": episode["audio"]["duration_s"],
               "memory_refs": episode["memory_refs"]}, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
