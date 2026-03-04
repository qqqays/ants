"""HumanApprovalTool — HITL tool for Google ADK long-running pattern."""

from __future__ import annotations


class HumanApprovalTool:
    """ANTS HITL tool for the Google ADK implementation.

    Implements the long-running function call pattern:
    1. OrchestratorAgent calls ``request_approval(phase, summary)``
    2. ADK Runner returns a ``LongRunningFunctionCall`` event to the caller
    3. The CLI/Web frontend displays the approval UI
    4. On human input, the caller calls ``runner.resume()`` with the decision
    """

    async def request_approval(self, phase: int, summary: str) -> dict:
        """Suspend the agent and wait for human approval.

        This function returns a ``pending`` status dict which ADK interprets as
        a long-running tool call, pausing the agent until ``runner.resume()`` is
        called with the human decision.

        Args:
            phase: The workflow phase that just completed (1, 2, or 3).
            summary: Human-readable summary of the completed phase.

        Returns:
            Pending status dict (resolved by external resume call).
        """
        return {
            "status": "pending",
            "phase": phase,
            "summary": summary,
            "message": f"Phase {phase} 完成，请审批后继续",
            "actions": ["approve", "redo", "abort"],
        }
