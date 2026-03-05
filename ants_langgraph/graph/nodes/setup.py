"""setup_session node — initialise a new ANTS session."""

from __future__ import annotations

import os
from pathlib import Path

from ...experience.library import get_experience_library
from ...shared_context.context import SharedContext
from ..state import ANTSState


async def setup_session(state: ANTSState) -> dict:
    """Initialise the session: scan the codebase and warm up the experience library.

    Returns a partial state update (only the keys that changed).
    """
    project_path = state["project_path"]
    session_id = state["session_id"]

    # Count files in the project (simple scan — Tree-sitter indexing is out of MVP scope)
    file_count = sum(
        len(files)
        for _, _, files in os.walk(project_path)
        if not any(part.startswith(".") for part in _.split(os.sep))
    )

    # Initialise session directory
    ctx = SharedContext(project_path, session_id)
    ctx.init_session(state["goal"])

    # Warm up experience library metadata
    lib = get_experience_library(project_path)
    meta = await lib.get_meta()

    memory_line = (
        f"[会话启动] 目标：{state['goal']}\n"
        f"代码库：{file_count} 个文件\n"
        f"经验库：已有 {meta.total_entries} 条经验\n"
    )

    return {
        "session_memory": memory_line,
        "experience_budget_used": 0,
        "injected_experience_ids": [],
        "agent_plan": [],
        "loaded_skill_names": [],
    }
