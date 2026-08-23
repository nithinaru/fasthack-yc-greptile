#!/usr/bin/env python3
"""Repo Radio — programmatic episode cover art (M4).

Given episode JSON files (PRD §5 contract), emit square SVG covers in the
late-night FM booth design language: #0A0A0F background, subtle radial glow,
waveform bars from the episode's real audio.peaks, repo name in Hedvig
Letters Serif, EP-NNN in JetBrains Mono, verdict badge + tint.

Pure stdlib, string-built SVG. Serve SVG directly (no PNG conversion; if
cairosvg happens to be importable we opportunistically write a PNG too, but
it is never required).

Usage:
    python scripts/cover_art.py web/episodes/ep-000.json [...]   # explicit files
    python scripts/cover_art.py --all                            # local + live episodes
Output goes to web/covers/ep-NNN.svg.

feed.xml tradeoff (step done by main() with --feed): we deliberately do NOT
touch pipeline/ code. Instead we download the live /feed.xml, inject
<itunes:image href=".../covers/ep-NNN.svg"/> per item (and a channel-level
image), and re-upload it to the Modal volume. The next pipeline publish
OVERWRITES feed.xml, dropping the images — this is a post-processing pass
that day-of ops must re-run after each publish (cheap: `--all --feed`).
"""

import json
import math
import re
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
LIVE = "https://nithin-alaska--repo-radio-serve-fastapi-app.modal.run"
OUT_DIR = ROOT / "web" / "covers"

S = 1024  # square canvas

# Verdict palette per PRD §6: accent / dark bg pair.
VERDICTS = {
    "HYPE": ("#F43F5E", "#2A0E14"),
    "REAL": ("#34D399", "#0B231A"),
    "MIXED": ("#FBBF24", "#261C08"),
}

BG = "#0A0A0F"
GLOW = "#1A1025"
AMBER = "#FFB020"
TEXT_DIM = "#8888A0"


def _downsample(peaks, n):
    """Average `peaks` into n buckets (peaks is ~240 floats 0..1)."""
    if not peaks:
        return [0.3] * n
    out = []
    step = len(peaks) / n
    for i in range(n):
        lo, hi = int(i * step), max(int(i * step) + 1, int((i + 1) * step))
        chunk = peaks[lo:hi] or [0.0]
        out.append(sum(chunk) / len(chunk))
    return out


def build_svg(ep):
    epid = ep["id"]  # ep-NNN
    verdict = (ep.get("verdict") or "MIXED").upper()
    accent, tint = VERDICTS.get(verdict, VERDICTS["MIXED"])
    full_name = ep.get("repo", {}).get("full_name", "unknown/repo")
    peaks = ep.get("audio", {}).get("peaks") or []

    n_bars = 48
    bars = _downsample(peaks, n_bars)

    # Waveform band geometry: centered vertically in lower-middle area.
    wf_x, wf_w = 96, S - 192
    wf_cy, wf_maxh = 560, 220
    bar_w = wf_w / n_bars * 0.62
    gap = wf_w / n_bars

    bar_elems = []
    for i, p in enumerate(bars):
        h = max(10, p * wf_maxh)
        x = wf_x + i * gap + (gap - bar_w) / 2
        bar_elems.append(
            f'<rect x="{x:.1f}" y="{wf_cy - h / 2:.1f}" width="{bar_w:.1f}" '
            f'height="{h:.1f}" rx="{bar_w / 2:.1f}" fill="{AMBER}"/>'
        )

    # Repo name sizing: shrink for long names (single line, mid-anchor).
    name = escape(full_name)
    fs = 64 if len(full_name) <= 22 else (48 if len(full_name) <= 32 else 38)

    ep_label = escape(epid.upper())  # EP-NNN
    v_label = escape(verdict)
    badge_w = 60 + len(verdict) * 30

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{S}" height="{S}" viewBox="0 0 {S} {S}">
  <defs>
    <radialGradient id="glow" cx="50%" cy="42%" r="75%">
      <stop offset="0%" stop-color="{GLOW}"/>
      <stop offset="60%" stop-color="{GLOW}" stop-opacity="0.55"/>
      <stop offset="100%" stop-color="{BG}"/>
    </radialGradient>
    <radialGradient id="tint" cx="50%" cy="88%" r="80%">
      <stop offset="0%" stop-color="{tint}" stop-opacity="0.9"/>
      <stop offset="55%" stop-color="{tint}" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="{tint}" stop-opacity="0"/>
    </radialGradient>
  </defs>

  <rect width="{S}" height="{S}" fill="{BG}"/>
  <rect width="{S}" height="{S}" fill="url(#glow)"/>
  <rect width="{S}" height="{S}" fill="url(#tint)"/>

  <!-- booth frame -->
  <rect x="26" y="26" width="{S - 52}" height="{S - 52}" fill="none"
        stroke="{accent}" stroke-opacity="0.28" stroke-width="2" rx="18"/>

  <!-- wordmark + ON AIR lamp -->
  <text x="96" y="132" font-family="JetBrains Mono, monospace" font-size="30"
        letter-spacing="8" fill="{TEXT_DIM}">REPO RADIO · 102.3 FM</text>
  <circle cx="{S - 128}" cy="122" r="10" fill="{accent}"/>
  <circle cx="{S - 128}" cy="122" r="18" fill="{accent}" fill-opacity="0.25"/>

  <!-- episode label -->
  <text x="96" y="236" font-family="JetBrains Mono, monospace" font-size="44"
        letter-spacing="10" fill="{AMBER}">{ep_label}</text>

  <!-- repo name (display serif) -->
  <text x="96" y="340" font-family="Hedvig Letters Serif, serif" font-size="{fs}"
        fill="#EDEDF2">{name}</text>

  <!-- waveform from real audio.peaks -->
  <g opacity="0.95">{''.join(bar_elems)}</g>
  <line x1="{wf_x}" y1="{wf_cy}" x2="{wf_x + wf_w}" y2="{wf_cy}"
        stroke="{AMBER}" stroke-opacity="0.18" stroke-width="2"/>

  <!-- verdict badge -->
  <g transform="translate(96, 800)">
    <rect x="0" y="0" width="{badge_w}" height="76" rx="38"
          fill="{tint}" stroke="{accent}" stroke-width="2.5"/>
    <text x="{badge_w / 2:.0f}" y="51" text-anchor="middle"
          font-family="JetBrains Mono, monospace" font-size="34"
          letter-spacing="6" fill="{accent}">{v_label}</text>
  </g>

  <!-- footer freq ticks -->
  <g stroke="{TEXT_DIM}" stroke-opacity="0.35" stroke-width="2">
    {''.join(f'<line x1="{96 + i * 42}" y1="{S - 84}" x2="{96 + i * 42}" y2="{S - 84 - (14 if i % 5 else 26)}"/>' for i in range(20))}
  </g>
</svg>
'''


def write_cover(ep, out_dir=OUT_DIR):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ep['id']}.svg"
    path.write_text(build_svg(ep))
    # Optional PNG if cairosvg is already around — never a hard dep.
    try:
        import cairosvg  # noqa

        cairosvg.svg2png(url=str(path), write_to=str(path.with_suffix(".png")))
    except Exception:
        pass
    return path


def _fetch_json(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.load(r)
    except Exception:
        return None


def gather_all():
    """Local web/episodes/*.json plus any live episodes not present locally."""
    eps = {}
    for p in sorted((ROOT / "web" / "episodes").glob("ep-*.json")):
        try:
            ep = json.loads(p.read_text())
            eps[ep["id"]] = ep
        except Exception:
            print(f"skip unparseable {p}", file=sys.stderr)
    # Probe live sequentially until two consecutive 404s.
    misses, i = 0, 0
    while misses < 2 and i < 100:
        epid = f"ep-{i:03d}"
        if epid not in eps:
            live = _fetch_json(f"{LIVE}/episodes/{epid}.json")
            if live:
                eps[epid] = live
                misses = 0
            else:
                misses += 1
        i += 1
    return [eps[k] for k in sorted(eps)]


def patch_feed(ep_ids):
    """Download live feed.xml, inject itunes:image per item + channel image.

    NOTE: pipeline publish overwrites feed.xml on the volume — re-run this
    after every publish. Writes web/covers/feed.xml (upload separately with
    `modal volume put`). Does not edit pipeline/ code by design.
    """
    try:
        with urllib.request.urlopen(f"{LIVE}/feed.xml", timeout=15) as r:
            xml = r.read().decode("utf-8")
    except Exception as e:
        print(f"feed.xml fetch failed: {e}", file=sys.stderr)
        return None

    # Ensure itunes namespace on <rss>.
    if "xmlns:itunes" not in xml:
        xml = xml.replace(
            "<rss",
            '<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"',
            1,
        )
    # Strip any images we injected on a previous run (idempotent re-runs).
    xml = re.sub(r'\s*<itunes:image href="[^"]*"\s*/>', "", xml)

    # Channel-level image: newest episode's cover.
    if ep_ids:
        chan_img = f'<itunes:image href="{LIVE}/covers/{sorted(ep_ids)[-1]}.svg"/>'
        xml = xml.replace("<item>", f"{chan_img}\n<item>", 1)

    # Per-item: match the ep id in each <item> block via guid/link/enclosure.
    def add_item_img(m):
        block = m.group(0)
        found = re.search(r"ep-\d{3}", block)
        if found and found.group(0) in ep_ids:
            img = f'<itunes:image href="{LIVE}/covers/{found.group(0)}.svg"/>'
            return block.replace("</item>", f"{img}\n</item>")
        return block

    xml = re.sub(r"<item>.*?</item>", add_item_img, xml, flags=re.S)
    out = OUT_DIR / "feed.xml"
    out.write_text(xml)
    return out


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if "--all" in argv or not args:
        eps = gather_all()
    else:
        eps = [json.loads(Path(a).read_text()) for a in args]
    written = [write_cover(ep) for ep in eps]
    for p in written:
        print(p.relative_to(ROOT))
    if "--feed" in argv:
        f = patch_feed({ep["id"] for ep in eps})
        if f:
            print(f.relative_to(ROOT))


if __name__ == "__main__":
    main(sys.argv[1:])
