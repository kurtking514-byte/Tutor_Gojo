"""
orchestrator.orchestrator_models - Lightweight data shapes shared by the
orchestrator's components.

Phase 9 constraint: these are pure data containers for future
expansion. No methods, no business logic, no provider knowledge.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Intent:
    """Classification result describing what kind of request this is.

    Phase 9 only ever produces a single default value ("chat") - the
    field exists so future phases have somewhere to record real
    classifications without changing the shape of the pipeline.
    """

    name: str = "chat"


@dataclass
class PlanStep:
    """A single step of an ExecutionPlan.

    Phase 9 only ever produces one step ("send_to_provider") - richer
    step types (tool calls, memory lookups, etc.) are future work.
    """

    action: str = "send_to_provider"


@dataclass
class ExecutionPlan:
    """An ordered list of steps to fulfill a request.

    Phase 9 only ever produces a single-step plan that mirrors today's
    pass-through behavior.
    """

    steps: List[PlanStep] = field(default_factory=lambda: [PlanStep()])
