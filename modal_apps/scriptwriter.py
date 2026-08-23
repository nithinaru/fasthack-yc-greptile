"""Repo Radio — Modal app #1: scriptwriter.

Serves POST /script: Greptile findings in, strict episode-script JSON out.
Model: Qwen/Qwen2.5-7B-Instruct on vLLM (A10G, L4 fallback).

Deploy:   modal deploy modal_apps/scriptwriter.py
Dev:      modal serve modal_apps/scriptwriter.py
Warm-up:  SCRIPTWRITER_MIN_CONTAINERS=1 modal deploy modal_apps/scriptwriter.py
Mocks:    set USE_MOCKS=1 (deploy env) or send {"mock": true} in the body.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import modal

APP_NAME = "repo-radio-scriptwriter"
MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
MODELS_DIR = "/models"
# Flip to 1 before demos: SCRIPTWRITER_MIN_CONTAINERS=1 modal deploy ...
MIN_CONTAINERS = int(os.environ.get("SCRIPTWRITER_MIN_CONTAINERS", "0"))
SCALEDOWN_WINDOW = 15 * 60  # seconds; generous so back-to-back demos stay warm
MAX_RETRIES = 2  # parse-failure retries after the first attempt

LOCAL_DIR = Path(__file__).parent

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "vllm==0.6.3.post1",
        "fastapi[standard]==0.115.4",
        "huggingface_hub==0.26.2",
        "hf_transfer==0.1.8",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "HF_HOME": MODELS_DIR})
    # Bundle the persona prompt, the mock response, and the pure helpers.
    .add_local_dir(LOCAL_DIR, remote_path="/root/modal_apps")
)

models_volume = modal.Volume.from_name("repo-radio-models", create_if_missing=True)

app = modal.App(APP_NAME)


def _use_mocks() -> bool:
    return os.environ.get("USE_MOCKS") == "1"


@app.cls(
    image=image,
    gpu=["A10G", "L4"],
    volumes={MODELS_DIR: models_volume},
    timeout=10 * 60,
    scaledown_window=SCALEDOWN_WINDOW,
    min_containers=MIN_CONTAINERS,
    secrets=[],
)
class Scriptwriter:
    @modal.enter()
    def load(self):
        import sys

        sys.path.insert(0, "/root")
        from modal_apps import script_common  # noqa: F401  (imported for endpoint use)

        self.host_prompt = Path("/root/modal_apps/prompts/host.txt").read_text()
        self.llm = None
        if _use_mocks():
            return  # mock mode: never touch the GPU / weights

        from huggingface_hub import snapshot_download
        from vllm import LLM

        # Weights land in the shared volume; first cold start downloads,
        # later ones read from the cache.
        snapshot_download(MODEL_NAME, cache_dir=MODELS_DIR)
        models_volume.commit()
        self.llm = LLM(
            model=MODEL_NAME,
            download_dir=MODELS_DIR,
            dtype="bfloat16",
            gpu_memory_utilization=0.90,
            max_model_len=8192,
            enforce_eager=False,
        )

    def _generate_once(self, messages: list[dict]) -> str:
        from vllm import SamplingParams
        from vllm.sampling_params import GuidedDecodingParams

        from modal_apps.script_common import SCRIPT_JSON_SCHEMA

        params = SamplingParams(
            temperature=0.7,
            top_p=0.9,
            max_tokens=2048,
            guided_decoding=GuidedDecodingParams(json=SCRIPT_JSON_SCHEMA),
        )
        outputs = self.llm.chat(messages=messages, sampling_params=params)
        return outputs[0].outputs[0].text

    @modal.asgi_app()
    def web(self):
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse

        from modal_apps.script_common import build_messages, load_mock, parse_script_json

        api = FastAPI(title=APP_NAME)

        @api.post("/script")
        def script(body: dict):
            # Mock-first rule: env flag or per-request flag bypasses the LLM.
            if _use_mocks() or body.get("mock") is True:
                return JSONResponse(load_mock("/root/modal_apps/mock_script_response.json"))

            if self.llm is None:
                # Deployed with USE_MOCKS=1 but request wants real output.
                return JSONResponse(
                    {"error": "model not loaded (container started in mock mode)"},
                    status_code=502,
                )

            messages = build_messages(body, self.host_prompt)
            last_error = "unknown"
            for attempt in range(1 + MAX_RETRIES):
                raw = ""
                try:
                    raw = self._generate_once(messages)
                    return JSONResponse(parse_script_json(raw))
                except Exception as exc:  # parse/validation failure -> retry
                    last_error = str(exc)
                    messages = messages + [
                        {"role": "assistant", "content": raw},
                        {
                            "role": "user",
                            "content": (
                                "Your previous output failed validation: "
                                f"{last_error}. Respond again with ONLY the strict "
                                "JSON object matching the required schema."
                            ),
                        },
                    ]
            return JSONResponse(
                {"error": f"script generation failed after {1 + MAX_RETRIES} attempts: {last_error}"},
                status_code=502,
            )

        @api.get("/health")
        def health():
            return {"ok": True, "mock_mode": _use_mocks()}

        return api
