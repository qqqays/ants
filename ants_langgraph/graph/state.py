"""ANTSState — LangGraph StateGraph definition for the ANTS workflow."""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages


class TaskItem(TypedDict):
    id: str
    title: str
    description: str
    assigned_agent: str
    phase: int
    depends_on: list[str]
    status: Literal["pending", "in_progress", "completed", "needs_redo", "skipped"]
    output: dict | None


class ANTSState(TypedDict):
    # ── Session core ────────────────────────────────────────────────
    session_id: str
    goal: str
    project_path: str
    current_phase: int          # 1=planning, 2=execution, 3=verification

    # ── Task management ─────────────────────────────────────────────
    tasks: list[TaskItem]       # Produced by Planner, updated by Orchestrator
    current_task_id: str | None

    # ── Messages / memory ───────────────────────────────────────────
    messages: Annotated[list, add_messages]  # Streaming-compatible message flow
    session_memory: str         # Accumulated step summary (each node appends)

    # ── Experience context (progressive disclosure state) ───────────
    experience_budget_used: int           # Tokens spent on experiences so far
    injected_experience_ids: list[str]    # IDs already injected (avoid dupes)

    # ── Human-in-the-loop ───────────────────────────────────────────
    human_decision: str | None   # "approve" | "redo" | "edit" | "abort"
    human_note: str | None

    # ── Flow control ────────────────────────────────────────────────
    phase_status: Literal["running", "waiting_human", "completed"]
    workflow_status: Literal["running", "paused", "completed", "aborted"]
