"""Ask-the-host flow (contracts/wallet_api.md): debit 1 credit → answer job.

Mock mode (USE_MOCKS=1): the job completes immediately with a canned qa_segment
built from fixtures/ep-000.json — a real citation with real code_html and the
fixture MP3 as audio, so Lane C can render + play the full loop with no backend
dependencies. Live mode (D4): Greptile (genius:false) → Modal /script (answer
mode) → Modal /tts → S3, filled in when ENDPOINTS.md lands.
"""
import json
import logging
import threading
import uuid

import settings

log = logging.getLogger("server.ask")

# In-memory job store (PRD sanctions this; App Runner runs a single container).
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


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
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "pending",
            "user_id": user_id,
            "episode_id": episode_id,
            "question": question,
        }
    return job_id


def get_job(job_id: str) -> dict | None:
    with _jobs_lock:
        return _jobs.get(job_id)


def run_job(job_id: str) -> None:
    """Executed as a FastAPI background task after the debit succeeded."""
    job = get_job(job_id)
    if job is None:
        return
    try:
        if settings.USE_MOCKS:
            qa = _mock_qa_segment(job["question"])
        else:
            qa = _live_answer(job)
        with _jobs_lock:
            job["status"] = "done"
            job["qa_segment"] = qa
    except Exception as e:
        log.exception("ask job %s failed", job_id)
        with _jobs_lock:
            job["status"] = "error"
            job["error"] = str(e)


def _post_json(url: str, body: dict, timeout: float = 120.0) -> dict:
    import httpx

    resp = httpx.post(url, json=body, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _load_episode(episode_id: str) -> dict:
    """Episode JSON from S3 (live source of truth); fixtures as fallback so the
    flow still works right after a fresh deploy with only ep-000 baked."""
    import boto3

    try:
        obj = boto3.client("s3", region_name=settings.AWS_REGION).get_object(
            Bucket=settings.S3_BUCKET, Key=f"episodes/{episode_id}.json"
        )
        return json.loads(obj["Body"].read())
    except Exception as e:
        fixture = settings.FIXTURES_DIR / f"{episode_id}.json"
        if fixture.exists():
            log.warning("episode %s not in S3 (%s); using fixture", episode_id, e)
            return json.loads(fixture.read_text())
        raise


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
    """D4 live path: Greptile (genius:false) → Modal /script (answer mode) →
    Modal /tts → assemble WAV → S3. Needs MODAL_* URLs (modal_apps/ENDPOINTS.md)
    and live keys in the environment."""
    import boto3

    import qa_render
    from pipeline import greptile  # the ONE sanctioned cross-lane import

    if not settings.MODAL_SCRIPT_URL or not settings.MODAL_TTS_URL:
        raise RuntimeError("MODAL_SCRIPT_URL / MODAL_TTS_URL unset — see modal_apps/ENDPOINTS.md")

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

    key = f"audio/{job['episode_id']}-qa-{uuid.uuid4().hex[:8]}.wav"
    boto3.client("s3", region_name=settings.AWS_REGION).put_object(
        Bucket=settings.S3_BUCKET, Key=key, Body=wav_bytes,
        ContentType="audio/wav", CacheControl="public, max-age=31536000",
    )

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
    return {"question": job["question"], "audio_url": f"/{key}", "segments": segments}
