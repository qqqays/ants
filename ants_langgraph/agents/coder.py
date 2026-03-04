"""CoderAgent — writes code for a single task."""

from __future__ import annotations

from .base import BaseAgent
from ..experience.library import get_experience_library
from ..experience.budget import ExperienceBudgetManager
from ..experience.reflect import reflect_and_save


class CoderAgent(BaseAgent):
    def __init__(self, project_path: str, agent_id: str = "coder"):
        self.project_path = project_path
        self.agent_id = agent_id

    async def run(self, task: dict, context: dict) -> dict:
        lib = get_experience_library(self.project_path)
        budget = ExperienceBudgetManager()

        experiences = await lib.query(
            problem=task.get("description", ""),
            agent_id=self.agent_id,
            top_k=5,
            min_score=0.5,
        )
        budget.try_add(experiences)

        output = {
            "code_changes": f"# Stub implementation for: {task.get('title', '')}",
            "notes": budget.to_prompt_section(),
            "error": "",
        }

        # Persist new experiences asynchronously
        import asyncio
        asyncio.create_task(
            reflect_and_save(task, {"output": output}, lib, context.get("session_id", ""))
        )

        return {"passed": True, "output": output}
