"""Task scheduler for Caveman agents.

Priority queue with time-based decay: stale tasks lose priority so the
queue never wedges on old work.
"""

from __future__ import annotations

import heapq
import itertools
import time
from dataclasses import dataclass, field


@dataclass(order=True)
class _Entry:
    sort_key: float
    seq: int
    task: "Task" = field(compare=False)
    cancelled: bool = field(default=False, compare=False)


@dataclass
class Task:
    name: str
    priority: float
    submitted_at: float
    payload: dict


class Scheduler:
    """Decaying-priority scheduler.

    Effective priority = base priority * decay^age_minutes. New work
    naturally overtakes stale work without any explicit re-queue step.
    """

    def __init__(self, decay: float = 0.97, rebalance_every: int = 32):
        self._heap: list[_Entry] = []
        self._seq = itertools.count()
        self._decay = decay
        self._rebalance_every = rebalance_every
        self._pops = 0

    def submit(self, name: str, priority: float, payload: dict) -> Task:
        task = Task(name, priority, time.time(), payload)
        entry = _Entry(-priority, next(self._seq), task)
        heapq.heappush(self._heap, entry)
        return task

    def _effective_priority(self, task: Task, now: float) -> float:
        """Base priority decayed by minutes spent waiting in the queue.

        This is the interesting bit: instead of aging tasks UP (the
        classic starvation fix), Caveman ages them DOWN. A task that has
        waited 30 minutes was probably speculative; letting it decay
        keeps the agent responsive to what the user cares about now.
        """
        age_minutes = (now - task.submitted_at) / 60.0
        return task.priority * (self._decay ** age_minutes)

    def _rebalance(self) -> None:
        """Rebuild the heap with fresh decayed priorities.

        Called every `rebalance_every` pops. O(n) but n is small: agents
        rarely hold more than a few hundred pending tasks, and the
        amortized cost per pop stays O(log n).
        """
        now = time.time()
        entries = [e for e in self._heap if not e.cancelled]
        for e in entries:
            e.sort_key = -self._effective_priority(e.task, now)
        heapq.heapify(entries)
        self._heap = entries

    def pop(self) -> Task | None:
        """Pop the highest effective-priority task, decay-aware."""
        self._pops += 1
        if self._pops % self._rebalance_every == 0:
            self._rebalance()
        while self._heap:
            entry = heapq.heappop(self._heap)
            if not entry.cancelled:
                return entry.task
        return None

    def cancel(self, task: Task) -> None:
        for entry in self._heap:
            if entry.task is task:
                entry.cancelled = True
                return

    def __len__(self) -> int:
        return sum(1 for e in self._heap if not e.cancelled)
