#!/usr/bin/env python3
"""Regenerate fixtures/ep-000.json (+ sibling fixtures) from fixtures/src/.

Deterministic, stdlib-only. Run from repo root: python3 fixtures/generate_ep000.py
code_html: <pre class="shiki"> with one <span class="line" data-line="N"> per
line; cited lines additionally get class "cited".
"""

import html
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src"

WPS = 2.6  # host speaking rate, words/sec
GAP = 0.35  # silence between segments, sec

SCRIPT = [
    (None, "It's 11:47 PM in San Francisco, and GitHub's hottest new repo just crossed four thousand stars. This is Repo Radio — I read the code so you don't have to."),
    (None, "Tonight's subject: Caveman. The README promises a full autonomous agent runtime — memory, tools, scheduling, the works. Four thousand stars in three days. Let's see what's actually in the cave."),
    (("core/agent.py", 12, 38), "Crack open core/agent.py and the skeleton is clean: an Agent class, a tool registry, a run loop. Credit where due — this is readable code."),
    (("llm/client.py", 8, 24), "But here in llm/client.py? The 'proprietary reasoning engine' is forty lines wrapping someone else's chat API. That's not a reasoning engine, folks. That's a phone call."),
    (("core/scheduler.py", 51, 88), "Now, the plot twist. The scheduler is legitimately clever — priority queues with decay, so stale tasks lose their place in line. I haven't seen that pattern in the other frameworks. This is the part worth stealing."),
    (("memory/store.py", 3, 9), "And the 'long-term memory' the README brags about? Six lines. A dictionary. And a TODO that says, quote, 'make this persistent.' The cave paintings were more durable."),
    (None, "So: verdict MIXED. Real craftsmanship in the scheduler, marketing everywhere else. Star it for the scheduler. Don't bet your startup on the memory."),
    (None, "That's the broadcast. Wallet's open if you've got questions — ten cents, answered on air. Repo Radio: we read the code so you don't have to. Stay curious."),
]


def render_code_html(rel_path: str, start: int, end: int) -> str:
    lines = (SRC / rel_path).read_text().splitlines()
    out = ['<pre class="shiki"><code>']
    for n, line in enumerate(lines, 1):
        cls = "line cited" if start <= n <= end else "line"
        out.append(f'<span class="{cls}" data-line="{n}">{html.escape(line)}\n</span>')
    out.append("</code></pre>")
    return "".join(out)


def build():
    segments = []
    t = 0.0
    for i, (cite, text) in enumerate(SCRIPT):
        dur = round(len(text.split()) / WPS, 1)
        citation = None
        if cite:
            f, s, e = cite
            citation = {"file": f, "start_line": s, "end_line": e,
                        "code_html": render_code_html(f, s, e)}
        segments.append({"i": i, "start": round(t, 2), "end": round(t + dur, 2),
                         "text": text, "citation": citation})
        t += dur + GAP
    total = round(t - GAP, 2)

    # deterministic fake waveform: speech-shaped envelope, 240 buckets
    peaks = [round(abs(math.sin(k * 0.7)) * (0.35 + 0.6 * abs(math.sin(k * 0.13))), 3)
             for k in range(240)]

    episode = {
        "id": "ep-000",
        "date": "2026-08-22",
        "repo": {"full_name": "cavemanlabs/caveman",
                 "url": "https://github.com/cavemanlabs/caveman",
                 "language": "Python", "stars_at_airtime": 4102, "velocity_per_hr": 57},
        "title": "Caveman: 4,000 stars and a six-line memory",
        "verdict": "MIXED",
        "audio": {"url": "/audio/ep-000.mp3", "duration_s": total, "peaks": peaks},
        "segments": segments,
        "memory_refs": [],
        "qa_segments": [],
    }
    (ROOT / "ep-000.json").write_text(json.dumps(episode, indent=2) + "\n")
    print(f"ep-000.json written: {len(segments)} segments, {total}s")
    return total


if __name__ == "__main__":
    build()
