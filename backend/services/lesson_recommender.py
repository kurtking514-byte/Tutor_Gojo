"""
lesson_recommender.py - Deterministic "what should the student learn
next" engine for Tutor Gojo.

Given the memory context returned by memory_service.get_memory_context(),
this module decides on a lesson recommendation using pure Python rules.
It never calls Gemini, never touches the database, and never writes
anywhere - it is a read-only function of its input.

Design note on schema: topic_mastery.mastery_level is stored as a
string enum (not_started | shaky | developing | comfortable | strong),
not a numeric 0.0-1.0 score (see memory_database.py's schema comments).
"Weak" is therefore defined against that enum - not_started and shaky -
which is the ordinal equivalent of "below 0.5" on a 5-step scale
(not_started=0.0, shaky=0.25, developing=0.5, comfortable=0.75,
strong=1.0).

Public API:
    build_lesson_recommendation(memory_context) -> dict
"""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Ordinal position of each mastery_level value, low = weaker. Mirrors the
# comment in memory_database.py's topic_mastery table definition.
_MASTERY_ORDER = {
    "not_started": 0,
    "shaky": 1,
    "developing": 2,
    "comfortable": 3,
    "strong": 4,
}

# mastery_level values considered "weak" - ordinal < developing (2),
# i.e. the equivalent of "below 0.5" on the not_started..strong scale.
_WEAK_MASTERY_LEVELS = {"not_started", "shaky"}

_ESTIMATED_DURATION = {
    "misconception": "15-20 minutes",
    "weak_topic": "20-30 minutes",
    "project_continuation": "30-45 minutes",
    "continue_path": "20-30 minutes",
    "no_history": "15-20 minutes",
}


# ---------------------------------------------------------------------------
# Private helpers - memory extraction
# ---------------------------------------------------------------------------

def _get_weak_topics(topic_mastery):
    """Return topic_mastery rows whose mastery_level is weak, ordered
    weakest-first, then alphabetically by topic/subtopic for a stable
    tie-break."""
    weak = [
        row for row in (topic_mastery or [])
        if row.get("mastery_level") in _WEAK_MASTERY_LEVELS
    ]
    weak.sort(key=lambda row: (
        _MASTERY_ORDER.get(row.get("mastery_level"), 99),
        row.get("topic") or "",
        row.get("subtopic") or "",
    ))
    return weak


def _get_active_misconceptions(misconceptions):
    """Return misconceptions with status == 'active' (defensive - the
    caller's memory_context already filters to active via
    memory_service.get_memory_context(), but this holds even if a
    differently-filtered dict is passed in). Ordered by occurrence
    count (most frequent first), then alphabetically by name."""
    active = [
        row for row in (misconceptions or [])
        if row.get("status", "active") == "active"
    ]
    active.sort(key=lambda row: (
        -int(row.get("occurrence_count") or 0),
        row.get("name") or "",
    ))
    return active


def _get_recent_topics(recent_journal_entries):
    """Flatten topics_covered across recent journal entries into an
    ordered, de-duplicated list (first-seen order, which is
    newest-first since the journal is queried newest-first)."""
    topics = []
    seen = set()
    for entry in recent_journal_entries or []:
        for topic in entry.get("topics_covered") or []:
            if topic and topic not in seen:
                seen.add(topic)
                topics.append(topic)
    return topics


def _get_active_project(active_projects):
    """Return the most relevant active project, or None. active_projects
    is already ordered by updated_at DESC by the database layer, so the
    first entry is the most recently touched one."""
    if not active_projects:
        return None
    return active_projects[0]


def _get_preference_hints(learning_preferences):
    """Scan learning_preferences for a small set of recognized
    preference values and turn them into (reason_note, practice_hint)
    pairs. Unrecognized preference values are ignored rather than
    guessed at. Iterates in a fixed, sorted order for determinism."""
    prefs = sorted(
        (learning_preferences or []),
        key=lambda row: row.get("preference_key") or "",
    )

    reason_notes = []
    practice_hints = []

    for row in prefs:
        value = (row.get("preference_value") or "").strip().lower()
        if not value:
            continue

        if "example" in value and "Work through worked examples before practicing independently." not in practice_hints:
            practice_hints.append("Work through worked examples before practicing independently.")
        if ("visual" in value or "diagram" in value) and "Use a diagram or visual walkthrough of the concept." not in practice_hints:
            practice_hints.append("Use a diagram or visual walkthrough of the concept.")
        if "project" in value and "Practice the concept inside a small project rather than isolated drills." not in practice_hints:
            practice_hints.append("Practice the concept inside a small project rather than isolated drills.")
        if ("fast" in value or "accelerated" in value) and "prefers a faster pace" not in reason_notes:
            reason_notes.append("prefers a faster pace")
        if ("patient" in value or "slow" in value) and "prefers a patient, unhurried pace" not in reason_notes:
            reason_notes.append("prefers a patient, unhurried pace")
        if ("direct" in value or "concise" in value) and "prefers direct, concise feedback" not in reason_notes:
            reason_notes.append("prefers direct, concise feedback")

    return reason_notes, practice_hints


# ---------------------------------------------------------------------------
# Private helpers - assembly
# ---------------------------------------------------------------------------

def _format_topic_label(row):
    topic = row.get("topic") or "General"
    subtopic = row.get("subtopic")
    return f"{topic} ({subtopic})" if subtopic else topic


def _append_project_practice(practice, active_project):
    """If there's an active project, add one practice suggestion tying
    the recommendation back into it. This applies regardless of which
    branch produced the primary recommendation, per the rule that an
    active project should steer practice toward advancing it."""
    if not active_project:
        return practice
    name = active_project.get("name") or "your current project"
    next_steps = active_project.get("next_steps")
    if next_steps:
        practice = practice + [f"Apply this to '{name}': {next_steps}"]
    else:
        practice = practice + [f"Apply this to your active project '{name}'."]
    return practice


def _build_reason(base_reason, reason_notes):
    if not reason_notes:
        return base_reason
    return f"{base_reason} (Note: student {', and '.join(reason_notes)}.)"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_lesson_recommendation(memory_context):
    """Deterministically decide what the student should learn next.

    Priority order:
        1. Active misconceptions - correcting a wrong mental model takes
           priority over introducing new/advanced material.
        2. Weak topics (mastery_level in {not_started, shaky}) - review
           the weakest topic first, preferring one not already covered
           in the most recent session if an equally-weak alternative
           exists.
        3. No weaknesses or misconceptions - continue the student's
           current path: the most recent journal topic, or (if there's
           no journal history at all) a starting recommendation.

    An active project, if present, always contributes one practice
    suggestion tying the recommendation back to advancing that project.
    Learning preferences, if present, always shape the reason text and
    practice suggestions.

    Args:
        memory_context: the dict returned by
            memory_service.get_memory_context(). Not mutated.

    Returns:
        dict with keys: title, reason, topics, difficulty,
        estimated_duration, recommended_practice.
    """
    memory_context = memory_context or {}

    topic_mastery = memory_context.get("topic_mastery") or []
    misconceptions = memory_context.get("misconceptions") or []
    recent_journal_entries = memory_context.get("recent_journal_entries") or []
    active_projects = memory_context.get("active_projects") or []
    learning_preferences = memory_context.get("learning_preferences") or []
    student_profile = memory_context.get("student_profile")

    weak_topics = _get_weak_topics(topic_mastery)
    active_misconceptions = _get_active_misconceptions(misconceptions)
    recent_topics = _get_recent_topics(recent_journal_entries)
    active_project = _get_active_project(active_projects)
    reason_notes, practice_hints = _get_preference_hints(learning_preferences)

    # --- Branch 1: active misconceptions take priority -------------------
    if active_misconceptions:
        top = active_misconceptions[0]
        name = top.get("name") or "an open misconception"
        topic = top.get("topic")

        title = f"Correct misconception: {name}"
        base_reason = (
            f"This misconception has come up {top.get('occurrence_count') or 1} time(s) "
            f"and should be resolved before introducing more advanced material"
            + (f" in {topic}." if topic else ".")
        )
        reason = _build_reason(base_reason, reason_notes)

        topics = [topic] if topic else []
        practice = [f"Revisit the concept behind '{name}' with a fresh explanation and a check-for-understanding exercise."]
        practice += practice_hints
        practice = _append_project_practice(practice, active_project)

        return {
            "title": title,
            "reason": reason,
            "topics": topics,
            "difficulty": "review",
            "estimated_duration": _ESTIMATED_DURATION["misconception"],
            "recommended_practice": practice,
        }

    # --- Branch 2: weak topics ---------------------------------------------
    if weak_topics:
        # Prefer a weak topic not already covered in the most recent
        # session (logical continuation), but fall back to the
        # weakest one overall if every weak topic was just covered -
        # remediation still matters more than novelty.
        candidate = next(
            (row for row in weak_topics if row.get("topic") not in recent_topics),
            weak_topics[0],
        )

        label = _format_topic_label(candidate)
        mastery_level = candidate.get("mastery_level")
        trend = candidate.get("trend")

        title = f"Review: {label}"
        base_reason = f"Current mastery is '{mastery_level}'"
        if trend and trend != "stable":
            base_reason += f" and trending '{trend}'"
        base_reason += ", so reinforcing the fundamentals here will pay off before moving on."
        reason = _build_reason(base_reason, reason_notes)

        difficulty = "beginner" if mastery_level == "not_started" else "beginner-to-intermediate"

        practice = [f"Work through a short set of guided exercises on {label}."]
        practice += practice_hints
        practice = _append_project_practice(practice, active_project)

        return {
            "title": title,
            "reason": reason,
            "topics": [candidate.get("topic")] if candidate.get("topic") else [],
            "difficulty": difficulty,
            "estimated_duration": _ESTIMATED_DURATION["weak_topic"],
            "recommended_practice": practice,
        }

    # --- Branch 3: no weaknesses - continue current path -------------------
    if recent_topics:
        latest_topic = recent_topics[0]
        title = f"Continue: {latest_topic}"
        base_reason = (
            f"No active weaknesses or misconceptions were found, so the recommendation "
            f"is to build on '{latest_topic}', the most recently covered topic."
        )
        reason = _build_reason(base_reason, reason_notes)

        practice = [f"Extend the last session's work on {latest_topic} with a slightly harder variant."]
        practice += practice_hints
        practice = _append_project_practice(practice, active_project)

        difficulty = "project" if active_project else "intermediate"

        return {
            "title": title,
            "reason": reason,
            "topics": [latest_topic],
            "difficulty": difficulty,
            "estimated_duration": (
                _ESTIMATED_DURATION["project_continuation"] if active_project
                else _ESTIMATED_DURATION["continue_path"]
            ),
            "recommended_practice": practice,
        }

    # --- Branch 4: truly no history to go on --------------------------------
    if active_project:
        name = active_project.get("name") or "your current project"
        title = f"Continue project: {name}"
        base_reason = "No topic history is recorded yet, so the clearest next step is to keep building the active project."
        reason = _build_reason(base_reason, reason_notes)

        practice = ["Pick up where the project's next steps leave off."]
        practice += practice_hints
        practice = _append_project_practice(practice, active_project)

        return {
            "title": title,
            "reason": reason,
            "topics": [],
            "difficulty": "project",
            "estimated_duration": _ESTIMATED_DURATION["project_continuation"],
            "recommended_practice": practice,
        }

    # No topic mastery, no misconceptions, no journal, no project -
    # fall back to whatever the student profile states as interests,
    # or a generic starting point if even that is empty.
    domain_interests = (student_profile or {}).get("domain_interests") or []
    if domain_interests:
        interest = domain_interests[0]
        title = f"Get started: {interest}"
        base_reason = f"There's no learning history yet, so this starts from a stated interest area: {interest}."
    else:
        title = "Get started"
        base_reason = "There's no learning history yet, so the first step is to pick a topic to begin with."
    reason = _build_reason(base_reason, reason_notes)

    practice = ["Tell your tutor what you'd like to learn first, or pick a topic to explore together."]
    practice += practice_hints
    practice = _append_project_practice(practice, active_project)

    return {
        "title": title,
        "reason": reason,
        "topics": [domain_interests[0]] if domain_interests else [],
        "difficulty": "beginner",
        "estimated_duration": _ESTIMATED_DURATION["no_history"],
        "recommended_practice": practice,
    }


if __name__ == "__main__":
    print("lesson_recommender.py loaded.")
    print("Public function: build_lesson_recommendation(memory_context) -> dict")
    print("Pure Python rules - no Gemini, no database access, no writes.")
