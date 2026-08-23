# LANES.md — Parallel build plan (4 lanes, Claude Code orchestrated, building TODAY)

**Operating model:** You run **four Claude Code sessions in parallel** (four terminal tabs, one per lane, all in the same repo clone — or separate clones if you prefer zero working-tree contention; the git protocol works either way). Each lane's session is that lane's **orchestrator**: it owns a mission, decomposes it into the subtasks below, and fans work out to its own subagents (Task tool) where parallelism helps — e.g., Lane C splitting player / sync-panel / wallet-strip across subagents, or Lane B deploying both Modal apps at once. You are the tech lead: you paste each orchestrator its lane prompt, arbitrate contract questions, and enforce the git protocol.

**Reality check:** 4 lanes ≠ 4× speed for one human. The win is that B/C/D run long and mostly autonomous while your attention lives in Lane A (the critical path). Kick off all four, then rotate, camping on A.

---

## 0. Repo + git protocol (non-negotiable)

- One repo (`repo-radio`), **one branch: `main`**. No feature branches — lanes touch disjoint directories by design, so merge ceremony buys nothing.
- **Every update → push.** After every completed micro-task (target cadence ≤ 10 min):
  ```
  git add -A && git commit -m "<lane>: <what>" && git pull --rebase && git push
  ```
  Rebase conflict = someone edited outside their lane. Fix the ownership violation, not just the conflict.
- **Directory ownership (prevents 95% of conflicts):**
  - Lane A → `pipeline/`
  - Lane B → `modal_apps/`
  - Lane C → `web/`
  - Lane D → `server/`
  - Shared, **frozen at Gate 0**: `contracts/`, `fixtures/`, `CLAUDE.md`, `Makefile`. Changes after freeze = one `SYNC:` commit + paste the change notice into all four sessions.
- Commit prefixes: `A:` `B:` `C:` `D:` `SYNC:` `FIX:`.
- **Never break main:** `make smoke` before every push (fixtures validate against schema; `python -c "import pipeline"`; server import check; `web/index.html` serves 200 locally). Lane 0 writes the smoke script first.
- Secrets: `.env` (gitignored) + `.env.example` (committed). Never in code.

## CLAUDE.md (commit at repo root — every Claude Code session and subagent reads it automatically)

```markdown
# Repo Radio — agent instructions
Read contracts/ and fixtures/ FIRST. They are frozen; code conforms to them, never the reverse.
Each session owns exactly ONE directory (pipeline/ | modal_apps/ | web/ | server/). Never edit outside your lane. contracts/, fixtures/, Makefile changes require the human's SYNC approval.
After every completed subtask: make smoke, then git add -A && git commit -m "<lane>: <what>" && git pull --rebase && git push. Small commits, high frequency.
Stack: Python 3.11, FastAPI, boto3. Frontend is ONE static web/index.html, no build step, Tailwind v4 CDN, wavesurfer.js v7, fonts: Hedvig Letters Serif (display) / Inter (UI) / JetBrains Mono (code).
Mock-first: everything must run against fixtures/ with USE_MOCKS=1 before touching live APIs. Live keys are in .env.
Full spec: REPO_RADIO_PRD.md (§5 integrations, §6 contracts, §7 UI). Lane briefs: LANES.md.
When blocked on a contract ambiguity, ASK the human — do not improvise a schema change.
```

---

## Lane 0 — Foundation (YOU + one Claude Code session, ~20 min, blocking)

Everything else waits on this:
1. `git init` repo-radio on GitHub; commit REPO_RADIO_PRD.md, LANES.md, HANDOFF.md, CLAUDE.md.
2. Commit `contracts/episode.schema.json` + `contracts/wallet_api.md` (transcribed from PRD §6) and `fixtures/`: `ep-000.json` built from the sample script in HANDOFF.md §4 (fake cited files under `fixtures/src/`, code_html rendered with pygments/shiki, any stub MP3 for now — Lane A's voice.py will replace it with real Kokoro audio as its first live test), `greptile_response.json`, `script_response.json`, `wallet.json`.
3. `.env` from HANDOFF.md checklist; `.env.example`; Makefile with `smoke`, `deploy-web`, `bake-episode` targets.
4. AWS: S3 bucket + CloudFront distro + DynamoDB `wallets` (session generates the AWS CLI commands; you run/approve them). Upload fixtures; verify the CloudFront URL serves ep-000.
5. Open the four lane sessions, paste each its prompt. **Go.**

---

## Lane A — Content Pipeline (`pipeline/`) — THE CRITICAL PATH

**Mission:** repo in → published episode in S3 out.

Subtasks in order:
- A1. `trending.py`: watchlist.json + GitHub search, star-velocity scoring → pick repo.
- A2. `greptile.py`: index + poll-until-ready + the 5-query battery (PRD §5.2); persist raw responses to `runs/`; `USE_MOCKS=1` returns fixtures.
- A3. `script.py`: call Modal `/script` (mock until B posts ENDPOINTS.md); validate strict JSON; retry ×2 on parse fail.
- A4. `voice.py`: call Modal `/tts` per segment; cumulative timestamps incl. 0.35s gaps; assemble MP3 (pydub/ffmpeg); compute waveform `peaks`.
- A5. `render.py`: pre-render `code_html` per citation (shiki via npx, one span per line, cited lines get class `cited`); fetch cited file content from GitHub raw.
- A6. `publish.py`: assemble episode JSON → S3 upload (JSON+MP3) → regenerate `feed.xml` → CloudFront invalidation.
- A7. `memory.py`: claude-mem write-after / search-before (PRD §5.7, **20-min timebox**) → `memory_digest` into the script prompt; export `memory.json` to S3. Fallback ready: plain S3 JSON append/read.
- A8. `make bake-episode REPO=owner/name` runs A1→A7.

**DoD:** `make bake-episode` produces a real playable episode end-to-end twice; the second episode (related repo) demonstrates a memory callback.

**Orchestrator prompt (paste into Claude Code session A):**
> Read CLAUDE.md, REPO_RADIO_PRD.md §5–6, and LANES.md Lane A. You own `pipeline/` only. Build subtasks A1–A8 in order, mock-first (`USE_MOCKS=1` against fixtures/), committing and pushing after each per the git protocol. Use subagents where subtasks are independent (A1, A5 can run while A2 is being built). Flip to live one integration at a time: Greptile first (keys in .env), Modal when modal_apps/ENDPOINTS.md appears in a pull. Ask me before any deviation from contracts/.

---

## Lane B — Model Serving (`modal_apps/`)

**Mission:** two Modal web endpoints, warm and fast.

- B1. `scriptwriter.py`: vLLM + Qwen2.5-7B-Instruct, A10G/L4, `POST /script` per PRD §5.3, guided JSON decoding, host persona in `prompts/host.txt` (tune wording there, not in code).
- B2. `voice.py`: Kokoro-82M, T4, `POST /tts` per PRD §5.4 (per-segment audio + durations). Test both shortlisted voices; pick one; hard-code.
- B3. `modal deploy` both; write URLs + working curl examples to `modal_apps/ENDPOINTS.md`; **commit+push immediately** (unblocks Lane A).
- B4. Latency pass: p50 for 5-segment script + TTS, cold vs warm documented; `keep_warm=1` before any demo window.

**DoD:** ENDPOINTS.md curls work from a fresh shell; script <30s and 5-segment TTS <20s warm.

**Orchestrator prompt (session B):**
> Read CLAUDE.md, PRD §5.3–5.4, LANES.md Lane B. You own `modal_apps/` only. Build B1–B4 in order — run B1 and B2 as parallel subagents, they share nothing. Response shapes in contracts/ are law. Deploy early even if rough; Lane A needs live URLs more than perfection. Commit+push ENDPOINTS.md the second deploys succeed.

---

## Lane C — Frontend (`web/`)

**Mission:** the one gorgeous page, 100% functional on fixtures before any live data exists.

- C1. Skeleton + design system: layout regions, palette, fonts (**Hedvig Letters Serif** display / **Inter** UI / **JetBrains Mono** code), ON AIR lamp, verdict badges — PRD §7 to the letter.
- C2. Player: wavesurfer from `audio.url` + `peaks`; play/pause/seek; lamp + hero glow tied to play state.
- C3. Karaoke sync: segment activation on timeupdate, auto-scroll with 3s manual-scroll suppression, click-to-seek, code-card swap + cited-line highlights from pre-rendered `code_html`.
- C4. Wallet + call-in strip: balance chip (poll `GET /api/wallet`), top-up redirect + balance count-up on return, ask box (`POST /api/ask` → poll job → append qa_segment and play). Fixture server first.
- C5. Episode list + Host's Memory panel (renders `memory.json`; collapsible).
- C6. Polish: equalizer bars, scanline overlay, zero-credit state, favicon, OG tags.

**DoD:** demo-quality on fixtures; flips to live data with zero code changes.

**Orchestrator prompt (session C):**
> Read CLAUDE.md, PRD §7 (follow the UI spec exactly — palette hexes, fonts, ON AIR lamp) and §6 (contracts). You own `web/` only: ONE static index.html + small js modules, no build step. Build C1–C6 in order against fixtures/ (C2, C3, C4 can be parallel subagents once C1's skeleton exists). Fully demoable with USE_MOCKS=1 before any backend exists. Push after each subtask; `make deploy-web` syncs to S3.

---

## Lane D — Money + Serving API (`server/`)

**Mission:** FastAPI on App Runner — wallet, Stripe, ask-flow.

- D1. FastAPI skeleton + Dockerfile + CORS (CloudFront origin) + `/healthz`; all PRD §6.2 endpoints returning fixture data under `USE_MOCKS=1`. **Push within 30 min — Lane C is waiting.**
- D2. DynamoDB wallet: get / credit / atomic conditional debit.
- D3. Stripe: Checkout session (3 tiers, metadata) + signature-verified webhook → credit wallet. Stripe CLI locally first.
- D4. Ask-flow: debit → Greptile (`genius:false`; import `pipeline/greptile.py` — the ONE sanctioned cross-lane import) → Modal script (single-segment answer mode) → Modal TTS → qa audio+segment to S3 → in-memory job store.
- D5. Deploy to App Runner; curl the full loop; write the public base URL into `web/config.js` via a `SYNC:` commit.
- D6. Pre-built fallback: `make serve-local` + Stripe CLI `listen --forward-to localhost:8080` + cloudflared tunnel — identical API from the laptop if App Runner misbehaves.

**DoD:** deployed URL passes: topup (test card 4242…) → webhook → credits up → ask → answer JSON with audio URL, <60s warm.

**Orchestrator prompt (session D):**
> Read CLAUDE.md, PRD §5.5–5.6 and §6.2, LANES.md Lane D. You own `server/` only (exception: you may IMPORT pipeline/greptile.py, never edit it). Build D1–D6 in order, mock-first, Stripe test mode. D1 pushed fast is the top priority. Build D6 as soon as D5 works — the fallback must exist before it's needed.

---

## Gates (order, not clock — you enforce; lanes pause, sync, verify)

| Gate | Pass criteria |
|---|---|
| **G0 — Contracts frozen** | Lane 0 done: fixtures serve via CloudFront; four sessions briefed and running. |
| **G1 — First real episode** | A×B live: `make bake-episode` on a real repo → plays in C's UI with sync working. **Immediately copy episode + screen-record to `demo_backup/`. This is the minimum viable demo — protect it.** |
| **G2 — Money loop** | C×D live: topup → ask → spoken answer in the UI. Bake episode #2 (memory callback). |
| **G3 — Freeze** | Only `FIX:` commits. keep_warm on. Final demo episode baked. Backup video recorded. Rehearse the demo (script in HANDOFF.md §5), once with wifi off. |

**Cut order if behind (pre-decided):** C6 polish extras → Memory UI panel (keep "previously on" in audio — free once memory.json exists) → claude-mem worker (→ S3 memory.json) → App Runner (→ D6 local) → episode #2.
**Never cut:** one real episode · karaoke sync · the Stripe→answer loop.
