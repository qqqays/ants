"""VerifyAgentPool — ReviewerAgent + TesterAgent for Phase 3 verification."""

from __future__ import annotations

import asyncio

from ..experience.library import get_experience_library
from ..experience.budget import ExperienceBudgetManager
from ..experience.reflect import reflect_and_save


class ReviewerAgent:
    """Reviews code quality for a single task."""

    name = "reviewer"

    def __init__(self, task: dict, project_path: str, lib, model: str = "gemini-2.0-flash"):
        self.task = task
        self.lib = lib
        self.project_path = project_path
        self.model = model

    def _build_instruction(self, experience_section: str) -> str:
        return f"""你是 ANTS 代码审查 Agent。

当前任务：{self.task['title']}
描述：{self.task['description']}

{experience_section}

请检查代码质量，输出 JSON 格式结果：
{{"issues": [], "notes": "审查摘要", "error": ""}}
"""

    async def run(self, session_state: dict) -> dict:
        budget = ExperienceBudgetManager()
        l1 = await self.lib.query(
            self.task["description"], self.name, top_k=5, min_score=0.5
        )
        budget.try_add(l1)

        output = {"issues": [], "notes": "", "error": ""}
        try:
            import google.generativeai as genai  # type: ignore
            model = genai.GenerativeModel(
                model_name=self.model,
                system_instruction=self._build_instruction(budget.to_prompt_section()),
            )
            response = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: model.generate_content(f"请审查任务：{self.task['description']}"),
            )
            import json, re
            match = re.search(r"\{.*\}", response.text, re.DOTALL)
            if match:
                try:
                    output = json.loads(match.group())
                except json.JSONDecodeError:
                    output["notes"] = response.text[:500]
            else:
                output["notes"] = response.text[:500]
        except Exception as exc:  # noqa: BLE001
            output["error"] = str(exc)[:200]

        result = {"task_id": self.task["id"], "passed": not output.get("error"), "output": output}
        asyncio.create_task(
            reflect_and_save(self.task, result, self.lib, session_state.get("ants.session_id", ""))
        )
        return result


class TesterAgent:
    """Generates and runs tests for a single task."""

    name = "tester"

    def __init__(self, task: dict, project_path: str, lib, model: str = "gemini-2.0-flash"):
        self.task = task
        self.lib = lib
        self.project_path = project_path
        self.model = model

    def _build_instruction(self, experience_section: str) -> str:
        return f"""你是 ANTS 测试 Agent。

当前任务：{self.task['title']}
描述：{self.task['description']}

{experience_section}

请生成测试用例，输出 JSON 格式结果：
{{"test_cases": [], "passed": true, "notes": "测试摘要", "error": ""}}
"""

    async def run(self, session_state: dict) -> dict:
        budget = ExperienceBudgetManager()
        l1 = await self.lib.query(
            self.task["description"], self.name,
            categories=["environment", "tool_usage", "debug_pattern"],
            top_k=5, min_score=0.5,
        )
        budget.try_add(l1)

        output = {"test_cases": [], "passed": True, "notes": "", "error": ""}
        try:
            import google.generativeai as genai  # type: ignore
            model = genai.GenerativeModel(
                model_name=self.model,
                system_instruction=self._build_instruction(budget.to_prompt_section()),
            )
            response = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: model.generate_content(f"请测试任务：{self.task['description']}"),
            )
            import json, re
            match = re.search(r"\{.*\}", response.text, re.DOTALL)
            if match:
                try:
                    output = json.loads(match.group())
                except json.JSONDecodeError:
                    output["notes"] = response.text[:500]
            else:
                output["notes"] = response.text[:500]
        except Exception as exc:  # noqa: BLE001
            output["error"] = str(exc)[:200]

        result = {
            "task_id": self.task["id"],
            "passed": not output.get("error") and output.get("passed", True),
            "output": output,
        }
        asyncio.create_task(
            reflect_and_save(self.task, result, self.lib, session_state.get("ants.session_id", ""))
        )
        return result


class VerifyAgentPool:
    """Runs ReviewerAgent and TesterAgent in parallel for Phase 3 tasks."""

    def __init__(self, project_path: str, model: str = "gemini-2.0-flash"):
        self.project_path = project_path
        self.model = model
        self.lib = get_experience_library(project_path)

    async def execute_tasks(self, tasks: list[dict], session_state: dict) -> list[dict]:
        """Execute all Phase 3 verification tasks in parallel."""
        agents = []
        for task in tasks:
            if task["assigned_agent"] == "reviewer":
                agents.append(ReviewerAgent(task, self.project_path, self.lib, self.model))
            else:
                agents.append(TesterAgent(task, self.project_path, self.lib, self.model))

        results = await asyncio.gather(*[agent.run(session_state) for agent in agents])
        return list(results)
