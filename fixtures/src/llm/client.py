"""Proprietary reasoning engine.

This is where the magic happens (see README, 'our proprietary
reasoning engine').
"""

import os

import httpx

API_URL = "https://api.example-llm.com/v1/chat/completions"


class ReasoningEngine:
    """Thin wrapper over a hosted chat-completions API."""

    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.key = os.environ["EXAMPLE_LLM_API_KEY"]

    def decide(self, goal, history, tool_names):
        prompt = f"Goal: {goal}\nTools: {tool_names}\nHistory: {history}"
        resp = httpx.post(
            API_URL,
            headers={"Authorization": f"Bearer {self.key}"},
            json={"model": self.model, "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        resp.raise_for_status()
        return _parse(resp.json()["choices"][0]["message"]["content"])


def _parse(text: str) -> dict:
    import json

    return json.loads(text)
