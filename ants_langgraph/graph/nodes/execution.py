"""execution_phase_node — run Phase 2 coder tasks with dependency-aware parallelism."""

from __future__ import annotations

import asyncio

from langchain_core.messages import HumanMessage, SystemMessage

from ...experience.library import get_experience_library
from ...experience.budget import ExperienceBudgetManager
from ...experience.reflect import reflect_and_save
from ..state import ANTSState, TaskItem


def _make_query_experience_tool(lib, agent_id: str, budget: ExperienceBudgetManager):
    """Return a callable that does Level 2/3 dynamic experience retrieval."""

    async def query_experience(problem_description: str) -> str:
        """查询项目历史经验库。

        当遇到以下情况时主动调用：
        1. 遇到错误或异常，希望知道项目中是否有已知解法
        2. 不确定某个工具/命令在这个项目中的正确用法
        3. 不确定这个项目的编码规范（命名、格式、架构模式）
        4. 遇到可能与项目环境相关的问题

        参数:
            problem_description: 当前遇到的问题或疑问的自然语言描述

        返回: 最多 3 条最相关的项目历史经验，含具体解决方案。
        """
        results = await lib.query(
            problem=problem_description,
            agent_id=agent_id,
            top_k=3,
            min_score=0.4,
        )
        budget.try_add(results)
        if not results:
            return "（未找到相关历史经验）"
        from ...experience.entry import compress_entry
        lines = ["相关历史经验："]
        for r in results:
            lines.append(f"  • {compress_entry(r.entry)}  (相关度: {r.score:.2f})")
        return "\n".join(lines)  # ≤ 450 tokens

    return query_experience


def _build_coder_system_prompt(
    task: TaskItem, session_memory: str, experience_section: str
) -> str:
    return f"""你是 ANTS 编码 Agent，负责执行一个具体的编码任务。

项目背景：
{session_memory}

{experience_section}

当前任务：
ID: {task['id']}
标题：{task['title']}
描述：{task['description']}

规则：
- 直接完成任务，输出代码变更和说明
- 遇到不确定的情况时主动调用 query_experience 工具查询历史经验
- 输出格式：
  {{
    "code_changes": "代码变更说明或代码片段",
    "notes": "执行过程中的重要发现或注意事项",
    "error": ""（如有错误则填写）
  }}
"""


async def run_coder_task(task: TaskItem, state: ANTSState) -> dict:
    """Execute a single coder task with Level 1 + Level 2 experience injection."""
    lib = get_experience_library(state["project_path"])
    budget = ExperienceBudgetManager()
    agent_id = f"coder_{task['id']}"

    # Level 1: task-level experience
    l1 = await lib.query(task["description"], agent_id, top_k=5, min_score=0.5)
    budget.try_add(l1)

    system_prompt = _build_coder_system_prompt(
        task=task,
        session_memory=state.get("session_memory", ""),
        experience_section=budget.to_prompt_section(),
    )

    output = {"code_changes": "", "notes": "", "error": ""}
    try:
        from langchain_openai import ChatOpenAI  # type: ignore
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        response = await llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"请执行任务：{task['description']}"),
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

    passed = not output.get("error")

    # Reflect asynchronously
    asyncio.create_task(
        reflect_and_save(task, {"output": output}, lib, state.get("session_id", ""))
    )

    return {
        "task_id": task["id"],
        "passed": passed,
        "output": output,
    }


async def execution_phase_node(state: ANTSState) -> dict:
    """Execute all Phase 2 tasks respecting dependency ordering."""
    tasks = list(state.get("tasks", []))
    pending = [t for t in tasks if t["phase"] == 2 and t["status"] == "pending"]

    while pending:
        completed_ids = {t["id"] for t in tasks if t["status"] == "completed"}
        ready = [
            t for t in pending
            if all(dep in completed_ids for dep in t["depends_on"])
        ]

        if not ready:
            break  # Deadlock guard

        results = await asyncio.gather(*[run_coder_task(t, state) for t in ready])

        result_map = {r["task_id"]: r for r in results}
        updated: list[TaskItem] = []
        for t in tasks:
            if t["id"] in result_map:
                r = result_map[t["id"]]
                updated.append(
                    {
                        **t,
                        "status": "completed" if r["passed"] else "needs_redo",
                        "output": r["output"],
                    }
                )
            else:
                updated.append(t)

        tasks = updated
        pending = [t for t in tasks if t["phase"] == 2 and t["status"] == "pending"]

    return {
        "tasks": tasks,
        "current_phase": 2,
        "phase_status": "completed",
        "session_memory": state.get("session_memory", "")
        + f"\n[Phase 2] 执行完成，共 {len([t for t in tasks if t['phase'] == 2])} 个任务",
    }
