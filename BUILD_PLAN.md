# BUILD_PLAN.md — single-agent milestone plan (hacking window: now → 5:00pm)

One Claude Code session builds this in milestone order. Use subagents inside a milestone only where chunks are truly independent (noted). Commit+push per milestone, `M<n>:` prefix, scoped adds, `make smoke` first.

**Repo layout:** `pipeline/` `modal_apps/` `server/` `web/` `fixtures/` `prompts/` `runs/` + Makefile (`smoke`, `bake-episode`, `publish`), `.env`/`.env.example`.

---

## M0 — Scaffold + fixtures (~20 min) — everything depends on this
- Repo skeleton, Makefile, .env.example, .gitignore (runs/, .env, *.mp3 in runs).
- `fixtures/ep-000.json` per PRD §4 from the Caveman script below; fake cited files in `fixtures/src/` (agent.py, llm/client.py, core/scheduler.py, memory/store.py — 30–90 plausible lines each); `code_html` pre-rendered (one span per line, cited range class="cited"); silent 2-min placeholder MP3 (ffmpeg anullsrc) with segment timestamps matching durations.
- `fixtures/greptile_response.json`, `script_response.json`, `wallet.json`. `make smoke` validates ep-000 against the contract.
- **Caveman fixture script (verbatim, citations per PRD §6):**
  1. "It's 11:47 PM in San Francisco, and GitHub's hottest new repo just crossed four thousand stars. This is Repo Radio — I read the code so you don't have to."
  2. "Tonight's subject: Caveman. The README promises a full autonomous agent runtime — memory, tools, scheduling, the works. Four thousand stars in three days. Let's see what's actually in the cave."
  3. (core/agent.py 12–38) "Crack open core/agent.py and the skeleton is clean: an Agent class, a tool registry, a run loop. Credit where due — this is readable code."
  4. (llm/client.py 8–24) "But here in llm/client.py? The 'proprietary reasoning engine' is forty lines wrapping someone else's chat API. That's not a reasoning engine, folks. That's a phone call."
  5. (core/scheduler.py 51–88) "Now, the plot twist. The scheduler is legitimately clever — priority queues with decay, so stale tasks lose their place in line. I haven't seen that pattern in the other frameworks. This is the part worth stealing."
  6. (memory/store.py 3–9) "And the 'long-term memory' the README brags about? Six lines. A dictionary. And a TODO that says, quote, 'make this persistent.' The cave paintings were more durable."
  7. "So: verdict MIXED. Real craftsmanship in the scheduler, marketing everywhere else. Star it for the scheduler. Don't bet your startup on the memory."
  8. "That's the broadcast. Wallet's open if you've got questions — a dollar gets you ten, answered on air. Repo Radio: we read the code so you don't have to. Stay curious."
- Also NOW (human, parallel): pre-index the whole `watchlist.json` in Greptile — it takes minutes per repo and gates M3.

## M1 — Frontend on fixtures (~45 min) — the face; PRD §5 to the letter
Subagent split OK: (a) skeleton+design system+player, (b) sync panel+code card, (c) wallet strip+episode list+memory panel.
**DoD:** open the page locally against fixtures — plays, syncs, looks premium. This alone is a demoable screen.

## M2 — Modal apps deploy (~40 min)
`modal_apps/script.py` (Qwen/vLLM, guided JSON, prompts/host.txt), `modal_apps/tts.py` (Kokoro, per-segment durations), `server/app.py` (/serve: wallet API stubs w/ USE_MOCKS + static from Volume). Deploy all; record URLs in `.env` + `ENDPOINTS.md` with working curls.
**DoD:** curl /script with fixture findings → valid JSON <30s warm; curl /tts 5 segments → audio+durations <20s warm; /serve serves the M1 page + fixtures publicly.

## M3 — Pipeline live (~45 min) — ⛔ GATE: first REAL episode by ~3:15pm
`pipeline/`: trending.py → greptile.py (battery, runs/ cache) → script.py → voice.py (timeline+gaps, MP3, peaks) → render.py (code_html from GitHub raw) → publish.py (upload to Modal Volume, feed.xml) → memory.py (claude-mem search-before via :37777, memory.json write-after, 20-min timebox) → `make bake-episode REPO=…`.
Bake the real episode on the day's best watchlist repo. **The second it plays in the UI: copy episode+audio to demo_backup/ and screen-record.** Then bake ep #2 on a related repo (memory callback).
**DoD:** two real episodes served from Modal, sync working.

## M4 — Stripe wallet live (~30 min)
SQLite wallet on Volume, tiers $1→10/$5→55/$10→120, Checkout + dashboard-registered webhook → credit; /api/ask: atomic debit → Greptile (genius:false) → /script answer mode → /tts → qa_segment published → UI polls, plays, balance ticks down.
**DoD:** full loop on the public URL with card 4242…, <60s warm.

## M5 — Memory visible + polish (~20 min)
Memory panel renders memory.json; "previously on" audible in ep #2; ON AIR lamp/equalizer/zero-credit state pass; favicon+OG; README: one-liner, architecture diagram (trending → Greptile → Qwen/Kokoro on Modal → Modal serve → Stripe wallet → claude-mem), sponsor map, honest AWS note ("S3/CloudFront path built behind env flag; credits in approval").
**DoD:** PRD §7 checklist all green.

## M6 — Demo lock (4:30pm, hard stop)
keep_warm on all Modal apps · bake/verify final demo episode · rehearse PITCH.md ×2 (once wifi-off from local copy) · export Codex logs · final push · claude-mem track writeup (3 sentences + worker screenshot).

---

## Cut order if behind (execute, don't debate)
polish extras → memory UI panel (keep "previously on" audio — free once memory.json exists) → claude-mem worker (→ memory.json only) → episode #2 → **never cut:** one real episode, karaoke sync, the Stripe→answer loop.

## Failure fallbacks (pre-decided)
Qwen JSON drift → guided decoding + 2 retries + last-good cache. Kokoro slow → parallel per-segment calls, fewer/longer segments. Modal cold start at judging → keep_warm from 4:15 + warm-up curl 4:55. Greptile slow indexing → whole watchlist pre-indexing since M0; demo whichever repo finished. Stripe webhook flaky → debug credit endpoint behind env flag (disclose if asked). Venue wifi dies → local static server + demo_backup + recording.
