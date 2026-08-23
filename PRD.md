# Repo Radio — PRD (v2, hackathon-day architecture)
**The Fast Hackathon @ YC · repo: nithinaru/fasthack-yc-greptile · solo · hacking ends 5:00pm**

## 1. What we're building

**One-liner:** A daily AI-generated podcast that reads the source code of GitHub's fastest-trending repos and calls **HYPE / REAL / MIXED** — with a Stripe credit wallet where $1 buys 10 on-air questions, and a host that remembers every codebase it has ever covered.

**The problem:** a new "revolutionary" dev tool trends on GitHub every day. Everyone stars it; nobody reads the code. READMEs are marketing — the code is the truth — and nobody has an evening per repo to verify.

**The product:** the pipeline picks the fastest-rising repo (star velocity: stars/hour, not total stars — we catch things while they're blowing up), Greptile indexes and interrogates the actual source with file/line citations, an open LLM writes a 2-minute radio segment with personality and a verdict, open TTS voices it. **Signature interaction:** as the host speaks, the cited files slide on screen and highlight at the exact lines, karaoke-style — visible proof every claim traces to real code. Listeners top up a wallet and spend credits to ask the host anything, answered on air the same way. claude-mem gives the host longitudinal memory: "previously on" callbacks, verdict upgrades, category trend calls.

**v2 changes from v1 (already decided, do not revisit):**
- **No AWS in today's build** (credit approval delay). Modal hosts everything: models, the FastAPI API, and all static content (site, episode JSON, MP3s, RSS). Wallet = SQLite on a Modal Volume. If discussing infra in docs/pitch: "distribution is designed for S3+CloudFront behind an env flag; today it serves from Modal" — honest, never claimed as deployed.
- **Pricing:** $1 → 10 credits, $5 → 55, $10 → 120. 1 question = 1 credit = 10¢. Bonus tiers = the Starbucks stored-value model (float + feels-free pricing).
- **Single build agent**, milestone order in BUILD_PLAN.md.

## 2. Sponsor integrations (all four live; each load-bearing)

| Sponsor | Role |
|---|---|
| **Greptile** | The brain. Indexes repos; a 5-query battery fact-checks the README against source with citations; powers call-in answers. |
| **Modal** | Everything else. Qwen2.5-7B (vLLM) writes scripts; Kokoro-82M voices them; the same platform serves the FastAPI API + static site + audio + RSS. |
| **Stripe** | The wallet. Checkout top-ups (test mode) → webhook credits balance → atomic debit per question. |
| **claude-mem** | The memory ($1,000 separate prize track). Search-before-script, write-after-episode, visible "Host's Memory" panel. Hits their "build an integration" + "timeline as retrieval" + "give the skills a face" directions. |
| OpenAI Codex | Eligibility: must play a meaningful, logged role in the build during the event. |

## 3. Integration specs

### 3.1 Trending picker
`pipeline/trending.py`: `watchlist.json` (8–12 hand-picked hot AI/dev-tool repos w/ star samples) + GitHub Search API (`topic:ai created:>2026-07-01 sort:stars`). Rank by star velocity = Δstars/Δhours between samples. `--repo owner/name` override for demos. Auth: `GITHUB_TOKEN` (fine-grained PAT, public read).

### 3.2 Greptile (api.greptile.com/v2)
Headers: `Authorization: Bearer $GREPTILE_API_KEY` + `X-GitHub-Token: $GITHUB_TOKEN`.
- Index: `POST /repositories {"remote":"github","repository":"owner/name","branch":"main"}`; poll until ready. **Pre-index the entire watchlist immediately — indexing takes minutes per repo.**
- The 5-query battery (each: `POST /query`, `genius:true`, messages=[{role:"user",content:Q}], repositories=[…]):
  1. What does this repo actually do architecturally? Name the 2–3 core modules and what each owns.
  2. Is the core functionality implemented here or delegated to external APIs/SDKs? Cite the files that prove it.
  3. Which README claims are NOT fully supported by the code (stubbed/TODO/missing)? Cite files and lines.
  4. What's the single most technically interesting file/function, and why? Cite it.
  5. What's sketchiest — untested, TODO-ridden, hardcoded, security-questionable? Cite files and lines.
- Call-in answers: one `/query` with the user's question, `genius:false` (latency).
- Persist all raw responses to `runs/` — never re-query what you already have.

### 3.3 Modal — three apps (or one app, three functions; builder's choice)
1. **/script** — Qwen2.5-7B-Instruct via vLLM (A10G/L4). In: `{repo_meta, greptile_findings[5], memory_digest}`. Out (strict JSON, guided decoding, 2 retries): `{"title","verdict":"HYPE|REAL|MIXED","segments":[{"text","citation":{"file","start_line","end_line"}|null}]}`. Host persona in `prompts/host.txt`: late-night FM host, sharp/warm/wry, never cruel; every claim traces to a finding; ~2 min; one "previously on" callback when memory_digest is non-empty. Answer mode: same endpoint, `mode:"answer"` → single segment, 15–25s.
2. **/tts** — Kokoro-82M (T4). In: `{segments:[text,…]}`. Out: per-segment audio (b64) + `duration_s` each. **Timestamps = cumulative durations + 0.35s gaps** (count the gaps!) → drives karaoke sync. Assemble one MP3 with ffmpeg/pydub; compute ~240-bucket waveform peaks.
3. **/serve** — FastAPI ASGI app (CPU): the wallet API (§3.4) + static file serving from a Modal Volume: `/static/index.html`, `/static/episodes/ep-NNN.json`, `/static/audio/ep-NNN.mp3`, `/static/feed.xml`, `/static/memory.json`. Pipeline publishes by uploading to the Volume. `keep_warm=1` on all before demo windows.

### 3.4 Stripe (test mode) + wallet API
```
POST /api/topup            {user_id, tier: 1|5|10}         → {checkout_url}
POST /api/stripe/webhook   (signed, checkout.session.completed) → credit wallet
GET  /api/wallet/{user_id}                                  → {credits}
POST /api/ask              {user_id, episode_id, question}  → 402 | {job_id}
GET  /api/ask/{job_id}                                      → pending | {qa_segment}
```
Tiers: $1→10, $5→55, $10→120 credits (metadata carries user_id+credits). Wallet store: SQLite on the Modal Volume; debit = single transaction `UPDATE … SET credits=credits-1 WHERE user_id=? AND credits>=1`. Webhook endpoint registered in Stripe dashboard (test mode → Developers → Webhooks → the Modal /serve URL); `STRIPE_WEBHOOK_SECRET` in .env. Demo card: 4242 4242 4242 4242. user_id = lowercase email in localStorage.

### 3.5 claude-mem
Worker runs locally (found on :37777 previously; verify). Search-before-script via its `/api/search` → top-k notes → `memory_digest` text into the /script prompt. Write-after-episode: append findings (repo, claims, verdict, cited files, stars, category tags) to `memory.json` and publish it to the Modal Volume (worker has no HTTP write endpoint — it indexes passively; memory.json is the sanctioned write path). 20-minute timebox on any claude-mem debugging; fallback = memory.json alone (feature survives; claim only what runs). UI reads `/static/memory.json`.

## 4. Episode JSON contract (frozen)
```json
{ "id":"ep-001","date":"2026-08-23",
  "repo":{"full_name":"owner/name","url":"…","language":"Python","stars_at_airtime":4210,"velocity_per_hr":38},
  "title":"…","verdict":"MIXED",
  "audio":{"url":"/static/audio/ep-001.mp3","duration_s":128,"peaks":[0.1,0.4]},
  "segments":[{"i":0,"start":0.0,"end":14.2,"text":"…",
    "citation":{"file":"core/loop.py","start_line":41,"end_line":68,"code_html":"<pre>…one span per line, cited lines class=\"cited\"…</pre>"}|null}],
  "memory_refs":[{"episode_id":"ep-000","note":"…"}],
  "qa_segments":[{"question":"…","audio_url":"…","segments":[…]}] }
```
`peaks` pre-computed (waveform renders instantly, no audio-decode/CORS risk). `code_html` pre-rendered at generation time (pygments or shiki via npx; plain escaped lines with the cited range highlighted is acceptable).

## 5. UI spec — one static page, "late-night FM booth meets terminal"
- Layout: top bar (REPO RADIO wordmark · pulsing **ON AIR lamp** tied to play state · wallet chip) / hero player (repo in mono, big title in Hedvig Letters Serif, verdict badge, wavesurfer bar waveform, controls) / sync panel below (transcript left — active segment glows, auto-scroll w/ 3s manual-scroll suppression, click-to-seek; code card right — filename tab, cited lines amber-highlighted, swaps per segment) / right sidebar (episode list + collapsible Host's Memory panel) / footer "☎ CALL THE SHOW" ask strip (flips to top-up tiers at 0 credits).
- Palette: bg `#0A0A0F` (radial glow `#1A1025` behind hero), cards `#12121A`, borders `#26263A`, signature amber `#FFB020` (waveform progress/active line/cited code/lamp), dim amber `#7A5A1E`, text `#EDEDF2`/`#8B8B9E`, sparing teal `#5EEAD4` mono micro-labels. Verdicts: HYPE `#F43F5E`/`#2A0E14` · REAL `#34D399`/`#0B231A` · MIXED `#FBBF24`/`#261C08` (uppercase mono, 1px border).
- Fonts (Google Fonts): **Hedvig Letters Serif** titles · **Inter** 400/500/600 UI · **JetBrains Mono** code/timestamps/badges only.
- Libs (CDN, no build): Tailwind v4 (`https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4`), wavesurfer.js v7 esm, Lucide icons. Karaoke sync hand-rolled (~30 lines on timeupdate). Garnish: CSS 5-bar equalizer on now-playing row; optional 3% scanline overlay. ON AIR lamp: red pill, `box-shadow 0 0 12px rgba(244,63,94,.6)`, 2s pulse while playing.

## 6. Fixture episode (build UI against this before any live API)
Fictional repo `cavemanlabs/caveman` ("autonomous agent runtime"), verdict MIXED, 8 segments — full script in BUILD_PLAN §M0 (cold open → README promise → clean agent.py → "reasoning engine is a phone call" (llm/client.py) → genuinely-novel scheduler (core/scheduler.py) → memory is 6 lines + TODO (memory/store.py) → verdict → outro). Fake cited files in `fixtures/src/`.

## 7. Definition of done (by 4:30pm — judging at 5)
1. Modal /serve URL loads the page; one REAL episode (real Greptile + Qwen + Kokoro on a real trending repo) plays with working karaoke sync + code highlighting.
2. Stripe test top-up → credits appear → ask → credit debits → spoken answer plays with citations, <60s warm.
3. Memory: episode #2 (related repo) carries a "previously on"; memory panel renders; claude-mem worker screenshot saved.
4. Demo backup: episode copied locally + screen recording. keep_warm on. Codex logs exported.
