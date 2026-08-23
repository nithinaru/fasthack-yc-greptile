# HANDOFF.md — everything Claude Code needs to build Repo Radio today

Read order for the humans and agents involved: this file → REPO_RADIO_PRD.md (full spec) → LANES.md (who builds what, git protocol, prompts).

---

## 1. What we're building (context in four sentences)

Repo Radio is a daily AI-generated podcast that reads the source code of GitHub's fastest-trending repos and calls **HYPE / REAL / MIXED** — Greptile interrogates the code with citations, Qwen (vLLM on Modal) writes the radio script, Kokoro-82M (Modal) voices it, and S3/CloudFront serves the page, audio, and RSS (a podcast is just XML on a CDN). The signature interaction: as the host speaks, the cited files highlight on screen karaoke-style, proving every claim traces to real code. Listeners hold a Starbucks-style Stripe wallet ($5→45cr, $10→100cr, $20→220cr; 1 question = 1 credit = 10¢) and spend credits to ask the host questions, answered on air. The host has long-term memory of every codebase it has covered (claude-mem), enabling "previously on" callbacks and verdict upgrades — also a separate $1,000 prize track at the event.

Sponsor map (all load-bearing): Greptile = brain · Modal = writer+voice (open models) · AWS = distribution+wallet store · Stripe = wallet · OpenAI Codex = required primary coding agent *at the event* · DoorDash = lunch.

**Eligibility note, in one line:** the hackathon requires OpenAI Codex to play a meaningful role in building the project — whatever is built before the event, plan real, demonstrable Codex work during tomorrow's window (features, fixes, deploys) and keep its logs and commits.

## 2. Environment checklist (before Lane 0)

Keys/accounts → `.env` (gitignored; commit `.env.example` with blank values):
```
GREPTILE_API_KEY=        # app.greptile.com
GITHUB_TOKEN=            # fine-grained PAT, public-repo read (also sent to Greptile as X-GitHub-Token)
AWS_REGION=us-west-2     # aws configure done separately; IAM needs S3, CloudFront, DynamoDB, App Runner
S3_BUCKET=repo-radio-live
STRIPE_SECRET_KEY=       # TEST mode
STRIPE_WEBHOOK_SECRET=   # from `stripe listen` or dashboard endpoint
MODAL_SCRIPT_URL=        # filled by Lane B via ENDPOINTS.md
MODAL_TTS_URL=           # filled by Lane B
USE_MOCKS=1              # flip to 0 per-integration as they go live
```
Local tools: Python 3.11 venv · node ≥ 20 · ffmpeg · `pip install modal` + `modal setup` · Stripe CLI · `npx claude-mem install` (worker running) · AWS CLI configured.

Also prepare `pipeline/watchlist.json`: 8–12 currently-trending AI/dev-tool repos with today's star counts (pick: one hyped wrapper, one genuinely solid tool, one funny one). This is both the trending algorithm's candidate pool and your demo-repo shortlist. **Pre-index the whole list in Greptile the moment you have API credits — indexing takes minutes per repo.**

## 3. Kickoff prompt for the first Claude Code session (Lane 0)

> Read HANDOFF.md, REPO_RADIO_PRD.md, and LANES.md in this directory. Execute Lane 0 exactly: initialize the git repo (repo-radio, single branch main); write CLAUDE.md from the template in LANES.md; transcribe PRD §6 into contracts/episode.schema.json and contracts/wallet_api.md; build fixtures/ep-000.json from the sample episode in HANDOFF.md §4, including fake cited source files under fixtures/src/ and pre-rendered code_html (one span per line, cited lines get class "cited"), with a placeholder MP3; write fixtures/greptile_response.json, script_response.json, wallet.json; write the Makefile (smoke, deploy-web, bake-episode targets) and .env.example; generate the AWS CLI commands for the S3 bucket + CloudFront distro + DynamoDB wallets table and wait for me to run/approve them; upload fixtures and verify the CloudFront URL serves ep-000.json. Commit and push after every step. When done, print the four lane prompts from LANES.md for me to paste into four new sessions.

## 4. Fixture episode ep-000 — sample script (use verbatim)

Fictional repo `cavemanlabs/caveman` ("autonomous agent runtime — memory, tools, scheduling"), verdict **MIXED**. Segments (citation → fake file in `fixtures/src/`):

1. *(no citation)* "It's 11:47 PM in San Francisco, and GitHub's hottest new repo just crossed four thousand stars. This is Repo Radio — I read the code so you don't have to."
2. *(no citation)* "Tonight's subject: Caveman. The README promises a full autonomous agent runtime — memory, tools, scheduling, the works. Four thousand stars in three days. Let's see what's actually in the cave."
3. *(core/agent.py, lines 12–38)* "Crack open core/agent.py and the skeleton is clean: an Agent class, a tool registry, a run loop. Credit where due — this is readable code."
4. *(llm/client.py, lines 8–24)* "But here in llm/client.py? The 'proprietary reasoning engine' is forty lines wrapping someone else's chat API. That's not a reasoning engine, folks. That's a phone call."
5. *(core/scheduler.py, lines 51–88)* "Now, the plot twist. The scheduler is legitimately clever — priority queues with decay, so stale tasks lose their place in line. I haven't seen that pattern in the other frameworks. This is the part worth stealing."
6. *(memory/store.py, lines 3–9)* "And the 'long-term memory' the README brags about? Six lines. A dictionary. And a TODO that says, quote, 'make this persistent.' The cave paintings were more durable."
7. *(no citation)* "So: verdict MIXED. Real craftsmanship in the scheduler, marketing everywhere else. Star it for the scheduler. Don't bet your startup on the memory."
8. *(no citation)* "That's the broadcast. Wallet's open if you've got questions — ten cents, answered on air. Repo Radio: we read the code so you don't have to. Stay curious."

Lane A's first live TTS run should replace the placeholder MP3 with real Kokoro audio of this script (also your voice-casting test).

## 5. The 90-second demo (for judging — memorize the beats)

1. **Hit play before you speak.** ON AIR lamp ignites, host's voice fills the table. Then: "This is Repo Radio — the podcast that reads the source code of trending repos so you don't have to."
2. **The sync moment.** Let a claim land while the cited file highlights; click a transcript line to seek. "Fact-checked against the source by Greptile. Script by Qwen, voice by Kokoro — self-hosted on Modal. The feed is S3 + CloudFront — a podcast is just XML on a CDN, so AWS is our distribution."
3. **Money loop — hand the judge the laptop.** $10 top-up (test card 4242 4242 4242 4242) → 100 credits → they ask a question → 99 → the host answers on air, code highlighting along. "Ten cents a question — a dollar kills curiosity, ten cents feels free, and the wallet float is the Starbucks model."
4. **Memory.** Open the Host's Memory panel. "It remembers every codebase it's covered — claude-mem underneath. Episode 2 caught that this framework's rival had stubbed auth. Longitudinal code journalism."
5. **Close.** "Repo Radio — we read the code so you don't have to."

Rules: always demo the cached episode; live generation is the encore if a judge asks. Rehearse once with wifi off (local static server + local MP3/JSON).

## 6. Fallbacks already designed in (don't improvise new ones)

Waveform/CORS → `peaks` ship inside episode JSON. Code highlighting → `code_html` pre-rendered at generation time. Modal cold starts → keep_warm before demo windows. LLM JSON drift → guided decoding + 2 retries + last-good cache. App Runner/webhook trouble → Lane D6 local FastAPI + cloudflared + Stripe CLI forward. claude-mem stalls (20-min timebox) → S3 memory.json, feature survives, claim only what runs. Behind schedule → LANES.md cut order, no debate.
