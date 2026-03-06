"""BaseAgent — abstract interface shared by all ANTS agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..skills.skill import Skill
from ..skills.registry import SkillRegistry, get_skill_registry


class BaseAgent(ABC):
    """Minimal interface that every ANTS agent must implement."""

    #: Unique agent identifier (e.g. "planner", "coder_task_001")
    agent_id: str = ""

    #: Skills loaded for this agent instance (set via load_skills)
    loaded_skills: list[Skill]

    def _init_skills(self) -> None:
        if not hasattr(self, "loaded_skills"):
            self.loaded_skills = []

    def load_skills(self, skill_names: list[str], registry: SkillRegistry | None = None) -> None:
        """Load skills by name from the registry into this agent.

        Args:
            skill_names: List of skill names to activate.
            registry: Optional custom registry; defaults to the global singleton.
        """
        reg = registry or get_skill_registry()
        self.loaded_skills = reg.load_skills(skill_names)

    def build_role_prompt(self) -> str:
        """Return the combined role prompt from all loaded skills.

        Falls back to an empty string when no skills are loaded.
        """
        self._init_skills()
        return SkillRegistry.build_role_prompt(self.loaded_skills)

    def skill_experience_categories(self) -> list[str]:
        """Return merged experience categories from all loaded skills."""
        self._init_skills()
        return SkillRegistry.combined_experience_categories(self.loaded_skills)

    @abstractmethod
    async def run(self, task: dict, context: dict) -> dict:
        """Execute the agent's task.

        Args:
            task: The task item dict (matches TaskItem TypedDict).
            context: Shared session context (state snapshot).

        Returns:
            A result dict with at least {"passed": bool, "output": dict}.
        """
