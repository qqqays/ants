"""ProblemDocument — records and retrieves known project issues on-demand."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


ProblemStatus = Literal["open", "resolved", "wont_fix"]

_WRITE_LOCK = asyncio.Lock()


@dataclass
class ProblemEntry:
    """A single recorded project problem."""

    id: str = field(
        default_factory=lambda: (
            f"prob_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            f"_{uuid.uuid4().hex[:6]}"
        )
    )
    title: str = ""
    description: str = ""
    context: str = ""         # Error messages, stack traces, relevant code
    solution: str = ""        # How it was resolved (filled on resolve)
    status: str = "open"      # "open" | "resolved" | "wont_fix"
    tags: list[str] = field(default_factory=list)
    source_agent: str = ""
    session_id: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    resolved_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "context": self.context,
            "solution": self.solution,
            "status": self.status,
            "tags": self.tags,
            "source_agent": self.source_agent,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProblemEntry":
        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            context=data.get("context", ""),
            solution=data.get("solution", ""),
            status=data.get("status", "open"),
            tags=data.get("tags", []),
            source_agent=data.get("source_agent", ""),
            session_id=data.get("session_id", ""),
            created_at=data.get("created_at", ""),
            resolved_at=data.get("resolved_at"),
        )

    def to_prompt_line(self) -> str:
        """Compact representation for prompt injection (≤ 150 tokens)."""
        status_icon = {"open": "⚠️", "resolved": "✅", "wont_fix": "🚫"}.get(
            self.status, "❓"
        )
        solution_part = f" → {self.solution[:150]}" if self.solution else ""
        return (
            f"{status_icon} [{self.id}] {self.title}: "
            f"{self.description[:100]}{solution_part}"
        )


class ProblemDocument:
    """Project-level problem document: record, query, and resolve known issues.

    Stored at ``<project_path>/.ants/problems/problems.jsonl``.
    All agents can load this document on-demand when encountering issues.
    """

    def __init__(self, project_path: str) -> None:
        self._dir = Path(project_path) / ".ants" / "problems"
        self._path = self._dir / "problems.jsonl"
        self._entries: list[ProblemEntry] = []
        self._loaded = False

    # ── Helpers ──────────────────────────────────────────────────────

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    async def _load(self) -> list[ProblemEntry]:
        if self._loaded:
            return self._entries
        self._ensure_dir()
        entries: list[ProblemEntry] = []
        if self._path.exists():
            with self._path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(ProblemEntry.from_dict(json.loads(line)))
                        except json.JSONDecodeError:
                            continue
        self._entries = entries
        self._loaded = True
        return entries

    async def _rewrite(self) -> None:
        async with _WRITE_LOCK:
            with self._path.open("w", encoding="utf-8") as f:
                for e in self._entries:
                    f.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")

    # ── Write ────────────────────────────────────────────────────────

    async def record(
        self,
        title: str,
        description: str,
        context: str = "",
        tags: list[str] | None = None,
        source_agent: str = "",
        session_id: str = "",
    ) -> str:
        """Record a new problem and return its ID."""
        await self._load()
        entry = ProblemEntry(
            title=title,
            description=description,
            context=context,
            tags=tags or [],
            source_agent=source_agent,
            session_id=session_id,
        )
        self._entries.append(entry)
        self._ensure_dir()
        async with _WRITE_LOCK:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        return entry.id

    async def resolve(
        self, problem_id: str, solution: str, status: str = "resolved"
    ) -> bool:
        """Mark a problem as resolved. Returns True if found."""
        await self._load()
        for entry in self._entries:
            if entry.id == problem_id:
                entry.solution = solution
                entry.status = status
                entry.resolved_at = datetime.now(timezone.utc).isoformat()
                await self._rewrite()
                return True
        return False

    # ── Query ────────────────────────────────────────────────────────

    async def query(
        self,
        problem: str,
        top_k: int = 3,
        status_filter: str | None = None,
    ) -> list[ProblemEntry]:
        """Simple keyword-based search over problem titles and descriptions.

        Args:
            problem: Natural language description of the current issue.
            top_k: Maximum number of results to return.
            status_filter: If set, only return entries with this status.

        Returns:
            Up to ``top_k`` problem entries, best-match first.
        """
        await self._load()
        keywords = {w.lower() for w in problem.split() if len(w) > 1}
        scored: list[tuple[int, ProblemEntry]] = []
        for entry in self._entries:
            if status_filter and entry.status != status_filter:
                continue
            haystack = (
                f"{entry.title} {entry.description} {entry.context} "
                f"{' '.join(entry.tags)}"
            ).lower()
            score = sum(1 for kw in keywords if kw in haystack)
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_k]]

    async def list_all(self, status_filter: str | None = None) -> list[ProblemEntry]:
        """Return all problem entries, optionally filtered by status."""
        await self._load()
        if status_filter:
            return [e for e in self._entries if e.status == status_filter]
        return list(self._entries)

    # ── Prompt injection ─────────────────────────────────────────────

    async def to_prompt_section(
        self,
        problem: str = "",
        top_k: int = 3,
        include_resolved: bool = True,
    ) -> str:
        """Return a prompt-injectable section with relevant known problems.

        Args:
            problem: Current problem description for relevance ranking.
            top_k: Max entries to include.
            include_resolved: Whether to include resolved problems.
        """
        if problem:
            entries = await self.query(problem, top_k=top_k)
        else:
            entries = await self.list_all()
            if not include_resolved:
                entries = [e for e in entries if e.status != "resolved"]
            entries = entries[:top_k]

        if not entries:
            return ""

        lines = ["【已知项目问题（按相关度排序）】"]
        for e in entries:
            lines.append(e.to_prompt_line())
        return "\n".join(lines)


def get_problem_document(project_path: str) -> ProblemDocument:
    """Return a ProblemDocument rooted at <project_path>/.ants/problems/."""
    return ProblemDocument(project_path)
