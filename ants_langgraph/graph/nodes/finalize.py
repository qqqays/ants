"""finalize_session_node — write back experiences and mark session complete."""

from __future__ import annotations

from ...experience.library import get_experience_library
from ...shared_context.context import SharedContext
from ..state import ANTSState


async def finalize_session_node(state: ANTSState) -> dict:
    """Finalise the session: prune the experience library and write a summary."""
    project_path = state["project_path"]

    # Prune stale/deprecated experiences
    lib = get_experience_library(project_path)
    await lib.prune()

    # Update session metadata
    ctx = SharedContext(project_path, state["session_id"])
    ctx.mark_complete("completed")

    # Build final summary
    tasks = state.get("tasks", [])
    completed = sum(1 for t in tasks if t["status"] == "completed")
    total = len(tasks)
    meta = await lib.get_meta()

    summary = (
        f"\n[会话完成] 目标：{state['goal']}\n"
        f"任务：{completed}/{total} 已完成\n"
        f"经验库：现有 {meta.total_entries} 条经验\n"
    )

    ctx.append_memory(summary)

    return {
        "workflow_status": "completed",
        "phase_status": "completed",
        "session_memory": state.get("session_memory", "") + summary,
    }
