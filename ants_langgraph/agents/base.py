"""BaseAgent — abstract interface shared by all ANTS agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    """Minimal interface that every ANTS agent must implement."""

    #: Unique agent identifier (e.g. "planner", "coder_task_001")
    agent_id: str = ""

    @abstractmethod
    async def run(self, task: dict, context: dict) -> dict:
        """Execute the agent's task.

        Args:
            task: The task item dict (matches TaskItem TypedDict).
            context: Shared session context (state snapshot).

        Returns:
            A result dict with at least {"passed": bool, "output": dict}.
        """
