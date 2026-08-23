#!/usr/bin/env python3
"""Repo Radio smoke test — run via `make smoke` before EVERY push.

Checks (lane artifacts that don't exist yet are SKIPPED, not failed, so
early lanes can push before later lanes have started):
  1. fixtures/ep-000.json AND web/episodes/ep-000.json validate against
     contracts/episode.schema.json (jsonschema if installed, else a
     built-in structural check). Other fixtures/*.json just parse.
  2. `import pipeline` and `import server` work with USE_MOCKS=1 set
     (each submodule imported in its own subprocess so one broken file
     doesn't block the report). modal_apps/*.py import-checked too;
     "ModuleNotFoundError: No module named 'modal'" is a soft warning,
     not a failure (the modal SDK may not be installed locally).
  3. web/index.html exists and references config.js.
  4. fixtures/audio/ep-000.mp3 exists and is non-empty.
  5. .env.example has no AWS vars (AWS_REGION/S3_BUCKET/CLOUDFRONT_*).
Exit code 0 = safe to push.
"""

import http.client
import http.server
import json
import os
import pathlib
import socket
import subprocess
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAIL = []
WARN = []
def ok(msg): print(f"  ok    {msg}")
def skip(msg): print(f"  skip  {msg}")
def warn(msg): print(f"  warn  {msg}"); WARN.append(msg)
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


def validate_episode(path, schema):
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        fail(f"{path}: invalid JSON: {e}")
        return
    try:
        import jsonschema
        jsonschema.validate(data, schema)
        err = None
    except ImportError:
        err = structural_validate(data, schema)
    except Exception as e:
        err = str(e).splitlines()[0]
    if err:
        fail(f"{path}: schema violation: {err}")
    else:
        ok(f"{path.relative_to(ROOT)} validates against episode.schema.json")


def check_fixtures():
    schema_path = ROOT / "contracts/episode.schema.json"
    if not schema_path.exists():
        fail("contracts/episode.schema.json missing")
        return
    schema = json.loads(schema_path.read_text())

    ep_fixture = ROOT / "fixtures/ep-000.json"
    if ep_fixture.exists():
        validate_episode(ep_fixture, schema)
    else:
        skip("fixtures/ep-000.json not present yet")

    ep_web = ROOT / "web/episodes/ep-000.json"
    if ep_web.exists():
        validate_episode(ep_web, schema)
    else:
        skip("web/episodes/ep-000.json not present yet")

    for p in sorted((ROOT / "fixtures").glob("*.json")):
        if p.name == "ep-000.json":
            continue
        try:
            json.loads(p.read_text())
            ok(f"{p.name} parses")
        except json.JSONDecodeError as e:
            fail(f"{p.name}: invalid JSON: {e}")


def check_import_dir(name):
    """Import every top-level .py in a package dir, each in its own
    subprocess so one bad module doesn't block the rest of the report."""
    d = ROOT / name
    if not d.exists():
        skip(f"{name}/ not present yet")
        return
    py_files = sorted(f for f in d.glob("*.py") if not f.name.startswith("test_"))
    if not py_files:
        skip(f"{name}/ has no importable modules yet")
        return
    env = dict(os.environ)
    env["USE_MOCKS"] = "1"
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    for f in py_files:
        mod = f"{name}.{f.stem}"
        proc = subprocess.run(
            [sys.executable, "-c", f"import {mod}"],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0:
            ok(f"import {mod}")
            continue
        stderr = proc.stderr.strip().splitlines()
        last = stderr[-1] if stderr else "unknown error"
        if name == "modal_apps" and "ModuleNotFoundError: No module named 'modal'" in last:
            warn(f"import {mod}: modal SDK not installed locally (soft)")
        else:
            fail(f"import {mod}: {last}")


def check_web():
    index = ROOT / "web/index.html"
    if not index.exists():
        skip("web/index.html not present yet")
        return
    html = index.read_text()
    if "config.js" in html:
        ok("web/index.html references config.js")
    else:
        fail("web/index.html does not reference config.js")

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


def check_fixture_audio():
    audio = ROOT / "fixtures/audio/ep-000.mp3"
    if not audio.exists():
        fail("fixtures/audio/ep-000.mp3 missing")
        return
    if audio.stat().st_size > 0:
        ok(f"fixtures/audio/ep-000.mp3 exists ({audio.stat().st_size} bytes)")
    else:
        fail("fixtures/audio/ep-000.mp3 is empty")


def check_env_example():
    envf = ROOT / ".env.example"
    if not envf.exists():
        fail(".env.example missing")
        return
    text = envf.read_text()
    aws_markers = ("AWS_REGION", "S3_BUCKET", "CLOUDFRONT_")
    hits = [m for m in aws_markers if m in text]
    if hits:
        fail(f".env.example still has AWS vars: {', '.join(hits)}")
    else:
        ok(".env.example has no AWS vars")


if __name__ == "__main__":
    print("smoke:")
    check_fixtures()
    check_fixture_audio()
    check_import_dir("pipeline")
    check_import_dir("server")
    check_import_dir("modal_apps")
    check_web()
    check_env_example()

    print("\n--- PASS/FAIL ---")
    print(f"  failures: {len(FAIL)}   warnings: {len(WARN)}")
    if FAIL:
        for m in FAIL:
            print(f"  FAIL  {m}")
        print(f"\nSMOKE FAILED ({len(FAIL)}): do NOT push.")
        sys.exit(1)
    if WARN:
        for m in WARN:
            print(f"  warn  {m}")
    print("\nsmoke passed — safe to push.")
