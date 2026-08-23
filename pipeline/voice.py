"""A4 — Voice: Modal /tts per segment → timeline → assembled MP3 → waveform peaks.

PRD §5.4: synthesize per segment, record each duration; cumulative sums (plus
0.35s silence gaps BETWEEN segments — the gaps count in the timeline) are the
start/end timestamps that drive karaoke sync. Concatenate to one MP3 with ffmpeg.

USE_MOCKS=1 (default): no TTS call — durations are estimated at the fixture
generator's speaking rate (2.6 words/sec, so timings match fixtures/ep-000.json),
the "assembled" MP3 is a copy of fixtures/audio/ep-000.mp3, and peaks come from
fixtures/ep-000.json.
Live mode needs MODAL_TTS_URL in the environment and ffmpeg on PATH.

API:  synthesize(texts, out_mp3) -> {"duration_s", "peaks", "timeline": [{"start","end"}...]}
CLI:  python -m pipeline.voice --out /tmp/ep.mp3   (uses fixture script text)
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_EP = ROOT / "fixtures" / "ep-000.json"
FIXTURE_MP3 = ROOT / "fixtures" / "audio" / "ep-000.mp3"

GAP_S = 0.35          # silence between segments — counted in the timeline
MOCK_WPS = 2.6        # matches fixtures/generate_ep000.py
N_PEAKS = 240         # waveform buckets, matches fixture
PCM_RATE = 8000       # decode rate for peak computation


def _use_mocks() -> bool:
    return os.environ.get("USE_MOCKS", "1") == "1"


def _timeline(durations: list[float]) -> tuple[list[dict], float]:
    """Cumulative start/end per segment with GAP_S between segments."""
    timeline, t = [], 0.0
    for dur in durations:
        timeline.append({"start": round(t, 2), "end": round(t + dur, 2)})
        t += dur + GAP_S
    total = round(t - GAP_S, 2) if durations else 0.0
    return timeline, total


def _tts_call(texts: list[str]) -> list[dict]:
    """POST /tts {segments:[...]} → [{audio_b64, duration_s}, ...] per segment."""
    url = os.environ.get("MODAL_TTS_URL")
    if not url:
        raise RuntimeError("MODAL_TTS_URL unset — Lane B's ENDPOINTS.md not wired into .env yet")
    req = urllib.request.Request(
        url, data=json.dumps({"segments": texts}).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        out = json.load(resp)
    segs = out["segments"] if isinstance(out, dict) else out
    if len(segs) != len(texts):
        raise RuntimeError(f"/tts returned {len(segs)} segments for {len(texts)} texts")
    return segs


def _assemble_mp3(seg_files: list[Path], out_mp3: Path) -> None:
    """Concatenate segment audio with GAP_S silence between, via ffmpeg."""
    with tempfile.TemporaryDirectory() as td:
        silence = Path(td) / "gap.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", f"anullsrc=r=24000:cl=mono", "-t", str(GAP_S), str(silence)],
            check=True,
        )
        concat = Path(td) / "concat.txt"
        lines = []
        for i, f in enumerate(seg_files):
            if i:
                lines.append(f"file '{silence}'")
            lines.append(f"file '{f}'")
        concat.write_text("\n".join(lines) + "\n")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", str(concat), "-ar", "24000", "-b:a", "96k", str(out_mp3)],
            check=True,
        )


def compute_peaks(mp3_path: Path, n: int = N_PEAKS) -> list[float]:
    """Decode to mono PCM and take per-bucket abs-max, normalized to 0..1."""
    pcm = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(mp3_path),
         "-f", "s16le", "-ac", "1", "-ar", str(PCM_RATE), "-"],
        check=True, capture_output=True,
    ).stdout
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm[: (len(pcm) // 2) * 2])
    if not samples:
        return [0.0] * n
    bucket = max(1, math.ceil(len(samples) / n))
    peaks = [max(abs(s) for s in samples[k * bucket:(k + 1) * bucket] or [0])
             for k in range(n)]
    top = max(peaks) or 1
    return [round(p / top, 3) for p in peaks]


def synthesize(texts: list[str], out_mp3: Path) -> dict:
    """All segment texts → assembled MP3 at out_mp3 + timeline/peaks metadata."""
    out_mp3 = Path(out_mp3)
    out_mp3.parent.mkdir(parents=True, exist_ok=True)

    if _use_mocks():
        durations = [round(len(t.split()) / MOCK_WPS, 1) for t in texts]
        timeline, total = _timeline(durations)
        shutil.copyfile(FIXTURE_MP3, out_mp3)
        peaks = json.loads(FIXTURE_EP.read_text())["audio"]["peaks"]
        return {"duration_s": total, "peaks": peaks, "timeline": timeline}

    segs = _tts_call(texts)
    durations = [float(s["duration_s"]) for s in segs]
    timeline, total = _timeline(durations)
    with tempfile.TemporaryDirectory() as td:
        seg_files = []
        for i, s in enumerate(segs):
            ext = s.get("format", "wav")
            f = Path(td) / f"seg-{i:02d}.{ext}"
            f.write_bytes(base64.b64decode(s["audio_b64"]))
            seg_files.append(f)
        _assemble_mp3(seg_files, out_mp3)
    return {"duration_s": total, "peaks": compute_peaks(out_mp3), "timeline": timeline}


def main() -> None:
    ap = argparse.ArgumentParser(description="voice the episode script")
    ap.add_argument("--out", required=True, help="output MP3 path")
    args = ap.parse_args()
    texts = [s["text"] for s in json.loads((ROOT / "fixtures" / "script_response.json").read_text())["segments"]]
    meta = synthesize(texts, Path(args.out))
    meta["peaks"] = f"[{len(meta['peaks'])} peaks]"
    json.dump(meta, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
