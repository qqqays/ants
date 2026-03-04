"""CoderAgentPool + CoderAgent — parallel coder execution using ADK ParallelAgent."""

from __future__ import annotations

import asyncio

from ..experience.library import get_experience_library
from ..experience.budget import ExperienceBudgetManager
from ..experience.entry import compress_entry
from ..experience.reflect import reflect_and_save


class CoderAgent:
    """Single Coder Agent: executes one coding task with Level 1/2/3 experience injection.

    In production ADK this would extend ``google.adk.agents.LlmAgent``.
    """

    def __init__(
        self,
        task: dict,
        project_path: str,
        lib,
        agent_id: str,
        model: str = "gemini-2.0-flash",
    ):
        self.task = task
        self.lib = lib
        self.project_path = project_path
        self.name = agent_id
        self.model = model

    async def _query_experience(self, problem_description: str) -> str:
        """Level 2/3 dynamic experience retrieval (agent-initiated).

        查询项目历史经验库。

        当遇到以下情况时主动调用：
        1. 遇到错误或异常，希望知道项目中是否有已知解法
        2. 不确定某个工具/命令在这个项目中的正确用法
        3. 不确定这个项目的编码规范（命名、格式、架构模式）
        4. 遇到可能与项目环境相关的问题

        参数:
            problem_description: 当前遇到的问题或疑问的自然语言描述

        返回: 最多 3 条最相关的项目历史经验，含具体解决方案。
        """
        results = await self.lib.query(
            problem=problem_description,
            agent_id=self.name,
            top_k=3,
            min_score=0.4,
        )
        if not results:
            return "（未找到相关历史经验）"
        lines = ["相关历史经验："]
        for r in results:
            lines.append(f"  • {compress_entry(r.entry)}  (相关度: {r.score:.2f})")
        return "\n".join(lines)

    def _build_instruction(self, experience_section: str) -> str:
        return f"""你是 ANTS 编码 Agent，负责执行一个具体的编码任务。

当前任务：
ID: {self.task['id']}
标题：{self.task['title']}
描述：{self.task['description']}

{experience_section}

规则：
- 直接完成任务，输出代码变更和说明
- 遇到不确定的情况时主动调用 query_experience 工具查询历史经验
"""

    async def after_invoke(self, result: dict, session_state: dict) -> None:
        """ADK lifecycle hook: persist new experiences after task completion."""
        asyncio.create_task(
            reflect_and_save(
                self.task,
                result,
                self.lib,
                session_state.get("ants.session_id", ""),
            )
        )

    async def run(self, session_state: dict) -> dict:
        """Execute the coding task."""
        budget = ExperienceBudgetManager()
        l1 = await self.lib.query(
            self.task["description"], "coder", top_k=5, min_score=0.5
        )
        budget.try_add(l1)

        output = {"code_changes": "", "notes": "", "error": ""}
        try:
            import google.generativeai as genai  # type: ignore
            model = genai.GenerativeModel(
                model_name=self.model,
                system_instruction=self._build_instruction(budget.to_prompt_section()),
            )
            response = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: model.generate_content(
                    f"请执行任务：{self.task['description']}"
                ),
            )
            import json, re
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
            "task_id": self.task["id"],
            "passed": not output.get("error"),
            "output": output,
        }
        await self.after_invoke(result, session_state)
        return result


class CoderAgentPool:
    """Dynamically creates N CoderAgent instances and executes tasks in parallel.

    Uses ``asyncio.gather`` for concurrency (equivalent to ADK ParallelAgent).
    In production ADK, replace with ``google.adk.agents.ParallelAgent``.
    """

    def __init__(self, project_path: str, model: str = "gemini-2.0-flash"):
        self.project_path = project_path
        self.model = model
        self.lib = get_experience_library(project_path)

    async def execute_tasks(
        self, tasks: list[dict], session_state: dict
    ) -> list[dict]:
        """Execute tasks respecting dependency order, parallelising where possible."""
        completed_ids: set[str] = set()
        results: list[dict] = []

        while True:
            ready = [
                t
                for t in tasks
                if t["status"] == "pending"
                and all(dep in completed_ids for dep in t["depends_on"])
            ]
            if not ready:
                break

            agents = [
                CoderAgent(
                    task=task,
                    project_path=self.project_path,
                    lib=self.lib,
                    agent_id=f"coder_{task['id']}",
                    model=self.model,
                )
                for task in ready
            ]

            batch_results = await asyncio.gather(
                *[agent.run(session_state) for agent in agents]
            )

            for result in batch_results:
                results.append(result)
                if result["passed"]:
                    completed_ids.add(result["task_id"])
                # Update task status
                for t in tasks:
                    if t["id"] == result["task_id"]:
                        t["status"] = "completed" if result["passed"] else "needs_redo"
                        t["output"] = result["output"]

        return results
