"""build_ants_graph() — assemble and compile the ANTS LangGraph StateGraph."""

from __future__ import annotations

import uuid

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore

from .state import ANTSState
from .nodes import (
    setup_session,
    planner_node,
    phase_checkpoint_node,
    execution_phase_node,
    verification_phase_node,
    finalize_session_node,
)


def route_after_checkpoint(state: ANTSState) -> str:
    """Route execution based on the human decision at a phase boundary."""
    decision = state.get("human_decision")
    if decision == "abort":
        return "abort"
    if decision == "redo":
        return "redo"
    return "proceed"


def route_after_workflow(state: ANTSState) -> str:
    """Exit the graph if it was aborted."""
    if state.get("workflow_status") == "aborted":
        return "abort"
    return "proceed"


def build_ants_graph(db_path: str = ".ants/checkpoints.db"):
    """Build and compile the ANTS workflow graph.

    Args:
        db_path: Path to the SQLite checkpoint database.

    Returns:
        A compiled LangGraph CompiledStateGraph ready to stream.
    """
    graph = StateGraph(ANTSState)

    # ── Register nodes ───────────────────────────────────────────────
    graph.add_node("setup_session", setup_session)
    graph.add_node("planner", planner_node)
    graph.add_node("phase1_checkpoint", phase_checkpoint_node)
    graph.add_node("execution_phase", execution_phase_node)
    graph.add_node("phase2_checkpoint", phase_checkpoint_node)
    graph.add_node("verification_phase", verification_phase_node)
    graph.add_node("phase3_checkpoint", phase_checkpoint_node)
    graph.add_node("finalize", finalize_session_node)

    # ── Register edges ───────────────────────────────────────────────
    graph.set_entry_point("setup_session")
    graph.add_edge("setup_session", "planner")
    graph.add_edge("planner", "phase1_checkpoint")

    # Phase 1 checkpoint routing
    graph.add_conditional_edges(
        "phase1_checkpoint",
        route_after_checkpoint,
        {
            "proceed": "execution_phase",
            "redo": "planner",
            "abort": END,
        },
    )

    graph.add_edge("execution_phase", "phase2_checkpoint")

    # Phase 2 checkpoint routing
    graph.add_conditional_edges(
        "phase2_checkpoint",
        route_after_checkpoint,
        {
            "proceed": "verification_phase",
            "redo": "execution_phase",
            "abort": END,
        },
    )

    graph.add_edge("verification_phase", "phase3_checkpoint")

    # Phase 3 checkpoint routing
    graph.add_conditional_edges(
        "phase3_checkpoint",
        route_after_checkpoint,
        {
            "proceed": "finalize",
            "redo": "verification_phase",
            "abort": END,
        },
    )

    graph.add_edge("finalize", END)

    # SQLite checkpointer (local file, no Redis required)
    import os
    db_dir = os.path.dirname(db_path) or "."
    os.makedirs(db_dir, exist_ok=True)
    checkpointer = SqliteSaver.from_conn_string(db_path)

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=[
            "phase1_checkpoint",
            "phase2_checkpoint",
            "phase3_checkpoint",
        ],
    )


def generate_session_id() -> str:
    """Generate a unique session ID."""
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"session_{ts}_{uuid.uuid4().hex[:6]}"
