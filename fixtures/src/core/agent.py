"""Caveman agent core.

The Agent owns the think-act loop: it pulls a task, asks the LLM what to
do, dispatches tools, and records the outcome.
"""

from dataclasses import dataclass, field
from typing import Any, Callable

from llm.client import ReasoningEngine


@dataclass
class Agent:
    """A single autonomous agent with a tool registry and a run loop."""

    name: str
    engine: ReasoningEngine
    tools: dict[str, Callable[..., Any]] = field(default_factory=dict)
    max_steps: int = 25

    def register_tool(self, name: str, fn: Callable[..., Any]) -> None:
        if name in self.tools:
            raise ValueError(f"tool already registered: {name}")
        self.tools[name] = fn

    def run(self, goal: str) -> list[dict]:
        """Run the think-act loop until the engine says done or max_steps."""
        history: list[dict] = []
        for step in range(self.max_steps):
            decision = self.engine.decide(goal, history, list(self.tools))
            if decision["action"] == "done":
                break
            tool = self.tools[decision["action"]]
            result = tool(**decision.get("args", {}))
            history.append({"step": step, "action": decision["action"], "result": result})
        return history

    def reset(self) -> None:
        pass
