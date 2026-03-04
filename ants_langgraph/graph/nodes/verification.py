"""verification_phase_node — Phase 3 reviewer + tester tasks."""

from __future__ import annotations

import asyncio

from langchain_core.messages import HumanMessage, SystemMessage

from ...experience.library import get_experience_library
from ...experience.budget import ExperienceBudgetManager
from ...experience.reflect import reflect_and_save
from ..state import ANTSState, TaskItem


def _build_reviewer_prompt(task: TaskItem, session_memory: str, experience_section: str) -> str:
    return f"""你是 ANTS 代码审查 Agent。

项目背景：
{session_memory}

{experience_section}

审查任务：
标题：{task['title']}
描述：{task['description']}

请检查代码质量并输出审查结果（JSON 格式）：
{{
  "issues": ["问题列表，若无问题则为空数组"],
  "notes": "审查摘要",
  "error": ""
}}
"""


def _build_tester_prompt(task: TaskItem, session_memory: str, experience_section: str) -> str:
    return f"""你是 ANTS 测试 Agent。

项目背景：
{session_memory}

{experience_section}

测试任务：
标题：{task['title']}
描述：{task['description']}

请生成测试用例并给出测试结果（JSON 格式）：
{{
  "test_cases": ["测试用例列表"],
  "passed": true,
  "notes": "测试摘要",
  "error": ""
}}
"""


async def run_verify_task(task: TaskItem, state: ANTSState) -> dict:
    """Execute a single verification task (reviewer or tester)."""
    lib = get_experience_library(state["project_path"])
    budget = ExperienceBudgetManager()

    l1 = await lib.query(task["description"], task["assigned_agent"], top_k=5, min_score=0.5)
    budget.try_add(l1)

    if task["assigned_agent"] == "reviewer":
        prompt = _build_reviewer_prompt(task, state.get("session_memory", ""), budget.to_prompt_section())
    else:
        prompt = _build_tester_prompt(task, state.get("session_memory", ""), budget.to_prompt_section())

    output = {"notes": "", "error": ""}
    try:
        from langchain_openai import ChatOpenAI  # type: ignore
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        response = await llm.ainvoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=f"请执行验证任务：{task['description']}"),
            ]
        )
        import json, re
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

    passed = not output.get("error") and output.get("passed", True)

    asyncio.create_task(
        reflect_and_save(task, {"output": output}, lib, state.get("session_id", ""))
    )

    return {"task_id": task["id"], "passed": passed, "output": output}


async def verification_phase_node(state: ANTSState) -> dict:
    """Execute all Phase 3 verification tasks."""
    tasks = list(state.get("tasks", []))
    pending = [t for t in tasks if t["phase"] == 3 and t["status"] == "pending"]

    if not pending:
        return {
            "current_phase": 3,
            "phase_status": "completed",
            "session_memory": state.get("session_memory", "") + "\n[Phase 3] 无验证任务，跳过",
        }

    results = await asyncio.gather(*[run_verify_task(t, state) for t in pending])
    result_map = {r["task_id"]: r for r in results}

    updated: list[TaskItem] = []
    for t in tasks:
        if t["id"] in result_map:
            r = result_map[t["id"]]
            updated.append({**t, "status": "completed" if r["passed"] else "needs_redo", "output": r["output"]})
        else:
            updated.append(t)

    return {
        "tasks": updated,
        "current_phase": 3,
        "phase_status": "completed",
        "session_memory": state.get("session_memory", "")
        + f"\n[Phase 3] 验证完成，共 {len(pending)} 个验证任务",
    }
