"""ANTS Google ADK CLI — run an ANTS session using the ADK orchestrator."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from .adk_agents.orchestrator import OrchestratorAgent


async def run_session(goal: str, project_path: str) -> None:
    """Run an ANTS ADK session interactively."""
    session_id = f"session_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    # ADK Session State (maps to google.adk.sessions.Session.state)
    session_state: dict = {
        "ants.session_id": session_id,
        "ants.project_path": project_path,
        "ants.session_memory": f"[会话启动] 目标：{goal}\n",
        "ants.workflow_status": "running",
    }

    print(f"\n🚀 启动 ANTS ADK 会话 {session_id}")
    print(f"   目标：{goal}\n")

    orchestrator = OrchestratorAgent(project_path)
    final_state = await orchestrator.run(goal, session_state)

    status = final_state.get("ants.workflow_status", "unknown")
    print(f"\n{'✅ 会话完成' if status == 'completed' else '🛑 会话终止'} (状态: {status})")
    memory = final_state.get("ants.session_memory", "")
    if memory:
        print("\n会话摘要:")
        print(memory.strip())


def main() -> None:
    """CLI entry point: ants-adk <goal> [project_path]"""
    import argparse

    parser = argparse.ArgumentParser(
        prog="ants-adk",
        description="ANTS — Google ADK-based multi-agent coding assistant",
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
