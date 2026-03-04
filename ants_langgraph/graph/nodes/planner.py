"""planner_node — generate the task list with Level 1 experience injection."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from ...experience.library import get_experience_library
from ...experience.budget import ExperienceBudgetManager
from ..state import ANTSState, TaskItem


def _build_planner_system_prompt(project_meta: str, experience_section: str) -> str:
    return f"""你是 ANTS 任务规划 Agent。

项目信息：
{project_meta}

{experience_section}

任务：根据用户目标，分析代码库，生成分阶段的任务清单（JSON 数组格式）。

每个任务对象必须包含以下字段：
- id: 唯一字符串（如 "task_001"）
- title: 简短标题
- description: 详细描述
- assigned_agent: "coder" | "reviewer" | "tester"
- phase: 2（执行阶段）或 3（验证阶段）
- depends_on: 依赖的任务 id 列表（可为空列表）
- status: "pending"
- output: null

规则：
- 独立任务设置相同 phase，Orchestrator 会并行执行
- 如有历史经验可参考，优先遵循项目约定
- 只返回 JSON 数组，不要添加其他文本
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


async def planner_node(state: ANTSState) -> dict:
    """Planner node: generate task list with Level 1 experience injection."""
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
                HumanMessage(content=f"目标：{state['goal']}\n\n请生成任务清单（JSON 数组）"),
            ]
        )
        tasks = _parse_tasks(response.content)
    except Exception:  # noqa: BLE001
        # If LLM is unavailable (e.g. no API key in tests), create a stub task
        tasks = _parse_tasks("")

    # Record experience load feedback
    for exp in accepted:
        await lib.feedback(exp.entry.id, helpful=None)

    new_ids = [e.entry.id for e in accepted]
    existing_ids = state.get("injected_experience_ids") or []

    return {
        "tasks": tasks,
        "current_phase": 1,
        "phase_status": "completed",
        "experience_budget_used": budget._used,
        "injected_experience_ids": existing_ids + new_ids,
        "session_memory": state["session_memory"]
        + f"\n[Phase 1] Planner 生成 {len(tasks)} 个任务",
    }
