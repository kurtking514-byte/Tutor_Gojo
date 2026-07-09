"""
orchestrator.provider_selector - Deterministic provider recommendation.

Phase 9D replaces the Phase 9 placeholder (which always returned None)
with a deterministic mapping from classified intent to a recommended
provider name. This class still does not choose providers in any way
that affects dispatch: llm_router continues to own provider selection,
priority ordering, and failover exclusively via
_dispatch_send()/_stream_with_failover(). It does not import
providers/*, does not import llm_router, makes no network calls, and
its result is stored on ExecutionContext.preferred_provider but is not
read anywhere that influences routing yet - it only exists so that a
later phase has a stable, already-wired recommendation to build on.

Phase 11A moves the provider knowledge this class used to embed
directly (the former _INTENT_PROVIDER_MAP dict) into
router.provider_capabilities.ProviderCapabilityRegistry. This class no
longer knows which providers exist or what they support - it only asks
that registry, through its real public API (all_capabilities() and
supports()), which provider (if any) supports the classified intent.
Runtime behavior is unchanged: the same intent names resolve to the
same provider names as before (or None, including for the "chat"
intent and any unmapped/unrecognized intent name) - only where that
knowledge lives has moved, not what is returned.

Phase 11B moves the "which single provider supports this intent"
lookup itself into the registry, via its new preferred_provider(intent)
method. This class no longer loops over all_capabilities()/supports()
to work that out - it delegates the entire lookup and returns whatever
the registry decides. Runtime behavior is unchanged: the same intent
names resolve to the same provider names as before (or None).

Phase 11E has this class first ask the registry's
is_supported_intent(intent_name) predicate (Phase 11D) before
delegating to preferred_provider(intent_name). This is not a new
decision - is_supported_intent() is itself defined in terms of
providers_for_intent(), the same underlying static mapping
preferred_provider() reads - so for every intent name the outcome is
identical to Phase 11B: unsupported intents (including "chat" and any
unrecognized name) still resolve to None, and supported intents still
resolve to whatever preferred_provider() returns. Only the shape of
the call has changed, not the result.
"""

from router.provider_capabilities import get_capability_registry

# Phase 11A: shared, read-only capability registry - see
# router/provider_capabilities.py. This class no longer embeds
# provider knowledge itself; it only queries this registry.
_capability_registry = get_capability_registry()


class ProviderSelector:
    """Future home of provider recommendation logic.

    Today this returns a deterministic recommendation based solely on
    `context.intent.name`, resolved entirely by
    router.provider_capabilities.ProviderCapabilityRegistry.preferred_provider()
    (Phase 11B). It never calls a provider, never inspects provider
    health, latency, cost, or API keys, and never touches llm_router.
    Its result is purely advisory - OpenClawOrchestrator stores it on
    ExecutionContext.preferred_provider, but llm_router's existing
    priority-list/failover logic remains the sole decision-maker for
    which provider actually handles a request.
    """

    def select_provider(self, context):
        """Returns a preferred provider name for context.intent.name,
        or None if no provider supports that intent (including the
        "chat" intent and any unrecognized intent name) - None means
        the router's normal priority list applies unchanged.

        Does not dispatch, does not call providers, does not read
        provider health/latency/cost/API keys, and does not modify
        `context` - it only reads `context.intent.name` and delegates
        to router.provider_capabilities.ProviderCapabilityRegistry:
        first is_supported_intent() to check whether any provider
        supports the intent, then preferred_provider() to obtain the
        recommendation itself (Phase 11E). Because
        is_supported_intent() is defined in terms of the same static
        mapping preferred_provider() reads, this returns exactly what
        Phase 11B returned for every intent name - unsupported intents
        (including "chat" and any unrecognized name) yield None,
        supported intents yield preferred_provider()'s result.
        """
        if context.intent is None:
            return None

        intent_name = context.intent.name

        if not _capability_registry.is_supported_intent(intent_name):
            return None

        return _capability_registry.preferred_provider(intent_name)
