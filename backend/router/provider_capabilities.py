"""
router.provider_capabilities - Deterministic Provider Capability Registry.

Phase 11A introduces a static, deterministic registry of which
provider(s) support which classified intents. This replaces the
provider knowledge that previously lived directly inside
orchestrator.provider_selector.ProviderSelector as an inline dict
(Phase 9D's _INTENT_PROVIDER_MAP) with a dedicated, read-only registry,
so provider knowledge lives in one place instead of embedded in the
selector.

This registry is purely descriptive - like router.provider_health, it
does not choose providers, does not affect dispatch, priority
ordering, health, cooldown, or latency, and is not read by
llm_router.py at all. ProviderSelector is (today) its only caller, and
even there the result remains purely advisory: what
ExecutionContext.preferred_provider ends up holding is unchanged from
Phase 9D - only where the underlying provider knowledge lives has
moved, not what is ultimately returned.

Architectural constraints (Phase 11A):
  - This module owns capability data only: which provider "supports"
    which intent name. It does not import llm_router, does not import
    providers/*, and makes no network calls.
  - Capability data is static and deterministic: a fixed mapping
    defined once at module load time (see _CAPABILITIES below). There
    is no dynamic registration, no plugin mechanism, and no runtime
    mutation - the three public methods below are all pure reads.

Phase 11B adds preferred_provider(intent), moving the "which single
provider, if any, supports this intent" lookup that used to live as a
loop inside orchestrator.provider_selector.ProviderSelector into this
registry instead. This is not new knowledge - the underlying data and
the one-provider-per-intent shape are unchanged from Phase 11A - it is
the same deterministic lookup, just owned by this module rather than
performed by the caller against all_capabilities()/supports(). Runtime
behavior is unchanged: the same intent names resolve to the same
provider names as before (or None, including for "chat" and any
unmapped/unrecognized intent name).

Phase 11C adds providers_for_intent(intent), a read-only metadata query
returning every provider that supports a given intent, in fixed
declaration order, as a list (empty if none do). This is purely
additive: it introduces no new capability data, does not change
preferred_provider()'s single-provider selection, and is not called by
ProviderSelector or anything else yet - it exists so a later phase has
a stable "all candidates for an intent" query to build on, the same
way preferred_provider() was staged in 11B before being wired in.

Phase 11D adds is_supported_intent(intent), a read-only boolean
predicate answering "does any provider support this intent at all?".
It introduces no new capability data and no new iteration logic - it
is implemented directly in terms of providers_for_intent(), so it is
purely a convenience view over the same fixed mapping. Like 11C, it
is not yet called by ProviderSelector or anything else and changes no
runtime behavior.

Phase 11F adds supported_intents(), a read-only metadata query
returning every unique intent name supported by any provider, as a
fresh list on each call. It introduces no new capability data: it is
built directly from all_capabilities(), the same static snapshot
all_capabilities() already exposes, iterated in fixed provider
declaration order with intents within each provider sorted for
determinism (since the underlying per-provider sets carry no
guaranteed order of their own) and de-duplicated as they are
collected. It is not called by ProviderSelector or anything else and
changes no runtime behavior.

Phase 11G adds capability_summary(), a read-only aggregate view built
entirely out of existing registry methods: provider_names comes from
all_capabilities()'s fixed declaration order, intent_names comes from
supported_intents() (Phase 11F), and providers/supported_intents are
simply their respective counts. No new capability data or iteration
logic is introduced - this is purely a convenience aggregation for
observability. It is not called by ProviderSelector or anything else
and changes no runtime behavior.

Phase 11H adds validate(), a read-only internal-consistency check
built as far as practical on top of existing registry methods
(all_capabilities(), get_capabilities(), supported_intents(),
capability_summary()). It exists solely for future diagnostics/
startup validation, is not called anywhere yet, never raises (all
checks are wrapped so any unexpected condition simply yields False
rather than propagating an exception), never mutates registry state,
and performs no logging, printing, routing, or provider selection.
Adding it changes no runtime behavior, since nothing invokes it.
"""

from typing import Dict, FrozenSet


# Deterministic provider -> supported-intents mapping. This is the same
# knowledge Phase 9D's _INTENT_PROVIDER_MAP encoded (there, as
# intent -> provider), simply relocated here so ProviderSelector no
# longer embeds provider knowledge directly. The mapping is fixed at
# module load and never mutated afterward.
_CAPABILITIES: Dict[str, FrozenSet[str]] = {
    "gemini": frozenset({"tutoring", "planning", "memory_update"}),
    "openrouter": frozenset({"research", "document"}),
    "groq": frozenset({"coding", "debugging"}),
}


class ProviderCapabilityRegistry:
    """Read-only, deterministic registry of provider capabilities.

    Capability data is static (defined once at module load, see
    _CAPABILITIES above) - there is no write path, no runtime
    registration, and no mutation of any kind. Every method below is a
    pure read against that fixed mapping.
    """

    def __init__(self, capabilities=None):
        self._capabilities = (
            dict(_CAPABILITIES) if capabilities is None else dict(capabilities)
        )

    def supports(self, provider, intent):
        """Returns True if `provider` supports `intent`, False
        otherwise.

        `intent` is an intent name string (e.g. context.intent.name),
        matching the same identifiers Phase 9D's _INTENT_PROVIDER_MAP
        used as keys ("coding", "debugging", "research", "document",
        "tutoring", "planning", "memory_update"). An unrecognized
        provider, an unrecognized intent, or the "chat" intent (which,
        as before, no provider is mapped to) all return False.
        """
        return intent in self._capabilities.get(provider, frozenset())

    def get_capabilities(self, provider):
        """Returns the frozenset of intent names `provider` supports,
        or an empty frozenset if `provider` is unrecognized. Read-only
        - never creates an entry and never mutates the registry.
        """
        return self._capabilities.get(provider, frozenset())

    def all_capabilities(self):
        """Returns a dict snapshot of every provider's capabilities,
        keyed by provider name, mirroring the shape of
        ProviderHealthRegistry.all_health(). For observability, and
        (Phase 11A) for ProviderSelector to determine which provider,
        if any, supports a given intent.
        """
        return dict(self._capabilities)

    def preferred_provider(self, intent):
        """Returns the provider name that supports `intent`, or None
        if no provider does - including the "chat" intent and any
        unrecognized intent name, matching Phase 9D's
        _INTENT_PROVIDER_MAP.get(intent) behavior exactly.

        (Phase 11B) Deterministic: iterates the registry's own static
        capability data in its fixed load-time order and returns the
        first provider whose capability set contains `intent`. Today
        every intent maps to at most one provider, so "first" and
        "only" coincide; this is a pure read against the same static
        mapping supports()/get_capabilities() already expose - no
        randomness, no external state, no side effects.
        """
        for provider, intents in self._capabilities.items():
            if intent in intents:
                return provider
        return None

    def providers_for_intent(self, intent):
        """Returns a list of every provider name that supports
        `intent`, in the registry's fixed declaration order, or an
        empty list if no provider does (including the "chat" intent
        and any unrecognized intent name).

        (Phase 11C) Deterministic and read-only: iterates the same
        static _CAPABILITIES data supports()/get_capabilities()/
        preferred_provider() already read, in that same fixed
        load-time order, collecting every match rather than stopping
        at the first one. Purely additive - it does not change what
        preferred_provider() returns, is not yet called by
        ProviderSelector or anything else, and never mutates the
        registry.
        """
        return [
            provider
            for provider, intents in self._capabilities.items()
            if intent in intents
        ]

    def is_supported_intent(self, intent):
        """Returns True if one or more providers support `intent`,
        False otherwise - including the "chat" intent and any
        unrecognized intent name.

        (Phase 11D) Deterministic and read-only: reuses
        providers_for_intent()'s own static-data lookup rather than
        re-implementing the iteration, so this is purely a boolean
        view over the same fixed mapping - no new capability data, no
        randomness, no external state, no side effects.
        """
        return bool(self.providers_for_intent(intent))

    def supported_intents(self):
        """Returns a fresh list of every unique intent name supported
        by any provider.

        (Phase 11F) Deterministic and read-only: built from the same
        static snapshot all_capabilities() already exposes, iterated
        in fixed provider declaration order. Because each provider's
        capability set carries no guaranteed internal order, intents
        within a provider are sorted before being collected, so the
        result is stable across calls and processes. Duplicates
        (an intent supported by more than one provider) are collapsed
        to a single entry, keeping the first declaration-order
        occurrence. Returns a new list object every call - mutating
        the returned list never affects registry state.
        """
        seen = set()
        result = []
        for _provider, intents in self.all_capabilities().items():
            for intent in sorted(intents):
                if intent not in seen:
                    seen.add(intent)
                    result.append(intent)
        return result

    def capability_summary(self):
        """Returns a fresh dict summarizing the registry:

            {
                "providers": <number>,
                "supported_intents": <number>,
                "provider_names": [...],
                "intent_names": [...],
            }

        (Phase 11G) Deterministic and read-only: built entirely from
        existing registry methods rather than any new iteration over
        _capabilities. provider_names is the key order of
        all_capabilities() (the registry's fixed declaration order);
        intent_names is supported_intents() (Phase 11F), which is
        already deterministic and de-duplicated; providers and
        supported_intents are simply the counts of those two lists.
        Every call returns a new dict containing new lists - mutating
        the returned summary never affects registry state.
        """
        provider_names = list(self.all_capabilities().keys())
        intent_names = self.supported_intents()
        return {
            "providers": len(provider_names),
            "supported_intents": len(intent_names),
            "provider_names": provider_names,
            "intent_names": intent_names,
        }

    def validate(self):
        """Returns True if the registry's metadata is internally
        consistent, False otherwise. Never raises.

        (Phase 11H) A read-only diagnostic check, not called anywhere
        yet - it exists for future startup validation/diagnostics.
        Reuses existing registry methods (all_capabilities(),
        get_capabilities(), supported_intents(), capability_summary())
        rather than re-deriving their logic, and performs no
        mutation, logging, printing, routing, or provider selection.

        Checks performed:
          - Every provider has at least one supported intent.
          - Provider names are unique.
          - Every supported intent name is a non-empty string.
          - No provider has duplicate intents (naturally satisfied by
            frozenset storage, but explicitly re-checked here).
          - capability_summary() and supported_intents() agree with
            each other and with all_capabilities().

        Any unexpected condition (including data of an unexpected
        shape) is treated as a validation failure rather than an
        exception - the whole check is wrapped in a broad except so
        this method can never raise.
        """
        try:
            capabilities = self.all_capabilities()

            provider_names = list(capabilities.keys())
            if len(provider_names) != len(set(provider_names)):
                return False

            for provider in provider_names:
                intents = self.get_capabilities(provider)

                if len(intents) == 0:
                    return False

                intents_list = list(intents)
                if len(intents_list) != len(set(intents_list)):
                    return False

                for intent in intents_list:
                    if not isinstance(intent, str) or intent == "":
                        return False

            summary = self.capability_summary()
            intent_names = self.supported_intents()

            if summary["provider_names"] != provider_names:
                return False
            if summary["intent_names"] != intent_names:
                return False
            if summary["providers"] != len(provider_names):
                return False
            if summary["supported_intents"] != len(intent_names):
                return False

            for intent in intent_names:
                if not isinstance(intent, str) or intent == "":
                    return False

            return True
        except Exception:
            return False


# Module-level singleton - mirrors the get_health_registry() pattern in
# router/provider_health.py, so there is exactly one registry instance
# per process, shared by every caller.
_registry = ProviderCapabilityRegistry()


def get_capability_registry():
    """Returns the shared ProviderCapabilityRegistry instance."""
    return _registry
