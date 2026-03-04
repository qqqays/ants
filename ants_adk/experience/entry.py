"""ExperienceEntry dataclass — single unit stored in the experience library."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


CATEGORIES = Literal[
    "environment",
    "tool_usage",
    "project_convention",
    "debug_pattern",
    "domain_knowledge",
]

SCOPES = Literal["shared", "private"]
STATUSES = Literal["active", "deprecated", "merged"]


@dataclass
class ExperienceEntry:
    # ── Identity ────────────────────────────────────────────────────
    id: str = field(default_factory=lambda: f"exp_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}")
    source_agent: str = ""
    session_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # ── Classification ───────────────────────────────────────────────
    category: str = "environment"
    tags: list[str] = field(default_factory=list)
    scope: str = "shared"  # "shared" | "private"

    # ── Content ─────────────────────────────────────────────────────
    trigger: str = ""      # Problem/scenario that triggered this experience
    solution: str = ""     # Concrete, actionable solution
    context: dict = field(default_factory=dict)

    # ── Quality ─────────────────────────────────────────────────────
    usefulness_score: float = 0.5
    use_count: int = 0
    last_used_at: str | None = None

    # ── Lifecycle ───────────────────────────────────────────────────
    status: str = "active"  # "active" | "deprecated" | "merged"
    superseded_by: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_agent": self.source_agent,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "category": self.category,
            "tags": self.tags,
            "scope": self.scope,
            "trigger": self.trigger,
            "solution": self.solution,
            "context": self.context,
            "usefulness_score": self.usefulness_score,
            "use_count": self.use_count,
            "last_used_at": self.last_used_at,
            "status": self.status,
            "superseded_by": self.superseded_by,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExperienceEntry":
        return cls(
            id=data.get("id", ""),
            source_agent=data.get("source_agent", ""),
            session_id=data.get("session_id", ""),
            created_at=data.get("created_at", ""),
            category=data.get("category", "environment"),
            tags=data.get("tags", []),
            scope=data.get("scope", "shared"),
            trigger=data.get("trigger", ""),
            solution=data.get("solution", ""),
            context=data.get("context", {}),
            usefulness_score=data.get("usefulness_score", 0.5),
            use_count=data.get("use_count", 0),
            last_used_at=data.get("last_used_at"),
            status=data.get("status", "active"),
            superseded_by=data.get("superseded_by"),
        )


def compress_entry(entry: ExperienceEntry) -> str:
    """Compress an experience entry to ≤150 tokens for prompt injection.

    Format: [{category}] {trigger} → {solution}
    """
    trigger = entry.trigger[:80]
    solution = entry.solution[:200]
    return f"[{entry.category}] {trigger} → {solution}"
