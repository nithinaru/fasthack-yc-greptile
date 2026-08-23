"""Pure-python helpers for the Repo Radio TTS service.

This module must import cleanly anywhere: no modal, no torch, no kokoro.
numpy and soundfile are used when available, with stdlib fallbacks (array +
wave) so local tests run with zero third-party dependencies.
"""

from __future__ import annotations

import base64
import io
import struct
import wave

SAMPLE_RATE = 24000

try:  # optional third-party deps
    import numpy as _np
except ImportError:  # pragma: no cover - environment dependent
    _np = None

try:
    import soundfile as _sf
except ImportError:  # pragma: no cover - environment dependent
    _sf = None


def num_samples(samples) -> int:
    """Length of a sample buffer (numpy array, list, or array.array)."""
    return len(samples)


def duration_seconds(n_samples: int, sample_rate: int = SAMPLE_RATE) -> float:
    """Exact audio duration: samples / sample_rate."""
    return n_samples / float(sample_rate)


def encode_wav(samples, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Encode float samples in [-1, 1] as 16-bit PCM WAV bytes.

    Uses soundfile when installed; otherwise the stdlib wave module.
    """
    if _sf is not None and _np is not None:
        buf = io.BytesIO()
        arr = _np.asarray(samples, dtype=_np.float32)
        _sf.write(buf, arr, sample_rate, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    # stdlib fallback: manual float -> int16 conversion
    def to_int16(x: float) -> int:
        x = max(-1.0, min(1.0, float(x)))
        return int(x * 32767)

    pcm = struct.pack("<%dh" % len(samples), *(to_int16(s) for s in samples))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def make_silence(duration_s: float = 0.5, sample_rate: int = SAMPLE_RATE):
    """A buffer of zeros (numpy if available, else a plain list of floats)."""
    n = int(round(duration_s * sample_rate))
    if _np is not None:
        return _np.zeros(n, dtype=_np.float32)
    return [0.0] * n


def build_segment_entry(samples, sample_rate: int = SAMPLE_RATE, fmt: str = "wav") -> dict:
    """One response entry: base64 WAV + exact duration for karaoke sync."""
    wav_bytes = encode_wav(samples, sample_rate)
    return {
        "audio_b64": base64.b64encode(wav_bytes).decode("ascii"),
        "format": fmt,
        "duration_s": duration_seconds(num_samples(samples), sample_rate),
    }


def build_response(entries: list[dict], voice: str, sample_rate: int = SAMPLE_RATE) -> dict:
    return {
        "segments": entries,
        "voice": voice,
        "sample_rate": sample_rate,
    }


def synthesize_mock_response(texts: list[str], voice: str, sample_rate: int = SAMPLE_RATE) -> dict:
    """Mock mode: one 0.5s silent WAV per input segment, correct duration_s."""
    entries = [
        build_segment_entry(make_silence(0.5, sample_rate), sample_rate)
        for _ in texts
    ]
    return build_response(entries, voice, sample_rate)
