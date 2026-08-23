# Repo Radio — Product Requirements Document
**The Fast Hackathon (Greptile @ YC) · Sunday Aug 24, 2026 · Solo build, 4-hour window (1–5pm)**

---

## 1. Product overview

**One-liner:** A daily AI-generated podcast that reads the code of GitHub's fastest-trending repos and tells you what's hype and what's real — top up a wallet, spend credits to ask the host anything, answered on air.

**Walk-past version:** "We read the code of trending repos so you don't have to — as a podcast."

**The problem.** AI-agent builders face a new "revolutionary" framework, MCP server, or dev tool trending on GitHub every single day. Everyone stars it; nobody reads the code. READMEs are marketing — the code is the truth. Verifying a single repo costs an evening of source-reading that nobody has.

**The insight.** GitHub gives you the diff; Repo Radio gives you the *consequence* — while your hands are busy. Audio is the only medium that fits into the 30–60 min/day of dead time (commute, gym, dishes) where developers can't read but can listen.

**The product.** A pipeline picks the fastest-rising repo on GitHub, Greptile indexes and interrogates the actual source, an open-source LLM writes a radio segment with a verdict — **HYPE / REAL / MIXED** — and an open-source TTS model voices it. The signature on-screen moment: as the host speaks, the cited source files slide into view with the exact lines highlighted, karaoke-style. Listeners keep a Starbucks-style credit wallet and spend credits to ask the host questions, answered on air with the same code-grounded rigor. The host has long-term memory (claude-mem) of every codebase it has ever covered, enabling longitudinal journalism: follow-ups, verdict upgrades, and category-level trend calls.

**Persona (primary):** AI-agent builders and hackathon-goers optimizing their workflow, who need to know within hours whether a trending tool is worth adopting.

**Signature segment (writes itself):**
> "The README says it's a full agent runtime. We read the code. It's 400 lines wrapping the OpenAI SDK — but the scheduler in `core/loop.py` is legitimately novel. Here's why."

---

## 2. Prize strategy

### 2.1 Judging criteria map (overall track)
| Criterion | Weight | How Repo Radio scores it |
|---|---|---|
| Technical Difficulty | 30% | 5-service pipeline: Greptile codebase interrogation → self-hosted open LLM (vLLM on Modal) → self-hosted open TTS (Kokoro on Modal) → S3/CloudFront podcast infra + DynamoDB wallet → claude-mem long-term memory. Two self-hosted models, agent memory, live payments. |
| Execution | 25% | Rehearsed build from this PRD; every risky piece has a pre-planned fallback; demo runs off a cached episode with the live path as the encore. |
| Creativity | 20% | A podcast whose host reads source code and fact-checks READMEs against it. Nobody else in the room will have an audio product. |
| Impact | 15% | Hype-vs-real is a daily, real problem for the exact audience in the room. 10¢ paid questions prove willingness-to-pay live. |
| Presentation | 10% | 90-second demo: play episode → judge pays → asks → hears the answer on air with code highlighting. Ends inside a working payment loop. |

### 2.2 Sponsor integration map — every sponsor load-bearing
| Sponsor | Role | Remove it and… |
|---|---|---|
| **Greptile** | The brain: indexes repos, answers the interrogation battery with file/line citations; fact-checks READMEs against source | there is no product |
| **Modal** | The writer + voice: Qwen 2.5-7B (vLLM) writes scripts; Kokoro-82M voices them; both open-source models pulled from GitHub | no episodes |
| **AWS** | The podcast infrastructure: S3+CloudFront serve app, audio, episode JSON, and RSS; DynamoDB holds the wallet | no distribution, no wallet |
| **Stripe** | The Starbucks wallet: Checkout top-ups → credits → metered questions; webhook is the gate on the ask pipeline | no monetization loop |
| **OpenAI** | Codex is the primary coding agent building the entire project (eligibility requirement — keep session logs + commit history as proof) | not eligible |
| **DoorDash** | "Powered the developer." (Say it as a joke if asked.) | hungry |

### 2.3 Claude-Mem Memory Prize ($1,000, judged separately)
Repo Radio hits three of their seven directions simultaneously:
- **Build an integration:** claude-mem wired into an autonomous media pipeline — somewhere it definitely doesn't live yet.
- **Build on the timeline:** mem-search + timeline as the retrieval layer feeding every script.
- **Give the skills a face:** the "Host's Memory" UI panel makes memory visible and searchable.
And it passes their meta-criterion — *something someone would actually use* — because memory is what turns one-shot summaries into a show with continuity: "fourth agent framework this month wrapping the same SDK; the one we covered in July had stubbed auth — these folks actually built theirs."

---

## 3. Feature spec (ruthlessly scoped: 3 features, nothing else)

### F1 — The Broadcast (must-ship)
1. Trending picker selects today's repo by star velocity (see §5.1).
2. Greptile indexes it and answers the 5-query interrogation battery (§5.2).
3. Qwen on Modal writes a 3–5 min radio script: cold open → what it claims → what the code says → most interesting file → verdict. Output is segmented with citations (§5.3).
4. Kokoro on Modal voices each segment; per-segment durations build the sync timeline (§5.4).
5. Episode JSON + MP3 + updated RSS land in S3, served via CloudFront (§5.5).
6. Web player plays the episode with karaoke-synced transcript + cited-code highlighting (§7).

**Acceptance:** paste nothing, click nothing — today's episode is on the page, plays, verdict badge shows, code panel follows the audio.

### F2 — Wallet + Call-in (must-ship)
1. "Add funds" → Stripe Checkout, tiers: **$5 → 45 cr · $10 → 100 cr · $20 → 220 cr** (bigger top-ups earn bonus credits — the Starbucks tilt).
2. `checkout.session.completed` webhook credits the wallet in DynamoDB.
3. "Ask the host" costs **1 credit (=10¢)**: atomic decrement → Greptile query → Qwen writes a 15–25s answer segment → Kokoro voices it → it plays on air with its citations highlighted.
4. Zero balance flips the ask box into the top-up flow.

**Acceptance:** a judge tops up with test card `4242 4242 4242 4242`, balance animates to 100, asks a question, balance ticks to 99, answer plays with code highlighted — under 60 seconds end to end.

### F3 — Host's Memory via claude-mem (ship if ≥45 min remain after F1+F2 integration checkpoint)
1. After every episode: write observations (repo, claims checked, verdict, cited files, stars at airtime, category tags).
2. Before every script: mem-search for prior coverage of the repo / author / category; inject a `memory_digest` into the script prompt → "previously on" lines and verdict-upgrade callbacks.
3. UI: "Host's Memory" sidebar panel — timeline of remembered facts per episode.

**Acceptance:** generate episode 2 about a related repo; the script demonstrably references episode 1's findings; the memory panel shows the timeline.

**Graceful degradation:** if claude-mem integration stalls past its timebox, fall back to a plain `memory.json` in S3 (append findings, prepend to prompt) — the *product feature* survives, and claude-mem remains the named architecture in the pitch with the working panel as UI. (Only claim what actually runs.)

### Non-goals (do not build tomorrow)
No accounts/auth beyond an email field + localStorage token. No mobile polish beyond "stacks cleanly." No starred-repo personalization (roadmap slide). No Spotify/Apple submission (RSS exists; submission is roadmap). No comments/social. No admin UI — pipeline runs from CLI.

---

## 4. System architecture

```
┌─────────────── GENERATION (batch, runs on laptop — deliberate, see note) ───────────────┐
│  trending.py ──► Greptile API ──► Modal /script (Qwen-vLLM) ──► Modal /tts (Kokoro)     │
│      │               ▲   │              ▲                             │                 │
│      │               │   └── citations ─┤                             │                 │
│      │        GitHub PAT                │◄── memory_digest ── claude-mem worker (local) │
│      │                                  │                        ▲                      │
│      └── GitHub Search API              └── observations ────────┘                      │
│                                                                                         │
│  assemble.py ──► S3: /episodes/ep-NNN.json  /audio/ep-NNN.mp3  /feed.xml  memory.json   │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────── SERVING (AWS) ───────────────────────────┐
│  CloudFront ──► S3 static: index.html + episode JSON + MP3 + RSS    │
│  App Runner: FastAPI                                                │
│    POST /api/topup            ──► Stripe Checkout session           │
│    POST /api/stripe/webhook   ◄── checkout.session.completed        │
│    GET  /api/wallet/{uid}     ──► DynamoDB `wallets`                │
│    POST /api/ask              ──► debit → Greptile → Modal → S3     │
│    GET  /api/ask/{job_id}     ──► answer segment JSON (poll)        │
└─────────────────────────────────────────────────────────────────────┘

Frontend: ONE static index.html (Tailwind CDN + wavesurfer.js + Shiki + Lucide)
```

**Why generation runs on the laptop:** it's a batch job; claude-mem's worker (SQLite + Chroma) lives happily on local disk; zero deploy risk; and the demo never depends on a cloud cron. Honest framing for judges: "generation is a batch pipeline — today it runs from my machine, in production it's a scheduled Modal cron." The *serving* path (site, wallet, ask flow) is fully on AWS.

---

## 5. Integration specs

### 5.1 Trending picker (GitHub API)
- GitHub Search: `GET /search/repositories?q=topic:ai+topic:agents+created:>2026-07-01&sort=stars&order=desc` plus a curated watchlist file `watchlist.json` (8–12 currently-hot repos hand-picked tonight).
- Velocity: sample `stargazers_count` at t0 and t0+30min during the hack (or use tonight's samples) → `velocity = Δstars / Δhours`. Highest velocity wins. **Pragmatism rule:** the watchlist is the real source tomorrow; the search API is the "algorithm" story. Curate candidates that make great radio (a hyped wrapper, a genuinely good tool, something funny).
- Auth: fine-grained GitHub PAT (public repo read). Also passed to Greptile as `X-GitHub-Token`.

### 5.2 Greptile (docs.greptile.com/api-reference)
Headers on every call: `Authorization: Bearer $GREPTILE_API_KEY` + `X-GitHub-Token: $GITHUB_PAT`.

**Index** (do this the moment hacking starts — indexing takes minutes on big repos):
```
POST https://api.greptile.com/v2/repositories
{ "remote": "github", "repository": "owner/name", "branch": "main" }
```
Poll `GET /repositories/{id}` until status is ready. Pre-index the whole watchlist at 1:05pm.

**Interrogation battery** — 5 calls to `POST /query`, each `{ "messages": [{"role":"user","content": Q}], "repositories": [{"remote":"github","repository":"owner/name","branch":"main"}], "genius": true }`:
1. "In 3 sentences: what does this repo actually do, architecturally? Name the 2–3 core modules and what each owns."
2. "Is the core functionality implemented in this codebase, or mostly delegated to external APIs/SDKs? Name the specific files that prove it."
3. "List claims the README makes that are NOT fully supported by the code (stubbed, TODO, missing). Cite files and lines."
4. "What is the single most technically interesting or novel file/function here, and why? Cite it."
5. "What are the sketchiest parts — untested, TODO-ridden, hardcoded, or security-questionable? Cite files and lines."

Each response includes an answer + `sources` (file paths + line ranges) → these flow into the script prompt AND the episode JSON citations. `genius: true` is slower but smarter — use it for the battery; use `genius: false` for live call-in answers (latency matters there).

### 5.3 Modal app #1 — scriptwriter (open LLM)
- Model: **Qwen2.5-7B-Instruct** served with vLLM on an A10G/L4, `keep_warm=1` from 4:30pm (judging) onward; also warm at checkpoints.
- Endpoint: `POST /script` → body `{ repo_meta, greptile_findings[5], memory_digest }` → returns strict JSON:
```json
{ "title": "…", "verdict": "HYPE|REAL|MIXED",
  "segments": [ { "text": "…", "citation": {"file":"core/loop.py","start_line":41,"end_line":68} | null } ] }
```
- Prompt persona (bake into the system prompt): late-night FM host — sharp, warm, a little wry; never cruel; every factual claim must trace to a Greptile finding; 3–5 min read length; open with a hook, end with the verdict. Include 1 "previously on" callback when memory_digest is non-empty.
- Enforce JSON with guided decoding / retry-on-parse-fail (max 2 retries).

### 5.4 Modal app #2 — voice (open TTS)
- Model: **Kokoro-82M** (hexgrad/Kokoro-82M). GPU (T4 is plenty) for speed; CPU works as emergency fallback.
- Endpoint: `POST /tts` → `{ segments: ["text", …] }` → returns per-segment WAV/MP3 (base64) + `duration_s` each.
- **Critical detail:** synthesize per segment and record each duration → cumulative sums are the `start`/`end` timestamps that drive karaoke sync. Concatenate with ~0.35s silence gaps (count the gaps in the timeline!). Assemble to one MP3 with ffmpeg/pydub.
- Voice: pick one Kokoro voice tonight and hard-code it (am_michael or af_bella class of voices — test both, choose the more "FM host").

### 5.5 AWS
- **S3 bucket** (e.g. `repo-radio-live`): `/index.html`, `/episodes/ep-NNN.json`, `/audio/ep-NNN.mp3`, `/feed.xml`, `/memory.json`, `/covers/…`. **CORS: allow GET from the CloudFront origin** (wavesurfer fetches + decodes audio — without CORS the waveform breaks; fallback is pre-computed peaks in episode JSON).
- **CloudFront** distro in front of the bucket (default root `index.html`). Short TTL (60s) or invalidate on publish.
- **DynamoDB** table `wallets`: PK `user_id` (S). Attributes: `credits` (N), `ledger` (L of {ts, type, amount, ref}). Debit = `UpdateExpression: SET credits = credits - :one` with `ConditionExpression: credits >= :one` — atomic, no race.
- **App Runner** service running the FastAPI container (Dockerfile, port 8080). Env vars: all keys. Fallback if App Runner fights you (>30 min): run FastAPI on the laptop + one Lambda Function URL for the Stripe webhook, or `stripe listen --forward-to localhost` (§ RACEDAY risks).
- **RSS** `feed.xml`: valid podcast RSS 2.0 with `<enclosure url=".../audio/ep-NNN.mp3" type="audio/mpeg">` per episode. This is the "AWS *is* the podcast infrastructure" line — a podcast is XML + MP3s on a CDN.

### 5.6 Stripe (test mode all day)
- `POST /api/topup {user_id, tier}` → create Checkout Session, `line_items` = the tier price, `metadata: {user_id, credits}` → return session URL.
- Webhook `checkout.session.completed` (verify signature with `STRIPE_WEBHOOK_SECRET`) → read metadata → increment DynamoDB credits + ledger entry.
- Frontend polls `GET /api/wallet/{uid}` after Checkout redirect; animate the balance count-up.
- Demo card: `4242 4242 4242 4242`, any future date, any CVC.
- **Pitch line:** "One dollar per question kills curiosity; ten cents feels free while the wallet keeps money in the ecosystem. Starbucks holds ~$1.5–2B in unspent balances — the float is the business model."

### 5.7 claude-mem (github.com/thedotmack/claude-mem)
- Install locally tonight: `npx claude-mem install` (sets up worker service, SQLite + Chroma at `~/.claude-mem/`).
- Integration surface: the worker's HTTP API (search endpoints) + SDK. **Timebox: 20 min at hack time to confirm the exact write/search endpoints** (the repo + its skills docs are the source of truth); if the write path is awkward, drive it via the CLI/SDK from `pipeline/memory.py`.
- Write after each episode: one observation per finding (repo, claim, verdict, files, stars, category tags like `agent-framework`, `sdk-wrapper`).
- Read before each script: mem-search on repo name, author, and category tags → top-k results → `memory_digest` (plain text bullets) → into the Qwen prompt → also export to S3 `memory.json` for the UI panel and for the App Runner ask-flow (server can't reach the laptop's worker — it reads the S3 digest).
- Fallback (if timebox blows): `memory.json` append/read directly; keep the UI panel and the "previously on" behavior; pitch claude-mem as the memory layer **only if it's actually wired in** — otherwise present the feature as "host memory" and name claude-mem as the intended layer honestly.

### 5.8 Codex compliance (eligibility)
- Codex CLI is the primary coding agent for the entire build: `npm i -g @openai/codex`, auth with the $50 OpenAI credit link handed out at the event (API key mode).
- Every lane (see LANES.md) is a Codex session. Keep terminal scrollback, `codex` session logs, and granular commit history — that's the proof. Commits land with lane prefixes so the history reads as a Codex-driven build.
- Tonight's docs (this PRD, LANES.md, mock fixtures) are design artifacts — the code gets written tomorrow, by Codex, inside the window.

---

## 6. Data contracts (freeze at 1:20pm — changes after that require a cross-lane sync commit)

### 6.1 `episodes/ep-NNN.json`
```json
{
  "id": "ep-004",
  "date": "2026-08-24",
  "repo": { "full_name": "acme/hypetool", "url": "https://github.com/acme/hypetool",
            "language": "Python", "stars_at_airtime": 4210, "velocity_per_hr": 38 },
  "title": "HypeTool: 4,000 stars for a wrapper?",
  "verdict": "MIXED",
  "audio": { "url": "/audio/ep-004.mp3", "duration_s": 214, "peaks": [0.1, 0.4, "…"] },
  "segments": [
    { "i": 0, "start": 0.0,  "end": 14.2, "text": "cold open …", "citation": null },
    { "i": 1, "start": 14.2, "end": 32.6, "text": "…",
      "citation": { "file": "core/loop.py", "start_line": 41, "end_line": 68,
                    "code_html": "<pre class=\"shiki\">…pre-rendered…</pre>" } }
  ],
  "memory_refs": [ { "episode_id": "ep-001", "note": "Rival X had stubbed auth (July)" } ],
  "qa_segments": [ { "question": "Is the auth real?", "audio_url": "/audio/ep-004-qa-1.mp3",
                     "segments": [ "…same shape as above…" ] } ]
}
```
Notes: `peaks` = pre-computed waveform (wavesurfer renders instantly, CORS-proof). `code_html` = Shiki output pre-rendered at generation time (better architecture AND removes the CDN risk).

### 6.2 Wallet API (FastAPI, App Runner)
```
POST /api/topup            {user_id, tier: 5|10|20}        → {checkout_url}
POST /api/stripe/webhook   (Stripe signed)                 → 200
GET  /api/wallet/{user_id}                                 → {credits: int}
POST /api/ask              {user_id, episode_id, question} → 402 {error:"no_credits"} | {job_id}
GET  /api/ask/{job_id}                                     → {status:"pending"} | {status:"done", qa_segment: {…}}
```
`user_id` = lowercase email, stored in localStorage. CORS: allow the CloudFront origin.

### 6.3 Mock fixtures (committed at 1:05pm — every lane builds against these)
`fixtures/ep-000.json` (a complete fake episode, hand-written tonight from this schema, with a real 30s MP3 stub), `fixtures/wallet.json`, `fixtures/greptile_response.json`, `fixtures/script_response.json`. **The frontend must be 100% functional against fixtures alone.**

---

## 7. UI spec — one static page, premium feel

**Stack:** single `index.html`, vanilla JS modules, no build step. Tailwind v4 Play CDN (`https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4`), wavesurfer.js v7 (`https://cdn.jsdelivr.net/npm/wavesurfer.js@7/dist/wavesurfer.esm.js`), Shiki v4 only as fallback (code ships pre-rendered in episode JSON), Lucide icons (`https://unpkg.com/lucide@latest`). Deploy = `aws s3 cp`.

**Layout (desktop, max-w 1280, 12-col):**
- Top bar: "REPO RADIO" wordmark + frequency gag ("102.3 FM") · pulsing **ON AIR lamp** (red glow while playing, grey when paused) · wallet chip top-right ("◈ 100 credits").
- Hero (cols 1–8): repo name small in mono, episode title large in **Hedvig Letters Serif**, verdict badge, wavesurfer bar waveform (barWidth 3, gap 2, radius 3), play/time controls.
- Sidebar (cols 9–12): episode list (row = ep number, repo, verdict dot); "Host's Memory" timeline collapsed at bottom.
- Sync panel (cols 1–8, below hero): transcript left (active segment glows amber, auto-scrolls, click-to-seek), code card right (filename tab, pre-rendered highlighted code, cited lines get amber left border + subtle glow; card swaps when the active segment's citation changes).
- Footer strip: "☎ CALL THE SHOW" — question input + [ASK · 1 credit] button; flips to top-up tiers at zero balance.
- Mobile: stack everything; episode list becomes chip row. No further mobile work.

**Design language — "late-night FM booth meets terminal":**
- Background `#0A0A0F` with a subtle radial glow `#1A1025` behind the hero; cards `#12121A`, borders `#26263A`.
- Signature amber `#FFB020`: waveform progress, active transcript line, cited code lines, ON AIR glow states. Dim amber `#7A5A1E` for unplayed waveform.
- Text `#EDEDF2` / secondary `#8B8B9E`; sparing terminal-teal `#5EEAD4` for mono micro-labels.
- Verdict badges (uppercase mono, 1px border, letter-spaced): HYPE `#F43F5E` on `#2A0E14` · REAL `#34D399` on `#0B231A` · MIXED `#FBBF24` on `#261C08`.
- **Fonts (Google Fonts): "Hedvig Letters Serif" for titles/display** (single 400 weight — size and tight tracking do the work; it has an optical-size axis, use `opsz` 24 for the hero), **"Inter" (400/500/600) for all UI text**, **"JetBrains Mono" (400/500/700) strictly for code, timestamps, badges, and micro-labels**. Three faces, three jobs — don't let them bleed into each other.
- Signature element: the ON AIR lamp pill — red dot + "ON AIR" mono caps, `box-shadow: 0 0 12px 2px rgba(244,63,94,.6)`, 2s pulse keyframes tied to play state; hero radial glow brightens on play. Garnish: CSS-only 5-bar equalizer on the now-playing episode row (staggered scaleY animation, paused via `animation-play-state`). Optional 3%-opacity scanline overlay on body.

**Sync logic (hand-rolled, ~30 lines):** on `timeupdate`, find segment where `start ≤ t < end` → toggle `.active`, `scrollIntoView({block:'center', behavior:'smooth'})`; if citation changed → swap code card + highlight lines. Pause auto-scroll for 3s after any manual wheel event. Pad segment windows ±0.5s. Segments are click-to-seek (turns any timestamp drift into a driveable feature).

**UI risk fallbacks:** waveform → pre-computed peaks (already in contract) → hidden `<audio controls>` + equalizer bars. Code highlighting → pre-rendered `code_html` (already in contract) → plain `<pre>` in JetBrains Mono with amber-highlighted lines.

---

## 8. Pricing & business

Wallet tiers: $5 → 45 cr · $10 → 100 cr · $20 → 220 cr. 1 question = 1 credit = 10¢.
Marginal cost per question ≈ one Greptile query (cents) + ~10–20s GPU on Modal (~1–2¢) → roughly break-even to slightly positive at 10¢, priced to make asking feel free. Revenue thesis = wallet float + volume (Starbucks model). Roadmap slide: starred-repo personal feeds ($9/mo), team/standup edition, Spotify/Apple distribution via the RSS that already exists, sponsor-read slots ("this hype-check brought to you by…").

---

## 9. Definition of done (5:00pm)

1. CloudFront URL loads the page; today's real episode plays with working karaoke sync and code highlighting.
2. Stripe test top-up → credits appear; ask → credit debits → spoken answer plays with citations. Full loop < 60s.
3. At least 2 baked episodes (1 primary + 1 about a related repo proving the memory callback), RSS validates.
4. Memory panel renders from memory.json; claude-mem worker demonstrably wrote/read it (screenshot the worker UI as backup evidence).
5. A cached full demo path works with zero network beyond CloudFront (and a local copy as final fallback).
6. Codex session logs + commit history exportable; pitch rehearsed 3×.
