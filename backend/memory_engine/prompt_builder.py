"""
memory_engine.prompt_builder - future replacement for
chat_service._format_memory_context().

Status: LIVE, but disconnected. Nothing here is called by any existing
code.

PromptBuilder turns an already-retrieved, already-ranked MemoryContext
into the compact Markdown block meant for the model prompt. It is a
pure serializer: it does not decide which memories matter (that's
MemoryRetriever's job) and it does not decide their order (that's
MemoryRanker's job). It reads each item's existing fields and writes
one line per item, in the order it was given, and never touches the
MemoryContext or the objects inside it.
"""

from typing import List, Optional

from memory_engine.models import (
    CuriosityItem,
    JournalEntry,
    LearningPreference,
    MemoryContext,
    Misconception,
    MistakePattern,
    Strength,
    TopicMasteryEntry,
)

# (MemoryContext attribute name, section header) - listed in the exact
# order the fields are declared on MemoryContext, so the output section
# order always matches the dataclass and never has to be guessed at.
_LIST_SECTIONS = (
    ("strengths", "Strengths"),
    ("weak_topics", "Weak Topics"),
    ("active_misconceptions", "Active Misconceptions"),
    ("mistake_patterns", "Mistake Patterns"),
    ("learning_preferences", "Learning Preferences"),
    ("recent_journal_entries", "Recent Journal Entries"),
    ("open_curiosity_backlog", "Curiosity Backlog"),
)


class PromptBuilder:
    """Serializes a MemoryContext into a Markdown block.

    No filtering, no ranking, no mutation - just formatting. Item
    order is always preserved exactly as given.
    """

    def build(self, context: MemoryContext) -> str:
        sections: List[str] = []

        for attr_name, header in _LIST_SECTIONS:
            items = getattr(context, attr_name)
            lines = [self._format_item(item) for item in items]
            if lines:
                sections.append(self._render_section(header, lines))

        confidence_line = self._format_confidence(context.current_confidence)
        if confidence_line is not None:
            sections.append(f"### Confidence\n{confidence_line}")

        if not sections:
            return ""

        return "## Student Memory\n\n" + "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Section rendering
    # ------------------------------------------------------------------

    def _render_section(self, header: str, lines: List[str]) -> str:
        bullets = "\n".join(f"- {line}" for line in lines)
        return f"### {header}\n{bullets}"

    # ------------------------------------------------------------------
    # Per-item formatting
    #
    # Each formatter reads only the real fields already defined on that
    # dataclass in models.py and joins them into a single readable
    # line. Nothing is invented, nothing is scored, nothing is mutated.
    # ------------------------------------------------------------------

    def _format_item(self, item) -> str:
        if isinstance(item, Strength):
            return self._format_strength(item)
        if isinstance(item, TopicMasteryEntry):
            return self._format_topic_mastery(item)
        if isinstance(item, Misconception):
            return self._format_misconception(item)
        if isinstance(item, MistakePattern):
            return self._format_mistake_pattern(item)
        if isinstance(item, LearningPreference):
            return self._format_learning_preference(item)
        if isinstance(item, JournalEntry):
            return self._format_journal_entry(item)
        if isinstance(item, CuriosityItem):
            return self._format_curiosity_item(item)
        # Defensive fallback - should never trigger given MemoryContext's
        # declared field types, but avoids silently dropping an item.
        return str(item)

    def _format_strength(self, item: Strength) -> str:
        return item.name

    def _format_topic_mastery(self, item: TopicMasteryEntry) -> str:
        if item.subtopic:
            return f"{item.topic} ({item.subtopic})"
        return item.topic

    def _format_misconception(self, item: Misconception) -> str:
        return item.name

    def _format_mistake_pattern(self, item: MistakePattern) -> str:
        return item.description

    def _format_learning_preference(self, item: LearningPreference) -> str:
        # preference_value is the human-readable statement of the
        # preference (e.g. "wants examples first"); preference_key is
        # only a fallback for the rare case a value wasn't recorded.
        return item.preference_value if item.preference_value else item.preference_key

    def _format_journal_entry(self, item: JournalEntry) -> str:
        if item.summary:
            return item.summary
        if item.topics_covered:
            return ", ".join(item.topics_covered)
        # entry_date is the one field JournalEntry guarantees is always
        # present, so it's the last-resort fallback rather than an
        # empty line.
        return item.entry_date

    def _format_curiosity_item(self, item: CuriosityItem) -> str:
        return item.question if item.question else "(untitled question)"

    def _format_confidence(self, value: Optional[float]) -> Optional[str]:
        if value is None:
            return None
        return f"{value:.2f}"
