"""A6 — Publish: assemble episode JSON → Modal Volume (+ local web/ mirror) → feed.xml.

v2 (all-Modal): the Volume `repo-radio-data` (env MODAL_VOLUME) is the live
static root Modal /serve reads from — layout `/static/episodes/ep-NNN.json`,
`/static/audio/ep-NNN.mp3`, `/static/memory.json`, `/static/feed.xml`. We push
there via `modal volume put` (subprocess), one file at a time.

The local mirror at web/ (web/episodes/, web/audio/, web/memory.json,
web/feed.xml) is ALWAYS written too — it's what the checked-in static site
serves locally and is the zero-network demo fallback. In USE_MOCKS=1 mode we
do ONLY the local copy (no Modal CLI calls, no keys needed).

The old S3+CloudFront path is kept behind PUBLISH_S3=1 — designed for
S3+CloudFront; not deployed today (PRD v2 note, §1). It is dead weight for
today's demo but costs nothing to keep for the pitch/README honesty note.

API:  assemble_episode(...) -> episode dict (schema-validated)
      publish_episode(episode, mp3_path) -> {"json": url, "mp3": url, "feed": url}
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "web"
SCHEMA = ROOT / "contracts" / "episode.schema.json"

SHOW_TITLE = "Repo Radio"
SHOW_DESC = "We read the code of trending repos so you don't have to."


def _use_mocks() -> bool:
    return os.environ.get("USE_MOCKS", "1") == "1"


def _site_base() -> str:
    return os.environ.get("SITE_BASE_URL", "").rstrip("/")


def validate_episode(ep: dict) -> dict:
    """Validate against contracts/episode.schema.json (jsonschema or structural)."""
    schema = json.loads(SCHEMA.read_text())
    try:
        import jsonschema  # type: ignore

        jsonschema.validate(ep, schema)
    except ImportError:
        sys.path.insert(0, str(ROOT / "scripts"))
        import smoke  # Lane 0's structural validator — read-only reuse

        err = smoke.structural_validate(ep, schema)
        if err:
            raise ValueError(f"episode fails schema: {err}") from None
    return ep


def assemble_episode(
    ep_id: str,
    repo_pick: dict,
    script: dict,
    voice_meta: dict,
    cited_segments: list[dict],
    memory_refs: list[dict] | None = None,
) -> dict:
    """Merge pipeline stage outputs into one schema-valid episode dict.

    cited_segments: script segments after render.attach_citations (code_html present).
    voice_meta: synthesize() output — duration_s, peaks, timeline aligned by index.
    """
    timeline = voice_meta["timeline"]
    if len(timeline) != len(cited_segments):
        raise ValueError(f"timeline has {len(timeline)} entries for {len(cited_segments)} segments")
    segments = [
        {
            "i": i,
            "start": t["start"],
            "end": t["end"],
            "text": seg["text"],
            "citation": seg["citation"],
        }
        for i, (seg, t) in enumerate(zip(cited_segments, timeline))
    ]
    episode = {
        "id": ep_id,
        "date": dt.date.today().isoformat(),
        "repo": {
            "full_name": repo_pick["full_name"],
            "url": repo_pick.get("url", f"https://github.com/{repo_pick['full_name']}"),
            "language": repo_pick.get("language") or "Unknown",
            "stars_at_airtime": int(repo_pick.get("stars_at_airtime", 0)),
            "velocity_per_hr": float(repo_pick.get("velocity_per_hr", 0)),
        },
        "title": script["title"],
        "verdict": script["verdict"],
        "audio": {
            "url": f"/audio/{ep_id}.mp3",
            "duration_s": voice_meta["duration_s"],
            "peaks": voice_meta["peaks"],
        },
        "segments": segments,
        "memory_refs": memory_refs or [],
        "qa_segments": [],
    }
    return validate_episode(episode)


def _rfc822(date_str: str) -> str:
    d = dt.datetime.fromisoformat(date_str).replace(tzinfo=dt.timezone.utc)
    return format_datetime(d)


def build_feed(episodes: list[dict]) -> str:
    """Podcast RSS 2.0 — one <item> with <enclosure> per episode, newest first."""
    base = _site_base()
    items = []
    for ep in sorted(episodes, key=lambda e: e["id"], reverse=True):
        items.append(f"""    <item>
      <title>{escape(ep["title"])}</title>
      <description>{escape(f'{ep["repo"]["full_name"]} — verdict {ep["verdict"]}. {SHOW_DESC}')}</description>
      <guid isPermaLink="false">{escape(ep["id"])}</guid>
      <pubDate>{_rfc822(ep["date"])}</pubDate>
      <enclosure url="{escape(base + ep["audio"]["url"])}" length="0" type="audio/mpeg"/>
    </item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{escape(SHOW_TITLE)}</title>
    <link>{escape(base or "/")}</link>
    <description>{escape(SHOW_DESC)}</description>
    <language>en-us</language>
{chr(10).join(items)}
  </channel>
</rss>
"""


def _modal_volume() -> str:
    return os.environ.get("MODAL_VOLUME", "repo-radio-data")


def _modal_put(local: Path, remote: str) -> None:
    """`modal volume put <volume> <local> <remote>` — one file, via subprocess."""
    subprocess.run(
        ["modal", "volume", "put", _modal_volume(), str(local), remote, "-f"],
        check=True,
    )


def _publish_modal(ep_json: Path, ep_mp3: Path, memory_json: Path, feed: Path, ep_id: str) -> None:
    _modal_put(ep_json, f"/static/episodes/{ep_id}.json")
    _modal_put(ep_mp3, f"/static/audio/{ep_id}.mp3")
    if memory_json.exists():
        _modal_put(memory_json, "/static/memory.json")
    _modal_put(feed, "/static/feed.xml")
    print(f"  published to Modal Volume {_modal_volume()}:/static/", file=sys.stderr)


def _aws(*args: str) -> None:
    subprocess.run(["aws", *args], check=True)


def _publish_s3(ep_json: Path, ep_mp3: Path, feed: Path, ep_id: str) -> None:
    """Old S3+CloudFront path — designed for S3+CloudFront; not deployed today.

    Kept behind PUBLISH_S3=1 for the pitch/README honesty note (PRD v2 §1);
    Modal is the only live distribution path for the hackathon demo.
    """
    bucket = os.environ.get("S3_BUCKET")
    region = os.environ.get("AWS_REGION", "us-west-2")
    if not bucket:
        raise RuntimeError("S3_BUCKET unset — cannot publish to S3")
    _aws("s3", "cp", str(ep_json), f"s3://{bucket}/episodes/{ep_id}.json", "--region", region,
         "--content-type", "application/json")
    _aws("s3", "cp", str(ep_mp3), f"s3://{bucket}/audio/{ep_id}.mp3", "--region", region,
         "--content-type", "audio/mpeg")
    _aws("s3", "cp", str(feed), f"s3://{bucket}/feed.xml", "--region", region,
         "--content-type", "application/rss+xml")
    dist = os.environ.get("CLOUDFRONT_DISTRIBUTION_ID")
    if dist:
        _aws("cloudfront", "create-invalidation", "--distribution-id", dist,
             "--paths", f"/episodes/{ep_id}.json", f"/audio/{ep_id}.mp3", "/feed.xml")
    else:
        print("  CLOUDFRONT_DISTRIBUTION_ID unset — skipping invalidation", file=sys.stderr)
    print(f"  published (optional path) to s3://{bucket}", file=sys.stderr)


def publish_episode(episode: dict, mp3_path: Path) -> dict:
    """Write episode+MP3 to the local web/ mirror, rebuild feed.xml.

    USE_MOCKS=1: local copy only, no keys/CLI needed. Live mode also pushes
    to the Modal Volume; PUBLISH_S3=1 additionally mirrors to S3 (optional,
    not part of today's deploy).
    """
    ep_id = episode["id"]
    (SITE / "episodes").mkdir(parents=True, exist_ok=True)
    (SITE / "audio").mkdir(parents=True, exist_ok=True)

    ep_json = SITE / "episodes" / f"{ep_id}.json"
    ep_mp3 = SITE / "audio" / f"{ep_id}.mp3"
    ep_json.write_text(json.dumps(episode, indent=2) + "\n")
    if Path(mp3_path).resolve() != ep_mp3.resolve():
        ep_mp3.write_bytes(Path(mp3_path).read_bytes())

    all_eps = [json.loads(p.read_text()) for p in sorted((SITE / "episodes").glob("ep-*.json"))]
    feed = SITE / "feed.xml"
    feed.write_text(build_feed(all_eps))

    memory_json = SITE / "memory.json"

    published = {"json": f"/episodes/{ep_id}.json", "mp3": f"/audio/{ep_id}.mp3", "feed": "/feed.xml"}
    if _use_mocks():
        print(f"  [mock] published to {SITE}", file=sys.stderr)
        return published

    _publish_modal(ep_json, ep_mp3, memory_json, feed, ep_id)
    if os.environ.get("PUBLISH_S3") == "1":
        _publish_s3(ep_json, ep_mp3, feed, ep_id)
    return published
