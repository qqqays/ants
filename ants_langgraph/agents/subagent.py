"""SubAgent — a dynamically-created agent that loads skills on-demand.

The AgentPlan produced by the Planner specifies:
  - which phase each sub-agent belongs to
  - which skill names to load
  - which tasks to execute

SubAgent assembles a combined role prompt from all loaded skills and
injects relevant project experience before running each task.
"""

from __future__ import annotations

from ..skills.registry import get_skill_registry
from ..experience.library import get_experience_library
from ..experience.budget import ExperienceBudgetManager
from ..experience.reflect import reflect_and_save
from ..problems.document import get_problem_document
from .base import BaseAgent


class SubAgent(BaseAgent):
    """A skill-loaded sub-agent created dynamically by the planner.

    Args:
        agent_id: Unique identifier (e.g. "sub_coder_task_001").
        skill_names: Skills to load from the registry.
        project_path: Filesystem path to the project root.
        phase_name: Human-readable phase label (e.g. "development").
    """

    def __init__(
        self,
        agent_id: str,
        skill_names: list[str],
        project_path: str,
        phase_name: str = "",
    ) -> None:
        self.agent_id = agent_id
        self.project_path = project_path
        self.phase_name = phase_name
        self.load_skills(skill_names, get_skill_registry())

    # ── Prompt assembly ──────────────────────────────────────────────

    def _build_system_prompt(
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

    async def run(self, task: dict, context: dict) -> dict:
        """Execute a task using loaded skills and project experience.

        Args:
            task: TaskItem dict.
            context: Shared session state snapshot.

        Returns:
            ``{"passed": bool, "output": dict}``
        """
        lib = get_experience_library(self.project_path)
        budget = ExperienceBudgetManager()

        # Query experience using categories from loaded skills
        categories = self.skill_experience_categories() or None
        experiences = await lib.query(
            problem=task.get("description", ""),
            agent_id=self.agent_id,
            categories=categories,
            top_k=5,
            min_score=0.5,
        )
        budget.try_add(experiences)

        # Load relevant known problems
        problem_doc = get_problem_document(self.project_path)
        problem_section = await problem_doc.to_prompt_section(
            problem=task.get("description", ""), top_k=3
        )

        system_prompt = self._build_system_prompt(
            task=task,
            experience_section=budget.to_prompt_section(),
            problem_section=problem_section,
            session_memory=context.get("session_memory", ""),
        )

        output: dict = {"notes": system_prompt[:200], "error": ""}

        try:
            from langchain_openai import ChatOpenAI  # type: ignore
            from langchain_core.messages import HumanMessage, SystemMessage  # type: ignore
            import json, re

            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
            response = await llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=f"请执行任务：{task.get('description', '')}"),
                ]
            )
            content = response.content
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

        passed = not output.get("error")

        import asyncio
        asyncio.create_task(
            reflect_and_save(
                task, {"output": output}, lib, context.get("session_id", "")
            )
        )

        return {"passed": passed, "output": output}
