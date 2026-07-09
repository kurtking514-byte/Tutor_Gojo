"""
orchestrator.openclaw_orchestrator - Orchestration seam for Tutor Gojo.

Phase 9 introduces this seam WITHOUT changing any current behavior.
Today, OpenClawOrchestrator does nothing but immediately hand a request
back to llm_router's existing provider-selection/failover mechanism - no
planning, no task decomposition, no tool use, and no retry behavior
beyond what llm_router already does. Those are explicitly out of scope
for this phase and are left for a future one.

This class exists so that future orchestration logic has a stable,
already-wired-in place to live - reached via llm_router's
"execution_mode" setting - without chat_service.py or gemini_client.py
ever needing to know it exists, or needing to change when it grows real
behavior later.

Public contract mirrors every provider's send/stream signature exactly,
so llm_router can treat "orchestrated mode" and "direct mode" as two
equally valid ways to fulfill the exact same request:
    send(message, history=None, use_search=False) -> str
    stream(message, history=None, use_search=False) -> Iterator[str]

Phase 9 architecture update:
  OpenClawOrchestrator is now a coordinator that owns three small
  components - IntentClassifier, Planner, and ProviderSelector - and
  threads a single ExecutionContext through them before handing off to
  dispatch. This is purely an internal restructuring: every request
  still flows through exactly one intent classification, one plan, and
  one provider-selector call.

Phase 9E:
  ExecutionContext.preferred_provider (populated by ProviderSelector) is
  now passed into _dispatch_send()/_stream_with_failover() as the
  `preferred_provider` reordering hint. This does not give the
  orchestrator any dispatch or failover authority of its own - the
  router remains the sole decision-maker. If the preferred provider is
  None (e.g. for a "chat" intent) or not present in the router's
  resolved priority list, the router's behavior is byte-for-byte
  identical to before this phase. All other flow is unchanged.

Phase 11I adds a private helper, _validate_provider_registry(), that
obtains the shared ProviderCapabilityRegistry via its existing public
accessor (get_capability_registry()) and returns the boolean result of
registry.validate() (Phase 11H). This is staged infrastructure only:
the helper is not called anywhere in this module or elsewhere, does
not run automatically, never raises, and never logs or prints. It
exists so a future startup-validation phase has a ready-made,
already-wired entry point without needing to redesign this class.
Adding it changes no runtime behavior, since nothing invokes it.

Phase 11J adds a second private helper, _is_ready(), that simply calls
_validate_provider_registry() and returns its boolean result. It
exists only to centralize future startup/readiness checks behind one
name, so later phases have a single readiness entry point to call
rather than reaching into individual validation helpers directly. Like
_validate_provider_registry(), it is staged infrastructure only: not
called from __init__(), send(), stream(), _build_context(), or
anywhere else, does not run automatically, never raises, and never
logs or prints. Adding it changes no runtime behavior, since nothing
invokes it.

Import boundaries (Phase 9 architectural constraints):
  - Does NOT import chat_service, memory_engine, or database.
  - Does NOT import providers/* directly, and does not choose a
    provider itself - provider selection stays exactly where it already
    lives: llm_router's registry and priority-list/failover logic.
    ProviderSelector only ever supplies a *recommendation*; the router
    decides whether and how to use it.
  - Imports llm_router's dispatch engine (_dispatch_send,
    _stream_with_failover) rather than llm_router.send_message()/
    stream_message(). This is deliberate and required to avoid
    recursion: send_message()/stream_message() are the functions that
    check "execution_mode" and route into this orchestrator in the
    first place. Calling them again from here would re-check
    "execution_mode", see "orchestrated" again, and re-enter this same
    orchestrator indefinitely. _dispatch_send()/_stream_with_failover()
    are the router's actual provider-selection-and-failover engine, used
    internally by send_message()/stream_message() themselves in direct
    mode - calling them here goes straight to a provider, exactly once,
    with the router's normal failover behavior intact.
  - IntentClassifier, Planner, and ProviderSelector each import no
    providers and no llm_router - they only see ExecutionContext and
    orchestrator_models. OpenClawOrchestrator is the only piece of this
    package that talks to llm_router.
  - Phase 11I additionally imports
    router.provider_capabilities.get_capability_registry, the same
    public accessor ProviderSelector already uses internally, solely
    for the staged _validate_provider_registry() helper below. This
    import is not used by send()/stream()/_build_context() and does
    not participate in dispatch, failover, or provider selection.
"""

from llm_router import _dispatch_send, _stream_with_failover

from orchestrator.execution_context import ExecutionContext
from orchestrator.intent_classifier import IntentClassifier
from orchestrator.planner import Planner
from orchestrator.provider_selector import ProviderSelector
from router.provider_capabilities import get_capability_registry


class OpenClawOrchestrator:
    """A coordinator composed of small components rather than a single
    file accumulating logic.

    Owns one IntentClassifier, one Planner, and one ProviderSelector.
    Each request builds an ExecutionContext and threads it through:

        ExecutionContext
            -> IntentClassifier.classify()      (fills context.intent)
            -> Planner.create_plan()            (fills context.plan)
            -> ProviderSelector.select_provider()
                                     (fills context.preferred_provider)
            -> _dispatch_send() / _stream_with_failover()
               (preferred_provider passed through as a reordering hint)

    None of these components perform dispatch or failover themselves -
    that stays exactly where it already lives, in llm_router. This
    class still contains no business logic of its own beyond wiring
    the pipeline together and forwarding the recommendation; task
    decomposition, tool use, and further provider intelligence remain
    reserved for future phases.
    """

    def __init__(self):
        self._intent_classifier = IntentClassifier()
        self._planner = Planner()
        self._provider_selector = ProviderSelector()

    def _build_context(self, message, history, use_search):
        """Assembles an ExecutionContext and runs it through
        IntentClassifier -> Planner -> ProviderSelector.

        preferred_provider is populated on the context and is passed to
        the router below as a reordering hint only - the router
        decides whether to honor it and remains solely responsible for
        dispatch and failover.
        """
        context = ExecutionContext(
            message=message, history=history, use_search=use_search
        )
        context.intent = self._intent_classifier.classify(context)
        context.plan = self._planner.create_plan(context)
        context.preferred_provider = self._provider_selector.select_provider(
            context
        )
        return context

    def _validate_provider_registry(self):
        """Staged infrastructure for future startup validation - not
        called anywhere yet and does not run automatically.

        (Phase 11I) Obtains the shared ProviderCapabilityRegistry via
        its existing public accessor, get_capability_registry(), and
        returns the boolean result of registry.validate() (Phase
        11H). Never raises - any unexpected condition is treated as
        validation failure rather than propagated - and never logs or
        prints. Performs no dispatch, routing, provider selection, or
        mutation of any kind.
        """
        try:
            registry = get_capability_registry()
            return registry.validate()
        except Exception:
            return False

    def _is_ready(self):
        """Staged infrastructure for future startup/readiness checks -
        not called anywhere yet and does not run automatically.

        (Phase 11J) Centralizes readiness behind one name: delegates
        entirely to _validate_provider_registry() (Phase 11I) and
        returns its boolean result. Never raises - any unexpected
        exception is treated as "not ready" rather than propagated -
        and never logs or prints. Performs no dispatch, routing,
        provider selection, or mutation of any kind.
        """
        try:
            return self._validate_provider_registry()
        except Exception:
            return False

    def send(self, message, history=None, use_search=False):
        """Builds an ExecutionContext (classify -> plan -> select),
        then delegates immediately to llm_router's dispatch-and-failover
        engine, passing context.preferred_provider through as a
        reordering hint. The router still owns provider selection and
        failover in full: if preferred_provider is None or not in the
        router's resolved priority list, this is byte-for-byte the same
        as before Phase 9E.
        """
        context = self._build_context(message, history, use_search)
        return _dispatch_send(
            message,
            history=history,
            use_search=use_search,
            preferred_provider=context.preferred_provider,
        )

    def stream(self, message, history=None, use_search=False):
        """Builds an ExecutionContext (classify -> plan -> select),
        then delegates immediately to llm_router's streaming
        dispatch-and-failover engine, passing context.preferred_provider
        through as a reordering hint. Returns exactly what
        _stream_with_failover() returns - a lazy generator - without
        wrapping it in another generator layer, so passing through the
        orchestrator changes neither laziness nor chunk timing.
        """
        context = self._build_context(message, history, use_search)
        return _stream_with_failover(
            message,
            history=history,
            use_search=use_search,
            preferred_provider=context.preferred_provider,
        )


# Module-level singleton - mirrors the providers.*.get_provider() pattern
# used elsewhere, so there is exactly one orchestrator instance per
# process.
_orchestrator = OpenClawOrchestrator()


def get_orchestrator():
    """Returns the shared OpenClawOrchestrator instance."""
    return _orchestrator
