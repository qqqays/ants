"""reflect() — extract and persist new experiences after task completion."""

from __future__ import annotations

import asyncio
from typing import Any

from .entry import ExperienceEntry
from .library import ExperienceLibrary


async def build_reflection_input(task: dict, result: dict) -> dict:
    """Build a structured dict from task + result for LLM-based reflection.

    In MVP mode this returns a minimal heuristic extraction.
    Replace the body with an LLM call for richer extraction.
    """
    output = result.get("output", {}) or {}
    error = output.get("error", "")
    code_changes = output.get("code_changes", "")
    notes = output.get("notes", "")

    entries: list[dict] = []

    # Heuristic: if there was an error, record it as debug_pattern experience
    if error:
        entries.append({
            "category": "debug_pattern",
            "trigger": f"Task '{task.get('title', '')}' produced error: {error[:200]}",
            "solution": notes or code_changes[:300] or "See task output for details.",
            "tags": ["error", task.get("assigned_agent", "unknown")],
        })

    # Heuristic: record any notable solution as project_convention
    if notes and not error:
        entries.append({
            "category": "project_convention",
            "trigger": f"Task '{task.get('title', '')}': {task.get('description', '')[:100]}",
            "solution": notes[:300],
            "tags": [task.get("assigned_agent", "unknown")],
        })

    return {"entries": entries}


async def reflect_and_save(
    task: dict,
    result: dict,
    lib: ExperienceLibrary,
    session_id: str = "",
) -> None:
    """Extract experiences from a completed task and persist them.

    This is called asynchronously so it does not block the main workflow.
    """
    try:
        reflection = await build_reflection_input(task, result)
        for entry_data in reflection.get("entries", []):
            entry = ExperienceEntry(
                source_agent=task.get("assigned_agent", "unknown"),
                session_id=session_id,
                category=entry_data.get("category", "project_convention"),
                trigger=entry_data.get("trigger", ""),
                solution=entry_data.get("solution", ""),
                tags=entry_data.get("tags", []),
                scope="shared",
            )
            if entry.trigger and entry.solution:
                await lib.add(entry)
    except Exception:  # noqa: BLE001
        # reflect() must never crash the main workflow
        pass
