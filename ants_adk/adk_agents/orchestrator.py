"""OrchestratorAgent — Root Agent that manages phase transitions and HITL."""

from __future__ import annotations

import asyncio
from typing import Any

from ..experience.library import get_experience_library
from ..shared_context.context import SharedContext
from .planner import PlannerAgent
from .coder_pool import CoderAgentPool
from .verify_pool import VerifyAgentPool
from .hitl_tool import HumanApprovalTool
from .subagent import SubAgent


SESSION_KEYS = {
    "goal": "ants.goal",
    "project_path": "ants.project_path",
    "tasks": "ants.tasks",
    "agent_plan": "ants.agent_plan",
    "current_phase": "ants.current_phase",
    "session_memory": "ants.session_memory",
    "experience_budget": "ants.experience_budget_used",
    "session_id": "ants.session_id",
}


class OrchestratorAgent:
    """ANTS main orchestrator agent.

    In production ADK this would extend ``google.adk.agents.LlmAgent`` with:
    - ``model="gemini-2.0-flash"``
    - ``tools=[FunctionTool(self.get_phase_summary), FunctionTool(self.request_human_approval)]``
    - ``sub_agents=[PlannerAgent(...), CoderAgentPool(...), VerifyAgentPool(...)]``

    For MVP purposes this class implements the orchestration logic directly,
    exercising all the same sub-agents and HITL tool.

    The Planner now returns an ``agent_plan`` — a list of SubAgent descriptors
    with skill assignments.  The Orchestrator instantiates ``SubAgent`` objects
    for each item in the plan and runs them in the appropriate phase.
    """

    def __init__(self, project_path: str, model: str = "gemini-2.0-flash"):
        self.project_path = project_path
        self.model = model
        self.lib = get_experience_library(project_path)
        self.ctx = SharedContext(project_path)
        self.hitl = HumanApprovalTool()

        self._planner = PlannerAgent(project_path, model=model)
        self._coder_pool = CoderAgentPool(project_path, model=model)
        self._verify_pool = VerifyAgentPool(project_path, model=model)

    def _build_instruction(self) -> str:
        return """
你是 ANTS 多 Agent 编排器，负责协调多个专业 Agent 完成编码任务。

工作流程：
1. 委派 PlannerAgent 生成任务清单和 SubAgent 计划（Phase 1）
2. 调用 request_human_approval(phase=1) 等待人工审批
3. 按 agent_plan 实例化 SubAgent（每个 SubAgent 携带指定 skill），执行编码任务（Phase 2）
4. 调用 request_human_approval(phase=2) 等待人工审批
5. 委派 VerifyAgentPool 执行代码审查和测试（Phase 3）
6. 调用 request_human_approval(phase=3) 等待最终审批

规则：
- 每个阶段完成后必须调用 request_human_approval，不能跳过
- 人工返回 "redo" 时重新执行本阶段
- 人工返回 "abort" 时立即终止
"""

    def get_phase_summary(self, session_state: dict, phase: int) -> str:
        """Build a human-readable summary of a completed phase."""
        tasks = session_state.get(SESSION_KEYS["tasks"], [])
        phase_tasks = [t for t in tasks if t.get("phase") == phase]
        completed = sum(1 for t in phase_tasks if t.get("status") == "completed")
        total = len(phase_tasks)
        goal = session_state.get(SESSION_KEYS["goal"], "")
        agent_plan = session_state.get(SESSION_KEYS["agent_plan"], [])
        _PHASE_NAME = {1: "planning", 2: "development", 3: "testing"}
        phase_name = _PHASE_NAME.get(phase, "")
        phase_agents = [a for a in agent_plan if a.get("phase_name") == phase_name]
        lines = [
            f"=== Phase {phase} 完成摘要 ===",
            f"目标：{goal}",
            f"任务：{completed}/{total} 已完成",
        ]
        if phase_agents:
            lines.append(f"SubAgent：{len(phase_agents)} 个")
            for a in phase_agents:
                lines.append(
                    f"  • [{a['agent_id']}] 技能：{', '.join(a.get('skill_names', []))}"
                )
        for t in phase_tasks:
            icon = {"completed": "✅", "needs_redo": "❌", "pending": "⏳"}.get(t.get("status", ""), "?")
            lines.append(f"  {icon} [{t['id']}] {t['title']}")
        return "\n".join(lines)

    async def _run_subagents_for_phase(
        self,
        phase_name: str,
        agent_plan: list[dict],
        tasks: list[dict],
        session_state: dict,
    ) -> None:
        """Instantiate and run SubAgents for a given phase in parallel."""
        phase_items = [a for a in agent_plan if a.get("phase_name") == phase_name]
        if not phase_items:
            return

        # Build a task lookup
        task_map = {t["id"]: t for t in tasks}

        async def _run_one(plan_item: dict) -> None:
            agent = SubAgent(
                agent_id=plan_item["agent_id"],
                skill_names=plan_item.get("skill_names", []),
                project_path=self.project_path,
                phase_name=plan_item.get("phase_name", ""),
                model=self.model,
            )
            for task_id in plan_item.get("task_ids", []):
                task = task_map.get(task_id)
                if task is None or task.get("status") != "pending":
                    continue
                sub_state = {**session_state, "current_task": task}
                result = await agent.run(sub_state)
                task["status"] = "completed" if result["passed"] else "needs_redo"
                task["output"] = result.get("output")

        await asyncio.gather(*[_run_one(item) for item in phase_items])

    async def run(
        self,
        goal: str,
        session_state: dict,
        human_input_fn=None,
    ) -> dict:
        """Run the full ANTS orchestration workflow.

        Args:
            goal: Natural language goal.
            session_state: Mutable ADK-style session state dict.
            human_input_fn: Async callable ``(approval_data) -> {"action": str}``
                            for HITL. Defaults to CLI input.

        Returns:
            Final session state.
        """
        if human_input_fn is None:
            human_input_fn = _cli_human_input

        session_state[SESSION_KEYS["goal"]] = goal
        session_state[SESSION_KEYS["current_phase"]] = 0

        # ── Phase 1: Planning ────────────────────────────────────────
        print("\n[Phase 1] 规划中...")
        tasks, agent_plan = await self._planner.run(goal, session_state)
        session_state[SESSION_KEYS["tasks"]] = tasks
        session_state[SESSION_KEYS["agent_plan"]] = agent_plan
        session_state[SESSION_KEYS["current_phase"]] = 1

        summary = self.get_phase_summary(session_state, 1)
        approval = await self.hitl.request_approval(phase=1, summary=summary)
        decision = await human_input_fn(approval)
        if decision.get("action") == "abort":
            return {**session_state, "ants.workflow_status": "aborted"}
        if decision.get("action") == "redo":
            tasks, agent_plan = await self._planner.run(goal, session_state)
            session_state[SESSION_KEYS["tasks"]] = tasks
            session_state[SESSION_KEYS["agent_plan"]] = agent_plan

        # ── Phase 2: Execution (skill-based SubAgents) ───────────────
        print("\n[Phase 2] 执行中（SubAgent + Skills）...")
        await self._run_subagents_for_phase(
            "development", agent_plan, tasks, session_state
        )
        # Fallback: also run classic CoderAgentPool for tasks without SubAgent coverage
        covered_ids: set[str] = {
            tid
            for item in agent_plan
            if item.get("phase_name") == "development"
            for tid in item.get("task_ids", [])
        }
        uncovered = [
            t for t in tasks
            if t.get("phase") == 2
            and t.get("status") == "pending"
            and t["id"] not in covered_ids
        ]
        if uncovered:
            await self._coder_pool.execute_tasks(uncovered, session_state)
        session_state[SESSION_KEYS["current_phase"]] = 2

        summary = self.get_phase_summary(session_state, 2)
        approval = await self.hitl.request_approval(phase=2, summary=summary)
        decision = await human_input_fn(approval)
        if decision.get("action") == "abort":
            return {**session_state, "ants.workflow_status": "aborted"}
        if decision.get("action") == "redo":
            for t in tasks:
                if t.get("phase") == 2:
                    t["status"] = "pending"
                    t["output"] = None
            await self._run_subagents_for_phase(
                "development", agent_plan, tasks, session_state
            )

        # ── Phase 3: Verification ────────────────────────────────────
        print("\n[Phase 3] 验证中...")
        await self._run_subagents_for_phase(
            "testing", agent_plan, tasks, session_state
        )
        phase3_tasks = [
            t for t in tasks
            if t.get("phase") == 3 and t.get("status") == "pending"
        ]
        if phase3_tasks:
            await self._verify_pool.execute_tasks(phase3_tasks, session_state)
        session_state[SESSION_KEYS["current_phase"]] = 3

        summary = self.get_phase_summary(session_state, 3)
        approval = await self.hitl.request_approval(phase=3, summary=summary)
        decision = await human_input_fn(approval)
        if decision.get("action") == "abort":
            return {**session_state, "ants.workflow_status": "aborted"}

        # ── Finalize ─────────────────────────────────────────────────
        await self.lib.prune()
        meta = await self.lib.get_meta()
        session_state["ants.workflow_status"] = "completed"
        session_state[SESSION_KEYS["session_memory"]] = (
            session_state.get(SESSION_KEYS["session_memory"], "")
            + f"\n[会话完成] 经验库：现有 {meta.total_entries} 条经验"
        )
        return session_state


async def _cli_human_input(approval_data: dict) -> dict:
    """Default CLI-based HITL input handler."""
    phase = approval_data.get("phase", "?")
    summary = approval_data.get("summary", "")
    print(f"\n⏸  Phase {phase} 完成，等待审批")
    print(summary)
    print("\n操作：[Enter] 批准 | [r] 重做 | [q] 终止")

    try:
        raw = await asyncio.get_running_loop().run_in_executor(None, lambda: input("> ").strip())
    except (EOFError, KeyboardInterrupt):
        raw = "q"

    action_map = {"": "approve", "r": "redo", "q": "abort"}
    return {"action": action_map.get(raw, "approve"), "note": ""}

