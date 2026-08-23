# ENDPOINTS.md — fill after `make publish`

Record the three Modal URLs here (and mirror them into `.env`:
`MODAL_SCRIPT_URL`, `MODAL_TTS_URL`, `MODAL_SERVE_URL`) as soon as
`make publish` prints them.

| App | Env var | URL |
|---|---|---|
| `/script` (Qwen2.5-7B via vLLM) | `MODAL_SCRIPT_URL` | `https://nithin-alaska--repo-radio-script-script-web.modal.run` |
| `/tts` (Kokoro-82M) | `MODAL_TTS_URL` | `https://nithin-alaska--tts.modal.run` |
| `/serve` (FastAPI: wallet API + static site) | `MODAL_SERVE_URL` | `https://nithin-alaska--repo-radio-serve-fastapi-app.modal.run` |

---

## /script — episode segments (PRD §3.3.1)

Strict JSON out: `{"title","verdict":"HYPE|REAL|MIXED","segments":[{"text","citation":{"file","start_line","end_line"}|null}]}`

```bash
curl -sS "https://nithin-alaska--repo-radio-script-script-web.modal.run" \
  -H "content-type: application/json" \
  -d '{
    "repo_meta": {
      "full_name": "cavemanlabs/caveman",
      "url": "https://github.com/cavemanlabs/caveman",
      "language": "Python",
      "stars_at_airtime": 4210,
      "velocity_per_hr": 38
    },
    "greptile_findings": [
      "core modules: core/agent.py, llm/client.py, core/scheduler.py",
      "reasoning engine is a thin wrapper over an external chat API (llm/client.py:8-24)",
      "README claims persistent long-term memory; memory/store.py is a 6-line dict with a TODO",
      "scheduler uses a priority queue with decay — genuinely novel",
      "sketchiest: memory/store.py — no persistence, TODO comment"
    ],
    "memory_digest": ""
  }' | python3 -m json.tool
```

Answer mode (call-in questions):

```bash
curl -sS "https://nithin-alaska--repo-radio-script-script-web.modal.run" \
  -H "content-type: application/json" \
  -d '{
    "mode": "answer",
    "repo_meta": {"full_name": "cavemanlabs/caveman"},
    "question": "Is the scheduler actually novel or just a priority queue?",
    "greptile_findings": ["core/scheduler.py:51-88 implements decay-based priority reordering"]
  }' | python3 -m json.tool
```

---

## /tts — voice a segment list (PRD §3.3.2)

In: `{segments:[text,…]}`. Out: per-segment audio (b64) + `duration_s` each.

```bash
curl -sS "https://nithin-alaska--tts.modal.run" \
  -H "content-type: application/json" \
  -d '{
    "segments": [
      "It'\''s 11:47 PM in San Francisco.",
      "This is Repo Radio — I read the code so you don'\''t have to."
    ]
  }' | python3 -c "import json,sys; d=json.load(sys.stdin); print([s['duration_s'] for s in d['segments']])"
```

---

## /serve — wallet API + static site (PRD §3.3.3 / §3.4)

Static site: `GET https://nithin-alaska--repo-radio-serve-fastapi-app.modal.run/static/index.html`, `/static/episodes/ep-NNN.json`, `/static/audio/ep-NNN.mp3`, `/static/feed.xml`, `/static/memory.json`.

### POST /api/topup

```bash
curl -sS -X POST "https://nithin-alaska--repo-radio-serve-fastapi-app.modal.run/api/topup" \
  -H "content-type: application/json" \
  -d '{"user_id": "demo@example.com", "tier": 1}' | python3 -m json.tool
# -> {"checkout_url": "https://checkout.stripe.com/..."}
```

### POST /api/stripe/webhook

Registered in the Stripe dashboard (test mode → Developers → Webhooks →
`https://nithin-alaska--repo-radio-serve-fastapi-app.modal.run/api/stripe/webhook`), signed with `STRIPE_WEBHOOK_SECRET`.
Not curl-able directly in test mode without a real signed payload — use
`stripe trigger checkout.session.completed` or the dashboard's "send test
webhook" against this URL.

### GET /api/wallet/{user_id}

```bash
curl -sS "https://nithin-alaska--repo-radio-serve-fastapi-app.modal.run/api/wallet/demo@example.com" | python3 -m json.tool
# -> {"credits": 10}
```

### POST /api/ask

```bash
curl -sS -X POST "https://nithin-alaska--repo-radio-serve-fastapi-app.modal.run/api/ask" \
  -H "content-type: application/json" \
  -d '{"user_id": "demo@example.com", "episode_id": "ep-000", "question": "Is the memory really just a dict?"}' \
  -i
# -> 402 if credits <= 0, else 200 {"job_id": "..."}
```

### GET /api/ask/{job_id}

```bash
curl -sS "https://nithin-alaska--repo-radio-serve-fastapi-app.modal.run/api/ask/<job_id>" | python3 -m json.tool
# -> {"status": "pending"} | {"status": "done", "qa_segment": {...}}
```

---

## Warm latency (measured 2026-08-23)

All three apps now run with `MIN_CONTAINERS=1` (script and tts were already
set from initial deploy; serve was redeployed today with
`SERVE_MIN_CONTAINERS=1 .venv/bin/modal deploy modal_apps/serve.py`, no code
changes). Each row below discarded one warm-up call before taking samples.

| Endpoint | Check | Latency (samples) | keep_warm |
|---|---|---|---|
| `/script` `GET /health` | health ping (not a generation call) | 0.319s, 0.261s, 0.337s | ✅ `SCRIPT_MIN_CONTAINERS=1` |
| `/tts` `POST /` | 1-segment synthesis (real audio) | 0.967s total, `duration_s`=5.475 | ✅ `REPO_RADIO_TTS_MIN_CONTAINERS=1` |
| `/serve` `GET /episodes/ep-001.json` | static episode JSON fetch | 0.710s, 0.586s, 0.598s | ✅ `SERVE_MIN_CONTAINERS=1` (redeployed today) |

Known cold-start numbers (not re-measured today — script generation was not
re-run to avoid burning GPU repeatedly):

| Endpoint | Cold-start | Notes |
|---|---|---|
| `/script` | ≈42–64s | container + model load; one known full generation bake ≈53s warm (after cold load) |
| `/tts` | ≈100s image pull + ≈28s | for an 8-segment synthesis, warm-ish container |
| `/serve` | ≈5–8s | container + static asset mount, no model load |

All three endpoints confirmed responding 200 and keep-warm (`MIN_CONTAINERS=1`)
as of this measurement pass.
