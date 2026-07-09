"""
orchestrator.planner - Deterministic, intent-aware planning.

Phase 9C replaces the Phase 9 placeholder (which always returned a
fixed one-step plan) with a planner that branches on
`context.intent.name` using plain if/elif logic. The Planner only ever
builds and returns an ExecutionPlan - it does not call providers, does
not call llm_router, does not execute tools or memory operations, does
not modify ExecutionContext, and does not select a provider or perform
routing.
"""

from .orchestrator_models import ExecutionPlan, PlanStep


class Planner:
    """Creates an ExecutionPlan for an ExecutionContext.

    Branches deterministically on context.intent.name. Every intent
    today produces the same single "send_to_provider" step, except
    "memory_update", which appends a second, non-executed
    "future_memory_store" placeholder step - preparing the plan shape
    for future memory integration without any component actually
    running that step yet.
    """

    def create_plan(self, context):
        """Returns an ExecutionPlan built from context.intent.name.

        Does not consult provider availability or history, does not
        call providers or llm_router, does not execute tools or
        memory operations, and does not modify `context` - it only
        reads `context.intent.name` and returns a plan.
        """
        intent_name = context.intent.name if context.intent else "chat"

        if intent_name == "memory_update":
            return ExecutionPlan(
                steps=[
                    PlanStep(action="send_to_provider"),
                    PlanStep(action="future_memory_store"),
                ]
            )
        elif intent_name == "chat":
            return ExecutionPlan(steps=[PlanStep(action="send_to_provider")])
        elif intent_name == "tutoring":
            return ExecutionPlan(steps=[PlanStep(action="send_to_provider")])
        elif intent_name == "coding":
            return ExecutionPlan(steps=[PlanStep(action="send_to_provider")])
        elif intent_name == "debugging":
            return ExecutionPlan(steps=[PlanStep(action="send_to_provider")])
        elif intent_name == "planning":
            return ExecutionPlan(steps=[PlanStep(action="send_to_provider")])
        elif intent_name == "research":
            return ExecutionPlan(steps=[PlanStep(action="send_to_provider")])
        elif intent_name == "document":
            return ExecutionPlan(steps=[PlanStep(action="send_to_provider")])
        else:
            return ExecutionPlan(steps=[PlanStep(action="send_to_provider")])
