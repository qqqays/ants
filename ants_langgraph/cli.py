"""ANTS LangGraph CLI — run an ANTS session from the command line."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from langgraph.types import Command

from .graph.builder import build_ants_graph, generate_session_id


def print_progress(event: dict) -> None:
    """Print a compact progress update for a graph event."""
    for node_name, update in event.items():
        if node_name == "__interrupt__":
            continue
        phase = update.get("current_phase", "")
        memory = update.get("session_memory", "")
        if memory:
            last_line = memory.strip().split("\n")[-1]
            print(f"  [{node_name}] {last_line}")
        elif phase:
            print(f"  [{node_name}] Phase {phase}")
        else:
            print(f"  [{node_name}] ✓")


async def run_session(goal: str, project_path: str) -> None:
    """Run an ANTS session interactively, pausing for human approval at each phase."""
    db_path = os.path.join(project_path, ".ants", "checkpoints.db")
    graph = build_ants_graph(db_path=db_path)

    session_id = generate_session_id()
    config = {"configurable": {"thread_id": session_id}}

    initial_state: dict[str, Any] = {
        "session_id": session_id,
        "goal": goal,
        "project_path": project_path,
        "current_phase": 0,
        "tasks": [],
        "messages": [],
        "session_memory": "",
        "experience_budget_used": 0,
        "injected_experience_ids": [],
        "human_decision": None,
        "human_note": None,
        "phase_status": "running",
        "workflow_status": "running",
        "current_task_id": None,
    }

    print(f"\n🚀 启动 ANTS 会话 {session_id}")
    print(f"   目标：{goal}\n")

    async for event in graph.astream(initial_state, config, stream_mode="updates"):
        if "__interrupt__" in event:
            interrupt_data = event["__interrupt__"][0].value
            phase = interrupt_data.get("phase", "?")
            summary = interrupt_data.get("summary", "")
            print(f"\n⏸  Phase {phase} 完成，等待审批")
            print(summary)
            print("\n操作：[Enter] 批准 | [r] 重做 | [e] 编辑任务 | [q] 终止")

            try:
                raw = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                raw = "q"

            action_map = {"": "approve", "r": "redo", "e": "edit", "q": "abort"}
            action = action_map.get(raw, "approve")

            note = ""
            if action == "edit":
                print("（编辑功能暂未在 CLI 实现，将使用原任务清单）")
                action = "approve"

            print(f"→ 决策：{action}\n")

            # Resume the graph
            async for resume_event in graph.astream(
                Command(resume={"action": action, "note": note}),
                config,
                stream_mode="updates",
            ):
                print_progress(resume_event)
        else:
            print_progress(event)

    print("\n✅ ANTS 会话完成")


def main() -> None:
    """CLI entry point: ants-langgraph <goal> [project_path]"""
    import argparse

    parser = argparse.ArgumentParser(
        prog="ants-langgraph",
        description="ANTS — LangGraph-based multi-agent coding assistant",
    )
    parser.add_argument("goal", help="The development goal (natural language)")
    parser.add_argument(
        "project_path",
        nargs="?",
        default=os.getcwd(),
        help="Path to the target project (default: current directory)",
    )

    args = parser.parse_args()
    asyncio.run(run_session(args.goal, args.project_path))


if __name__ == "__main__":
    main()
