"""Repo Radio TTS service — Modal app serving POST /tts with Kokoro-82M.

Deploy:  modal deploy modal_apps/tts.py
Test:    curl -X POST <url>/tts -H 'content-type: application/json' \
             -d '{"segments": ["Hello from Repo Radio."], "mock": true}'

Contract (PRD §3.3):
  POST /tts  body: { "segments": ["text", ...], "voice": optional str, "mock": optional bool }
  response:  { "segments": [ { "audio_b64", "format", "duration_s" }, ... ],
               "voice": str, "sample_rate": 24000 }

Segments are synthesized independently and never concatenated server-side.
The pipeline assembles the final MP3 and inserts 0.35s gaps between
segments; karaoke-sync timestamps are:

    start[i] = sum(duration_s[0..i-1]) + i * 0.35
    end[i]   = start[i] + duration_s[i]

duration_s (samples / sample_rate) drives that timeline, so it must be exact.
"""

from __future__ import annotations

import os

import modal

from voice_common import (
    SAMPLE_RATE,
    build_response,
    build_segment_entry,
    synthesize_mock_response,
)

# Voice shortlist (A/B via {"voice": ...} in the body):
#   am_michael - warm male FM-host read (default)
#   af_bella   - bright female alternative
VOICE = "am_michael"

# Keep-warm knob: set REPO_RADIO_TTS_MIN_CONTAINERS=1 before deploy to avoid
# cold starts during the demo. Default 0 (scale to zero).
MIN_CONTAINERS = int(os.environ.get("REPO_RADIO_TTS_MIN_CONTAINERS", "0"))

app = modal.App("repo-radio-tts")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("espeak-ng", "ffmpeg")
    .pip_install("kokoro>=0.9", "soundfile", "numpy", "torch", "fastapi[standard]")
    .env({"HF_HOME": "/models/hf"})  # cache HF weights in the mounted Volume
    .add_local_file(
        os.path.join(os.path.dirname(__file__), "voice_common.py"),
        remote_path="/root/voice_common.py",
    )
)

# HF weights cache so cold starts only pay model load, not download.
models_volume = modal.Volume.from_name("repo-radio-models", create_if_missing=True)

_pipeline = None  # cached per container


def _get_pipeline():
    """Lazily build the Kokoro pipeline; auto-detect CUDA (T4) vs CPU fallback."""
    global _pipeline
    if _pipeline is None:
        import torch
        from kokoro import KPipeline

        device = "cuda" if torch.cuda.is_available() else "cpu"
        # lang_code "a" = American English (matches am_*/af_* voices)
        _pipeline = KPipeline(lang_code="a", device=device)
    return _pipeline


@app.function(
    image=image,
    gpu="T4",  # CPU works as an emergency fallback: drop this line and redeploy
    volumes={"/models": models_volume},
    min_containers=MIN_CONTAINERS,
    timeout=600,
)
@modal.fastapi_endpoint(method="POST", label="tts")
def tts(body: dict) -> dict:
    """POST /tts — synthesize each segment independently with Kokoro-82M."""
    texts = body.get("segments") or []
    if not isinstance(texts, list) or not all(isinstance(t, str) for t in texts):
        return {"error": "body.segments must be a list of strings"}

    voice = body.get("voice") or VOICE

    # Mock mode: contract-shaped response without touching the model.
    if body.get("mock") or os.environ.get("USE_MOCKS") == "1":
        return synthesize_mock_response(texts, voice)

    import numpy as np

    pipeline = _get_pipeline()
    entries = []
    for text in texts:
        # KPipeline may yield multiple chunks per text; join them into one
        # audio array for this segment (no cross-segment concatenation).
        chunks = []
        for result in pipeline(text, voice=voice):
            audio = result.audio if hasattr(result, "audio") else result[2]
            if audio is None:
                continue
            if hasattr(audio, "detach"):  # torch tensor -> numpy
                audio = audio.detach().cpu().numpy()
            chunks.append(np.asarray(audio, dtype=np.float32))
        samples = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
        entries.append(build_segment_entry(samples, SAMPLE_RATE))

    return build_response(entries, voice, SAMPLE_RATE)
