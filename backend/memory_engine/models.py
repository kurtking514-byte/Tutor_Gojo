"""
memory_engine.models - typed, in-memory representations of Tutor Gojo's
educational memory categories.

Status: SCAFFOLDING ONLY. Pure data containers - no parsing, no I/O,
no validation logic, no business rules. Field names deliberately mirror
the row shapes already produced by obsidian_backend.py (and, one layer
up, memory_database.py) so that a future MemoryReader implementation
can populate these without inventing a new vocabulary.

Every field is typed as Optional[...] unless the existing backend
guarantees it's always present (e.g. a journal entry's `entry_date`),
matching how the current YAML-frontmatter notes tolerate missing
values today.
"""

from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# 1. Student Profile
# ---------------------------------------------------------------------------

@dataclass
class StudentProfile:
    goals: Optional[str] = None
    background: Optional[str] = None
    preferred_languages: List[str] = field(default_factory=list)
    domain_interests: List[str] = field(default_factory=list)
    time_horizon: Optional[str] = None


# ---------------------------------------------------------------------------
# 2. Topic Mastery Map
# ---------------------------------------------------------------------------

@dataclass
class TopicMasteryEntry:
    topic: str
    subtopic: str = ""
    mastery_level: Optional[str] = None
    trend: Optional[str] = None
    last_exercised: Optional[str] = None
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# 3. Misconception Ledger
# ---------------------------------------------------------------------------

@dataclass
class Misconception:
    name: str
    topic: Optional[str] = None
    subtopic: Optional[str] = None
    occurrence_count: Optional[int] = None
    correction_attempts: Optional[int] = None
    status: Optional[str] = None
    first_observed: Optional[str] = None
    last_observed: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# 4. Consolidated Strengths
# ---------------------------------------------------------------------------

@dataclass
class Strength:
    name: str
    topic: Optional[str] = None
    subtopic: Optional[str] = None
    demonstration_count: Optional[int] = None
    first_confirmed: Optional[str] = None
    last_confirmed: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# 5. Learning Preferences
# ---------------------------------------------------------------------------

@dataclass
class LearningPreference:
    preference_key: str
    preference_value: Optional[str] = None
    evidence_count: Optional[int] = None
    notes: Optional[str] = None
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# 6. Coding Style Fingerprint
# ---------------------------------------------------------------------------

@dataclass
class CodingStyleTrait:
    trait_key: str
    trait_value: Optional[str] = None
    observed_count: Optional[int] = None
    first_observed: Optional[str] = None
    last_observed: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# 7. Recurring Mistake Patterns
# ---------------------------------------------------------------------------

@dataclass
class MistakePattern:
    description: str
    topic: Optional[str] = None
    occurrence_count: Optional[int] = None
    trend: Optional[str] = None
    first_observed: Optional[str] = None
    last_observed: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# 8. Learning Journal
# ---------------------------------------------------------------------------

@dataclass
class JournalEntry:
    entry_date: str
    summary: Optional[str] = None
    session_id: Optional[str] = None
    topics_covered: List[str] = field(default_factory=list)
    is_turning_point: bool = False
    unfinished_business: Optional[str] = None


# ---------------------------------------------------------------------------
# 9. Projects & Applied Work
# ---------------------------------------------------------------------------

@dataclass
class Project:
    id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    goals: Optional[str] = None
    design_decisions: Optional[str] = None
    next_steps: Optional[str] = None
    started_at: Optional[str] = None
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# 12. Growth Trajectory & Milestones
# ---------------------------------------------------------------------------

@dataclass
class Milestone:
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    achieved_at: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# 13. Curiosity Backlog
# ---------------------------------------------------------------------------

@dataclass
class CuriosityItem:
    id: Optional[int] = None
    question: Optional[str] = None
    raised_in_session: Optional[str] = None
    status: Optional[str] = None
    raised_at: Optional[str] = None
    addressed_at: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# 10. Assessment History
# ---------------------------------------------------------------------------

@dataclass
class AssessmentRecord:
    id: Optional[int] = None
    topic: Optional[str] = None
    subtopic: Optional[str] = None
    assessment_type: Optional[str] = None
    score: Optional[float] = None
    administered_at: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# 11. Motivational Signals
# ---------------------------------------------------------------------------

@dataclass
class MotivationalSignal:
    id: Optional[int] = None
    signal_type: Optional[str] = None
    value: Optional[str] = None
    observed_at: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------

@dataclass
class MemorySnapshot:
    """Everything known about the student, exactly as read from
    storage - one field per memory category, unfiltered and
    unranked. This is the full-fidelity object a MemoryReader is
    expected to produce.

    Covers the full 13-category list documented in memory_service.py's
    Backend Interface Contract, including assessment_history and
    motivational_signals - both of which exist in the current memory
    system but are not surfaced by today's 11-key
    memory_service.get_memory_context() dict.
    """
    student_profile: Optional[StudentProfile] = None
    topic_mastery: List[TopicMasteryEntry] = field(default_factory=list)
    misconceptions: List[Misconception] = field(default_factory=list)
    strengths: List[Strength] = field(default_factory=list)
    learning_preferences: List[LearningPreference] = field(default_factory=list)
    coding_style_traits: List[CodingStyleTrait] = field(default_factory=list)
    mistake_patterns: List[MistakePattern] = field(default_factory=list)
    journal_entries: List[JournalEntry] = field(default_factory=list)
    projects: List[Project] = field(default_factory=list)
    milestones: List[Milestone] = field(default_factory=list)
    curiosity_backlog: List[CuriosityItem] = field(default_factory=list)
    assessment_history: List[AssessmentRecord] = field(default_factory=list)
    motivational_signals: List[MotivationalSignal] = field(default_factory=list)


@dataclass
class MemoryContext:
    """The filtered/ranked subset of a MemorySnapshot that is actually
    intended to reach the Gemini prompt for a given turn.

    This is the future replacement for the ad-hoc selection logic that
    currently lives in chat_service._format_memory_context() (which
    reads only 6 of the available categories, e.g. only "weak" topic
    mastery rows and only journal topics_covered). Here, that selection
    is represented as explicit, inspectable data rather than being
    baked into string-formatting code.
    """
    strengths: List[Strength] = field(default_factory=list)
    weak_topics: List[TopicMasteryEntry] = field(default_factory=list)
    active_misconceptions: List[Misconception] = field(default_factory=list)
    mistake_patterns: List[MistakePattern] = field(default_factory=list)
    learning_preferences: List[LearningPreference] = field(default_factory=list)
    recent_journal_entries: List[JournalEntry] = field(default_factory=list)
    open_curiosity_backlog: List[CuriosityItem] = field(default_factory=list)
    current_confidence: Optional[float] = None
