"""
orchestrator.intent_classifier - Deterministic keyword-based intent
classification.

Phase 9B replaces the Phase 9 placeholder (which always returned
Intent("chat")) with a purely deterministic classifier built from
simple Python string operations only. No AI, no provider calls, no
memory, no embeddings, no regex, no fuzzy matching - just lowercasing
and `in` substring checks against fixed keyword lists.
"""

from .orchestrator_models import Intent


# Keyword groups, checked in classification-priority order. Each entry
# is a plain lowercase substring looked for in the lowercased message.
_MEMORY_UPDATE_KEYWORDS = (
    "remember",
    "memorize",
    "save this",
    "store this",
    "don't forget",
)

_DEBUGGING_KEYWORDS = (
    "debug",
    "bug",
    "traceback",
    "stack trace",
    "error",
    "exception",
    "fix this",
)

_CODING_KEYWORDS = (
    "code",
    "python",
    "java",
    "c++",
    "javascript",
    "function",
    "class",
    "algorithm",
    "program",
    "implement",
)

_DOCUMENT_KEYWORDS = (
    "pdf",
    "document",
    "paper",
    "essay",
    "report",
    "docx",
    "ppt",
    "spreadsheet",
)

_RESEARCH_KEYWORDS = (
    "research",
    "compare",
    "analysis",
    "analyze",
    "survey",
    "study",
    "investigate",
)

_PLANNING_KEYWORDS = (
    "plan",
    "roadmap",
    "schedule",
    "timeline",
    "milestone",
    "strategy",
)

_TUTORING_KEYWORDS = (
    "explain",
    "teach",
    "lesson",
    "learn",
    "why",
    "how does",
    "example",
)


def _contains_any(text, keywords):
    """Returns True if any keyword appears as a substring of text."""
    for keyword in keywords:
        if keyword in text:
            return True
    return False


class IntentClassifier:
    """Classifies an ExecutionContext's request into an Intent using
    deterministic keyword matching only.

    classify() lowercases context.message and checks it against fixed
    keyword lists in a fixed precedence order:
        memory_update > debugging > coding > document > research
        > planning > tutoring > chat

    The first category whose keywords match wins - there is no
    scoring, no weighting, and no randomness. If nothing matches, the
    result is Intent("chat"), matching the prior placeholder behavior
    for ordinary messages.
    """

    def classify(self, context):
        """Returns an Intent for context.message using plain substring
        checks - no AI, no provider calls, no memory, no regex, no
        fuzzy matching, no embeddings.
        """
        text = (context.message or "").lower()

        if _contains_any(text, _MEMORY_UPDATE_KEYWORDS):
            return Intent(name="memory_update")

        if _contains_any(text, _DEBUGGING_KEYWORDS):
            return Intent(name="debugging")

        if _contains_any(text, _CODING_KEYWORDS):
            return Intent(name="coding")

        if _contains_any(text, _DOCUMENT_KEYWORDS):
            return Intent(name="document")

        if _contains_any(text, _RESEARCH_KEYWORDS):
            return Intent(name="research")

        if _contains_any(text, _PLANNING_KEYWORDS):
            return Intent(name="planning")

        if _contains_any(text, _TUTORING_KEYWORDS):
            return Intent(name="tutoring")

        return Intent(name="chat")
