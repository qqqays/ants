"""SubAgent (ADK) — a dynamically-created agent that loads skills on-demand.

The AgentPlan produced by the Planner specifies:
  - which phase each sub-agent belongs to
  - which skill names to load
  - which tasks to execute

SubAgent assembles a combined role prompt from all loaded skills and
injects relevant project experience and known problems before running.
"""

from __future__ import annotations

import asyncio
import json
import re

from ..skills.registry import get_skill_registry, SkillRegistry
from ..skills.skill import Skill
from ..experience.library import get_experience_library
from ..experience.budget import ExperienceBudgetManager
from ..experience.reflect import reflect_and_save
from ..problems.document import get_problem_document


class SubAgent:
    """A skill-loaded sub-agent created dynamically by the ADK planner.

    Args:
        agent_id: Unique identifier (e.g. "sub_coder_task_001").
        skill_names: Skills to load from the registry.
        project_path: Filesystem path to the project root.
        phase_name: Human-readable phase label (e.g. "development").
        model: Gemini model to use.
    """

    def __init__(
        self,
        agent_id: str,
        skill_names: list[str],
        project_path: str,
        phase_name: str = "",
        model: str = "gemini-2.0-flash",
    ) -> None:
        self.name = agent_id
        self.project_path = project_path
        self.phase_name = phase_name
        self.model = model
        self.lib = get_experience_library(project_path)

        registry = get_skill_registry()
        self.loaded_skills: list[Skill] = registry.load_skills(skill_names)

    # ── Prompt assembly ──────────────────────────────────────────────

    def build_role_prompt(self) -> str:
        """Return the combined role prompt from all loaded skills."""
        return SkillRegistry.build_role_prompt(self.loaded_skills)

    def skill_experience_categories(self) -> list[str]:
        """Return merged experience categories from all loaded skills."""
        return SkillRegistry.combined_experience_categories(self.loaded_skills)

    def _build_instruction(
        self,
        task: dict,
        experience_section: str,
        problem_section: str,
        session_memory: str,
    ) -> str:
        role = self.build_role_prompt()
        parts: list[str] = []

        if role:
            parts.append(role)
        if session_memory:
            parts.append(f"项目背景：\n{session_memory}")
        if experience_section:
            parts.append(experience_section)
        if problem_section:
            parts.append(problem_section)

        parts.append(
            f"当前任务：\n"
            f"ID: {task.get('id', '')}\n"
            f"标题：{task.get('title', '')}\n"
            f"描述：{task.get('description', '')}\n\n"
            "规则：\n"
            "- 直接完成任务，输出结果\n"
            "- 遇到不确定情况时查询项目历史经验"
        )
        return "\n\n".join(parts)

    # ── Execution ────────────────────────────────────────────────────

    async def run(self, session_state: dict) -> dict:
        """Execute the task assigned to this sub-agent.

        Expects ``session_state`` to contain the task under ``"current_task"``.
        """
        task = session_state.get("current_task", {})
        budget = ExperienceBudgetManager()

        categories = self.skill_experience_categories() or None
        l1 = await self.lib.query(
            task.get("description", ""),
            self.name,
            categories=categories,
            top_k=5,
            min_score=0.5,
        )
        budget.try_add(l1)

        problem_doc = get_problem_document(self.project_path)
        problem_section = await problem_doc.to_prompt_section(
            problem=task.get("description", ""), top_k=3
        )

        instruction = self._build_instruction(
            task=task,
            experience_section=budget.to_prompt_section(),
            problem_section=problem_section,
            session_memory=session_state.get("ants.session_memory", ""),
        )

        output: dict = {"notes": "", "error": ""}
        try:
            import google.generativeai as genai  # type: ignore

            model = genai.GenerativeModel(
                model_name=self.model,
                system_instruction=instruction,
            )
            response = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: model.generate_content(
                    f"请执行任务：{task.get('description', '')}"
                ),
            )
            content = response.text
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                try:
                    output = json.loads(match.group())
                except json.JSONDecodeError:
                    output["notes"] = content[:500]
            else:
                output["notes"] = content[:500]
        except Exception as exc:  # noqa: BLE001
            output["error"] = str(exc)[:200]

        result = {
            "task_id": task.get("id", ""),
            "passed": not output.get("error"),
            "output": output,
        }
        asyncio.create_task(
            reflect_and_save(
                task, result, self.lib, session_state.get("ants.session_id", "")
            )
        )
        return result
