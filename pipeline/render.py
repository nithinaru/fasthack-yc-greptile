#!/usr/bin/env python3
"""Subtask A5: pre-render code_html for script citations.

Fetches source files (mock: fixtures/src/, live: raw.githubusercontent.com)
and renders them into the frozen code_html format defined by
fixtures/generate_ep000.py's render_code_html:

    <pre class="shiki"><code>
      one <span class="line" data-line="N">{escaped line}\n</span> per line
      (cited lines get class "line cited")
    </code></pre>

Output must stay byte-identical to the fixture generator. Real syntax
highlighting (shiki via npx) is deliberately NOT attempted here — the
pre-rendered plain format above is the contract; token-level highlighting
is a polish item for later.

Stdlib only. Mock mode is the default (USE_MOCKS unset or "1").
Self-test: python3 -m pipeline.render --selftest
"""

import html
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES_SRC = ROOT / "fixtures" / "src"


def _use_mocks() -> bool:
    return os.environ.get("USE_MOCKS", "1") == "1"


def fetch_source(repo_full_name: str, branch: str, path: str) -> str:
    """Return the text of `path` in `repo_full_name`@`branch`.

    Mock mode (USE_MOCKS=1, the default): reads fixtures/src/<path>.
    Live mode: GET https://raw.githubusercontent.com/{repo}/{branch}/{path},
    with Authorization: Bearer $GITHUB_TOKEN if set.
    """
    if _use_mocks():
        local = FIXTURES_SRC / path
        try:
            return local.read_text()
        except OSError as exc:
            raise RuntimeError(
                f"mock source not found: {local} "
                f"(repo={repo_full_name}, branch={branch}, path={path})"
            ) from exc

    url = f"https://raw.githubusercontent.com/{repo_full_name}/{branch}/{path}"
    req = urllib.request.Request(url)
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"failed to fetch {url}: HTTP {exc.code} {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"failed to fetch {url}: {exc.reason}") from exc


def render_code_html(source_text: str, start_line: int, end_line: int) -> str:
    """Render a whole file into the frozen code_html format.

    Byte-identical to fixtures/generate_ep000.py:render_code_html for the
    same input. Lines in [start_line, end_line] get class "line cited".
    """
    lines = source_text.splitlines()
    out = ['<pre class="shiki"><code>']
    for n, line in enumerate(lines, 1):
        cls = "line cited" if start_line <= n <= end_line else "line"
        out.append(f'<span class="{cls}" data-line="{n}">{html.escape(line)}\n</span>')
    out.append("</code></pre>")
    return "".join(out)


def attach_citations(segments, repo_full_name, branch="main"):
    """Return segments with code_html added to every non-null citation.

    Each segment has "text" and "citation" ({file,start_line,end_line} or
    null), as in fixtures/script_response.json. Other keys pass through
    untouched. Input is not mutated; source files are fetched once each.
    """
    cache = {}
    result = []
    for seg in segments:
        seg = dict(seg)
        cite = seg.get("citation")
        if cite is not None:
            cite = dict(cite)
            path = cite["file"]
            if path not in cache:
                cache[path] = fetch_source(repo_full_name, branch, path)
            cite["code_html"] = render_code_html(
                cache[path], cite["start_line"], cite["end_line"]
            )
            seg["citation"] = cite
        result.append(seg)
    return result


def _selftest() -> int:
    os.environ["USE_MOCKS"] = "1"
    script = json.loads((ROOT / "fixtures" / "script_response.json").read_text())
    episode = json.loads((ROOT / "fixtures" / "ep-000.json").read_text())

    expected = {}
    for seg in episode["segments"]:
        c = seg["citation"]
        if c:
            expected[(c["file"], c["start_line"])] = c["code_html"]

    rendered = attach_citations(script["segments"], "cavemanlabs/caveman")
    checked = 0
    for seg in rendered:
        c = seg["citation"]
        if c is None:
            continue
        key = (c["file"], c["start_line"])
        if key not in expected:
            print(f"selftest FAIL: no fixture citation for {key}")
            return 1
        if c["code_html"] != expected[key]:
            print(f"selftest FAIL: code_html mismatch for {key}")
            return 1
        checked += 1
    if checked == 0:
        print("selftest FAIL: no citations checked")
        return 1
    print("selftest OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
