# Repo Radio — agent instructions (fasthack-yc-greptile)

You are the single build agent for this project. There are no parallel lanes — you work milestone by milestone per BUILD_PLAN.md, using subagents for independent chunks when it genuinely speeds things up.

Read first, in order: PRD.md (what we're building, integration specs, data contracts, UI spec) → BUILD_PLAN.md (build order, gates, cut list).

Rules:
- Data contracts in PRD §5 are frozen. Code conforms to them; never improvise a schema change — ask the human.
- Mock-first: every milestone must work with USE_MOCKS=1 against fixtures/ before flipping any live API. Keys live in .env (gitignored; keep .env.example current).
- Commit and push at each completed milestone (and at most one mid-milestone push if it runs long). Scope adds: `git add <paths>`, never `git add -A`. Message format: `M<n>: <what>`.
- Never push broken: `make smoke` (fixtures validate, imports work, web serves) before every push.
- Stack: Python 3.11, FastAPI, Modal for ALL hosting (models + API + static). Frontend is ONE static web/index.html, no build step, Tailwind v4 CDN, wavesurfer.js v7. Fonts: Hedvig Letters Serif (display) / Inter (UI) / JetBrains Mono (code only).
- This is a 4-hour hackathon build. Working and demoable beats elegant. When a choice costs >10 minutes, pick the simpler path and note the tradeoff in a comment.
- Time gates and the cut order in BUILD_PLAN.md are law — if a gate slips, execute the cut, don't negotiate with it.
