"""ExperienceLibrary — project-level experience store shared by all agents."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .entry import ExperienceEntry, compress_entry
from .retriever import BM25Retriever, RetrievedExperience

CATEGORY_FILES = [
    "environment",
    "tool_usage",
    "project_convention",
    "debug_pattern",
    "domain_knowledge",
]

_WRITE_LOCK = asyncio.Lock()


class LibraryMeta:
    def __init__(self, total_entries: int, last_updated: str):
        self.total_entries = total_entries
        self.last_updated = last_updated


class ExperienceLibrary:
    """Project-level experience library. All agents share a single instance.

    In MVP mode (embed_fn=None) uses pure BM25 keyword retrieval.
    When embed_fn is provided, hybrid BM25 + vector retrieval is used.
    """

    def __init__(
        self,
        experience_dir: str,
        embed_fn: Callable[[str], list[float]] | None = None,
    ):
        self.dir = Path(experience_dir)
        self.embed_fn = embed_fn
        self._entries_dir = self.dir / "entries"
        self._meta_path = self.dir / "meta.json"
        self._retriever: BM25Retriever | None = None
        self._all_entries: list[ExperienceEntry] = []

    # ── Initialisation ───────────────────────────────────────────────

    def _ensure_dirs(self) -> None:
        self._entries_dir.mkdir(parents=True, exist_ok=True)

    def _category_path(self, category: str) -> Path:
        return self._entries_dir / f"{category}.jsonl"

    # ── Write ────────────────────────────────────────────────────────

    async def add(self, entry: ExperienceEntry) -> str:
        """Write one experience entry. Returns the stored ID.

        Performs deduplication: if a near-identical entry already exists
        (score ≥ 0.85), merges by updating use_count and solution instead
        of creating a new entry.
        """
        self._ensure_dirs()
        await self._load_all()

        # Deduplication
        if self._retriever:
            dupes = self._retriever.query(
                problem=entry.trigger,
                agent_id=entry.source_agent,
                categories=[entry.category],
                top_k=1,
                min_score=0.85,
            )
            if dupes:
                existing = dupes[0].entry
                existing.use_count += 1
                existing.solution = entry.solution  # Update with newer solution
                existing.last_used_at = datetime.now(timezone.utc).isoformat()
                await self._rewrite_category(existing.category)
                self._retriever = BM25Retriever(self._all_entries)
                return existing.id

        # Append new entry
        async with _WRITE_LOCK:
            path = self._category_path(entry.category)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

        self._all_entries.append(entry)
        self._retriever = BM25Retriever(self._all_entries)
        await self._save_meta()
        return entry.id

    async def _rewrite_category(self, category: str) -> None:
        """Rewrite JSONL file for a category (used during merge)."""
        async with _WRITE_LOCK:
            path = self._category_path(category)
            entries = [e for e in self._all_entries if e.category == category]
            with path.open("w", encoding="utf-8") as f:
                for e in entries:
                    f.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")

    # ── Read / retrieval ─────────────────────────────────────────────

    async def _load_all(self) -> list[ExperienceEntry]:
        """Load all active entries from disk into memory."""
        if self._all_entries:
            return self._all_entries

        self._ensure_dirs()
        entries: list[ExperienceEntry] = []
        for cat in CATEGORY_FILES:
            path = self._category_path(cat)
            if not path.exists():
                continue
            with path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(ExperienceEntry.from_dict(json.loads(line)))
                        except json.JSONDecodeError:
                            continue

        self._all_entries = entries
        self._retriever = BM25Retriever(entries)
        return entries

    async def query(
        self,
        problem: str,
        agent_id: str,
        categories: list[str] | None = None,
        top_k: int = 5,
        min_score: float = 0.4,
    ) -> list[RetrievedExperience]:
        """Retrieve the most relevant experiences for a problem description.

        MVP: pure BM25.  Future: BM25 × 0.4 + vector × 0.6 when embed_fn set.
        """
        await self._load_all()
        if not self._retriever:
            return []
        return self._retriever.query(
            problem=problem,
            agent_id=agent_id,
            categories=categories,
            top_k=top_k,
            min_score=min_score,
        )

    async def list_all(self) -> list[ExperienceEntry]:
        """Return all loaded entries."""
        return await self._load_all()

    # ── Feedback ─────────────────────────────────────────────────────

    async def feedback(self, entry_id: str, helpful: bool | None) -> None:
        """Record whether an experience was helpful.

        helpful=True  → usefulness_score += 0.1, use_count += 1
        helpful=False → usefulness_score -= 0.1
        helpful=None  → mark as "loaded" only (use_count += 1)
        """
        await self._load_all()
        for entry in self._all_entries:
            if entry.id == entry_id:
                entry.use_count += 1
                entry.last_used_at = datetime.now(timezone.utc).isoformat()
                if helpful is True:
                    entry.usefulness_score = min(1.0, entry.usefulness_score + 0.1)
                elif helpful is False:
                    entry.usefulness_score = max(0.0, entry.usefulness_score - 0.1)
                    if entry.usefulness_score < 0.2 and entry.use_count >= 3:
                        entry.status = "deprecated"
                await self._rewrite_category(entry.category)
                break

    # ── Meta ─────────────────────────────────────────────────────────

    async def get_meta(self) -> LibraryMeta:
        entries = await self._load_all()
        return LibraryMeta(
            total_entries=len(entries),
            last_updated=datetime.now(timezone.utc).isoformat(),
        )

    async def _save_meta(self) -> None:
        meta = {
            "total_entries": len(self._all_entries),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        self._meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    # ── Maintenance ──────────────────────────────────────────────────

    async def rebuild_index(self) -> None:
        """Rebuild BM25 index from current entries on disk."""
        self._all_entries = []
        self._retriever = None
        await self._load_all()

    async def prune(self, max_entries_per_category: int = 200) -> None:
        """Remove deprecated entries and prune low-quality ones if over cap."""
        await self._load_all()
        for cat in CATEGORY_FILES:
            cat_entries = [e for e in self._all_entries if e.category == cat]
            # Remove deprecated
            cat_entries = [e for e in cat_entries if e.status != "deprecated"]
            # Prune by score if over cap
            if len(cat_entries) > max_entries_per_category:
                cat_entries.sort(key=lambda e: e.usefulness_score, reverse=True)
                cat_entries = cat_entries[:max_entries_per_category]
            other_entries = [e for e in self._all_entries if e.category != cat]
            self._all_entries = other_entries + cat_entries

        # Rewrite all
        for cat in CATEGORY_FILES:
            await self._rewrite_category(cat)
        self._retriever = BM25Retriever(self._all_entries)
        await self._save_meta()


def get_experience_library(project_path: str) -> ExperienceLibrary:
    """Return an ExperienceLibrary rooted at <project_path>/.ants/experience/."""
    exp_dir = os.path.join(project_path, ".ants", "experience")
    return ExperienceLibrary(exp_dir)
