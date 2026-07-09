"""
memory_service.py - Read/write abstraction layer for Tutor Gojo's
educational memory (memory_database.py).

Mirrors the existing history_service.py pattern for database.py: thin
pass-through functions, same names as the layer below, so api.py and
chat_service.py never import memory_database.py directly.

The one thing this layer adds that memory_database.py doesn't do itself:
JSON encode/decode for the handful of fields memory_database.py stores
as JSON-encoded TEXT (documented in its own docstrings as "caller must
pre-serialize"). Everything above this module should only ever see
native Python lists/dicts/bools - never raw JSON strings.

Fields normalized here:
    - student_profile.preferred_languages   (JSON TEXT <-> list)
    - student_profile.domain_interests      (JSON TEXT <-> list)
    - learning_journal.topics_covered       (JSON TEXT <-> list)
    - assessments.is_correct                (0/1 <-> bool, like database.py's has_code)
    - learning_journal.is_turning_point     (0/1 <-> bool)

No other transformation happens here. This module does not build
prompts, does not call the Gemini client, and is not wired into
api.py's routes yet - that wiring is a separate, later task.
"""

import json
import traceback

import obsidian_backend

# ---------------------------------------------------------------------------
# Backend indirection
# ---------------------------------------------------------------------------
#
# memory_service is the permanent abstraction layer between the rest of
# the application and educational-memory storage. Callers (api.py,
# chat_service.py, and anything else above this module) must never
# import a concrete storage backend - such as memory_database - directly.
# They talk to memory_service, and memory_service alone decides which
# backend actually persists the data.
#
# SQLite (memory_database.py) is currently the only, and therefore the
# active, backend. Every function below calls out to `_backend` rather
# than to `memory_database` by name, so that a future backend (e.g. an
# Obsidian vault) can be substituted later purely by changing what
# `_backend` points at - with no change to any function body here and
# no change to any caller above this module.
#
# This is infrastructure only: no backend selection, configuration, or
# runtime switching is introduced yet. `_backend` is set once, below,
# to the same module this file already depended on.
# ---------------------------------------------------------------------------
# Backend Interface Contract
# ---------------------------------------------------------------------------
#
# This is documentation only - not enforced by any base class, Protocol,
# or runtime check. It exists so that anyone writing a new backend (e.g.
# an Obsidian-vault-backed module) has a single, authoritative list of
# every function `_backend` is expected to provide, with the exact
# signature memory_service calls it with today.
#
# A conforming backend module must expose all of the following,
# matching these names and parameters exactly (memory_service passes
# arguments through unchanged, aside from the JSON encode/decode noted
# in the module docstring above):
#
# 1. Student Profile
#    - get_student_profile() -> dict | None
#    - update_student_profile(goals=None, background=None,
#          preferred_languages=None, domain_interests=None,
#          time_horizon=None) -> None
#
# 2. Topic Mastery Map
#    - update_topic_mastery(topic, subtopic="", mastery_level=None,
#          trend=None, mark_exercised=False) -> None
#    - get_topic_mastery(topic=None) -> list[dict]
#
# 3. Misconception Ledger
#    - record_misconception(name, topic=None, subtopic=None, notes=None) -> None
#    - mark_misconception_resolved(name) -> None
#    - get_misconceptions(status=None) -> list[dict]
#
# 4. Consolidated Strengths
#    - record_strength(name, topic=None, subtopic=None, notes=None) -> None
#    - get_strengths(topic=None) -> list[dict]
#
# 5. Learning Preferences
#    - set_learning_preference(preference_key, preference_value, notes=None) -> None
#    - get_learning_preferences() -> list[dict]
#
# 6. Coding Style Fingerprint
#    - set_coding_style_trait(trait_key, trait_value, notes=None) -> None
#    - get_coding_style_traits() -> list[dict]
#
# 7. Recurring Mistake Patterns
#    - record_mistake_pattern(description, topic=None, trend=None, notes=None) -> None
#    - get_mistake_patterns(topic=None) -> list[dict]
#
# 8. Learning Journal
#    - add_journal_entry(summary, session_id=None, topics_covered=None,
#          is_turning_point=False, unfinished_business=None) -> None
#    - get_journal_entries(limit=50) -> list[dict]
#
# 9. Projects & Applied Work
#    - create_project(name, description=None, goals=None) -> project_id
#    - update_project(project_id, status=None, design_decisions=None,
#          next_steps=None) -> None
#    - get_projects(status=None) -> list[dict]
#
# 10. Assessment History
#    - record_assessment(question, session_id=None, topic=None, subtopic=None,
#          assessment_type="quiz", student_answer=None, expected_answer=None,
#          is_correct=None, context_notes=None) -> None
#    - get_assessment_history(topic=None, limit=50) -> list[dict]
#
# 11. Motivational & Engagement Signals
#    - record_motivational_signal(pattern_description, signal_type=None,
#          topic=None, notes=None) -> None
#    - get_motivational_signals(signal_type=None) -> list[dict]
#
# 12. Growth Trajectory & Milestones
#    - add_milestone(title, description=None, category=None, notes=None) -> None
#    - get_milestones(limit=None) -> list[dict]
#
# 13. Curiosity Backlog
#    - add_curiosity(question, raised_in_session=None, notes=None) -> None
#    - mark_curiosity_addressed(curiosity_id) -> None
#    - get_curiosity_backlog(status="open") -> list[dict]
#
# Initialization
#    - init_memory_database() -> None
#      (invoked via memory_service.initialize_memory_backend(); sets up
#      whatever schema/structure the backend needs before first use)
#
# Notes on shape, not enforced here but relied upon by memory_service
# and everything above it (see module docstring for the JSON/bool
# normalization memory_service itself performs on top of these):
#    - List-returning functions return a list of dicts with consistent
#      keys across rows.
#    - get_student_profile() returns None specifically when no profile
#      has ever been set, distinct from a dict with blank fields.
#    - JSON-encodable fields (preferred_languages, domain_interests,
#      topics_covered) are expected as JSON-encoded TEXT at this layer;
#      memory_service is responsible for decoding them to native lists.
#    - is_correct / is_turning_point are expected as 0/1/None at this
#      layer; memory_service is responsible for normalizing them to bool.
#
_backend = obsidian_backend
print(f"[DEBUG] memory_service module load: _backend = {_backend!r}")
print(f"[DEBUG] memory_service module load: _backend.__name__ = {_backend.__name__!r}")
print(f"[DEBUG] memory_service module load: id(_backend) = {id(_backend)}")


def _set_backend(backend):
    """Replace the active storage backend.

    Private - not part of memory_service's public API. This exists purely
    as preparation for future work (e.g. swapping in an Obsidian-backed
    module); nothing in the current codebase calls this yet, and no
    selection mechanism (config, env var, etc.) is wired up around it.
    """
    global _backend
    _backend = backend


def initialize_memory_backend():
    """Initialize the active storage backend's schema/tables.

    Callers (e.g. api.py's startup event) should initialize educational
    memory through memory_service rather than importing a concrete
    backend - such as memory_database - directly, so they never need to
    know which backend is active.
    """
    _backend.init_memory_database()


def _to_json(value):
    """Serialize a list/dict to a JSON string, or pass None through."""
    return None if value is None else json.dumps(value)


def _from_json(value):
    """Deserialize a JSON string to a list/dict, or pass None through
    as an empty list (never None) so callers can iterate safely."""
    if value is None:
        return []
    return json.loads(value)


# ---------------------------------------------------------------------------
# 1. Student Profile
# ---------------------------------------------------------------------------

def get_student_profile():
    """Return the student profile with preferred_languages and
    domain_interests decoded to lists, or None if never set."""
    profile = _backend.get_student_profile()
    if profile is None:
        return None
    profile["preferred_languages"] = _from_json(profile["preferred_languages"])
    profile["domain_interests"] = _from_json(profile["domain_interests"])
    return profile


def update_student_profile(goals=None, background=None, preferred_languages=None,
                            domain_interests=None, time_horizon=None):
    """Create or update the student profile. preferred_languages and
    domain_interests are accepted as native lists and encoded here."""
    _backend.update_student_profile(
        goals=goals,
        background=background,
        preferred_languages=_to_json(preferred_languages),
        domain_interests=_to_json(domain_interests),
        time_horizon=time_horizon,
    )


# ---------------------------------------------------------------------------
# 2. Topic Mastery Map
# ---------------------------------------------------------------------------

def update_topic_mastery(topic, subtopic="", mastery_level=None, trend=None, mark_exercised=False):
    print("[DEBUG] entering update_topic_mastery()")
    print(f"[DEBUG] update_topic_mastery: id(_backend) = {id(_backend)}")
    print(f"[DEBUG] update_topic_mastery: _backend.__name__ = {_backend.__name__!r}")
    print(f"[DEBUG] update_topic_mastery: _backend.update_topic_mastery = {_backend.update_topic_mastery!r}")
    try:
        print("[DEBUG] calling backend.update_topic_mastery")
        _backend.update_topic_mastery(
            topic, subtopic=subtopic, mastery_level=mastery_level,
            trend=trend, mark_exercised=mark_exercised,
        )
        print("[DEBUG] backend.update_topic_mastery returned")
    except Exception:
        print("[DEBUG] backend.update_topic_mastery raised an exception")
        print("[DEBUG] Full traceback for the exception above:")
        traceback.print_exc()
        raise


def get_topic_mastery(topic=None):
    return _backend.get_topic_mastery(topic=topic)


# ---------------------------------------------------------------------------
# 3. Misconception Ledger
# ---------------------------------------------------------------------------

def record_misconception(name, topic=None, subtopic=None, notes=None):
    _backend.record_misconception(name, topic=topic, subtopic=subtopic, notes=notes)


def mark_misconception_resolved(name):
    _backend.mark_misconception_resolved(name)


def get_misconceptions(status=None):
    return _backend.get_misconceptions(status=status)


# ---------------------------------------------------------------------------
# 4. Consolidated Strengths
# ---------------------------------------------------------------------------

def record_strength(name, topic=None, subtopic=None, notes=None):
    _backend.record_strength(name, topic=topic, subtopic=subtopic, notes=notes)


def get_strengths(topic=None):
    return _backend.get_strengths(topic=topic)


# ---------------------------------------------------------------------------
# 5. Learning Preferences
# ---------------------------------------------------------------------------

def set_learning_preference(preference_key, preference_value, notes=None):
    _backend.set_learning_preference(preference_key, preference_value, notes=notes)


def get_learning_preferences():
    return _backend.get_learning_preferences()


# ---------------------------------------------------------------------------
# 6. Coding Style Fingerprint
# ---------------------------------------------------------------------------

def set_coding_style_trait(trait_key, trait_value, notes=None):
    _backend.set_coding_style_trait(trait_key, trait_value, notes=notes)


def get_coding_style_traits():
    return _backend.get_coding_style_traits()


# ---------------------------------------------------------------------------
# 7. Recurring Mistake Patterns
# ---------------------------------------------------------------------------

def record_mistake_pattern(description, topic=None, trend=None, notes=None):
    _backend.record_mistake_pattern(description, topic=topic, trend=trend, notes=notes)


def get_mistake_patterns(topic=None):
    return _backend.get_mistake_patterns(topic=topic)


# ---------------------------------------------------------------------------
# 8. Learning Journal
# ---------------------------------------------------------------------------

def add_journal_entry(summary, session_id=None, topics_covered=None,
                       is_turning_point=False, unfinished_business=None):
    """Append a narrative journal entry. topics_covered is accepted as
    a native list and encoded here."""
    _backend.add_journal_entry(
        summary,
        session_id=session_id,
        topics_covered=_to_json(topics_covered),
        is_turning_point=is_turning_point,
        unfinished_business=unfinished_business,
    )


def get_journal_entries(limit=50):
    """Return recent journal entries with topics_covered decoded to a
    list and is_turning_point normalized to bool."""
    entries = _backend.get_journal_entries(limit=limit)
    for entry in entries:
        entry["topics_covered"] = _from_json(entry["topics_covered"])
        entry["is_turning_point"] = bool(entry["is_turning_point"])
    return entries


# ---------------------------------------------------------------------------
# 9. Projects & Applied Work
# ---------------------------------------------------------------------------

def create_project(name, description=None, goals=None):
    return _backend.create_project(name, description=description, goals=goals)


def update_project(project_id, status=None, design_decisions=None, next_steps=None):
    _backend.update_project(
        project_id, status=status, design_decisions=design_decisions, next_steps=next_steps,
    )


def get_projects(status=None):
    return _backend.get_projects(status=status)


# ---------------------------------------------------------------------------
# 10. Assessment History
# ---------------------------------------------------------------------------

def record_assessment(question, session_id=None, topic=None, subtopic=None,
                       assessment_type="quiz", student_answer=None,
                       expected_answer=None, is_correct=None, context_notes=None):
    _backend.record_assessment(
        question,
        session_id=session_id, topic=topic, subtopic=subtopic,
        assessment_type=assessment_type, student_answer=student_answer,
        expected_answer=expected_answer, is_correct=is_correct,
        context_notes=context_notes,
    )


def get_assessment_history(topic=None, limit=50):
    """Return recent assessments with is_correct normalized to bool
    (None stays None - it means "not yet graded", distinct from False)."""
    rows = _backend.get_assessment_history(topic=topic, limit=limit)
    for row in rows:
        if row["is_correct"] is not None:
            row["is_correct"] = bool(row["is_correct"])
    return rows


# ---------------------------------------------------------------------------
# 11. Motivational & Engagement Signals
# ---------------------------------------------------------------------------

def record_motivational_signal(pattern_description, signal_type=None, topic=None, notes=None):
    _backend.record_motivational_signal(
        pattern_description, signal_type=signal_type, topic=topic, notes=notes,
    )


def get_motivational_signals(signal_type=None):
    return _backend.get_motivational_signals(signal_type=signal_type)


# ---------------------------------------------------------------------------
# 12. Growth Trajectory & Milestones
# ---------------------------------------------------------------------------

def add_milestone(title, description=None, category=None, notes=None):
    _backend.add_milestone(title, description=description, category=category, notes=notes)


def get_milestones(limit=None):
    return _backend.get_milestones(limit=limit)


# ---------------------------------------------------------------------------
# 13. Curiosity Backlog
# ---------------------------------------------------------------------------

def add_curiosity(question, raised_in_session=None, notes=None):
    _backend.add_curiosity(question, raised_in_session=raised_in_session, notes=notes)


def mark_curiosity_addressed(curiosity_id):
    _backend.mark_curiosity_addressed(curiosity_id)


def get_curiosity_backlog(status="open"):
    return _backend.get_curiosity_backlog(status=status)


# ---------------------------------------------------------------------------
# Aggregate read - convenience composition, not a new data concept.
# Mirrors how api.py's /progress route already composes two
# history_service calls into one response.
# ---------------------------------------------------------------------------

def get_memory_context(recent_journal_limit=10, recent_milestone_limit=10):
    """Return one dict bundling all 13 memory categories. Intended for
    whatever eventually builds the tutor's system/context prompt, so
    that caller doesn't need to know about 13 separate functions.
    Journal and milestones are capped since they're append-only and can
    grow unbounded; everything else is naturally small (one row per
    tracked topic/trait/etc.), so it's returned in full.
    """
    return {
        "student_profile": get_student_profile(),
        "topic_mastery": get_topic_mastery(),
        "misconceptions": get_misconceptions(status="active"),
        "strengths": get_strengths(),
        "learning_preferences": get_learning_preferences(),
        "coding_style_traits": get_coding_style_traits(),
        "mistake_patterns": get_mistake_patterns(),
        "recent_journal_entries": get_journal_entries(limit=recent_journal_limit),
        "active_projects": get_projects(status="in_progress"),
        "recent_motivational_signals": get_motivational_signals(),
        "recent_milestones": get_milestones(limit=recent_milestone_limit),
        "open_curiosity_backlog": get_curiosity_backlog(status="open"),
    }
