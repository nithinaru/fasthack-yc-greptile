# Repo Radio — agent instructions
Read contracts/ and fixtures/ FIRST. They are frozen; code conforms to them, never the reverse.
Each session owns exactly ONE directory (pipeline/ | modal_apps/ | web/ | server/). Never edit outside your lane. contracts/, fixtures/, Makefile changes require the human's SYNC approval.
After every completed subtask: make smoke, then git add -A && git commit -m "<lane>: <what>" && git pull --rebase && git push. Small commits, high frequency.
Stack: Python 3.11, FastAPI, boto3. Frontend is ONE static web/index.html, no build step, Tailwind v4 CDN, wavesurfer.js v7, fonts: Hedvig Letters Serif (display) / Inter (UI) / JetBrains Mono (code).
Mock-first: everything must run against fixtures/ with USE_MOCKS=1 before touching live APIs. Live keys are in .env.
Full spec: REPO_RADIO_PRD.md (§5 integrations, §6 contracts, §7 UI). Lane briefs: LANES.md.
When blocked on a contract ambiguity, ASK the human — do not improvise a schema change.
