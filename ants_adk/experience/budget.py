"""ExperienceBudgetManager — token budget enforcement for experience injection."""

from __future__ import annotations

from .entry import compress_entry
from .retriever import RetrievedExperience


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token (GPT-4 tokenizer average)."""
    return max(1, len(text) // 4)


class ExperienceBudgetManager:
    """Manage per-task experience token budget to prevent context overflow.

    Enforces a hard cap of MAX_BUDGET tokens across all injected experiences.
    When adding new experiences, higher-scored entries are preferred.
    """

    MAX_BUDGET: int = 2000  # tokens

    def __init__(self) -> None:
        self._used: int = 0
        self._entries: list[RetrievedExperience] = []

    def try_add(self, experiences: list[RetrievedExperience]) -> list[RetrievedExperience]:
        """Try to add experiences, highest-scored first. Returns accepted entries."""
        accepted: list[RetrievedExperience] = []
        for exp in sorted(experiences, key=lambda e: e.score, reverse=True):
            text = compress_entry(exp.entry)
            cost = estimate_tokens(text)
            if self._used + cost <= self.MAX_BUDGET:
                self._used += cost
                self._entries.append(exp)
                accepted.append(exp)
        return accepted

    def to_prompt_section(self) -> str:
        """Format accepted experiences into a prompt-injectable text block."""
        if not self._entries:
            return ""
        lines = ["【项目历史经验（按相关度排序）】"]
        for exp in self._entries:
            lines.append(compress_entry(exp.entry))
        return "\n".join(lines)
