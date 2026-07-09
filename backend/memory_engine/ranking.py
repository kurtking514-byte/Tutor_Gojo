"""
memory_engine.ranking - relevance ordering of memory items that have
already been retrieved.

Status: LIVE, but disconnected. Nothing here is called by any existing
code.

MemoryRanker takes a MemoryContext (the candidate subset a
MemoryRetriever already selected) and reorders each of its lists by
simple keyword overlap with the current user message - how many of the
message's keywords show up in an item's searchable fields. This is
lexical overlap counting, not relevance/semantic scoring: no AI, no
embeddings, no fuzzy matching, stdlib only. It performs no retrieval of
its own (it never looks at a MemorySnapshot or excludes anything) and
builds no prompt text.
"""

import re
from typing import List, Tuple, TypeVar

from memory_engine.models import MemoryContext

T = TypeVar("T")

# Same stopword list and tokenizer as memory_engine.retrieval, kept as
# a small local copy (rather than an import) since those are private
# helpers on MemoryRetriever. Keeping the two in lockstep matters: the
# keywords used to rank an item here should be the same keywords that
# could have caused it to be retrieved in the first place.
_STOPWORDS = {
    "a", "an", "and", "are", "at", "be", "can", "do", "for", "how",
    "i", "in", "is", "it", "me", "my", "of", "on", "please", "show",
    "teach", "tell", "the", "to", "want", "what", "with", "you",
}

_WORD_RE = re.compile(r"[a-z0-9]+")

# The exact same searchable fields per category used in
# memory_engine.retrieval.MemoryRetriever.retrieve(), keyed by the
# MemoryContext attribute name they live under.
_SEARCHABLE_FIELDS = {
    "strengths": ("name", "topic", "subtopic", "notes"),
    "weak_topics": ("topic", "subtopic"),
    "active_misconceptions": ("name", "topic", "subtopic", "notes"),
    "mistake_patterns": ("description", "topic", "notes"),
    "learning_preferences": ("preference_key", "preference_value", "notes"),
    "recent_journal_entries": ("summary", "topics_covered", "unfinished_business"),
    "open_curiosity_backlog": ("question", "notes"),
}


class MemoryRanker:
    """Reorders the lists inside a MemoryContext by keyword overlap
    with the current user message.

    Only ranks; never retrieves, filters out, scores semantically, or
    builds prompt text.
    """

    def rank(self, context: MemoryContext, user_message: str) -> MemoryContext:
        keywords = self._extract_keywords(user_message)

        return MemoryContext(
            strengths=self._rank_list(context.strengths, keywords, "strengths"),
            weak_topics=self._rank_list(
                context.weak_topics, keywords, "weak_topics"
            ),
            active_misconceptions=self._rank_list(
                context.active_misconceptions, keywords, "active_misconceptions"
            ),
            mistake_patterns=self._rank_list(
                context.mistake_patterns, keywords, "mistake_patterns"
            ),
            learning_preferences=self._rank_list(
                context.learning_preferences, keywords, "learning_preferences"
            ),
            recent_journal_entries=self._rank_list(
                context.recent_journal_entries, keywords, "recent_journal_entries"
            ),
            open_curiosity_backlog=self._rank_list(
                context.open_curiosity_backlog, keywords, "open_curiosity_backlog"
            ),
            # Ranking never computes confidence - it only reorders
            # already-retrieved items. Pass the input value through
            # untouched, including None.
            current_confidence=context.current_confidence,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_keywords(self, user_message: str) -> List[str]:
        """Lowercases and tokenizes the user message into simple
        alphanumeric keywords, dropping overly generic stopwords.
        Identical logic to MemoryRetriever._extract_keywords.
        """
        words = _WORD_RE.findall(user_message.lower())
        return [w for w in words if w not in _STOPWORDS]

    def _rank_list(
        self,
        items: List[T],
        keywords: List[str],
        category: str,
    ) -> List[T]:
        """Returns a NEW list containing the same item objects as
        `items`, sorted by descending keyword-overlap score. Ties keep
        their original relative order (Python's sort is stable, and
        `reverse=True` does not disturb that stability).
        """
        field_names = _SEARCHABLE_FIELDS[category]
        if not keywords:
            return list(items)
        return sorted(
            items,
            key=lambda item: self._score(item, field_names, keywords),
            reverse=True,
        )

    def _score(self, item: T, field_names: Tuple[str, ...], keywords: List[str]) -> int:
        """Counts how many distinct keywords appear anywhere in the
        item's searchable fields. Simple lexical overlap - not a
        relevance/semantic score.
        """
        haystack = self._field_text(item, field_names)
        return sum(1 for keyword in keywords if keyword in haystack)

    def _field_text(self, item: T, field_names: Tuple[str, ...]) -> str:
        """Concatenates the requested fields of `item` into one
        lowercase string for keyword counting. Fields that are lists
        of strings (e.g. JournalEntry.topics_covered) are joined in;
        missing/None fields are skipped. Identical logic to
        MemoryRetriever._field_text.
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
