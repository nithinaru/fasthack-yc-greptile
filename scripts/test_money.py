#!/usr/bin/env python3
"""Headless end-to-end money-loop verifier (make test-money).

Runs against the deployed Modal wallet API (MODAL_SERVE_URL) with a fresh
throwaway user each run:

  1. GET  /api/wallet/{user}         -> baseline 0 credits
  2. POST /api/topup                 -> Stripe Checkout URL comes back
  3. POST /api/stripe/webhook        -> hand-signed checkout.session.completed
                                        (Stripe signature scheme: t=<ts>,
                                        v1=HMAC-SHA256(f"{ts}.{payload}", secret))
  4. GET  /api/wallet/{user}         -> credits == 10
  5. POST /api/ask                   -> 200 {job_id}, wallet drops to 9.
                                        NOTE: server/ask.py run_job does NOT
                                        refund on pipeline failure (the debit in
                                        app.py precedes job creation and the
                                        except-branch only marks the job error),
                                        so 9 is asserted unconditionally.
  6. GET  /api/ask/{job_id}          -> poll up to 60s; a pipeline 500/error is
                                        another lane's turf -> BLOCKED, not FAIL.

Stdlib only. Exit 0 iff every non-BLOCKED step passes.
"""
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PASS, FAIL, BLOCKED = "PASS", "FAIL", "BLOCKED"


def load_env() -> None:
    """Mimic the Makefile's `-include .env` + `export`: simple KEY=VALUE lines,
    environment wins over file."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def http(method: str, url: str, body: bytes | None = None,
         headers: dict | None = None, timeout: float = 30.0):
    """Return (status_code, parsed_json_or_None). Never raises on HTTP errors."""
    req = urllib.request.Request(url, data=body, method=method,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        status = e.code
    except (urllib.error.URLError, OSError) as e:
        return None, {"error": f"network: {e}"}
    try:
        return status, json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return status, {"raw": raw[:200].decode("utf-8", "replace")}


def post_json(url: str, obj: dict, headers: dict | None = None):
    h = {"content-type": "application/json", **(headers or {})}
    return http("POST", url, json.dumps(obj).encode(), h)


def stripe_signature(payload: bytes, secret: str, ts: int | None = None) -> str:
    """Stripe webhook signature scheme: v1 = HMAC-SHA256 over f"{t}.{payload}"."""
    ts = ts or int(time.time())
    signed = f"{ts}.".encode() + payload
    sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def main() -> int:
    load_env()
    base = os.environ.get("MODAL_SERVE_URL", "").rstrip("/")
    whsec = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not base:
        print("MODAL_SERVE_URL not set (.env) — cannot run"); return 2
    if not whsec:
        print("STRIPE_WEBHOOK_SECRET not set (.env) — cannot sign webhook"); return 2

    user = f"moneytest-{uuid.uuid4().hex[:8]}@example.com"
    results: list[tuple[str, str, str]] = []  # (step, status, detail)
    print(f"money-loop test against {base}\nuser: {user}\n")

    def wallet() -> tuple[int | None, int | None]:
        code, body = http("GET", f"{base}/api/wallet/{user}")
        return code, (body or {}).get("credits")

    # 1. baseline wallet
    code, credits = wallet()
    ok = code == 200 and credits == 0
    results.append(("1 wallet baseline", PASS if ok else FAIL,
                    f"HTTP {code}, credits={credits} (want 0)"))

    # 2. topup -> checkout_url
    code, body = post_json(f"{base}/api/topup", {"user_id": user, "tier": 1})
    url = (body or {}).get("checkout_url", "")
    ok = code == 200 and url.startswith("http")
    results.append(("2 topup checkout_url", PASS if ok else FAIL,
                    f"HTTP {code}, url={url[:60]}..." if ok else f"HTTP {code}, body={body}"))

    # 3. simulated signed webhook (what Stripe would send after card entry)
    now = int(time.time())
    event = {
        "id": f"evt_test_{uuid.uuid4().hex[:16]}",
        "object": "event",
        "api_version": "2024-06-20",
        "created": now,
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": f"cs_test_{uuid.uuid4().hex[:16]}",
            "object": "checkout.session",
            "payment_status": "paid",
            "metadata": {"user_id": user, "credits": "10"},
        }},
    }
    payload = json.dumps(event).encode()
    code, body = http("POST", f"{base}/api/stripe/webhook", payload, {
        "content-type": "application/json",
        "Stripe-Signature": stripe_signature(payload, whsec, now),
    })
    ok = code is not None and 200 <= code < 300
    detail3 = f"HTTP {code}" + ("" if ok else f", body={body}")
    if not ok and "verification failed" in str(body):
        # Our signing is stripe-lib-verified locally, so this means the server's
        # STRIPE_WEBHOOK_SECRET differs from .env's (e.g. stale Modal Secret
        # "repo-radio-secrets"): `modal secret` update it to match, redeploy /serve.
        detail3 += " [server webhook secret != .env STRIPE_WEBHOOK_SECRET?]"
    results.append(("3 signed webhook", PASS if ok else FAIL, detail3))

    # 4. wallet credited
    code, credits = wallet()
    ok = code == 200 and credits == 10
    results.append(("4 wallet == 10", PASS if ok else FAIL,
                    f"HTTP {code}, credits={credits}"))

    # 5. ask -> 200 {job_id} + debit to 9 (no refund on failure; see docstring)
    code, body = post_json(f"{base}/api/ask",
                           {"user_id": user, "episode_id": "ep-000",
                            "question": "test"})
    job_id = (body or {}).get("job_id")
    ask_ok = code == 200 and bool(job_id)
    results.append(("5a ask -> job_id", PASS if ask_ok else FAIL,
                    f"HTTP {code}, job_id={job_id}" if ask_ok else f"HTTP {code}, body={body}"))
    code, credits = wallet()
    ok = code == 200 and credits == 9
    results.append(("5b wallet == 9 (debit)", PASS if ok else FAIL,
                    f"HTTP {code}, credits={credits}"))

    # 6. optional poll: pipeline errors are BLOCKED (other lane), not FAIL
    if not ask_ok:
        results.append(("6 poll job done", BLOCKED, "no job_id from step 5"))
    else:
        status, detail = BLOCKED, "timed out after 60s (pipeline slow/cold?)"
        deadline = time.time() + 60
        while time.time() < deadline:
            code, body = http("GET", f"{base}/api/ask/{job_id}")
            st = (body or {}).get("status")
            if st == "done":
                status, detail = PASS, "status=done, qa_segment present" \
                    if body.get("qa_segment") else "status=done (no qa_segment?)"
                break
            if st == "error" or (code is not None and code >= 500):
                status = BLOCKED  # script/tts Modal apps = another session's turf
                detail = f"pipeline error (HTTP {code}): {str((body or {}).get('error'))[:120]}"
                break
            time.sleep(3)
        results.append(("6 poll job done", status, detail))

    # report
    print(f"{'step':<24} {'status':<8} detail")
    print("-" * 78)
    for step, status, detail in results:
        print(f"{step:<24} {status:<8} {detail}")
    failed = [r for r in results if r[1] == FAIL]
    blocked = [r for r in results if r[1] == BLOCKED]
    print("-" * 78)
    print(f"{len(results) - len(failed) - len(blocked)} pass, "
          f"{len(failed)} fail, {len(blocked)} blocked")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
