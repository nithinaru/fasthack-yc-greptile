"""Minimal code_html renderer for live QA citations (D4).

Mirrors the fixture format exactly (fixtures/ep-000.json):
  <pre class="shiki"><code><span class="line" data-line="N">escaped\n</span>…
with cited lines as <span class="line cited" data-line="N">.

Lane A's render.py owns episode rendering; this lives in server/ because the
ask-flow must render citations at answer time and only pipeline/greptile.py
is a sanctioned cross-lane import.
"""
import html
import logging
import urllib.request

log = logging.getLogger("server.qa_render")


def fetch_github_raw(repo_full_name: str, path: str, ref: str = "main", timeout: int = 10) -> str:
    url = f"https://raw.githubusercontent.com/{repo_full_name}/{ref}/{path}"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def render_code_html(source: str, cited_start: int, cited_end: int,
                     context: int = 8) -> str:
    """Render the cited range plus `context` lines around it, fixture-style."""
    lines = source.splitlines()
    lo = max(1, cited_start - context)
    hi = min(len(lines), cited_end + context)
    spans = []
    for n in range(lo, hi + 1):
        cls = "line cited" if cited_start <= n <= cited_end else "line"
        text = html.escape(lines[n - 1], quote=False).replace('"', "&quot;")
        spans.append(f'<span class="{cls}" data-line="{n}">{text}\n</span>')
    return '<pre class="shiki"><code>' + "".join(spans) + "</code></pre>"


def render_citation(repo_full_name: str, citation: dict, ref: str = "main") -> dict:
    """Take a Modal-script citation {file,start_line,end_line} and return the
    episode-schema citation with code_html. Falls back to a stub on fetch error
    rather than failing the whole answer."""
    out = {
        "file": citation["file"],
        "start_line": int(citation["start_line"]),
        "end_line": int(citation["end_line"]),
    }
    try:
        src = fetch_github_raw(repo_full_name, citation["file"], ref)
        out["code_html"] = render_code_html(src, out["start_line"], out["end_line"])
    except Exception as e:
        log.warning("could not fetch %s from %s: %s", citation["file"], repo_full_name, e)
        stub = f"// {citation['file']} (source unavailable)"
        out["code_html"] = (
            '<pre class="shiki"><code>'
            f'<span class="line cited" data-line="{out["start_line"]}">{html.escape(stub)}\n</span>'
            "</code></pre>"
        )
    return out
