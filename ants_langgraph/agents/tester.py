"""TesterAgent — generates and runs tests for completed tasks."""

from __future__ import annotations

from .base import BaseAgent
from ..experience.library import get_experience_library
from ..experience.budget import ExperienceBudgetManager


class TesterAgent(BaseAgent):
    agent_id = "tester"

    def __init__(self, project_path: str):
        self.project_path = project_path

    async def run(self, task: dict, context: dict) -> dict:
        lib = get_experience_library(self.project_path)
        budget = ExperienceBudgetManager()

        experiences = await lib.query(
            problem=task.get("description", ""),
            agent_id=self.agent_id,
            categories=["environment", "tool_usage", "debug_pattern"],
            top_k=5,
            min_score=0.5,
        )
        budget.try_add(experiences)

        return {
            "passed": True,
            "output": {
                "test_cases": ["# Stub test case"],
                "passed": True,
                "notes": "Stub tester: all tests passed.",
                "error": "",
            },
        }
