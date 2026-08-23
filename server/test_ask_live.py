"""Verification of the live ask path with faked network edges (Greptile, Modal,
GitHub raw). Proves orchestration, WAV assembly + gap timestamps, publishing
onto DATA_DIR, and that the produced qa_segment validates against the episode
schema. No live keys required — network calls are monkeypatched.

Run: python3 -m pytest server/test_ask_live.py -q
"""
import base64
import io
import json
import struct
import wave

import pytest

import server  # noqa: F401  (path shim)
import ask
import qa_render
import settings

SR = 24000


def wav_b64(seconds: float) -> tuple[str, float]:
    n = int(seconds * SR)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(struct.pack(f"<{n}h", *([1000] * n)))
    return base64.b64encode(buf.getvalue()).decode(), n / SR


SCRIPT_RESPONSE = {
    "title": "Is the scheduler real?",
    "verdict": "MIXED",
    "segments": [
        {"text": "Short answer: yes.",
         "citation": {"file": "core/scheduler.py", "start_line": 51, "end_line": 55}},
        {"text": "The decay logic is genuinely there.", "citation": None},
    ],
}

FAKE_SOURCE = "\n".join(f"line {n}" for n in range(1, 101))


@pytest.fixture()
def live_env(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "USE_MOCKS", False)
    monkeypatch.setattr(settings, "MODAL_SCRIPT_URL", "https://modal.test/script")
    monkeypatch.setattr(settings, "MODAL_TTS_URL", "https://modal.test/tts")
    # Live keys aren't available in CI/dev — fake them so _live_answer's
    # fail-fast key check passes; the actual network calls are monkeypatched
    # below so no real Greptile/GitHub call is ever made.
    monkeypatch.setattr(settings, "GREPTILE_API_KEY", "test-key")
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)

    calls = {}

    def fake_post(url, body, timeout=120.0):
        calls.setdefault(url, []).append(body)
        if url.endswith("/script"):
            return SCRIPT_RESPONSE
        if url.endswith("/tts"):
            segs = []
            for dur in (2.0, 1.5):
                b64, exact = wav_b64(dur)
                segs.append({"audio_b64": b64, "format": "wav", "duration_s": exact})
            return {"segments": segs, "voice": "am_michael", "sample_rate": SR}
        raise AssertionError(f"unexpected POST {url}")

    monkeypatch.setattr(ask, "_post_json", fake_post)

    from pipeline import greptile

    monkeypatch.setattr(greptile, "query", lambda repo, q, branch="main", genius=True: {
        "query": q, "message": "Yes — scheduler decay is implemented.",
        "sources": [{"filepath": "core/scheduler.py", "linestart": 51, "lineend": 88}],
    })
    monkeypatch.setattr(qa_render, "fetch_github_raw",
                        lambda repo, path, ref="main", timeout=10: FAKE_SOURCE)
    return calls


def test_live_answer_end_to_end(live_env):
    job = {"episode_id": "ep-000", "question": "Is the scheduler real?",
           "user_id": "judge@test.com"}
    qa = ask._live_answer(job)

    # Contract shape: {question, audio_url, segments[]}
    assert qa["question"] == job["question"]
    assert qa["audio_url"].startswith("/audio/ep-000-qa-")

    # Timestamps: seg0 [0, 2.0], gap 0.35, seg1 [2.35, 3.85]
    s0, s1 = qa["segments"]
    assert s0["start"] == 0.0 and s0["end"] == 2.0
    assert s1["start"] == 2.35 and s1["end"] == 3.85

    # Citation rendered fixture-style with cited class; null passes through.
    assert '<span class="line cited" data-line="51">' in s0["citation"]["code_html"]
    assert s1["citation"] is None

    # Audio actually landed on DATA_DIR/audio/, one WAV, correct total length.
    audio_path = settings.DATA_DIR / qa["audio_url"].lstrip("/")
    assert audio_path.exists()
    with wave.open(str(audio_path), "rb") as w:
        total = w.getnframes() / w.getframerate()
    assert abs(total - 3.85) < 0.01

    # Greptile was asked with genius=False semantics via our lambda; script
    # got answer mode with the finding wired through.
    script_body = live_env["https://modal.test/script"][0]
    assert script_body["mode"] == "answer"
    assert script_body["greptile_findings"][0]["sources"][0]["filepath"] == "core/scheduler.py"


def test_qa_segment_validates_against_episode_schema(live_env):
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((settings.REPO_ROOT / "contracts/episode.schema.json").read_text())
    qa_schema = {**schema["properties"]["qa_segments"]["items"],
                 "definitions": schema["definitions"]}
    qa = ask._live_answer({"episode_id": "ep-000", "question": "q?",
                           "user_id": "u@x.com"})
    jsonschema.validate(qa, qa_schema)


def test_missing_modal_urls_fail_fast(monkeypatch):
    monkeypatch.setattr(settings, "USE_MOCKS", False)
    monkeypatch.setattr(settings, "MODAL_SCRIPT_URL", "")
    monkeypatch.setattr(settings, "GREPTILE_API_KEY", "test-key")
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "test-token")
    with pytest.raises(RuntimeError, match="MODAL_SCRIPT_URL"):
        ask._live_answer({"episode_id": "ep-000", "question": "q?", "user_id": "u@x.com"})


def test_missing_greptile_keys_fail_fast(monkeypatch):
    monkeypatch.setattr(settings, "USE_MOCKS", False)
    monkeypatch.setattr(settings, "MODAL_SCRIPT_URL", "https://modal.test/script")
    monkeypatch.setattr(settings, "MODAL_TTS_URL", "https://modal.test/tts")
    monkeypatch.setattr(settings, "GREPTILE_API_KEY", "")
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "")
    with pytest.raises(RuntimeError, match="GREPTILE_API_KEY"):
        ask._live_answer({"episode_id": "ep-000", "question": "q?", "user_id": "u@x.com"})
