# Tutor Gojo Architecture

**Status:** Living document. Reflects the system as it exists today. Update this file in the same change that changes the architecture it describes — an architecture doc that drifts from the code is worse than no architecture doc.

---

## 1. Project Vision

Tutor Gojo is an AI coding tutor with a persistent personality ("the Confident Mentor") that remembers a student across sessions — what they're strong at, what they struggle with, what they've already covered, and how they like to be taught — and uses that memory to make every tutoring turn more relevant than a stateless chatbot could.

The project is built as a **long-term platform**, not a one-off chatbot wrapper. Two goals are treated as first-class, on equal footing with shipping features:

- **Modular architecture** — every capability (memory, LLM access, orchestration) lives behind a boundary that can be reasoned about, tested, and replaced independently of the others.
- **Maintainability** — the codebase is expected to be read, extended, and partially rewritten by many engineers (and AI agents) over a long lifetime. Code is written for the next person, not just to pass today's test.

Concretely, this has already shaped two major decisions: memory retrieval was rebuilt as a deterministic, inspectable pipeline instead of ad-hoc string formatting, and the Gemini integration was split into a provider/router shape specifically so additional LLM providers can be added later without disturbing the rest of the system.

---

## 2. Design Philosophy

| Principle | What it means here |
|---|---|
| **Separation of Concerns** | Reading memory, filtering it, ranking it, formatting it, and calling an LLM are five different jobs, done by five different modules. No module does two of these jobs at once. |
| **Layered Architecture** | Requests flow downward through clearly ordered layers (orchestration → memory → LLM), and each layer only talks to the layer immediately below it. |
| **Single Responsibility Principle** | Each class in the memory pipeline (`MemoryReader`, `MemoryRetriever`, `MemoryRanker`, `PromptBuilder`) does exactly one transformation and nothing else — enforced deliberately in each module's docstring ("only selects, never ranks"; "only ranks, never retrieves"; etc.). |
| **Backward Compatibility** | When internals are restructured (e.g. `gemini_client.py` being decomposed into a provider + router), the public function signatures callers depend on (`send_message`, `stream_message`) are preserved exactly, so callers never need to change. |
| **Incremental Refactoring** | Large changes are landed in small, independently-verifiable phases (memory engine → wired into chat_service → provider extraction → router introduction), each of which was audited for behavioral equivalence before moving to the next. |
| **Extensibility** | New capability is added by adding a new module that satisfies an existing contract (a new provider, a new memory category), not by editing unrelated code. |
| **Deterministic Memory Retrieval** | Memory filtering and ranking use plain keyword/field matching — no embeddings, no fuzzy matching, no model calls. Given the same snapshot and message, retrieval always produces the same result, which makes it testable and debuggable. |
| **Minimal Coupling** | Modules depend on data shapes (dataclasses) and narrow function contracts, not on each other's internals. |
| **High Cohesion** | Code that changes for the same reason lives in the same file (e.g. everything Gemini-SDK-specific lives in `GeminiProvider`; everything persona-related lives in `persona.py`). |

---

## 3. Architecture Principles

These principles are the distilled rules of thumb behind Section 2's design philosophy — the checklist a contributor should hold a change against before landing it. They're not new decisions; they're restatements of choices already made and explained in `DECISIONS.md`.

- **One responsibility per module** — if a module's docstring needs "and" to describe its job, it's a candidate for splitting. This is exactly how `memory_engine`'s four stages and the LLM layer's provider/router split arrived at their current shapes.
- **Explicit dependencies** — a module's allowed and forbidden dependencies (Section 6) are declared, not implied. Nothing reaches into another module's internals; everything goes through that module's public functions or data shapes.
- **Stable interfaces** — public function names and signatures (`send_message`, `stream_message`, the `send`/`stream` provider contract) are treated as commitments. They change only with a deliberate, documented reason.
- **Backward compatibility** — internal restructuring must not force callers to change. `gemini_client.py` exists specifically to absorb two rounds of internal restructuring (provider extraction, router introduction) without any caller noticing.
- **Incremental evolution** — architecture changes land as a sequence of small, independently verified phases (see `ROADMAP.md` and ADR-006 in `DECISIONS.md`), not as large rewrites.
- **Composition over duplication** — shared policy (generation defaults, persona text, the `MAX_HISTORY_TURNS` constant) lives in one place and is consumed by whoever needs it, rather than being copy-pasted per provider or per feature.
- **Keep orchestration separate from implementation** — `chat_service.py` decides *what* happens and *in what order*; it never decides *how* memory retrieval, ranking, or an LLM call actually works. Those decisions live in `memory_engine` and `providers/*` respectively.
- **Avoid hidden side effects** — retrieval and ranking never mutate their inputs; a function's return value is its only observable effect on the rest of the system, so callers can always reason locally about what a function did.

---

## 4. Current System Architecture

```
User
  ↓
chat_service.py
  ↓
  ├─→ database                      (history fetch / persistence)
  │
  ├─→ Memory Engine
  │     MemoryReader
  │         ↓
  │     MemoryRetriever
  │         ↓
  │     MemoryRanker
  │         ↓
  │     PromptBuilder
  │         ↓
  │   (returns a memory-prompt string, or "" on failure)
  │
  ├─→ Prompt Assembly
  │     (_augment_message_with_memory: prepend memory prompt to the
  │      user's message — persistence still uses the original message)
  │
  └─→ gemini_client.py               (compatibility facade)
        ↓
      llm_router.py                  (single dispatch point)
        ↓
      providers/gemini_provider.py   (GeminiProvider)
        ↓
      Gemini API  (google.generativeai SDK)
```

A second, independent path exists for **writing** memory after a turn completes:

```
chat_service._update_learning_memory()
  ↓
learning_summary.generate_learning_summary()   (LLM-based extraction)
  ↓
services/memory_service.py   (record_strength, update_topic_mastery, add_journal_entry, ...)
  ↓
Obsidian backend   (markdown files, source of truth)
```

### Layer explanations

- **`chat_service.py`** — the only orchestrator. Fetches history, persists messages, calls the memory pipeline, augments the message, calls the LLM layer, and triggers the post-turn memory write. Contains no retrieval, ranking, formatting, or LLM-SDK logic itself.
- **Memory Engine** (`memory_engine/`) — turns raw stored memory into a compact prompt block for this specific turn. Four stages, each with a single job (see Section 7).
- **Prompt Assembly** — the small step in `chat_service.py` that combines the memory-engine output with the user's raw message into the string actually sent to the LLM, while keeping the original message as what gets persisted and shown to the user.
- **`gemini_client.py`** — a thin, backward-compatible facade. Preserves the original public function names or behavior that other code (and history) depends on, while forwarding to the router.
- **`llm_router.py`** — the single seam where "which provider handles this request" will eventually be decided. Currently unconditional: it always dispatches to `GeminiProvider`.
- **`providers/gemini_provider.py`** — the only module that talks to the Gemini SDK. Owns model caching, history-format translation, streaming/non-streaming request construction, and Gemini-specific error handling.
- **Gemini API** — the external LLM service itself, accessed via `google.generativeai`.

---

## 5. Folder Structure

> Only folders/files that exist in the current codebase are documented below. Anything not listed here (e.g. an `api/` layer, a test suite layout, deployment config) is out of scope for this document until it exists — do not assume it or build against it.

### `memory_engine/`

- **Purpose:** Deterministic pipeline that turns stored student memory into a prompt-ready string for a single chat turn.
- **Responsibilities:** Typed data models (`models.py`), reading a full snapshot (`reader.py`), narrowing it to what's relevant to the current message (`retrieval.py`), ordering it by relevance (`ranking.py`), and serializing it to Markdown (`prompt_builder.py`).
- **Example files:** `models.py`, `reader.py`, `retrieval.py`, `ranking.py`, `prompt_builder.py`, `__init__.py`.
- **Must NOT contain:** any LLM/SDK calls, any database or filesystem I/O of its own (all storage access goes through `services/memory_service.py`), any orchestration logic (session handling, message persistence), any UI/formatting concerns beyond the single Markdown block `PromptBuilder` produces.

### `services/`

- **Purpose:** The existing, stable interface to the memory storage backend.
- **Responsibilities:** Exposes `get_*`/`record_*`/`update_*`/`add_*` functions per memory category (e.g. `get_topic_mastery`, `record_strength`, `add_journal_entry`) that `memory_engine.reader` and `chat_service` call. Internally reuses the Obsidian markdown backend.
- **Example files:** `memory_service.py`.
- **Must NOT contain:** memory_engine's dataclasses or filtering/ranking logic, LLM calls, chat orchestration.

### `providers/`

- **Purpose:** Home for LLM provider implementations — one module per vendor.
- **Responsibilities:** Each provider owns authentication/configuration, client/model caching, translating the generic `[(role, content), ...]` history format into that vendor's request shape, issuing streaming/non-streaming requests, and normalizing that vendor's errors. Every provider exposes the same two-function contract: `send(message, history=None, use_search=False) -> str` and `stream(...) -> Iterator[str]`.
- **Example files:** `gemini_provider.py`, `__init__.py`. (Future: `openai_provider.py`, `openrouter_provider.py`, `openclaw_provider.py`.)
- **Must NOT contain:** persona/system-prompt content, product features (quiz generation, code explanation), memory access, database access, provider-selection/routing logic.

### Top-level modules (no dedicated folder yet)

- `chat_service.py` — orchestration (see Section 6).
- `gemini_client.py` — backward-compatible facade over `llm_router`.
- `llm_router.py` — single LLM dispatch point.
- `persona.py` — provider-agnostic persona text and generic generation policy.
- `tutor_features.py` — quiz generation and code explanation, built on the generic send/stream interface.
- `database.py` — chat history and session persistence (SQLite-backed, per existing code references).
- `learning_summary.py` — post-turn LLM-based extraction of a structured learning summary from a session's transcript.
- `config.py` — settings and API key lookup (`get_api_key`, `get_setting`).

---

## 6. Module Responsibilities

### `chat_service`

- **Purpose:** Orchestrate a single chat turn end-to-end.
- **Responsibilities:** Session/history management, message persistence, invoking the memory pipeline, assembling the augmented prompt, invoking the LLM layer (streaming and non-streaming), triggering the post-turn learning-memory update, topic tagging for the progress dashboard.
- **Allowed dependencies:** `database`, `gemini_client`, `learning_summary`, `services.memory_service`, `memory_engine.*`.
- **Forbidden dependencies:** `providers.*` directly (must go through `gemini_client`/`llm_router`), Obsidian backend directly (must go through `services.memory_service`), any LLM SDK directly.

### `memory_engine`

- **Purpose:** Deterministic retrieval, ranking, and formatting of student memory for prompt injection.
- **Responsibilities:** See Section 7.
- **Allowed dependencies:** `services.memory_service` (via `reader.py` only).
- **Forbidden dependencies:** Any LLM/provider module, `database`, `chat_service` (no upward or sideways calls — data flows one direction, `chat_service` → `memory_engine`).

### `services` (memory_service)

- **Purpose:** Stable read/write interface to the memory storage backend.
- **Responsibilities:** One `get_*`/`record_*`/`update_*`/`add_*` function per memory category; internally delegates to the Obsidian backend's markdown parsing.
- **Allowed dependencies:** Obsidian backend.
- **Forbidden dependencies:** `memory_engine.*` (dependency points the other way — `memory_engine.reader` depends on `services`, not vice versa), any LLM/provider module, `chat_service`.

### `providers`

- **Purpose:** Vendor-specific LLM SDK integration.
- **Responsibilities:** See Section 8.
- **Allowed dependencies:** The vendor's own SDK, `config`, `persona` (for reading provider-agnostic prompt content/generation defaults, which the provider then maps to its own parameter names).
- **Forbidden dependencies:** `memory_engine.*`, `services.*`, `database`, `chat_service`, `tutor_features` (a provider must never know about product features built on top of it).

### `gemini_client`

- **Purpose:** Backward-compatible public entry point for Gemini communication.
- **Responsibilities:** Forwards `send_message`/`stream_message` to `llm_router`; forwards `configure_gemini`/`build_system_prompt`/`create_model`/`generate_content` directly to `GeminiProvider`; forwards `generate_quiz`/`explain_code` to `tutor_features`. Contains no logic of its own beyond this delegation.
- **Allowed dependencies:** `llm_router`, `providers.gemini_provider`, `tutor_features`.
- **Forbidden dependencies:** `memory_engine.*`, `services.*`, `database` — this module must remain a pure pass-through.

### `llm_router`

- **Purpose:** The single seam where provider selection will eventually be decided.
- **Responsibilities:** Today, unconditionally dispatches `send_message`/`stream_message` to `GeminiProvider`. No fallback, retry, health-check, or selection logic exists yet.
- **Allowed dependencies:** `providers.*`.
- **Forbidden dependencies:** `chat_service`, `memory_engine.*`, `services.*`, `database` — the router only ever talks downward to providers.

### `database`

- **Purpose:** Persistence of chat sessions and message history.
- **Responsibilities:** `create_session`, `get_chat_history`, `save_message`, `update_progress`.
- **Allowed dependencies:** Underlying SQLite (or equivalent) driver.
- **Forbidden dependencies:** Any LLM/provider module, `memory_engine.*`, `services.*`.

### `learning_summary`

- **Purpose:** Post-turn extraction of a structured learning summary (topics learned, strengths, misconceptions, mistake patterns, confidence, next lesson) from a session transcript.
- **Responsibilities:** `generate_learning_summary(messages)`. Uses an LLM call to produce the summary; the exact provider path it uses should go through the same `gemini_client`/`llm_router` seam as live chat, not a separate direct SDK call, to keep provider selection centralized.
- **Allowed dependencies:** `gemini_client` (or, once fully aligned, `llm_router`).
- **Forbidden dependencies:** `memory_engine.*`, `services.*` directly (writes happen through `chat_service._update_learning_memory` calling `services.memory_service`, not from within `learning_summary` itself).

### Obsidian backend

- **Purpose:** Source-of-truth storage for all educational memory, as markdown files with YAML frontmatter.
- **Responsibilities:** Parsing/writing markdown notes per memory category.
- **Allowed dependencies:** Filesystem, YAML/markdown parsing libraries.
- **Forbidden dependencies:** Everything above it in the stack — the Obsidian backend must never be called directly by `memory_engine`, `chat_service`, or any provider; all access goes through `services.memory_service`.

---

## 7. Memory Engine

The memory engine is a four-stage pipeline, each stage doing exactly one transformation:

```
MemoryReader.load_snapshot()
        ↓  MemorySnapshot   (everything known, unfiltered, unranked)
MemoryRetriever.retrieve(snapshot, message)
        ↓  MemoryContext    (only what's relevant to this message)
MemoryRanker.rank(context, message)
        ↓  MemoryContext    (same items, reordered by relevance)
PromptBuilder.build(ranked_context)
        ↓  str               (Markdown block, or "" if nothing to say)
```

- **`MemoryReader`** exists to isolate "how do I get memory out of storage" from everything downstream. It delegates every category read to `services.memory_service`'s existing `get_*` functions, converts results into typed dataclasses, and wraps any category-specific failure in a `MemoryLoadError` that names the category and chains the original exception — so a broken category degrades that category only, never the whole snapshot, and never silently.
- **`MemoryRetriever`** exists to reduce the full snapshot down to what's plausibly relevant to *this* message, using deterministic case-insensitive keyword matching against a handful of text fields per category. It performs no scoring and does not mutate the snapshot.
- **`MemoryRanker`** exists to order the already-retrieved candidates by keyword overlap with the current message, using a stable sort so ties preserve their original order. It never removes or adds items — same object references in, same references out, just reordered.
- **`PromptBuilder`** exists to turn the final `MemoryContext` into the exact Markdown block injected into the LLM prompt. It performs no filtering or ranking of its own; it is a pure serializer, and an empty context correctly produces `""`.
- **`MemorySnapshot`** is the full-fidelity, unfiltered representation of everything currently known about the student — one field per memory category (13 total, including categories like `assessment_history` and `motivational_signals` that predate the memory engine but weren't previously surfaced to the prompt).
- **`MemoryContext`** is the narrower, turn-specific subset that actually reaches `PromptBuilder` — explicit, inspectable data instead of the ad-hoc string-formatting logic this pipeline replaced.

### Why deterministic retrieval was chosen

Keyword-based filtering and ranking (no embeddings, no fuzzy matching, no model calls) were chosen deliberately so that, given the same snapshot and the same user message, the memory pipeline always produces the same result. This makes memory selection debuggable (a wrong result can be traced to a specific keyword/field, not an opaque similarity score), testable without mocking a model, and free of the latency and cost an embedding or LLM-based retrieval step would add to every single chat turn.

---

## 8. LLM Layer

```
gemini_client.py  (compatibility facade)
        ↓
llm_router.py     (single dispatch point)
        ↓
providers/gemini_provider.py  (GeminiProvider)
        ↓
Gemini API
```

- **`GeminiProvider`** contains everything specific to Google's Gemini SDK: `genai.configure`, cached `GenerativeModel` construction, translating `[(role, content), ...]` history into Gemini's `{"role": ..., "parts": [...]}` shape, issuing `start_chat`/`send_message` calls (streaming and non-streaming), and normalizing Gemini's own error strings into a consistent `ValueError`. It knows nothing about the tutor's persona content or product features — those are injected via `persona.py` and consumed separately by `tutor_features.py`.
- **`gemini_client.py`** is a thin, intentionally boring compatibility layer. Every function keeps its historical name and signature; `send_message`/`stream_message` forward to `llm_router`, while `configure_gemini`/`build_system_prompt`/`create_model`/`generate_content` forward directly to `GeminiProvider`, and `generate_quiz`/`explain_code` forward to `tutor_features`. This is what lets every existing caller (`chat_service.py` in particular) remain completely unaware that a router or provider abstraction exists underneath it.
- **`llm_router`** is currently a one-line pass-through with no conditional logic: both of its functions call straight into `GeminiProvider`. Its entire purpose is to already exist as the seam where provider selection will be added later, so that addition doesn't require touching `gemini_client.py` or anything above it.
- **Future providers** (OpenAI, OpenRouter, OpenClaw, etc.) are added by creating a new module under `providers/` that implements the same two-function contract (`send`/`stream` with the same signatures and return shapes as `GeminiProvider`), and then teaching `llm_router` how to choose between them. No other module in the system should need to change when a provider is added.

---

## 9. Dependency Rules

- `chat_service` orchestrates only — it must contain no retrieval, ranking, formatting, or LLM-SDK logic of its own.
- The memory engine never calls an LLM — memory selection is deterministic keyword matching, not model-based.
- Providers never access memory — `providers/*` must not import `memory_engine` or `services`.
- Providers never write to the database — persistence is `chat_service`'s and `services.memory_service`'s job, not a provider's.
- Business/product logic belongs outside providers — quiz generation, code explanation, and any future feature must be built in a feature module (e.g. `tutor_features.py`) on top of the provider's generic `send`/`stream`/`generate_content` interface, never inside `providers/*` itself.
- Feature modules should use provider interfaces, not SDK objects — `tutor_features.py` calls `gemini_client.generate_content`/`send_message`; it never imports `google.generativeai` or touches a raw model object.
- Avoid circular dependencies — data and calls flow one direction: `chat_service` → `memory_engine` → `services`; `chat_service` → `gemini_client` → `llm_router` → `providers`. Nothing downstream calls back upstream.

---

## 10. Coding Standards

- One responsibility per module — if a module's docstring needs "and" to describe its job, it's a candidate for splitting (this is exactly how the memory engine and the LLM layer arrived at their current shapes).
- Small, focused functions — each pipeline stage exposes one clear entry point (`retrieve`, `rank`, `build`) plus private helpers.
- Explicit error handling — expected failure modes get a named exception type (`MemoryLoadError`) that identifies what failed and preserves the original cause; unexpected exceptions are always logged, never silently swallowed.
- No hidden side effects — retrieval and ranking never mutate their inputs; callers can rely on the snapshot/context they passed in being unchanged after the call.
- Prefer composition over duplication — shared policy (e.g. `MAX_HISTORY_TURNS`, generation defaults, persona text) lives in one place (`persona.py`) and is consumed by whichever provider needs it, rather than being copy-pasted per provider.
- Maintain backward compatibility whenever possible — internal restructuring (provider extraction, router introduction) must preserve every existing public function's name, signature, and behavior unless there's a deliberate, documented reason not to.

---

## 11. Extension Guide

This section documents the expected workflow for the kinds of extension the architecture is deliberately designed to support (Section 3: "Extensibility"). Following these workflows is what keeps future expansion predictable — a contributor (or an AI agent) should be able to look up the kind of change they're making and know which modules to touch, and which to leave alone.

### Adding a memory category

1. Add the corresponding `get_*`/`record_*`/`update_*`/`add_*` function(s) to `services/memory_service.py`, following the existing per-category pattern.
2. Add the new field to the `MemorySnapshot` dataclass in `memory_engine/models.py`, and load it in `MemoryReader.load_snapshot()` by calling the new service function — wrapping any failure in `MemoryLoadError` like every other category.
3. If the category should be searchable, add its relevant text field(s) to `MemoryRetriever`'s keyword-matching logic in `retrieval.py`.
4. If the category should affect ordering, extend `MemoryRanker`'s scoring in `ranking.py`.
5. Extend `PromptBuilder` in `prompt_builder.py` to render the new category into the Markdown block, if and when it should appear in the prompt.
6. **Do not** touch `chat_service.py` — the memory pipeline's four-stage contract (Section 7) is what makes this possible without an orchestration change.

### Adding a provider

1. Create a new module under `providers/` (e.g. `providers/openai_provider.py`) implementing the same two-function contract as `GeminiProvider`: `send(message, history=None, use_search=False) -> str` and `stream(...) -> Iterator[str]`.
2. Map `persona.GENERATION_DEFAULTS` onto the new vendor's own parameter names inside that provider — do not modify `persona.py` itself for vendor-specific mapping.
3. Register the new provider in `llm_router.py`'s selection logic (once Phase 5's selection logic exists; today's unconditional dispatch is the seam this is designed to extend into, per ADR-005 in `DECISIONS.md`).
4. Write a behavioral-equivalence test suite for the new provider, following the pattern established for `GeminiProvider` in Phase 3 of `ROADMAP.md`.
5. **Do not** touch `chat_service.py`, `gemini_client.py`, `memory_engine/*`, or `services/*` — none of them should need to know a new provider exists.

### Adding a new feature (e.g. a new tutor capability)

1. Build the feature as a new function (or new module, for anything beyond a couple of functions) that consumes the existing provider interface — `gemini_client.generate_content`/`send_message` or, once available, `llm_router` directly — the same way `tutor_features.py` does today.
2. If the feature needs memory context beyond what's already in the prompt, read it through `services/memory_service.py` or the memory engine's existing output — never by reaching into the Obsidian backend directly.
3. **Do not** put feature logic inside `providers/*` — a provider must stay vendor-SDK-only (Section 6, "Forbidden dependencies").
4. Wire the feature into `chat_service.py` only at the orchestration level (deciding *when* to call it), not by embedding the feature's own logic into `chat_service.py`.

### Adding a service (a new storage-backed capability under `services/`)

1. Add the new function(s) to `services/memory_service.py` (or a new sibling module under `services/`, if the capability is unrelated to existing memory categories) that talk to the Obsidian backend or other storage.
2. Keep the function signature style consistent with existing services (`get_*`/`record_*`/`update_*`/`add_*`).
3. **Do not** import `memory_engine.*` from within `services/*` — the dependency points the other way (Section 6).
4. Consumers of the new service (`memory_engine.reader` and/or `chat_service`) call it the same way they call every other service function — no special-casing.

---

## 12. Architectural Decision Summary

| Decision | Rationale |
|---|---|
| **Obsidian as the source of truth** | Educational memory is stored as human-readable markdown with YAML frontmatter, accessed only through `services.memory_service`, so the storage format can evolve without every consumer needing to know how to parse it. |
| **Deterministic memory retrieval** | Chosen over embeddings/fuzzy matching for debuggability, testability, and zero added latency/cost per turn (Section 7). |
| **Layered memory engine** | Reader → Retriever → Ranker → PromptBuilder, each with a single responsibility, replacing what used to be ad-hoc aggregation and string-formatting spread across `memory_service` and `chat_service`. |
| **Provider abstraction** | `GeminiProvider` isolates all Gemini-SDK-specific code behind a small, vendor-agnostic `send`/`stream` contract, so a new vendor can be added as a sibling module rather than a rewrite. |
| **Compatibility wrapper** | `gemini_client.py` was kept, rather than renamed/removed, specifically so no existing caller had to change when the internals were restructured underneath it. |
| **LLM Router** | Introduced as a single, currently-unconditional dispatch point between `gemini_client` and providers, so that future provider selection logic has exactly one place to live. |

---

## 13. Future Architecture

Once the phases in `ROADMAP.md` are complete, the intended long-term shape is:

```
User
  ↓
chat_service
  ↓
Memory Engine (Reader → Retriever → Ranker → PromptBuilder)
  ↓
Prompt Assembly
  ↓
gemini_client (compatibility facade, retained indefinitely)
  ↓
llm_router  (provider selection: policy, health, cost, or user-configured)
  ↓
   ├─→ GeminiProvider    → Gemini API
   ├─→ OpenAIProvider    → OpenAI API
   ├─→ OpenRouterProvider→ OpenRouter API
   └─→ OpenClawProvider  → OpenClaw API
```

`llm_router` grows from an unconditional pass-through into the place where provider choice, failover, and (eventually) observability hooks live — without `chat_service.py` or any module above it changing at all. The memory engine's deterministic contract is expected to remain unchanged even as its underlying storage or ranking heuristics evolve, since everything above `MemoryReader` only depends on the `MemorySnapshot`/`MemoryContext` shapes, not on how they're populated.
