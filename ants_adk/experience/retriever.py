"""BM25-based retriever for the experience library (MVP mode)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from .entry import ExperienceEntry, compress_entry


@dataclass
class RetrievedExperience:
    entry: ExperienceEntry
    score: float          # Composite relevance score 0.0 ~ 1.0
    match_reason: str     # Human-readable explanation of the match


def _tokenize(text: str) -> list[str]:
    """Simple tokenizer: splits on whitespace and CJK character boundaries."""
    # Split ASCII words and individual CJK characters
    tokens = re.findall(r"[a-zA-Z0-9_\-\.]+|[\u4e00-\u9fff]", text.lower())
    return tokens


class BM25Retriever:
    """Pure-Python BM25 retriever over ExperienceEntry objects.

    Uses trigger + solution as the document corpus.
    Falls back gracefully when rank_bm25 is unavailable.
    """

    def __init__(self, entries: list[ExperienceEntry]):
        self._entries = entries
        self._corpus = [
            _tokenize(e.trigger + " " + e.solution) for e in entries
        ]
        self._bm25 = self._build_index()

    def _build_index(self):
        try:
            from rank_bm25 import BM25Okapi  # type: ignore
            if self._corpus:
                return BM25Okapi(self._corpus)
        except ImportError:
            pass
        return None

    def query(
        self,
        problem: str,
        agent_id: str,
        categories: list[str] | None = None,
        top_k: int = 5,
        min_score: float = 0.4,
    ) -> list[RetrievedExperience]:
        """Return the top-k most relevant entries for *problem*."""
        if not self._entries:
            return []

        query_tokens = _tokenize(problem)

        if self._bm25 is not None:
            raw_scores = self._bm25.get_scores(query_tokens)
            max_score = max(raw_scores) if max(raw_scores) > 0 else 1.0
            scores = [s / max_score for s in raw_scores]
        else:
            # Fallback: simple overlap ratio
            query_set = set(query_tokens)
            scores = []
            for doc_tokens in self._corpus:
                if not doc_tokens:
                    scores.append(0.0)
                    continue
                overlap = len(query_set & set(doc_tokens))
                scores.append(overlap / max(len(query_set), len(doc_tokens)))

        results: list[RetrievedExperience] = []
        for idx, (entry, score) in enumerate(zip(self._entries, scores)):
            if score < min_score:
                continue
            if entry.status != "active":
                continue
            if entry.scope == "private" and entry.source_agent != agent_id:
                continue
            if categories and entry.category not in categories:
                continue

            matched_tokens = set(query_tokens) & set(self._corpus[idx])
            match_reason = (
                f"关键词匹配: {', '.join(list(matched_tokens)[:5])}"
                if matched_tokens
                else "无关键词匹配"
            )
            results.append(RetrievedExperience(entry=entry, score=score, match_reason=match_reason))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]
