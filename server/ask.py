"""Ask-the-host flow (PRD §3.4/§3.5). The wallet debit happens in app.py before
a job is created; this module only builds the answer.

Mock mode (USE_MOCKS=1): the job completes after a short simulated delay with a
canned qa_segment built from fixtures/ep-000.json — a real citation with real
code_html and the fixture MP3 as audio, so the frontend can render + play the
full loop with no backend dependencies.

Live mode (USE_MOCKS=0): Greptile (genius:false) -> Modal /script (mode:
"answer") -> Modal /tts -> publish qa_segment onto the served static dir.
Guards clean errors if URLs/keys are missing rather than crashing weirdly.
"""
import json
import logging
import os
import threading
import time
import uuid

import settings

log = logging.getLogger("server.ask")

# Job store. In-memory locally; on Modal (MODAL_TASK_ID set) a shared
# modal.Dict, because the status poll can land on a different container than
# the one running the job (same cross-container issue as the wallet).
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

_jobs_dict = None


def _get_jobs_dict():
    global _jobs_dict
    if _jobs_dict is not None:
        return _jobs_dict
    if not os.environ.get("MODAL_TASK_ID"):
        return None
    with _jobs_lock:
        if _jobs_dict is None:
            import modal

            _jobs_dict = modal.Dict.from_name("repo-radio-jobs", create_if_missing=True)
            log.info("job store: modal.Dict 'repo-radio-jobs'")
    return _jobs_dict


def _store_set(job_id: str, job: dict) -> None:
    d = _get_jobs_dict()
    if d is not None:
        d[job_id] = job
    else:
        with _jobs_lock:
            _jobs[job_id] = job

MOCK_DELAY_S = 1.5


def _mock_qa_segment(question: str) -> dict:
    """qa_segments[] item shape from contracts/episode.schema.json, built from
    the ep-000 fixture so the citation/code_html/audio are all real assets."""
    citation = None
    audio_url = "/audio/ep-000.mp3"
    try:
        ep = json.loads((settings.FIXTURES_DIR / "ep-000.json").read_text())
        audio_url = ep["audio"]["url"]
        citation = next(
            (s["citation"] for s in ep["segments"] if s["citation"]), None
        )
    except (OSError, KeyError, json.JSONDecodeError) as e:
        log.warning("could not build mock qa from ep-000 fixture: %s", e)
    text = (
        "Good question. I went back to the source: the scheduler in "
        "core/scheduler.py really does implement priority decay — that part "
        "of the README holds up. The memory story is still six lines and a "
        "TODO, so don't build on that yet."
    )
    return {
        "question": question,
        "audio_url": audio_url,
        "segments": [
            {"i": 0, "start": 0.0, "end": 12.0, "text": text, "citation": citation}
        ],
    }


def create_job(user_id: str, episode_id: str, question: str) -> str:
    job_id = f"job-{uuid.uuid4().hex[:12]}"
    _store_set(job_id, {
        "status": "pending",
        "user_id": user_id,
        "episode_id": episode_id,
        "question": question,
        "created": time.time(),
    })
    return job_id


def get_job(job_id: str) -> dict | None:
    d = _get_jobs_dict()
    if d is not None:
        return d.get(job_id)
    with _jobs_lock:
        return _jobs.get(job_id)


def run_job(job_id: str) -> None:
    """Executed as a FastAPI background task after the debit succeeded."""
    job = get_job(job_id)
    if job is None:
        return
    try:
        if settings.USE_MOCKS:
            time.sleep(MOCK_DELAY_S)  # simulate script+tts latency for the UI
            qa = _mock_qa_segment(job["question"])
        else:
            qa = _live_answer(job)
        job["status"] = "done"
        job["qa_segment"] = qa
        _store_set(job_id, job)
    except Exception as e:
        log.exception("ask job %s failed", job_id)
        job["status"] = "error"
        job["error"] = str(e)
        _store_set(job_id, job)


def _post_json(url: str, body: dict, timeout: float = 120.0) -> dict:
    import httpx

    resp = httpx.post(url, json=body, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _load_episode(episode_id: str) -> dict:
    """Episode JSON from the served static dir (live source of truth), with
    fixtures as a fallback so the flow still works right after a fresh deploy
    with only ep-000 baked."""
    published = settings.DATA_DIR / "episodes" / f"{episode_id}.json"
    if published.exists():
        return json.loads(published.read_text())
    fixture = settings.FIXTURES_DIR / f"{episode_id}.json"
    if fixture.exists():
        log.warning("episode %s not published yet; using fixture", episode_id)
        return json.loads(fixture.read_text())
    raise FileNotFoundError(f"episode {episode_id} not found in {settings.DATA_DIR} or fixtures")


def _assemble_wav(tts_segments: list[dict], gap_s: float = 0.35) -> tuple[bytes, list[float]]:
    """Concatenate per-segment WAVs with silence gaps (stdlib only).
    Returns (wav_bytes, cumulative start offsets per segment)."""
    import base64
    import io
    import wave

    frames, starts = [], []
    params = None
    t = 0.0
    for i, seg in enumerate(tts_segments):
        with wave.open(io.BytesIO(base64.b64decode(seg["audio_b64"])), "rb") as w:
            if params is None:
                params = w.getparams()
            starts.append(t)
            data = w.readframes(w.getnframes())
            t += w.getnframes() / w.getframerate()
        frames.append(data)
        if i < len(tts_segments) - 1:
            gap_frames = int(gap_s * params.framerate)
            frames.append(b"\x00" * gap_frames * params.sampwidth * params.nchannels)
            t += gap_s
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setparams(params)
        w.writeframes(b"".join(frames))
    return out.getvalue(), starts


def _live_answer(job: dict) -> dict:
    """Live path: Greptile (genius:false) -> Modal /script (mode:"answer") ->
    Modal /tts -> assemble WAV -> publish onto the served static dir. Needs
    MODAL_SCRIPT_URL / MODAL_TTS_URL and Greptile/GitHub keys in the environment."""
    import qa_render
    from pipeline import greptile  # the one sanctioned cross-module import

    if not settings.MODAL_SCRIPT_URL or not settings.MODAL_TTS_URL:
        raise RuntimeError(
            "MODAL_SCRIPT_URL / MODAL_TTS_URL unset — deploy modal_apps/script.py "
            "and modal_apps/tts.py and set their URLs in .env"
        )
    if not settings.GREPTILE_API_KEY or not settings.GITHUB_TOKEN:
        raise RuntimeError("GREPTILE_API_KEY / GITHUB_TOKEN unset — cannot answer live questions")

    episode = _load_episode(job["episode_id"])
    repo = episode["repo"]["full_name"]

    finding = greptile.query(repo, job["question"], genius=False)

    script = _post_json(settings.MODAL_SCRIPT_URL, {
        "mode": "answer",
        "question": job["question"],
        "repo_meta": episode["repo"],
        "greptile_findings": [finding],
        "verdict": episode.get("verdict", "MIXED"),
    })

    texts = [s["text"] for s in script["segments"]]
    tts = _post_json(settings.MODAL_TTS_URL, {"segments": texts})
    wav_bytes, starts = _assemble_wav(tts["segments"])
    durations = [s["duration_s"] for s in tts["segments"]]

    audio_dir = settings.DATA_DIR / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{job['episode_id']}-qa-{uuid.uuid4().hex[:8]}.wav"
    (audio_dir / filename).write_bytes(wav_bytes)

    segments = []
    for i, s in enumerate(script["segments"]):
        citation = None
        if s.get("citation"):
            citation = qa_render.render_citation(repo, s["citation"])
        segments.append({
            "i": i,
            "start": round(starts[i], 3),
            "end": round(starts[i] + durations[i], 3),
            "text": s["text"],
            "citation": citation,
        })
    return {"question": job["question"], "audio_url": f"/audio/{filename}", "segments": segments}
