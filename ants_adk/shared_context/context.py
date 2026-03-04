"""SharedContext — session-level shared memory stored under .ants/sessions/."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


class SharedContext:
    """Lightweight shared context for a single ANTS session.

    Persists session metadata and a running memory log under
    <project_path>/.ants/sessions/<session_id>/.
    """

    def __init__(self, project_path: str, session_id: str = "") -> None:
        self.project_path = project_path
        self.session_id = session_id
        self._session_dir = Path(project_path) / ".ants" / "sessions" / session_id

    def init_session(self, goal: str) -> None:
        """Create session directory and write initial metadata."""
        self._session_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "session_id": self.session_id,
            "goal": goal,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
        }
        (self._session_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2)
        )

    def append_memory(self, text: str) -> None:
        """Append a line to the session memory log."""
        self._session_dir.mkdir(parents=True, exist_ok=True)
        log_path = self._session_dir / "memory.log"
        with log_path.open("a", encoding="utf-8") as f:
            ts = datetime.now(timezone.utc).isoformat()
            f.write(f"[{ts}] {text}\n")

    def read_memory(self) -> str:
        """Read the full session memory log."""
        log_path = self._session_dir / "memory.log"
        if not log_path.exists():
            return ""
        return log_path.read_text(encoding="utf-8")

    def mark_complete(self, status: str = "completed") -> None:
        """Update session status in metadata."""
        meta_path = self._session_dir / "meta.json"
        if not meta_path.exists():
            return
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["status"] = status
        meta["finished_at"] = datetime.now(timezone.utc).isoformat()
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
