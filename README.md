# Repo Radio

> **We read the code so you don't have to.**

[![Live demo](https://img.shields.io/badge/listen-live-7C3AED?style=for-the-badge)](https://nithin-alaska--repo-radio-serve-fastapi-app.modal.run)
[![Modal](https://img.shields.io/badge/runs%20on-Modal-7C3AED?style=for-the-badge)](https://modal.com)
[![Status](https://img.shields.io/badge/status-hackathon%20build-22C55E?style=for-the-badge)](#run-it)

**Repo Radio** is a daily AI podcast for the repos blowing up on GitHub. Instead of repeating the README, it inspects the source, turns its findings into a short radio segment, and gives every episode a verdict:

| Verdict | Meaning |
| :-- | :-- |
| ![HYPE](https://img.shields.io/badge/HYPE-ef4444?style=flat-square) | The claims outrun the code. |
| ![REAL](https://img.shields.io/badge/REAL-22c55e?style=flat-square) | The implementation earns the attention. |
| ![MIXED](https://img.shields.io/badge/MIXED-f59e0b?style=flat-square) | Promising, with important caveats. |

**The proof is part of the show.** As the host speaks, the player follows the transcript and opens the cited file at the exact line range—so every claim can be checked in context.

## Listen to it

**[Open the live player →](https://nithin-alaska--repo-radio-serve-fastapi-app.modal.run)**

Try the latest episode, **“Phone Harness: Driving Phones with Python,”** on [`ShawnPana/phone-harness`](https://github.com/ShawnPana/phone-harness): **REAL**.

## How it works

```text
GitHub momentum → source-code findings → scripted episode → voiced audio → cited, synced player
                                  ↘ listener question → credited on-air answer
```

- **Picks momentum, not popularity:** ranks repos by star velocity so the show covers a project while the conversation is happening.
- **Makes claims auditable:** findings carry file and line citations; the UI turns them into synchronized code highlights.
- **Sounds like a show:** Qwen writes the segment; Kokoro voices it; the generated timeline drives the transcript and waveform.
- **Remembers the arc:** host memory connects a new repo with past episodes and verdict trends.
- **Invites the audience in:** a Stripe credit wallet lets listeners call in a question and receive a cited response on air.

## Built with

| What | Stack |
| :-- | :-- |
| Compute, models, deployment | **Modal** · Qwen2.5-7B/vLLM · Kokoro-82M |
| Evidence and discovery | **GitHub** · **Greptile** |
| Product | **FastAPI** · static web player · **Stripe** wallet |
| Continuity | **claude-mem** |

## Run it

The default setup is deterministic and offline-friendly: `USE_MOCKS=1` uses the fixtures and makes no paid or live API calls.

```bash
make smoke                         # validate the build
make serve-local                   # open http://localhost:8080
make bake-episode REPO=owner/name  # create an episode
```

To publish the Modal services, configure the variables in [`.env.example`](.env.example) and run:

```bash
make publish
```

## Project map

| Directory | Purpose |
| :-- | :-- |
| [`pipeline/`](pipeline) | Research, script, voice, citation, and publishing stages |
| [`modal_apps/`](modal_apps) | Modal deployments for script, TTS, and serving |
| [`server/`](server) | FastAPI, wallet, Stripe webhook, and call-in flow |
| [`web/`](web) | Player, episode data, audio, transcript sync, and code cards |
| [`contracts/`](contracts) | Episode and wallet contracts |

## Contributors

Built by [Nithin Arus](https://github.com/nithinaru) with [OpenAI Codex](https://openai.com/codex).

---

*Repo Radio turns the GitHub hype cycle into a show you can verify.*
