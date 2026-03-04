"""PlannerAgent — generates task lists using Google ADK LlmAgent."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from ..experience.library import get_experience_library
from ..experience.budget import ExperienceBudgetManager


def _parse_tasks(content: str) -> list[dict]:
    """Extract a JSON task array from LLM output."""
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if match:
        try:
            raw = json.loads(match.group())
            tasks = []
            for i, item in enumerate(raw):
                tasks.append({
                    "id": item.get("id", f"task_{i:03d}"),
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                    "assigned_agent": item.get("assigned_agent", "coder"),
                    "phase": int(item.get("phase", 2)),
                    "depends_on": item.get("depends_on", []),
                    "status": "pending",
                    "output": None,
                })
            return tasks
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback
    return [{
        "id": "task_001",
        "title": "执行目标",
        "description": content[:500],
        "assigned_agent": "coder",
        "phase": 2,
        "depends_on": [],
        "status": "pending",
        "output": None,
    }]


class PlannerAgent:
    """ADK-style Planner Agent.

    In a production ADK setup this would extend ``google.adk.agents.LlmAgent``.
    The ``before_invoke`` lifecycle hook injects Level 1 experiences before
    the LLM is called.
    """

    name = "planner"

    def __init__(self, project_path: str, model: str = "gemini-2.0-pro"):
        self.project_path = project_path
        self.model = model
        self.lib = get_experience_library(project_path)

    async def before_invoke(self, session_state: dict) -> dict:
        """ADK lifecycle hook: inject Level 1 experiences before LLM call."""
        goal = session_state.get("ants.goal", "")

        budget = ExperienceBudgetManager()
        l1_exps = await self.lib.query(
            problem=goal,
            agent_id=self.name,
            categories=["project_convention", "arch_pattern", "domain_knowledge"],
            top_k=5,
            min_score=0.5,
        )
        budget.try_add(l1_exps)

        session_state["planner_experience_section"] = budget.to_prompt_section()
        session_state["experience_budget_used"] = budget._used
        return session_state

    def _build_instruction(self, session_state: dict) -> str:
        experience_section = session_state.get("planner_experience_section", "")
        return f"""你是 ANTS 任务规划 Agent。

任务：根据用户目标，分析代码库，生成分阶段的任务清单（JSON 格式）。

规则：
- 每个任务必须指定 phase（2=执行, 3=验证）、assigned_agent、depends_on
- 执行阶段的独立任务设置相同 phase，Orchestrator 会并行执行
- 如有历史经验可参考，优先遵循项目约定

项目历史经验：
{experience_section}
"""

    async def run(self, goal: str, session_state: dict) -> list[dict]:
        """Generate a task list for the given goal."""
        session_state = await self.before_invoke(session_state)

        instruction = self._build_instruction(session_state)

        try:
            import google.generativeai as genai  # type: ignore
            model = genai.GenerativeModel(
                model_name=self.model,
                system_instruction=instruction,
            )
            response = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: model.generate_content(
                    f"目标：{goal}\n\n请生成任务清单（JSON 数组）"
                ),
            )
            return _parse_tasks(response.text)
        except Exception:  # noqa: BLE001
            return _parse_tasks("")
