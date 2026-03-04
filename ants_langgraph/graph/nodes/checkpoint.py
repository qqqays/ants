"""phase_checkpoint_node — HITL gate between workflow phases."""

from __future__ import annotations

from langgraph.types import interrupt

from ..state import ANTSState


def _build_phase_summary(state: ANTSState) -> str:
    phase = state["current_phase"]
    tasks = [t for t in state.get("tasks", []) if t["phase"] == phase]
    completed = sum(1 for t in tasks if t["status"] == "completed")
    total = len(tasks)
    lines = [
        f"=== Phase {phase} 完成摘要 ===",
        f"目标：{state['goal']}",
        f"任务：{completed}/{total} 已完成",
    ]
    for t in tasks:
        status_icon = {"completed": "✅", "needs_redo": "❌", "pending": "⏳"}.get(
            t["status"], "?"
        )
        lines.append(f"  {status_icon} [{t['id']}] {t['title']}")
    return "\n".join(lines)


async def phase_checkpoint_node(state: ANTSState) -> dict:
    """Suspend execution and wait for human approval via LangGraph interrupt().

    Resumes when the caller injects a Command(resume={"action": ...}).
    """
    phase = state["current_phase"]
    summary = _build_phase_summary(state)

    # LangGraph interrupt() suspends the graph and returns the payload to the caller.
    human_response = interrupt(
        {
            "phase": phase,
            "summary": summary,
            "tasks": [t for t in state.get("tasks", []) if t["phase"] == phase],
            "actions": ["approve", "redo", "edit", "abort"],
        }
    )

    decision = human_response.get("action", "approve") if human_response else "approve"
    note = human_response.get("note", "") if human_response else ""

    if decision == "abort":
        return {"workflow_status": "aborted", "human_decision": "abort"}

    if decision == "redo":
        updated_tasks = [
            {**t, "status": "pending", "output": None} if t["phase"] == phase else t
            for t in state.get("tasks", [])
        ]
        return {"tasks": updated_tasks, "human_decision": "redo"}

    if decision == "edit" and phase == 1:
        edited_tasks = human_response.get("edited_tasks", state.get("tasks", []))
        return {"tasks": edited_tasks, "human_decision": "edit"}

    # approve
    return {
        "human_decision": "approve",
        "human_note": note,
        "phase_status": "completed",
    }
