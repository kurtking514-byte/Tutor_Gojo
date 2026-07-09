"""
memory_engine.retrieval - future replacement for the aggregation and
filtering logic currently split between memory_service.get_memory_context()
and chat_service._format_memory_context().

Status: LIVE, but disconnected. Nothing here is called by any existing
code.

MemoryRetriever narrows a full MemorySnapshot down to the subset of
memories that mention something in the current user message. This is
lightweight keyword filtering only - a search-space reduction, not a
ranking or relevance-scoring step. No embeddings, no AI, no vector
search, no fuzzy matching: just case-insensitive substring checks
against a handful of text fields per dataclass, using only the Python
standard library.
"""

import re
from typing import Iterable, List, TypeVar

from memory_engine.models import MemoryContext, MemorySnapshot, TopicMasteryEntry

T = TypeVar("T")

# Common words that are too generic to act as useful keywords (e.g. the
# verbs students naturally use to phrase a request). Filtering these
# out keeps matching focused on the actual subject matter without
# introducing any scoring or ranking behavior.
_STOPWORDS = {
    "a", "an", "and", "are", "at", "be", "can", "do", "for", "how",
    "i", "in", "is", "it", "me", "my", "of", "on", "please", "show",
    "teach", "tell", "the", "to", "want", "what", "with", "you",
}

_WORD_RE = re.compile(r"[a-z0-9]+")

# Mastery levels that qualify a TopicMasteryEntry as "weak" for the
# purposes of weak_topics retrieval. Applied before keyword filtering
# so that only genuinely weak topics are ever eligible - restores the
# semantics previously enforced in chat_service._format_memory_context().
_WEAK_MASTERY_LEVELS = {"not_started", "shaky"}


class MemoryRetriever:
    """Turns a full MemorySnapshot plus the current user message into
    the candidate subset worth considering for this turn.

    Only selects; never ranks, scores, or builds prompt text.
    """

    def retrieve(
        self,
        snapshot: MemorySnapshot,
        user_message: str,
    ) -> MemoryContext:
        keywords = self._extract_keywords(user_message)

        return MemoryContext(
            strengths=self._filter(
                snapshot.strengths, keywords, ("name", "topic", "subtopic", "notes")
            ),
            weak_topics=self._filter(
                self._weak_candidates(snapshot.topic_mastery),
                keywords,
                ("topic", "subtopic"),
            ),
            active_misconceptions=self._filter(
                snapshot.misconceptions,
                keywords,
                ("name", "topic", "subtopic", "notes"),
            ),
            mistake_patterns=self._filter(
                snapshot.mistake_patterns,
                keywords,
                ("description", "topic", "notes"),
            ),
            learning_preferences=self._filter(
                snapshot.learning_preferences,
                keywords,
                ("preference_key", "preference_value", "notes"),
            ),
            recent_journal_entries=self._filter(
                snapshot.journal_entries,
                keywords,
                ("summary", "topics_covered", "unfinished_business"),
            ),
            open_curiosity_backlog=self._filter(
                snapshot.curiosity_backlog, keywords, ("question", "notes")
            ),
            # Deciding how confident the student currently is would
            # require weighing/ranking the retrieved memories, which is
            # explicitly out of scope for a retriever that only selects
            # candidates. Left unset here.
            current_confidence=None,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _weak_candidates(
        self, topic_mastery: Iterable[TopicMasteryEntry]
    ) -> List[TopicMasteryEntry]:
        """Restricts topic_mastery to entries whose mastery_level marks
        them as weak, prior to any keyword filtering. This mirrors the
        legacy chat_service._format_memory_context() behavior, which
        only ever surfaced "not_started"/"shaky" topics as weak.
        """
        return [
            item
            for item in topic_mastery
            if getattr(item, "mastery_level", None) in _WEAK_MASTERY_LEVELS
        ]

    def _extract_keywords(self, user_message: str) -> List[str]:
        """Lowercases and tokenizes the user message into simple
        alphanumeric keywords, dropping overly generic stopwords.
        """
        words = _WORD_RE.findall(user_message.lower())
        return [w for w in words if w not in _STOPWORDS]

    def _filter(
        self,
        candidates: Iterable[T],
        keywords: List[str],
        field_names: tuple,
    ) -> List[T]:
        """Returns the subset of `candidates` whose given text fields
        contain at least one of `keywords`. Preserves the original
        dataclass instances - nothing is converted or copied.
        """
        if not keywords:
            return []
        return [
            item
            for item in candidates
            if self._matches(item, field_names, keywords)
        ]

    def _matches(self, item: T, field_names: tuple, keywords: List[str]) -> bool:
        haystack = self._field_text(item, field_names)
        return any(keyword in haystack for keyword in keywords)

    def _field_text(self, item: T, field_names: tuple) -> str:
        """Concatenates the requested fields of `item` into one
        lowercase string for substring matching. Fields that are
        lists of strings (e.g. JournalEntry.topics_covered) are joined
        in; missing/None fields are skipped.
        """
        parts: List[str] = []
        for name in field_names:
            value = getattr(item, name, None)
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                parts.extend(str(v) for v in value if v is not None)
            else:
                parts.append(str(value))
        return " ".join(parts).lower()
