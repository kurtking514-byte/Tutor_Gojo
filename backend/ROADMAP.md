# Tutor Gojo Roadmap

**Status:** Living document. Update the relevant phase's status and summary in the same change that completes or materially alters it.

---

## Completed

### Phase 1 — Memory Engine

**Status:** Completed

**Summary:**
Designed and built the `memory_engine` package as scaffolding alongside the existing, live `memory_service.py`/Obsidian read path, without touching it. Delivered four single-responsibility stages — `MemoryReader`, `MemoryRetriever`, `MemoryRanker`, `PromptBuilder` — plus the typed `MemorySnapshot`/`MemoryContext` data models covering all 13 memory categories (including `assessment_history` and `motivational_signals`, which existed in storage but weren't previously surfaced to any prompt). Retrieval and ranking were deliberately implemented as deterministic keyword matching (stdlib only, no embeddings, no model calls) rather than semantic search, to keep memory selection debuggable, testable, and free of added latency or cost. The package was built and reviewed function-by-function while remaining fully disconnected from the running application, so it carried zero risk to current behavior until explicitly wired in.

### Phase 2 — Memory Integration

**Status:** Completed

**Summary:**
Wired the memory engine into `chat_service.py`, replacing the old ad-hoc `_format_memory_context()`/`get_memory_context()` logic as the live path for building the per-turn memory prompt, while leaving the legacy function in place, unused, for reference. Added `_get_memory_prompt()` as a pure orchestrator of the four-stage pipeline, with explicit error handling: a scoped `MemoryLoadError` (a single category failing to load) and any other unexpected exception both degrade gracefully to an empty memory prompt rather than failing the chat turn, and neither is silently swallowed — both are logged. This phase went through a dedicated verification audit that traced the full pipeline end-to-end and confirmed the ten required properties (correct invocation, no skipped categories, no snapshot mutation, ranking-only reordering, correct empty-context behavior, no logic leakage into `chat_service`, proper error handling, backward compatibility, and legacy-code preservation). The audit caught and a follow-up fix resolved two production-blocking issues: an incorrect top-level import of `memory_service` in `reader.py` (it now matches the package-qualified import chat_service.py already used), and a `weak_topics` retrieval bug where keyword matching alone (without a mastery-level check) could surface already-mastered topics as "weak." Both fixes were verified end-to-end against the real call chain before sign-off.

### Phase 3 — Gemini Provider Extraction

**Status:** Completed

**Summary:**
Split the original monolithic `gemini_client.py` — which mixed Gemini SDK setup, model caching, history translation, streaming/non-streaming calls, the tutor's persona content, and product features (quiz generation, code explanation) into one file — into four purpose-built pieces: `providers/gemini_provider.py` (`GeminiProvider`, containing only Gemini-SDK-specific logic: configuration, model/client caching, history-format translation, request construction, streaming, and error normalization), `persona.py` (provider-agnostic persona text and generic generation defaults), `tutor_features.py` (quiz generation and code explanation, built on the generic provider interface rather than raw SDK calls), and a rewritten `gemini_client.py` reduced to a thin backward-compatible facade that forwards to the above. Every public function retained its original name and signature. Behavioral equivalence was verified with a stub Gemini SDK exercising non-streaming/streaming calls (with and without history), both error paths, quiz parsing, code explanation, and model-caching identity — outputs were byte-for-byte identical between the original and refactored versions, and `stream_message`'s lazy-generator behavior was confirmed unchanged.

### Phase 4 — LLM Router

**Status:** Completed

**Summary:**
Introduced `llm_router.py` as the single, currently-unconditional dispatch point between `gemini_client.py` and `providers/gemini_provider.py`. It exposes exactly the two functions `gemini_client.py` already depended on (`send_message`, `stream_message`) and, for now, always forwards to `GeminiProvider` — no provider selection, fallback, retry, or health-check logic was added. `gemini_client.py` was updated so that `send_message`/`stream_message` delegate through the router, while its other functions (`configure_gemini`, `build_system_prompt`, `create_model`, `generate_content`, `generate_quiz`, `explain_code`) continue to call `GeminiProvider`/`tutor_features` directly, since they were out of scope for this phase. The full behavioral test suite from Phase 3 was re-run against the new chain and produced identical output, and generator laziness through the added router hop was specifically re-confirmed.

---

## Future Phases

### Phase 5 — Multi-Provider Support

**Objective:** Allow Tutor Gojo to actually call more than one LLM vendor, using the provider contract and router seam already established.

**Deliverables:**
- One new provider module per vendor (e.g. `providers/openai_provider.py`, `providers/openrouter_provider.py`, `providers/openclaw_provider.py`), each implementing the same `send`/`stream` contract as `GeminiProvider`.
- Provider selection logic inside `llm_router.py` (e.g. driven by a `config.get_setting("provider", ...)` value), replacing today's unconditional dispatch.
- Per-provider mapping of `persona.GENERATION_DEFAULTS` onto that vendor's own parameter names.

**Success Criteria:**
- `chat_service.py` and `gemini_client.py` require zero changes.
- Switching the configured provider changes which vendor answers a turn without changing any prompt content, memory behavior, or persistence behavior.
- Each new provider has its own equivalent of Phase 3's behavioral-equivalence test suite.

### Phase 6 — Automatic Failover

**Objective:** Keep a chat turn alive when the primary provider is unavailable or erroring.

**Deliverables:**
- A defined ordering/policy for provider fallback inside `llm_router.py`.
- Consistent error classification across providers (transient vs. non-retryable) so the router can decide when to fail over vs. surface an error.
- Tests simulating a primary-provider failure and confirming a seamless fallback response.

**Success Criteria:**
- A single provider outage does not interrupt a chat session for the end user.
- Failover behavior is observable (see Phase 7) and does not silently mask a systemic issue.

### Phase 7 — Observability

**Objective:** Make it possible to see, after the fact, which provider handled a turn, how long it took, and whether anything degraded gracefully (an empty memory prompt, a provider fallback, a swallowed non-critical error).

**Deliverables:**
- Structured logging (or metrics) at the `llm_router` and memory-pipeline boundaries: provider used, latency, memory-load outcome per category.
- A lightweight way to inspect recent turns' provider/memory behavior without reading raw print statements.

**Success Criteria:**
- Any degraded turn (empty memory prompt, provider fallback, category load failure) is identifiable after the fact without reproducing the conversation.

### Phase 8 — Adaptive Memory

**Objective:** Improve retrieval/ranking quality beyond keyword matching, without giving up the debuggability that motivated the deterministic design.

**Deliverables:**
- An evaluation of where deterministic keyword matching under- or over-retrieves in practice.
- A proposal for what (if anything) changes in `MemoryRetriever`/`MemoryRanker` — kept as additive/optional rather than replacing the deterministic path outright, so the existing guarantees aren't lost by default.

**Success Criteria:**
- Any change preserves `MemorySnapshot`/`MemoryContext`'s existing shape, so `PromptBuilder` and everything above the memory engine is unaffected.
- Retrieval/ranking behavior remains inspectable and testable, even if it becomes more sophisticated.

### Phase 9 — Tutor Intelligence

**Objective:** Use the now-solid memory and provider foundation to make the tutor's teaching decisions smarter — not just recalling facts about the student, but adapting pacing, difficulty, and review scheduling.

**Deliverables:**
- Features built as consumers of the existing memory/provider interfaces (in the same spirit as `tutor_features.py`), not as changes to the memory engine or providers themselves.
- Use of currently-loaded-but-underused `MemorySnapshot` categories (e.g. `assessment_history`, `motivational_signals`, `coding_style_traits`) in retrieval/ranking or in new features.

**Success Criteria:**
- New intelligence features do not require changes to `MemoryReader`, `MemoryRetriever`, `MemoryRanker`, or `PromptBuilder`'s core contracts.

### Phase 10 — Production Hardening

**Objective:** Prepare the system for sustained real-world use.

**Deliverables:**
- Load/failure testing across the full chain (memory engine, providers, router, persistence).
- Formal test coverage for the dependency rules in `ARCHITECTURE.md` Section 9 (e.g. a check that `providers/*` never imports `memory_engine` or `services`).
- Documentation review pass to ensure `ARCHITECTURE.md` and this roadmap still match reality.

**Success Criteria:**
- The system degrades gracefully under partial failure (a slow/erroring provider, a missing memory category, a database hiccup) at every layer, not just the ones already covered by existing try/except blocks.
- Architecture and roadmap docs pass a review confirming no drift from the actual codebase.

### Phase 11 — Plugin / Extension System

**Objective:** Give Tutor Gojo a way to integrate external tools and capabilities — GitHub, web search, a terminal, a compiler, documentation lookup, and other external tools — through a defined plugin architecture, rather than growing `chat_service.py` with a new special case for every integration.

**Deliverables:**
- A plugin contract (analogous to the provider contract in Section 8 of `ARCHITECTURE.md`) that every integration implements, so `chat_service.py` invokes plugins uniformly instead of containing integration-specific logic.
- A plugin registry/discovery mechanism so available plugins can be enumerated and invoked without `chat_service.py` hardcoding a list of them.
- Reference plugin implementations demonstrating the contract — for example, one read-only integration (e.g. documentation lookup) and one that requires more careful sandboxing (e.g. a terminal or compiler plugin) — to prove the contract works across different risk profiles.
- Documentation of the plugin contract in `ARCHITECTURE.md`, following the same "Allowed dependencies / Forbidden dependencies" format already used for providers and services.

**Success Criteria:**
- `chat_service.py` gains a single, generic "invoke a plugin" seam rather than growing one bespoke code path per integration (GitHub, web search, terminal, compiler, documentation lookup, or any future external tool).
- A new integration can be added as a new plugin module without changes to `chat_service.py`, `memory_engine/*`, or `providers/*` — mirroring the isolation already achieved for LLM providers (ADR-004 and ADR-005 in `DECISIONS.md`).
- Plugins that execute code or access external systems (e.g. a terminal or compiler plugin) have an explicit permission/sandboxing model, rather than inheriting `chat_service.py`'s trust level implicitly.
- Existing chat behavior is unaffected when no plugins are enabled, preserving the backward-compatibility and incremental-rollout discipline established in prior phases (ADR-006 in `DECISIONS.md`).

---

## Long-Term Vision

Tutor Gojo's long-term goal is to be a coding tutor that gets measurably better at teaching *this specific student* the longer they use it — remembering not just what they've covered, but how they learn best, where they get stuck, and what motivates them — while remaining, underneath that experience, a small number of clean, single-purpose layers: a deterministic memory pipeline that can be inspected and improved independently of any model, and a provider layer that can add, swap, or fail over between LLM vendors without the rest of the system ever needing to know or care which one is answering. Every phase above is designed to add capability without collapsing that separation.
