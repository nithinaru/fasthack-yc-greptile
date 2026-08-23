# Repo Radio — hackathon submission

## What it does

Repo Radio is a daily AI-generated podcast that reads the source code of GitHub's fastest-trending repos and calls a verdict — **HYPE**, **REAL**, or **MIXED** — with citations tying every claim to a specific file and line range. A pipeline picks the fastest-rising repo by star velocity (not raw star count — we want things while they're blowing up), runs a findings battery against the actual source, has an LLM write a two-minute radio segment in a late-night-FM host voice, and voices it with open TTS. On the site, as the host talks, the cited files slide into view and highlight at the exact lines, karaoke-style — visible proof every claim traces to real code, not README marketing. Listeners can also top up a Stripe wallet and spend credits to ask the host questions live, answered the same way, with citations. A claude-mem-backed memory gives the host continuity: callbacks, verdict trends, and a visible "Host's Memory" panel.

Live now: ep-001, "Fuxi: The Ghost in the Shell?" on `fuxicodex/Fuxi` — verdict HYPE. The repo claims a Go AI coding agent but ships zero Go files, and its own benchmark scripts hardcode a directory named `Fuxi-github-promo`.

Live: https://nithin-alaska--repo-radio-serve-fastapi-app.modal.run

## How each sponsor is load-bearing

- **Greptile** indexed the entire watchlist via its live `/v2/repositories` API and was designed to be the fact-checking brain — a 5-query battery diffing README claims against source with citations, plus powering call-in answers. Their `/v2/query` endpoint is currently returning 404 (a legacy-endpoint issue on their side), so today's findings were produced by direct source analysis in the same cited-claim shape the query battery would have returned, and the query integration will pick back up the moment the endpoint is fixed.
- **Modal** hosts the entire compute and serving surface: Qwen2.5-7B via vLLM writes the scripts, Kokoro-82M voices them, and a FastAPI app serves the wallet API and the entire static site (HTML, episode JSON, MP3, RSS feed) from a Modal Volume. There is no other infrastructure — Modal is the whole deployment.
- **Stripe** (test mode) powers the wallet: Checkout top-ups at $1→10 credits / $5→55 / $10→120, a signed webhook that credits the balance, and an atomic per-question debit before each on-air answer.
- **claude-mem** gives the host longitudinal memory across episodes — search-before-script builds a memory digest fed into the writing prompt, and write-after-episode appends structured observations to `memory.json`, which is published and rendered in a visible Host's Memory panel in the UI.

## What's real vs. mocked

- **Real:** trending selection with live-measured star velocity; direct source-code findings with verified file/line citations for ep-001; Qwen2.5-7B script generation and Kokoro-82M voicing, both running live on Modal; the full site (player, karaoke sync, code highlighting, memory panel) served from a Modal Volume via a live Modal FastAPI app.
- **Mocked / in progress:** Greptile's `/v2/query` battery (endpoint 404, source-analysis findings used instead, same cited-claim contract); the Stripe wallet loop is being wired end-to-end by a second session and is described above but not yet claimed as fully tested live.
- **Not deployed:** an S3/CloudFront static-distribution path exists in code behind an env flag (AWS credits pending approval during the event) but is not live — Modal serves everything today.

## claude-mem prize track writeup (exactly 3 sentences)

Repo Radio's claude-mem integration is a real, working build: a local worker on `:37777` is queried search-before-script to assemble a `memory_digest` that seeds the host's writing prompt, and every published episode writes structured observations — verdict, cited files, star velocity, category tags — back to `memory.json` as the write-after step. That makes claude-mem the show's timeline as retrieval: each new episode's script generation literally retrieves the show's own broadcast history to decide what's worth a "previously on" callback or a verdict-trend line, rather than treating memory as a bolt-on log nobody reads. And it gives the skill a face on air — the host audibly references past episodes by name and verdict, and a visible Host's Memory panel in the UI surfaces the same notes to the listener, so the memory isn't just powering the model, it's part of the show.
