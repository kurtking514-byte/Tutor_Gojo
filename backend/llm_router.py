"""
llm_router.py - Provider-selecting LLM router with deterministic retry/failover.

Sits between gemini_client.py and individual provider modules. Determines
which provider(s) should handle a request by reading settings through the
app's existing settings mechanism (the same config.get_setting(key, default)
function providers.gemini_provider already uses for "model"/"level"/
"teaching_intensity"), then dispatches through the same name -> provider-
getter registry introduced in Phase 4/5.

Phase 6 adds deterministic failover on top of that dispatch: if the first
provider in priority order raises, the router tries the next one, in
order, until one succeeds or all have been tried. There is deliberately
no health scoring, no exponential backoff, and no circuit breaker here -
just "try the next one in a fixed list." Those richer policies are left
for a later phase (see ROADMAP.md).

Phase 9 adds a single optional seam on top of that, unchanged, dispatch
logic: an "execution_mode" setting ("direct", the default, or
"orchestrated"). In "direct" mode this file behaves exactly as it did
after Phase 6 - nothing about provider selection or failover changes.
In "orchestrated" mode, a request is handed to orchestrator.
OpenClawOrchestrator first, which today does nothing but call straight
back into this file's own dispatch engine - so orchestrated mode is
byte-identical to direct mode in every observable way. Phase 9
deliberately adds no planning, task decomposition, tool use, or new
retry behavior; it only establishes the seam a future phase will build
on. See _dispatch_send()/_stream_with_failover() for the actual
dispatch engine both modes share, and orchestrator/openclaw_orchestrator.py
for the orchestration seam itself.

Phase 9E adds one optional, backward-compatible parameter to the
dispatch engine: `preferred_provider`. This is purely a *reordering*
hint - if the named provider is present in the resolved priority list,
it is moved to the front (remaining providers keep their relative
order); if it's missing, invalid, falsy, or simply not passed, the
priority list is built exactly as before. The router remains the only
component that decides actual dispatch and failover: preferred_provider
never adds, removes, or skips a provider, and never changes retry
behavior - it only changes which provider is tried first. Existing
callers (send_message()/stream_message(), and anything calling
_dispatch_send()/_stream_with_failover() without this new argument) see
byte-for-byte identical behavior, since the parameter defaults to None.

Phase 10A adds a passive Provider Health Registry (router/provider_health.py).
After every provider call resolves, the router records a success or
failure against that provider's health entry - nothing more. This is
pure bookkeeping: the registry is never consulted by _priority_list(),
_dispatch_send(), or _stream_with_failover() to make a routing or
failover decision. Provider selection, ordering, and failover behavior
are byte-for-byte identical to before this phase. No cooldowns, no
latency tracking, and no provider scoring exist yet - those are left
for a later phase. Health belongs only to the router: OpenClaw and the
providers themselves never import or call the registry.

Phase 10B makes _priority_list() actually consult the Phase 10A health
registry when building an ordering, rather than just writing to it. After
the existing provider_priority -> legacy "provider" -> preferred_provider
resolution finishes exactly as before, one final pass runs: any provider
whose ProviderHealth.status (read via registry.get_health(name), the
registry's real public method) is "unhealthy" is moved to the end of the
list, preserving the relative order within both the healthy and
unhealthy groups. Unhealthy providers are never dropped - they are still
tried, just last, so a request still gets attempted end-to-end even if
every provider happens to be unhealthy (in which case the original
order is left unchanged, since reordering would accomplish nothing). A
provider get_health() has never recorded anything for returns None,
which is treated as healthy, matching ProviderHealth's own default
status field. This phase adds no cooldown timers, retry limits, latency
scoring, or backoff, and reads the registry through its actual
documented API only - no probing, no guessed method names, no
compatibility shims - see _priority_list() for where it's applied.
_dispatch_send() and _stream_with_failover() are untouched: they still
just iterate _priority_list()'s result in order, so failover behavior,
streaming laziness, and execution modes are exactly as they were in
Phase 10A.

Phase 10C adds cooldown-awareness on top of Phase 10B's health-aware
ordering, reading the two new real, public members Phase 10C adds to
ProviderHealthRegistry: is_in_cooldown() (read), backed by
cooldown_until, FAILURE_THRESHOLD, and COOLDOWN_DURATION (all defined
in router/provider_health.py, set as a side effect of
record_failure()/record_success()). After the Phase 10B health pass
finishes, one more partition-and-concatenate pass runs: any provider
currently in cooldown is moved to the end of the list, preserving
relative order within both the not-in-cooldown and in-cooldown groups.
As with the health pass, this never drops a provider - cooldown only
ever delays when a provider is tried, never whether it's tried - and if
every provider happens to be in cooldown, the list is returned
unchanged rather than emptied, so a request is still attempted. See
_priority_list() for the exact steps. _dispatch_send() and
_stream_with_failover() remain untouched by this phase too.

Phase 10D adds passive latency bookkeeping on top of Phase 10C, using
the two new real, public members Phase 10D adds to
ProviderHealthRegistry: record_latency() (write) and the
ProviderHealth.last_latency_ms field it writes (read via the existing
get_health()). _dispatch_send() measures elapsed wall-clock time
around each provider's send() call and records it - only on success,
since a failed call has no meaningful latency to report. Likewise,
_stream_with_failover() measures time-to-first-chunk and records it on
both the successful-first-chunk path and the legitimate-empty-stream
(StopIteration) path, for the same reason record_success() is already
called on both of those paths. As with every prior health-bookkeeping
phase, this is passive only: _priority_list() does not yet read
last_latency_ms for anything, so provider selection, ordering, and
failover behavior remain byte-for-byte identical to Phase 10C.
_dispatch_send() and _stream_with_failover() otherwise still just
iterate _priority_list()'s result in order.

Phase 10E makes _priority_list() finally consult the Phase 10D latency
data Phase 10D started recording, rather than just writing it. After
the existing provider_priority -> legacy "provider" -> preferred_provider
-> unhealthy-last -> cooldown-last passes finish exactly as they did in
Phase 10C, one final pass runs: among providers that are both healthy
and not in cooldown, any two whose ProviderHealth.last_latency_ms (read
via the registry's real, documented get_health(), never a new method)
are both present are ordered so the lower latency comes first. This is
a partial, position-preserving reorder, not a general sort: a provider
whose last_latency_ms is None keeps its exact existing position and is
never displaced, and unhealthy/cooldown providers are untouched by this
pass since they were already moved to the end by the Phase 10B/10C
passes and never carry a latency comparison against the healthy group.
Ties (equal latency) and the "no provider has a latency value yet" case
both leave the list exactly as-is, since Python's stable sort combined
with iterating candidates in their existing order guarantees no
gratuitous reordering. As with every prior ordering phase, nothing is
ever added, removed, or duplicated - only order changes - and
_dispatch_send()/_stream_with_failover() remain untouched: they still
just iterate _priority_list()'s result in order, so dispatch, failover,
streaming laziness, and execution modes are exactly as they were in
Phase 10D.

Public interface is unchanged from every prior phase and is exactly what
gemini_client.py depends on:
    send_message(message, history=None, use_search=False) -> str
    stream_message(message, history=None, use_search=False) -> Iterator[str]
"""

import time

from config import get_setting

from providers.gemini_provider import get_provider as _get_gemini_provider
from providers.openrouter_provider import get_provider as _get_openrouter_provider
from providers.groq_provider import get_provider as _get_groq_provider

from router.provider_health import get_health_registry

# Phase 10A: shared passive health registry. Recorded into after every
# provider call resolves, but never read by any routing/failover logic
# in this phase - see router/provider_health.py.
_health_registry = get_health_registry()

# --- Settings ---------------------------------------------------------
#
# Two independent settings are honored, both read via the same
# get_setting(key, default) mechanism used everywhere else in the app:
#
#   "provider"          - legacy single-provider setting from Phase 5.
#                          Still fully supported (see _priority_list()).
#   "provider_priority"  - new in Phase 6. An ordered list of provider
#                          names to attempt, first to last.
#
# Neither setting being present reproduces the original, pre-Phase-6
# behavior exactly: GeminiProvider is the only provider tried.
_PROVIDER_SETTING_KEY = "provider"
_PROVIDER_PRIORITY_SETTING_KEY = "provider_priority"

# Phase 9: which execution path handles a request.
#   "direct"       - the default. Bypasses the orchestrator entirely;
#                    behavior identical to every prior phase.
#   "orchestrated" - hands the request to OpenClawOrchestrator first,
#                    which (today) immediately calls back into this
#                    file's own dispatch engine. See module docstring.
_EXECUTION_MODE_SETTING_KEY = "execution_mode"
DEFAULT_EXECUTION_MODE = "direct"

DEFAULT_PROVIDER = "gemini"
DEFAULT_PROVIDER_PRIORITY = ["gemini", "openrouter"]

# Name -> zero-arg callable returning that provider's shared instance.
#
# This registry is the ONLY place a new provider needs to be registered
# once its module exists. Nothing in this file's dispatch/failover logic,
# and nothing in gemini_client.py or chat_service.py, needs to change when
# a provider is added or removed.
#
# To add a provider in a future phase:
#   1. Create providers/<name>_provider.py implementing the same
#      send(message, history=None, use_search=False) -> str and
#      stream(...) -> Iterator[str] contract as GeminiProvider.
#   2. Import its get_provider and add one line below.
#   3. Optionally add it to DEFAULT_PROVIDER_PRIORITY (or leave it
#      opt-in via the "provider_priority" setting only).
#
# Remaining future providers register the same way - left as explicit
# placeholders so the extension point stays obvious rather than implied:
#
#   from providers.openai_provider import get_provider as _get_openai_provider
#   from providers.openclaw_provider import get_provider as _get_openclaw_provider
#
_PROVIDER_REGISTRY = {
    "gemini": _get_gemini_provider,
    "openrouter": _get_openrouter_provider,
    "groq": _get_groq_provider,
    # "openai": _get_openai_provider,
    # "openclaw": _get_openclaw_provider,
}


def _priority_list(preferred_provider=None):
    """Builds the ordered list of provider names to attempt for this call.

    Backward compatibility is the whole point of this function: a caller
    who has only ever set the legacy "provider" setting (or never set
    anything at all) must see exactly the pre-Phase-6 behavior whenever
    that single provider succeeds - i.e. only one provider is ever
    contacted, in the same order it always was.

    Resolution order:
      1. Start from "provider_priority" if set, else DEFAULT_PROVIDER_PRIORITY.
      2. If the legacy "provider" setting is also set, move it to the
         front of that list (without duplicating it), so it's still the
         first (and, in the common case, only) provider tried.
      3. (Phase 9E) If `preferred_provider` is given and is present in
         the list built so far, move it to the front (without
         duplicating it), preserving the relative order of everyone
         else. This step is purely a reordering - it never adds a
         provider that wasn't already going to be tried, and never
         removes one. If `preferred_provider` is None, empty, or not
         present in the list, this step is a no-op and the list from
         steps 1-2 is returned unchanged - so any caller not passing
         this new argument sees byte-for-byte identical output to
         before Phase 9E.
      4. (Phase 10B) Any provider in the list built so far whose health
         entry's status - read via registry.get_health(name).status,
         the registry's real public method - is "unhealthy" is moved
         to the end of the list. Relative order is preserved
         separately within the healthy group and the unhealthy group -
         this step only ever partitions-and-concatenates, it never
         re-sorts within a group. A provider get_health() has never
         recorded anything for (returns None) is treated as healthy,
         matching ProviderHealth's own default status field. If every
         provider in the list is unhealthy, this step is a no-op (the
         list from steps 1-3 is returned as-is) so a request still
         gets attempted rather than deadlocking. If every provider is
         healthy, this step is also a no-op, so this phase is a
         byte-for-byte no-op in the all-healthy case that dominates
         normal operation.
      5. (Phase 10C) Any provider still in cooldown - per
         registry.is_in_cooldown(name), the registry's real public
         method - is moved to the end of the step-4 list. Same
         partition-and-concatenate shape as step 4: relative order is
         preserved separately within the not-in-cooldown group and the
         in-cooldown group, no provider is added or removed, and a
         provider with no health record (or one with no active
         cooldown) is treated as not in cooldown. If every provider is
         in cooldown, this step is a no-op (the step-4 list is returned
         as-is) so a request is still attempted rather than the router
         producing an empty list. If no provider is in cooldown, this
         step is also a no-op.
      6. (Phase 10E) Among providers in the step-5 list that are both
         healthy and not in cooldown, a stable, position-preserving
         reorder by ProviderHealth.last_latency_ms (read via the
         registry's real get_health(), ascending - lower latency
         first). A provider with no latency recorded (last_latency_ms
         is None) is never displaced from its step-5 position; only
         the positions occupied by providers that do have a recorded
         latency are refilled, in ascending-latency order, preserving
         the original relative order for ties. Unhealthy and
         in-cooldown providers are left exactly where steps 4-5 put
         them - this step never compares a healthy provider's latency
         against a non-healthy one's, and never moves a provider across
         the health/cooldown boundary steps 4-5 established. If fewer
         than two eligible providers have a recorded latency, there is
         nothing meaningful to reorder and the step-5 list is returned
         unchanged (this covers both "no provider has latency yet" and
         "exactly one provider has latency" - in the latter case that
         provider's own position doesn't change either, since sorting a
         single element is a no-op).
    """
    priority = get_setting(_PROVIDER_PRIORITY_SETTING_KEY, None)
    priority = list(priority) if priority else list(DEFAULT_PROVIDER_PRIORITY)

    legacy_single = get_setting(_PROVIDER_SETTING_KEY, None)
    if legacy_single:
        priority = [legacy_single] + [p for p in priority if p != legacy_single]

    if preferred_provider and preferred_provider in priority:
        priority = [preferred_provider] + [
            p for p in priority if p != preferred_provider
        ]

    # Phase 10B: health-aware pass. Everything above this point is
    # unchanged from Phase 9E - provider_priority -> legacy "provider" ->
    # preferred_provider. This uses only ProviderHealthRegistry's real,
    # documented public API (get_health()) - no guessed methods, no
    # duck-typing, no compatibility shims. get_health(name) returns
    # either a ProviderHealth instance (whose .status is "healthy" or
    # "unhealthy") or None if the router has never recorded a result
    # for that provider; None is treated as healthy, matching
    # ProviderHealth's own default status field. This step never adds,
    # removes, or duplicates a provider; it only ever partitions the
    # list into healthy/unhealthy and concatenates, preserving relative
    # order within each group.
    healthy = []
    unhealthy = []
    for name in priority:
        entry = _health_registry.get_health(name)
        if entry is not None and entry.status == "unhealthy":
            unhealthy.append(name)
        else:
            healthy.append(name)

    if not unhealthy or not healthy:
        # Nothing to reorder (no unhealthy providers), or reordering
        # would accomplish nothing because every provider is unhealthy
        # - in both cases the step-3 list passes through unchanged so a
        # request still gets attempted rather than never tried at all.
        after_health = priority
    else:
        after_health = healthy + unhealthy

    # Phase 10C: cooldown-aware final pass, applied on top of the
    # step-4 (health-ordered) list. Uses only the registry's real
    # public is_in_cooldown() method - same partition-and-concatenate
    # shape as the health step above, so it never adds, removes, or
    # duplicates a provider, and never reorders within either group.
    not_cooling = [p for p in after_health if not _health_registry.is_in_cooldown(p)]
    cooling = [p for p in after_health if _health_registry.is_in_cooldown(p)]

    if not cooling or not not_cooling:
        # No provider in cooldown, or every provider is in cooldown -
        # in both cases return the step-4 list unchanged so a request
        # is still attempted rather than the router ever producing an
        # empty priority list.
        after_cooldown = after_health
    else:
        after_cooldown = not_cooling + cooling

    return _order_by_latency(after_cooldown)


def _order_by_latency(priority):
    """Phase 10E: final, latency-aware ordering pass.

    Applied on top of the step-5 (health- and cooldown-ordered) list.
    Uses only the registry's real, documented get_health() method - the
    same read already used by steps 4-5 - so this never adds, removes,
    or duplicates a provider, and never touches a provider's health or
    cooldown status. It only ever reorders positions that are already
    known (from steps 4-5) to hold a healthy, not-in-cooldown provider.

    Algorithm: a stable, position-preserving partial sort.
      - Eligible positions are those holding a provider that is both
        healthy (get_health(name) is None, or its .status == "healthy"
        - None is treated as healthy, matching ProviderHealth's own
        default) and not in cooldown (per is_in_cooldown()). Since a
        provider in cooldown always has status "unhealthy" (cooldown is
        only ever set inside record_failure(), which always sets status
        to "unhealthy", and only cleared together with status by
        record_success()), "healthy" already implies "not in cooldown";
        the explicit is_in_cooldown() check is kept anyway so this
        function does not rely on that invariant holding forever in
        provider_health.py.
      - Among eligible positions, only those whose provider currently
        has a recorded last_latency_ms (not None) participate in
        reordering. A provider with no recorded latency keeps its exact
        existing position - it is treated as neither "faster" nor
        "slower" than anything, it simply never moves.
      - The providers occupying the participating positions are sorted
        ascending by last_latency_ms (lowest latency first) using
        Python's stable sort, then written back into those same
        positions in that new order. Ties keep their original relative
        order, since they're read out of `priority` in position order
        before sorting and Python's sort is stable.
      - Non-eligible positions (unhealthy or in-cooldown providers) are
        never read from or written to here - they stay exactly where
        steps 4-5 already placed them.

    If fewer than two positions participate, the list is returned
    unchanged: zero participating positions means no provider anywhere
    has a recorded latency yet, and one participating position has
    nothing to be reordered relative to - either way this is a no-op,
    matching the "None latency means don't move" and "one provider has
    latency, everyone else stays put" requirements exactly.
    """
    eligible_indices = []
    for i, name in enumerate(priority):
        entry = _health_registry.get_health(name)
        is_healthy = entry is None or entry.status == "healthy"
        if is_healthy and not _health_registry.is_in_cooldown(name):
            eligible_indices.append(i)

    # Among eligible positions, only ones with a recorded latency value
    # participate in the reorder; positions whose provider has no
    # recorded latency are dropped from `participating` (but remain in
    # `priority`, untouched, at their original index).
    participating = []
    for i in eligible_indices:
        entry = _health_registry.get_health(priority[i])
        latency = entry.last_latency_ms if entry is not None else None
        if latency is not None:
            participating.append((i, latency, priority[i]))

    if len(participating) < 2:
        # 0 providers with latency: nothing to reorder. Exactly 1:
        # sorting a single element is a no-op, and nothing else moves
        # since only participating positions are ever touched.
        return priority

    ordered_names = [
        name for _latency, name in
        sorted(((latency, name) for _i, latency, name in participating),
               key=lambda pair: pair[0])
    ]
    result = list(priority)
    for (i, _latency, _name), new_name in zip(participating, ordered_names):
        result[i] = new_name
    return result


def _get_provider_instance(name):
    """Looks up a named provider's shared instance via the registry.

    An unrecognized provider name fails loudly (ValueError naming the bad
    value and the registered options) rather than silently falling back,
    consistent with how the rest of the app treats misconfiguration as an
    explicit, debuggable failure. During failover this ValueError is
    caught like any other provider failure and simply means "this name
    in the priority list didn't work"; it does not stop the router from
    trying the remaining names.
    """
    try:
        get_instance = _PROVIDER_REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"Unknown provider '{name}' configured. Registered providers: "
            f"{sorted(_PROVIDER_REGISTRY)}"
        )
    return get_instance()


def _all_providers_failed(attempted_errors):
    """Builds the single, clear exception raised when every provider in
    the priority list has failed, summarizing what was tried and why
    each attempt failed.
    """
    tried = [name for name, _err in attempted_errors]
    details = "; ".join(
        f"{name} -> {type(err).__name__}: {err}" for name, err in attempted_errors
    )
    return RuntimeError(
        f"All configured providers failed for this request. "
        f"Tried in order {tried}. Failures: {details}"
    )


def _dispatch_send(message, history=None, use_search=False, preferred_provider=None):
    """Core non-streaming dispatch: tries each provider in
    _priority_list() order with failover. This is the router's actual
    provider-selection-and-failover mechanism - unchanged since Phase 6,
    aside from the Phase 9E `preferred_provider` reordering hint below.

    This is deliberately a separate function from send_message() so that
    OpenClawOrchestrator (Phase 9) can call straight into the dispatch
    engine without going back through send_message()'s execution_mode
    check. Calling send_message() from the orchestrator would re-check
    "execution_mode", see "orchestrated" again, and re-enter the
    orchestrator indefinitely; calling _dispatch_send() goes directly to
    a provider, exactly once, exactly like direct mode does.

    Tries each provider in _priority_list(preferred_provider) order. On
    any exception from a provider's send() call, the error is recorded
    and the router moves on to the next provider in the list. The first
    provider to succeed wins and its result is returned immediately - no
    further providers are contacted. If none succeed, a single
    RuntimeError summarizing every attempted provider and its failure is
    raised.

    `preferred_provider` (Phase 9E, optional, default None) only affects
    which provider in the resolved list is tried first - it does not
    change the set of providers tried, the failover mechanism, or retry
    behavior. Passing None (or omitting it, or passing a name not in the
    resolved list) reproduces every prior phase's behavior exactly.

    Matches every prior phase's behavior exactly when only one provider
    is configured (or reachable): that provider is tried once, and its
    result (or its exception, now wrapped with context) is what the
    caller sees.

    Phase 10A: after each attempt resolves, a success or failure is
    recorded against that provider's entry in the passive health
    registry (router/provider_health.py). This is bookkeeping only - it
    never changes which provider is tried next, never suppresses or
    raises an additional error, and never affects the value returned
    here.
    """
    attempted_errors = []
    for name in _priority_list(preferred_provider):
        try:
            provider = _get_provider_instance(name)
            # Phase 10D: measured only around the call itself, so
            # provider lookup/instantiation above is not included in
            # the recorded latency.
            _start = time.monotonic()
            result = provider.send(message, history=history, use_search=use_search)
        except Exception as err:  # noqa: BLE001 - deliberately broad: any
            # provider failure (bad config, network error, vendor outage)
            # should trigger failover, not just a specific exception type.
            attempted_errors.append((name, err))
            # Phase 10A: passive bookkeeping only - does not affect
            # failover, which proceeds to the next provider exactly as
            # before this phase. Phase 10D: no latency is recorded on
            # failure - only successful calls have a meaningful latency
            # to report.
            _health_registry.record_failure(name)
            continue

        # Phase 10D: elapsed time for the successful call, recorded as
        # passive bookkeeping alongside record_success() below - it
        # does not change what is returned and does not affect control
        # flow.
        _elapsed_ms = (time.monotonic() - _start) * 1000
        _health_registry.record_latency(name, _elapsed_ms)
        # Phase 10A: passive bookkeeping only - recorded after a
        # successful call, does not change what is returned below.
        _health_registry.record_success(name)
        return result

    raise _all_providers_failed(attempted_errors)


def send_message(message, history=None, use_search=False):
    """Route a non-streaming request with deterministic failover.

    Public entrypoint gemini_client.py depends on. Adds exactly one
    branch on top of Phase 6's unchanged dispatch logic: if
    "execution_mode" is "orchestrated", the request is handed to
    OpenClawOrchestrator, which today does nothing but call straight
    back into _dispatch_send() - so orchestrated mode produces
    byte-identical results to direct mode. When execution_mode is
    "direct" (the default, and the only behavior that existed before
    Phase 9), this is exactly the Phase 6 dispatch with zero added
    indirection.

    Signature is unchanged by Phase 9E: this function does not accept
    or pass a preferred_provider - that reordering hint only exists on
    the internal dispatch engine, reached by OpenClawOrchestrator
    directly. Calling _dispatch_send() here without that argument means
    it defaults to None, so direct-mode behavior is untouched.
    """
    mode = get_setting(_EXECUTION_MODE_SETTING_KEY, DEFAULT_EXECUTION_MODE)
    if mode == "orchestrated":
        # Local import: avoids a module-level circular import, since
        # orchestrator.openclaw_orchestrator imports _dispatch_send/
        # _stream_with_failover from this module. By the time this
        # branch runs, llm_router has already finished loading, so the
        # import below is safe.
        from orchestrator.openclaw_orchestrator import get_orchestrator
        return get_orchestrator().send(message, history=history, use_search=use_search)

    return _dispatch_send(message, history=history, use_search=use_search)


def stream_message(message, history=None, use_search=False):
    """Route a streaming request with deterministic failover, returning a
    lazy iterator of text chunks.

    Public entrypoint gemini_client.py depends on. Adds exactly one
    branch on top of Phase 6's unchanged streaming dispatch: if
    "execution_mode" is "orchestrated", the request is handed to
    OpenClawOrchestrator, which today does nothing but call straight
    back into _stream_with_failover() - so orchestrated mode returns the
    same generator, chunk-for-chunk, as direct mode.

    Laziness is preserved in both modes: this function reads the
    "execution_mode" setting eagerly (a plain in-memory config lookup,
    not a vendor call), but neither branch below does any provider work
    before returning - each just returns a generator object
    (_stream_with_failover(...), possibly by way of the orchestrator).
    Nothing about provider selection, calling a provider's stream(), or
    contacting a vendor happens until the caller starts iterating the
    returned generator, exactly as gemini_client.stream_message() has
    always relied on.

    Signature is unchanged by Phase 9E: see send_message()'s identical
    note above - preferred_provider is only threaded through by
    OpenClawOrchestrator calling _stream_with_failover() directly.
    """
    mode = get_setting(_EXECUTION_MODE_SETTING_KEY, DEFAULT_EXECUTION_MODE)
    if mode == "orchestrated":
        # Local import - see send_message()'s identical note on why this
        # must not be a module-level import.
        from orchestrator.openclaw_orchestrator import get_orchestrator
        return get_orchestrator().stream(message, history=history, use_search=use_search)

    return _stream_with_failover(message, history=history, use_search=use_search)


def _stream_with_failover(message, history=None, use_search=False, preferred_provider=None):
    """Generator implementing streaming failover.

    Retry flow:
      For each provider name in _priority_list(preferred_provider):
        1. Get the provider's stream() generator (does not itself start
           the request - providers are expected to be lazy the same way
           this router is).
        2. Pull exactly one chunk from it. This is the only "eager" part
           of the whole flow, and it is unavoidable: a provider's
           stream() is only guaranteed to raise once iteration begins
           (e.g. on connecting to the vendor), so failover cannot be
           decided without pulling at least one chunk to prove the
           provider is actually working.
        3. If that first pull raises, record the failure and move on to
           the next provider - nothing has been yielded to the caller
           yet, so switching providers here is invisible to them.
        4. If that first pull succeeds, yield it, then `yield from` the
           rest of that provider's generator untouched - no buffering,
           no peeking ahead, chunks reach the caller as the provider
           produces them.
        5. If a provider fails *after* its first chunk has already been
           yielded, that failure is NOT retried on a different provider:
           output has already reached the caller, so silently switching
           vendors mid-stream would risk duplicated or inconsistent
           output. The error is left to propagate as-is. (Mid-stream
           recovery is a candidate for a future phase, not this one.)

    If every provider fails its first-chunk check, a single RuntimeError
    summarizing all attempts is raised - the same failure format as
    send_message().

    `preferred_provider` (Phase 9E, optional, default None) only
    affects the order providers are attempted in - see _dispatch_send()'s
    identical note. This function is itself a generator, so nothing
    above - including resolving the priority list with
    preferred_provider - executes until the caller begins iterating;
    laziness is unaffected by this addition.

    Phase 10A: a success or failure is recorded against each attempted
    provider's health entry as its outcome becomes known (first-chunk
    success, first-chunk exception, or a legitimate empty stream, which
    counts as a success). This is bookkeeping only - it happens after
    the outcome is already decided, so it never changes which provider
    is tried next, never delays a yielded chunk, and never affects
    laziness.
    """
    attempted_errors = []
    for name in _priority_list(preferred_provider):
        try:
            provider = _get_provider_instance(name)
            # Phase 10D: measures time-to-first-chunk, so the clock
            # starts right before the provider's stream() is obtained
            # and stops as soon as the first chunk (or the empty-stream
            # StopIteration) is known.
            _start = time.monotonic()
            gen = provider.stream(message, history=history, use_search=use_search)
            first_chunk = next(gen)
        except StopIteration:
            # Provider produced a legitimate empty stream (zero chunks).
            # That's a valid response, not a failure - stop here rather
            # than trying (and needlessly contacting) the next provider.
            # Phase 10D: an empty stream still has a meaningful
            # time-to-"first-chunk" (there was none, but the provider
            # still took time to tell us that), so latency is recorded
            # here too, alongside the existing success bookkeeping.
            _elapsed_ms = (time.monotonic() - _start) * 1000
            _health_registry.record_latency(name, _elapsed_ms)
            # Phase 10A: a legitimate empty stream is a successful call,
            # not a failure, so it's recorded as a success.
            _health_registry.record_success(name)
            return
        except Exception as err:  # noqa: BLE001 - see send_message() note
            attempted_errors.append((name, err))
            # Phase 10A: passive bookkeeping only - does not affect
            # failover, which proceeds to the next provider exactly as
            # before this phase. Phase 10D: no latency is recorded on
            # failure - only a confirmed first chunk (or confirmed
            # empty stream) has a meaningful latency to report.
            _health_registry.record_failure(name)
            continue

        # First chunk obtained successfully: commit to this provider for
        # the remainder of the stream.
        # Phase 10D: elapsed time-to-first-chunk, recorded as passive
        # bookkeeping alongside record_success() below - computed before
        # yielding, but recording it does not delay or alter what
        # reaches the caller.
        _elapsed_ms = (time.monotonic() - _start) * 1000
        _health_registry.record_latency(name, _elapsed_ms)
        # Phase 10A: passive bookkeeping only - recorded once the first
        # chunk is confirmed, before yielding it; does not delay or
        # alter what reaches the caller.
        _health_registry.record_success(name)
        yield first_chunk
        yield from gen
        return

    raise _all_providers_failed(attempted_errors)


# --- Phase 7A: Observability -------------------------------------------
#
# Read-only diagnostics accessor. This is the single addition made for
# ROADMAP.md's Phase 7 ("Observability") first milestone: exposing the
# provider health/latency bookkeeping that Phase 10A/10D's
# ProviderHealthRegistry already collects, so it can be inspected after
# the fact instead of only ever being read internally by
# _priority_list().
#
# This function does not add any new bookkeeping, does not change what
# is recorded or when, and is never called by _priority_list(),
# _dispatch_send(), or _stream_with_failover() - it is purely a
# formatting/read layer on top of _health_registry.all_health(), which
# already exists. Per router/provider_health.py's own architectural
# note ("only llm_router.py imports or calls into this module"), this
# function is the one place api.py is expected to reach through rather
# than importing router.provider_health directly.
def get_diagnostics():
    """Returns a plain, JSON-serializable snapshot of every provider's
    currently recorded health/latency bookkeeping.

    Read-only: calls only ProviderHealthRegistry.all_health() and
    is_in_cooldown(), neither of which mutates registry state. Contains
    no API keys, credentials, or other secrets - ProviderHealth only
    ever stores a provider name, counters, timestamps, a derived
    status label, and a latency figure.

    Shape:
        {
            "providers": {
                "<provider_name>": {
                    "status": "healthy" | "unhealthy",
                    "consecutive_failures": <int>,
                    "last_success_at": <ISO 8601 str> | None,
                    "last_failure_at": <ISO 8601 str> | None,
                    "last_latency_ms": <float> | None,
                    "in_cooldown": <bool>,
                    "cooldown_until": <ISO 8601 str> | None,
                },
                ...
            }
        }

    Only providers the router has recorded at least one result for
    appear here (registered-but-never-called providers are simply
    absent, matching all_health()'s own behavior) - this function adds
    no default entries of its own.
    """
    providers = {}
    for name, entry in _health_registry.all_health().items():
        providers[name] = {
            "status": entry.status,
            "consecutive_failures": entry.consecutive_failures,
            "last_success_at": (
                entry.last_success_at.isoformat() if entry.last_success_at else None
            ),
            "last_failure_at": (
                entry.last_failure_at.isoformat() if entry.last_failure_at else None
            ),
            "last_latency_ms": entry.last_latency_ms,
            "in_cooldown": _health_registry.is_in_cooldown(name),
            "cooldown_until": (
                entry.cooldown_until.isoformat() if entry.cooldown_until else None
            ),
        }
    return {"providers": providers}
