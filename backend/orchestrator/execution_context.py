"""
orchestrator.execution_context - Data container passed between the
orchestrator's internal components.

Phase 9 constraint: no behavior lives here. ExecutionContext is
assembled once per request by OpenClawOrchestrator, threaded through
IntentClassifier -> Planner -> ProviderSelector, each of which reads
from and/or fills in a field, and is never inspected by
_dispatch_send()/_stream_with_failover() - those still receive plain
message/history/use_search arguments exactly as before.
"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ExecutionContext:
    """Everything the orchestrator's components need to do their part.

    Fields populated later in the pipeline (intent, plan,
    preferred_provider) start out as None and are filled in as the
    request passes through IntentClassifier, Planner, and
    ProviderSelector respectively.
    """

    message: str
    history: Optional[Any] = None
    use_search: bool = False
    preferred_provider: Optional[str] = None
    intent: Optional[Any] = None
    plan: Optional[Any] = None
