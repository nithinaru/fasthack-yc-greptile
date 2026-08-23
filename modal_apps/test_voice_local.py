"""Local contract test for the TTS service helpers.

Run:  python3 modal_apps/test_voice_local.py

No modal, torch, kokoro, numpy, or soundfile required — voice_common falls
back to stdlib implementations when third-party packages are missing.
"""

from __future__ import annotations

import base64
import io
import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from voice_common import SAMPLE_RATE, synthesize_mock_response  # noqa: E402


def test_mock_response_three_segments():
    texts = ["First segment.", "Second segment.", "Third segment."]
    resp = synthesize_mock_response(texts, voice="am_michael")

    # (b) response shape has required keys
    assert set(resp.keys()) == {"segments", "voice", "sample_rate"}, resp.keys()
    assert resp["voice"] == "am_michael"
    assert resp["sample_rate"] == SAMPLE_RATE == 24000

    # (a) 3 entries, duration ~0.5s each, valid base64 WAV
    assert len(resp["segments"]) == 3, len(resp["segments"])
    for entry in resp["segments"]:
        assert set(entry.keys()) == {"audio_b64", "format", "duration_s"}, entry.keys()
        assert entry["format"] == "wav"
        assert abs(entry["duration_s"] - 0.5) < 1e-6, entry["duration_s"]

        wav_bytes = base64.b64decode(entry["audio_b64"], validate=True)
        assert wav_bytes[:4] == b"RIFF", wav_bytes[:4]
        assert wav_bytes[8:12] == b"WAVE", wav_bytes[8:12]

        # decode with stdlib wave and cross-check the advertised duration
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getframerate() == SAMPLE_RATE
            decoded_duration = wf.getnframes() / wf.getframerate()
        assert abs(decoded_duration - entry["duration_s"]) < 1e-6


def main():
    test_mock_response_three_segments()
    print("OK: mock /tts response contract holds (3 segments, 0.5s silent WAVs)")


if __name__ == "__main__":
    main()
