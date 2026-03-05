"""PlannerAgent — generates task lists using Google ADK LlmAgent."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from ..experience.library import get_experience_library
from ..experience.budget import ExperienceBudgetManager
from ..skills.registry import get_skill_registry


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


def _default_agent_plan(tasks: list[dict]) -> list[dict]:
    """Generate a default agent_plan when the LLM does not produce one."""
    _ROLE_MAP = {
        "coder": ["coder"],
        "reviewer": ["code_reviewer"],
        "tester": ["tester"],
    }
    _PHASE_NAME = {2: "development", 3: "testing"}
    plan = []
    for task in tasks:
        role = task.get("assigned_agent", "coder")
        plan.append({
            "phase_name": _PHASE_NAME.get(task.get("phase", 2), "development"),
            "agent_id": f"sub_{role}_{task['id']}",
            "skill_names": _ROLE_MAP.get(role, ["coder"]),
            "task_ids": [task["id"]],
        })
    return plan


def _parse_planner_output(content: str) -> tuple[list[dict], list[dict]]:
    """Parse LLM output into (tasks, agent_plan)."""
    obj_match = re.search(r"\{.*\}", content, re.DOTALL)
    if obj_match:
        try:
            raw = json.loads(obj_match.group())
            if isinstance(raw, dict) and "tasks" in raw:
                tasks = _parse_tasks(json.dumps(raw.get("tasks", [])))
                raw_plan = raw.get("agent_plan", [])
                agent_plan = []
                for item in raw_plan:
                    agent_plan.append({
                        "phase_name": item.get("phase_name", "execution"),
                        "agent_id": item.get("agent_id", f"sub_{len(agent_plan):03d}"),
                        "skill_names": item.get("skill_names", ["coder"]),
                        "task_ids": item.get("task_ids", []),
                    })
                return tasks, agent_plan
        except (json.JSONDecodeError, ValueError):
            pass

    tasks = _parse_tasks(content)
    return tasks, _default_agent_plan(tasks)


class PlannerAgent:
    """ADK-style Planner Agent.

    In a production ADK setup this would extend ``google.adk.agents.LlmAgent``.
    The ``before_invoke`` lifecycle hook injects Level 1 experiences before
    the LLM is called.

    Now also emits an ``agent_plan`` — a list of SubAgent descriptors with
    skill assignments, enabling the Orchestrator to instantiate skill-loaded
    sub-agents for each phase.
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
        skill_names = list(get_skill_registry().list_names())
        return f"""你是 ANTS 任务规划 Agent。

任务：根据用户目标，分析代码库，生成分阶段的任务清单和 SubAgent 计划（JSON 格式）。

可用技能（skill_names）：{skill_names}

规则：
- 每个任务必须指定 phase（2=执行, 3=验证）、assigned_agent、depends_on
- 执行阶段的独立任务设置相同 phase，Orchestrator 会并行执行
- 同时输出 agent_plan，为每个任务指定携带哪些 skill 的 SubAgent
- 如有历史经验可参考，优先遵循项目约定
- 返回格式：{{"tasks": [...], "agent_plan": [...]}}

项目历史经验：
{experience_section}
"""

    async def run(self, goal: str, session_state: dict) -> tuple[list[dict], list[dict]]:
        """Generate a task list and agent_plan for the given goal.

        Returns:
            Tuple of (tasks, agent_plan).
        """
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
                    f"目标：{goal}\n\n请生成任务清单和 Agent 计划（JSON）"
                ),
            )
            return _parse_planner_output(response.text)
        except Exception:  # noqa: BLE001
            tasks = _parse_tasks("")
            return tasks, _default_agent_plan(tasks)

