"""PlannerAgent — generates task lists for a given goal."""

from __future__ import annotations

from .base import BaseAgent
from ..experience.library import get_experience_library
from ..experience.budget import ExperienceBudgetManager


class PlannerAgent(BaseAgent):
    agent_id = "planner"

    def __init__(self, project_path: str):
        self.project_path = project_path

    async def run(self, task: dict, context: dict) -> dict:
        lib = get_experience_library(self.project_path)
        budget = ExperienceBudgetManager()

        experiences = await lib.query(
            problem=context.get("goal", ""),
            agent_id=self.agent_id,
            categories=["project_convention", "arch_pattern", "domain_knowledge"],
            top_k=5,
            min_score=0.5,
        )
        budget.try_add(experiences)

        return {
            "passed": True,
            "output": {
                "experience_section": budget.to_prompt_section(),
                "notes": f"Planner loaded {len(experiences)} experiences.",
            },
        }
