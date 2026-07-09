"""
router.provider_health - Passive Provider Health Registry.

Phase 10A introduces the first piece of "Router Intelligence": a place
for llm_router to record what happened on each provider call - nothing
more. This registry is purely observational bookkeeping:

  - It does NOT implement cooldowns.
  - It does NOT implement latency tracking.
  - It does NOT implement provider scoring.
  - It is NEVER consulted by _priority_list(), _dispatch_send(), or
    _stream_with_failover() to make a routing or failover decision.

llm_router.py records a success after a provider call succeeds and a
failure after a provider call raises, but continues routing exactly as
it did before this phase - the registry is a passive log of health
signals, not a decision-maker. That comes in a later phase.

Architectural constraints (Phase 10A):
  - Health belongs only to the Router: only llm_router.py imports or
    calls into this module.
  - OpenClaw does not import this module.
  - Providers do not know this registry exists - they are never passed
    a reference to it and never call it themselves.

Phase 10C adds cooldowns on top of the existing passive bookkeeping:
after FAILURE_THRESHOLD consecutive failures, a provider's
cooldown_until is set to now + COOLDOWN_DURATION, and it stays in
cooldown until that moment passes or a success clears it early. This
module still only records and reports; llm_router.py is the sole
place that reads is_in_cooldown()/get_health() to make an ordering
decision, and even there cooldown only ever changes attempt *order*,
never which providers exist or whether they're tried at all.

Phase 10D adds passive latency bookkeeping alongside the existing
success/failure/cooldown bookkeeping: ProviderHealth.last_latency_ms
records the duration (in milliseconds) of the most recent successful
call to a provider, written only through the new record_latency(name,
latency_ms) method. record_latency() touches last_latency_ms and
nothing else - it does not affect consecutive_failures, status,
last_success_at, last_failure_at, or cooldown_until, and it is
independent of record_success()/record_failure() (llm_router.py calls
it separately, alongside whichever of those two it was already
calling). Nothing in this module reads last_latency_ms to make any
decision - it is recorded and reported only. As with every other
field here, llm_router.py is the sole writer and reader.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional


@dataclass
class ProviderHealth:
    """Passive health bookkeeping for a single provider.

    Fields:
        name: the provider's registry name (e.g. "gemini").
        consecutive_failures: number of failures in a row since the
            last recorded success (reset to 0 on every success).
        last_failure_at: UTC timestamp of the most recent recorded
            failure, or None if this provider has never failed.
        last_success_at: UTC timestamp of the most recent recorded
            success, or None if this provider has never succeeded.
        status: "healthy" if consecutive_failures == 0, else
            "unhealthy". This is a simple, deterministic derived label
            for observability only - it is not read by any routing or
            failover logic in this phase.
        cooldown_until: (Phase 10C) UTC timestamp before which this
            provider is considered "in cooldown", or None if it isn't
            in one. Set to now + COOLDOWN_DURATION once
            consecutive_failures reaches FAILURE_THRESHOLD; cleared
            (set back to None) on the next recorded success. See
            ProviderHealthRegistry.is_in_cooldown() for how this is
            read.
        last_latency_ms: (Phase 10D) duration, in milliseconds, of the
            most recent successful call to this provider, or None if
            no latency has ever been recorded for it. Written only by
            record_latency(); no other method on this class touches
            it, and it does not participate in status, cooldown, or
            any other derived field.
    """

    name: str
    consecutive_failures: int = 0
    last_failure_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    status: str = "healthy"
    cooldown_until: Optional[datetime] = None
    last_latency_ms: Optional[float] = None


class ProviderHealthRegistry:
    """Owns passive health information for every provider the router
    has seen a result from.

    This registry does not influence provider selection, ordering, or
    failover on its own - it only records what happened and answers
    read-only questions about it (is_in_cooldown(), get_health()).
    llm_router.py is the only caller, and it decides what to do with
    the answers; this class never reaches back into routing logic.
    `record_success`/`record_failure`/`record_latency` remain the only
    write entry points, called exclusively by llm_router.py after a
    provider call resolves.

    Cooldown policy (Phase 10C):
        FAILURE_THRESHOLD - number of consecutive failures after which
            a provider enters cooldown.
        COOLDOWN_DURATION - how long a provider stays in cooldown once
            entered, measured from the failure that triggered it.
        Both are module-level constants (see below the class) so a
        later phase can tune them without touching this class's logic.
    """

    # Phase 10C cooldown policy. Defined here, inside the class, so they
    # live right next to the logic that uses them and stay easy to
    # tune later without touching record_failure()/is_in_cooldown().
    FAILURE_THRESHOLD = 3
    COOLDOWN_DURATION = timedelta(minutes=5)

    def __init__(self):
        self._entries: Dict[str, ProviderHealth] = {}

    def _get_or_create(self, name):
        """Returns the ProviderHealth entry for `name`, creating a
        fresh healthy entry on first sight of that provider name.
        """
        entry = self._entries.get(name)
        if entry is None:
            entry = ProviderHealth(name=name)
            self._entries[name] = entry
        return entry

    def record_success(self, name, timestamp=None):
        """Records a successful call for provider `name`.

        Resets consecutive_failures to 0, sets last_success_at, marks
        the provider "healthy", and (Phase 10C) clears any active
        cooldown - a single success ends a cooldown early, it doesn't
        wait for COOLDOWN_DURATION to elapse. Does not return anything
        and does not raise - this is pure bookkeeping and must never
        affect the caller's control flow.
        """
        entry = self._get_or_create(name)
        entry.last_success_at = timestamp or datetime.now(timezone.utc)
        entry.consecutive_failures = 0
        entry.status = "healthy"
        entry.cooldown_until = None

    def record_failure(self, name, timestamp=None):
        """Records a failed call for provider `name`.

        Increments consecutive_failures, sets last_failure_at, and
        sets status to "unhealthy". (Phase 10C) If consecutive_failures
        has just reached FAILURE_THRESHOLD for the first time since the
        last success, also sets cooldown_until to now +
        COOLDOWN_DURATION. consecutive_failures itself is never reset
        here - only record_success() resets it, and only
        record_success() clears an active cooldown; this method never
        clears one. Does not return anything and does not raise - this
        is pure bookkeeping and must never affect the caller's control
        flow (in particular, it must never interfere with failover to
        the next provider).
        """
        entry = self._get_or_create(name)
        now = timestamp or datetime.now(timezone.utc)
        entry.last_failure_at = now
        entry.consecutive_failures += 1
        entry.status = "unhealthy"
        if entry.consecutive_failures == self.FAILURE_THRESHOLD:
            entry.cooldown_until = now + self.COOLDOWN_DURATION

    def record_latency(self, name, latency_ms):
        """Records the latency, in milliseconds, of a successful call
        to provider `name`.

        (Phase 10D) Writes only last_latency_ms - it does not touch
        consecutive_failures, status, last_success_at, last_failure_at,
        or cooldown_until, and it does not itself decide whether the
        call was a success (llm_router.py calls this separately from,
        but alongside, record_success()/record_failure()). Does not
        return anything and does not raise - this is pure bookkeeping
        and must never affect the caller's control flow.
        """
        entry = self._get_or_create(name)
        entry.last_latency_ms = latency_ms

    def get_health(self, name):
        """Returns the ProviderHealth entry for `name`, or None if the
        router has never recorded a result for it. Read-only,
        observational access.
        """
        return self._entries.get(name)

    def is_in_cooldown(self, name):
        """Returns True if provider `name` is currently in cooldown,
        False otherwise. Read-only - never creates an entry for an
        unknown name and never mutates any existing entry (in
        particular, it does not clear an expired cooldown_until; that
        stays until the next record_success() call, since this method
        only answers a question, it doesn't do bookkeeping).

        Rules:
          - Unknown provider (no recorded result yet): False.
          - Known provider with cooldown_until is None: False.
          - Known provider with cooldown_until in the past or exactly
            now: False (the cooldown has elapsed).
          - Known provider with cooldown_until still in the future:
            True.
        """
        entry = self._entries.get(name)
        if entry is None or entry.cooldown_until is None:
            return False
        return datetime.now(timezone.utc) < entry.cooldown_until

    def all_health(self):
        """Returns a dict snapshot of every recorded provider's health,
        keyed by provider name. For observability only.
        """
        return dict(self._entries)


# Module-level singleton - mirrors the get_orchestrator()/get_provider()
# pattern used elsewhere, so there is exactly one registry instance per
# process, shared by every call the router makes.
_registry = ProviderHealthRegistry()


def get_health_registry():
    """Returns the shared ProviderHealthRegistry instance."""
    return _registry
