#!/usr/bin/env python3
"""Repo Radio smoke test — run via `make smoke` before EVERY push.

Checks (lane artifacts that don't exist yet are SKIPPED, not failed, so
early lanes can push before later lanes have started):
  1. All fixtures parse; ep-000.json validates against contracts/episode.schema.json
     (jsonschema if installed, otherwise a built-in structural check).
  2. `import pipeline` works (if pipeline/ exists).
  3. Server modules import (if server/ exists).
  4. web/index.html serves 200 from a local static server (if it exists).
Exit code 0 = safe to push.
"""

import http.client
import http.server
import importlib
import json
import pathlib
import socket
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAIL = []
def ok(msg): print(f"  ok    {msg}")
def skip(msg): print(f"  skip  {msg}")
def fail(msg): print(f"  FAIL  {msg}"); FAIL.append(msg)


def structural_validate(ep, schema):
    for key in schema["required"]:
        if key not in ep:
            return f"missing top-level key: {key}"
    if ep["verdict"] not in ("HYPE", "REAL", "MIXED"):
        return f"bad verdict: {ep['verdict']}"
    for k in ("url", "duration_s", "peaks"):
        if k not in ep["audio"]:
            return f"audio missing: {k}"
    for s in ep["segments"]:
        for k in ("i", "start", "end", "text", "citation"):
            if k not in s:
                return f"segment {s.get('i')} missing: {k}"
        c = s["citation"]
        if c is not None:
            for k in ("file", "start_line", "end_line", "code_html"):
                if k not in c:
                    return f"citation in segment {s['i']} missing: {k}"
    return None


def check_fixtures():
    schema = json.loads((ROOT / "contracts/episode.schema.json").read_text())
    for p in sorted(ROOT.glob("fixtures/*.json")):
        try:
            data = json.loads(p.read_text())
        except json.JSONDecodeError as e:
            fail(f"{p.name}: invalid JSON: {e}")
            continue
        if p.name.startswith("ep-"):
            try:
                import jsonschema
                jsonschema.validate(data, schema)
                err = None
            except ImportError:
                err = structural_validate(data, schema)
            except Exception as e:
                err = str(e).splitlines()[0]
            if err:
                fail(f"{p.name}: schema violation: {err}")
            else:
                ok(f"{p.name} validates against episode.schema.json")
        else:
            ok(f"{p.name} parses")


def check_import(name):
    if not (ROOT / name).exists():
        skip(f"{name}/ not present yet")
        return
    try:
        mod = importlib.import_module(name)
        if getattr(mod, "__file__", None):
            ok(f"import {name}")
            return
    except ModuleNotFoundError as e:
        if str(e) != f"No module named '{name}'":
            fail(f"import {name}: {e}")
            return
    except Exception as e:
        fail(f"import {name}: {e}")
        return
    # namespace package (no __init__.py) — import each submodule directly
    errs = []
    for f in sorted((ROOT / name).glob("*.py")):
        try:
            importlib.import_module(f"{name}.{f.stem}")
        except Exception as e2:
            errs.append(f"{f.name}: {type(e2).__name__}: {e2}")
    if errs:
        fail(f"{name} submodule imports: " + "; ".join(errs))
    else:
        ok(f"{name}/*.py import individually")


def check_web():
    index = ROOT / "web/index.html"
    if not index.exists():
        skip("web/index.html not present yet")
        return
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(
        *a, directory=str(ROOT / "web"), **kw)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/index.html")
        code = conn.getresponse().status
        (ok if code == 200 else fail)(f"web/index.html serves {code}")
    finally:
        srv.shutdown()


if __name__ == "__main__":
    print("smoke:")
    check_fixtures()
    check_import("pipeline")
    check_import("server")
    check_web()
    if FAIL:
        print(f"\nSMOKE FAILED ({len(FAIL)}): do NOT push."); sys.exit(1)
    print("\nsmoke passed — safe to push.")
