"""
memory_engine.reader - loads a full MemorySnapshot by delegating to the
existing, already-working read functions on memory_service.py.

Status: LIVE, but disconnected. This module reuses memory_service's
public get_* functions (which in turn reuse obsidian_backend.py's
markdown parsing) to populate the memory_engine dataclasses. It does
NOT read markdown files, does NOT import yaml, and does NOT reimplement
any parsing logic.

Nothing in the existing application imports this module. It is not
wired into chat_service.py, prompt_builder.py, retrieval.py, or
ranking.py.
"""

from dataclasses import fields, is_dataclass
from typing import Any, Callable, List, Optional, Type, TypeVar

from services import memory_service

from memory_engine.models import (
    AssessmentRecord,
    CodingStyleTrait,
    CuriosityItem,
    JournalEntry,
    LearningPreference,
    MemorySnapshot,
    Milestone,
    Misconception,
    MistakePattern,
    MotivationalSignal,
    Project,
    StudentProfile,
    Strength,
    TopicMasteryEntry,
)

T = TypeVar("T")


class MemoryLoadError(RuntimeError):
    """Raised when a specific memory category fails to load from
    memory_service. Always names the category and chains the original
    exception, so failures are never silently swallowed.
    """

    def __init__(self, category: str, original: Exception):
        super().__init__(
            f"MemoryReader failed to load category '{category}' from "
            f"memory_service: {original!r}"
        )
        self.category = category
        self.original = original


def _to_dataclass(cls: Type[T], data: Any) -> Optional[T]:
    """Best-effort conversion of a single record returned by
    memory_service into the corresponding memory_engine dataclass.

    - If `data` is already an instance of `cls` (or any dataclass),
      it's returned as-is.
    - If `data` is a dict, only keys matching declared fields on `cls`
      are used; unknown keys are ignored so this stays forward
      compatible with extra fields memory_service might return.
    - If `data` is None, returns None.
    """
    if data is None:
        return None
    if isinstance(data, cls):
        return data
    if is_dataclass(data) and not isinstance(data, type):
        # A different dataclass shape (e.g. memory_service's own
        # internal record type) - fall through to dict-style mapping
        # via its own __dict__.
        data = data.__dict__
    if isinstance(data, dict):
        allowed = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in allowed}
        return cls(**filtered)
    raise TypeError(
        f"Cannot convert value of type {type(data)!r} into {cls.__name__}"
    )


def _to_dataclass_list(cls: Type[T], data: Any) -> List[T]:
    if data is None:
        return []
    items = data if isinstance(data, (list, tuple)) else [data]
    return [_to_dataclass(cls, item) for item in items]


def _call(category: str, func: Callable[[], Any]) -> Any:
    try:
        return func()
    except NotImplementedError:
        # A category memory_service hasn't implemented yet is treated
        # as "no data", not as a hard failure.
        return None
    except Exception as exc:  # noqa: BLE001 - intentionally broad, re-wrapped below
        raise MemoryLoadError(category, exc) from exc


class MemoryReader:
    """Loads a full MemorySnapshot from storage by delegating every
    category read to memory_service.py's existing get_* functions.

    This class performs no parsing, no filtering, no ranking, and no
    business logic of its own - it only calls memory_service, converts
    whatever it returns into the memory_engine dataclasses, and
    assembles a MemorySnapshot.
    """

    def load_snapshot(self) -> MemorySnapshot:
        return MemorySnapshot(
            student_profile=self.load_student_profile(),
            topic_mastery=self.load_topic_mastery(),
            misconceptions=self.load_misconceptions(),
            strengths=self.load_strengths(),
            learning_preferences=self.load_learning_preferences(),
            coding_style_traits=self.load_coding_style_traits(),
            mistake_patterns=self.load_mistake_patterns(),
            journal_entries=self.load_journal_entries(),
            projects=self.load_projects(),
            milestones=self.load_milestones(),
            curiosity_backlog=self.load_curiosity_backlog(),
            assessment_history=self.load_assessment_history(),
            motivational_signals=self.load_motivational_signals(),
        )

    def load_student_profile(self) -> Optional[StudentProfile]:
        data = _call("student_profile", memory_service.get_student_profile)
        return _to_dataclass(StudentProfile, data)

    def load_topic_mastery(self) -> List[TopicMasteryEntry]:
        data = _call("topic_mastery", memory_service.get_topic_mastery)
        return _to_dataclass_list(TopicMasteryEntry, data)

    def load_misconceptions(self) -> List[Misconception]:
        data = _call("misconceptions", memory_service.get_misconceptions)
        return _to_dataclass_list(Misconception, data)

    def load_strengths(self) -> List[Strength]:
        data = _call("strengths", memory_service.get_strengths)
        return _to_dataclass_list(Strength, data)

    def load_learning_preferences(self) -> List[LearningPreference]:
        data = _call(
            "learning_preferences", memory_service.get_learning_preferences
        )
        return _to_dataclass_list(LearningPreference, data)

    def load_coding_style_traits(self) -> List[CodingStyleTrait]:
        data = _call(
            "coding_style_traits", memory_service.get_coding_style_traits
        )
        return _to_dataclass_list(CodingStyleTrait, data)

    def load_mistake_patterns(self) -> List[MistakePattern]:
        data = _call("mistake_patterns", memory_service.get_mistake_patterns)
        return _to_dataclass_list(MistakePattern, data)

    def load_journal_entries(self) -> List[JournalEntry]:
        data = _call("journal_entries", memory_service.get_journal_entries)
        return _to_dataclass_list(JournalEntry, data)

    def load_projects(self) -> List[Project]:
        data = _call("projects", memory_service.get_projects)
        return _to_dataclass_list(Project, data)

    def load_milestones(self) -> List[Milestone]:
        data = _call("milestones", memory_service.get_milestones)
        return _to_dataclass_list(Milestone, data)

    def load_curiosity_backlog(self) -> List[CuriosityItem]:
        data = _call(
            "curiosity_backlog", memory_service.get_curiosity_backlog
        )
        return _to_dataclass_list(CuriosityItem, data)

    def load_assessment_history(self) -> List[AssessmentRecord]:
        data = _call(
            "assessment_history", memory_service.get_assessment_history
        )
        return _to_dataclass_list(AssessmentRecord, data)

    def load_motivational_signals(self) -> List[MotivationalSignal]:
        data = _call(
            "motivational_signals", memory_service.get_motivational_signals
        )
        return _to_dataclass_list(MotivationalSignal, data)
