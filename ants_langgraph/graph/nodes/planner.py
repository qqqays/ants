"""planner_node — generate the task list with Level 1 experience injection."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from ...experience.library import get_experience_library
from ...experience.budget import ExperienceBudgetManager
from ...skills.registry import get_skill_registry
from ..state import ANTSState, TaskItem, AgentPlanItem


def _build_planner_system_prompt(project_meta: str, experience_section: str) -> str:
    skill_names = list(get_skill_registry().list_names())
    return f"""你是 ANTS 任务规划 Agent。

项目信息：
{project_meta}

{experience_section}

可用技能（skill_names）：{skill_names}

任务：根据用户目标，分析代码库，生成两部分输出：

**Part 1 — 任务清单（tasks JSON 数组）**
每个任务对象必须包含：
- id: 唯一字符串（如 "task_001"）
- title: 简短标题
- description: 详细描述
- assigned_agent: "coder" | "reviewer" | "tester"
- phase: 2（执行阶段）或 3（验证阶段）
- depends_on: 依赖的任务 id 列表（可为空列表）
- status: "pending"
- output: null

**Part 2 — Agent 计划（agent_plan JSON 数组）**
每个条目描述一个应创建的 SubAgent：
- phase_name: 阶段名称（如 "requirements", "design", "development", "testing"）
- agent_id: 唯一 id（如 "sub_coder_task_001"）
- skill_names: 从可用技能中选择（列表）
- task_ids: 分配给此 SubAgent 的任务 id 列表

规则：
- 独立任务设置相同 phase，Orchestrator 会并行执行
- 如有历史经验可参考，优先遵循项目约定
- 只返回 JSON 对象，格式：{{"tasks": [...], "agent_plan": [...]}}，不要添加其他文本
"""


def _parse_tasks(content: str) -> list[TaskItem]:
    """Extract a JSON task array from LLM output."""
    # Try to find a JSON array in the output
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if match:
        try:
            raw = json.loads(match.group())
            tasks: list[TaskItem] = []
            for item in raw:
                tasks.append(
                    TaskItem(
                        id=item.get("id", f"task_{len(tasks):03d}"),
                        title=item.get("title", ""),
                        description=item.get("description", ""),
                        assigned_agent=item.get("assigned_agent", "coder"),
                        phase=int(item.get("phase", 2)),
                        depends_on=item.get("depends_on", []),
                        status=item.get("status", "pending"),
                        output=item.get("output"),
                    )
                )
            return tasks
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    # Fallback: return a single placeholder task so the graph can continue
    return [
        TaskItem(
            id="task_001",
            title="执行目标",
            description=content[:500],
            assigned_agent="coder",
            phase=2,
            depends_on=[],
            status="pending",
            output=None,
        )
    ]


def _parse_planner_output(content: str) -> tuple[list[TaskItem], list[AgentPlanItem]]:
    """Parse LLM output into (tasks, agent_plan).

    Accepts either:
    - A JSON object with "tasks" and "agent_plan" keys, or
    - A bare JSON array (legacy, treated as tasks only).
    """
    # Try structured output first
    obj_match = re.search(r"\{.*\}", content, re.DOTALL)
    if obj_match:
        try:
            raw = json.loads(obj_match.group())
            if isinstance(raw, dict) and "tasks" in raw:
                tasks = _parse_tasks(json.dumps(raw.get("tasks", [])))
                raw_plan = raw.get("agent_plan", [])
                agent_plan: list[AgentPlanItem] = []
                for item in raw_plan:
                    agent_plan.append(
                        AgentPlanItem(
                            phase_name=item.get("phase_name", "execution"),
                            agent_id=item.get("agent_id", f"sub_{len(agent_plan):03d}"),
                            skill_names=item.get("skill_names", ["coder"]),
                            task_ids=item.get("task_ids", []),
                        )
                    )
                return tasks, agent_plan
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    # Fallback: bare task list, generate default agent_plan
    tasks = _parse_tasks(content)
    agent_plan = _default_agent_plan(tasks)
    return tasks, agent_plan


def _default_agent_plan(tasks: list[TaskItem]) -> list[AgentPlanItem]:
    """Generate a default agent_plan when the LLM does not produce one."""
    _ROLE_MAP = {
        "coder": ["coder"],
        "reviewer": ["code_reviewer"],
        "tester": ["tester"],
    }
    plan: list[AgentPlanItem] = []
    _PHASE_NAME = {2: "development", 3: "testing"}
    for task in tasks:
        role = task.get("assigned_agent", "coder")
        plan.append(
            AgentPlanItem(
                phase_name=_PHASE_NAME.get(task.get("phase", 2), "development"),
                agent_id=f"sub_{role}_{task['id']}",
                skill_names=_ROLE_MAP.get(role, ["coder"]),
                task_ids=[task["id"]],
            )
        )
    return plan


async def planner_node(state: ANTSState) -> dict:
    """Planner node: generate task list + agent_plan with Level 1 experience injection."""
    lib = get_experience_library(state["project_path"])

    # Level 1: inject relevant experiences
    budget = ExperienceBudgetManager()
    l1_experiences = await lib.query(
        problem=state["goal"],
        agent_id="planner",
        categories=["project_convention", "arch_pattern", "domain_knowledge"],
        top_k=5,
        min_score=0.5,
    )
    accepted = budget.try_add(l1_experiences)

    # Build system prompt
    system_prompt = _build_planner_system_prompt(
        project_meta=state["session_memory"],
        experience_section=budget.to_prompt_section(),
    )

    # Call LLM
    try:
        from langchain_openai import ChatOpenAI  # type: ignore
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        response = await llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"目标：{state['goal']}\n\n请生成任务清单和 Agent 计划（JSON）"),
            ]
        )
        tasks, agent_plan = _parse_planner_output(response.content)
    except Exception:  # noqa: BLE001
        # If LLM is unavailable (e.g. no API key in tests), create stub
        tasks = _parse_tasks("")
        agent_plan = _default_agent_plan(tasks)

    # Record experience load feedback
    for exp in accepted:
        await lib.feedback(exp.entry.id, helpful=None)

    new_ids = [e.entry.id for e in accepted]
    existing_ids = state.get("injected_experience_ids") or []

    # Collect all skill names referenced in the agent_plan
    all_skill_names: list[str] = []
    seen: set[str] = set()
    for item in agent_plan:
        for sn in item.get("skill_names", []):
            if sn not in seen:
                seen.add(sn)
                all_skill_names.append(sn)

    return {
        "tasks": tasks,
        "agent_plan": agent_plan,
        "loaded_skill_names": all_skill_names,
        "current_phase": 1,
        "phase_status": "completed",
        "experience_budget_used": budget._used,
        "injected_experience_ids": existing_ids + new_ids,
        "session_memory": state["session_memory"]
        + f"\n[Phase 1] Planner 生成 {len(tasks)} 个任务，{len(agent_plan)} 个 SubAgent",
    }

