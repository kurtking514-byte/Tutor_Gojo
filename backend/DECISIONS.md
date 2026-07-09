# Tutor Gojo Architecture Decisions

**Status:** Living document. Each entry records *why* an architectural decision was made — the context, the alternatives that were weighed, and the trade-offs accepted — not *how* it was implemented. Implementation detail lives in `ARCHITECTURE.md`; sequencing and delivery status live in `ROADMAP.md`. This file is the historical record of reasoning behind both.

---

## ADR-001 — Obsidian as the Single Source of Truth

**Decision**

All persistent student memory (topic mastery, strengths, journal entries, assessment history, motivational signals, and the rest of the 13 memory categories) is stored as human-readable markdown files with YAML frontmatter, managed through Obsidian, and accessed exclusively through `services/memory_service.py`.

**Context**

Tutor Gojo needs to remember a student across sessions in enough detail to genuinely adapt its teaching — not just log transcripts, but track structured facts like which topics are mastered, which are weak, and what motivates a given student. That data needs to be durable, inspectable, and editable outside the application itself, since a tutor, parent, or the student may want to read or correct it directly.

**Alternatives Considered**

- **A relational database (SQLite/Postgres):** already used elsewhere in the project for chat history, so it was a natural candidate. Rejected as the *memory* store because it makes the data opaque to anyone without a DB client or admin tool, and schema migrations add friction to a data model that was still evolving.
- **A document database / JSON blobs:** more flexible than SQL, but still not human-readable or human-editable without tooling, and offers no natural authoring workflow.
- **A dedicated vector store:** considered and rejected at the storage layer for the same reasons it was rejected at the retrieval layer — see ADR-002.

**Why Obsidian Was Chosen**

- **Human-readable and human-editable** — markdown with YAML frontmatter can be opened, read, and corrected by a person with no special tooling.
- **Inspectable by default** — anyone can `grep` or open the vault and see exactly what the system knows about a student, which matters both for debugging and for trust.
- **Decouples storage format from consumers** — `services/memory_service.py` is the only module that knows the data lives in Obsidian; every other module depends on that service's function contracts, not on markdown parsing.

**Consequences**

- Reads and writes are file-based rather than transactional; concurrent-write safety is the responsibility of `services/memory_service.py`, not the storage format.
- All new memory categories must be added as new `get_*`/`record_*`/`update_*`/`add_*` functions in `services/memory_service.py` — nothing above that layer is allowed to touch the Obsidian backend directly (see `ARCHITECTURE.md` Section 8).

**Future Considerations**

If the memory vault grows large enough that full-snapshot reads become slow, an indexing or caching layer could be introduced *inside* `services/memory_service.py` without changing its public contract or requiring `memory_engine` to change at all.

---

## ADR-002 — Deterministic Memory Retrieval

**Decision**

Memory retrieval and ranking (`memory_engine/retrieval.py`, `memory_engine/ranking.py`) use plain, case-insensitive keyword matching against a fixed set of text fields per category. The project intentionally does not use embeddings, a vector database, or any AI-based retrieval step in this pipeline.

**Context**

Every chat turn needs to pull a small, relevant slice of a much larger memory snapshot before it can be added to the prompt. The obvious modern approach is semantic retrieval — embed the message and the memory, and pull the nearest neighbors. That approach was deliberately not taken.

**Why Embeddings/Vector Retrieval Were Avoided**

- **Determinism:** keyword matching given the same snapshot and the same message always produces the same result. Semantic retrieval, by contrast, depends on model/embedding versions, index state, and floating-point similarity scores that can shift subtly between runs.
- **Explainability:** a retrieval result can always be traced back to the specific field and keyword that matched. There is no opaque similarity score to interpret when something looks wrong.
- **Debuggability:** a bug in retrieval is a logic bug in a small, readable function — not a question of "was the embedding model or the index stale."
- **Predictability:** the same input always yields the same memory prompt, which matters for reproducing issues and for testing without mocking a model.
- **Lightweight:** no embedding calls, no vector index to build or maintain, and no added latency or per-call cost on top of every single chat turn.

**Advantages Summary**

| Property | Keyword Matching | Embeddings/Vector Retrieval |
|---|---|---|
| Deterministic | Yes | No (depends on model/index state) |
| Explainable | Yes — traceable to a field/keyword | No — similarity score only |
| Debuggable without mocking a model | Yes | No |
| Added latency/cost per turn | None | Embedding call + index lookup |

**Consequences**

- Retrieval quality is bounded by what keyword overlap can find; a memory that's phrased very differently from the current message may be missed even if it's conceptually relevant.
- This trade-off was made explicitly and is revisited in Phase 8 of `ROADMAP.md`.

**Future Considerations**

Hybrid retrieval — keeping deterministic keyword matching as the default, guaranteed path, and layering an optional semantic pass on top — may be explored in the future (see `ROADMAP.md` Phase 8: Adaptive Memory). Any such change is expected to be additive, not a replacement, so that the debuggability guarantee established here isn't lost by default.

---

## ADR-003 — Layered Memory Engine

**Decision**

Memory processing is split into four single-responsibility stages — `MemoryReader`, `MemoryRetriever`, `MemoryRanker`, `PromptBuilder` — rather than one large function that reads, filters, ranks, and formats memory in a single pass.

**Context**

The system this replaced (`_format_memory_context()`/`get_memory_context()` in `chat_service.py`) mixed reading, filtering, and string formatting together in ad-hoc fashion. That made it hard to test any one part in isolation, hard to reason about what a change to formatting might do to filtering, and hard to add new memory categories without touching a large, tangled function.

**Why It Was Split This Way**

- **One job per stage:** reading storage, narrowing to what's relevant, ordering by relevance, and serializing to text are four genuinely different concerns, each with its own failure modes (a storage error, a bad keyword match, an unstable sort, a formatting bug).
- **Independent testability:** each stage can be tested with plain data — a `MemorySnapshot` in, a `MemoryContext` out — without needing to mock an LLM, a database, or the other three stages.
- **Isolated failure:** a single category failing to load raises a scoped `MemoryLoadError` that degrades only that category, without one bad field taking down retrieval, ranking, or the whole memory prompt.
- **Safer extension:** adding a new memory category means extending `MemoryReader` (and the data models it populates); it does not require touching `MemoryRetriever`, `MemoryRanker`, or `PromptBuilder` unless their behavior specifically needs to change.

**Consequences**

- Four modules and two data models (`MemorySnapshot`, `MemoryContext`) exist where one function used to. This is more files to navigate, but each one is small and does exactly one thing.
- The pipeline's shape (`Reader → Retriever → Ranker → PromptBuilder`) is now a contract that other code (and future phases) can depend on — see `ARCHITECTURE.md` Section 6.

---

## ADR-004 — Provider Abstraction

**Decision**

Gemini-SDK-specific logic was extracted out of the original monolithic `gemini_client.py` into `providers/gemini_provider.py` (`GeminiProvider`), leaving `gemini_client.py` as a thin, backward-compatible facade.

**Context**

The original `gemini_client.py` mixed Gemini SDK configuration, model caching, chat-history translation, streaming/non-streaming calls, the tutor's persona content, and product features (quiz generation, code explanation) into a single file. That made it impossible to add a second LLM vendor without either duplicating all of that logic or entangling a new vendor's SDK calls with Gemini's.

**Why Gemini Logic Was Extracted Into a Provider**

- **Isolation of vendor-specific code:** everything that only makes sense in terms of Google's SDK — `genai.configure`, cached `GenerativeModel` objects, Gemini's specific history/request shapes, Gemini's specific error strings — now lives in exactly one module.
- **A vendor-agnostic contract:** `GeminiProvider` exposes the same two-function shape (`send`/`stream`) that any future provider must also implement, so the rest of the system can depend on the contract instead of the vendor.
- **Preparation for multiple vendors without a rewrite:** adding OpenAI, OpenRouter, or another vendor later means writing one new module that satisfies the same contract — not re-architecting `chat_service.py` or `gemini_client.py`.

**Why Provider-Specific SDK Code Should Remain Isolated**

If SDK calls leak outside `providers/*` — for example, into `tutor_features.py` or `chat_service.py` — then every future provider addition requires hunting down and updating every place that made an SDK-specific assumption. Keeping that code walled inside `providers/*` (enforced in `ARCHITECTURE.md` Section 8's dependency rules) means a provider can be added, replaced, or removed as a single, self-contained unit.

**Consequences**

- Every public function in `gemini_client.py` kept its original name and signature, verified byte-for-byte equivalent against the pre-refactor behavior, so no caller needed to change.
- Persona content and product features (quiz generation, code explanation) were pulled out into `persona.py` and `tutor_features.py` respectively, since neither belongs inside a vendor-specific provider (see `ARCHITECTURE.md` Section 8).

---

## ADR-005 — LLM Router

**Decision**

`llm_router.py` was introduced as the single dispatch point between `gemini_client.py` and the provider layer, currently forwarding unconditionally to `GeminiProvider`.

**Context**

Once Gemini-specific logic was isolated behind a provider contract (ADR-004), the system still needed exactly one place where "which provider handles this request" could eventually be decided — without that decision logic living inside `chat_service.py`, `gemini_client.py`, or scattered across callers.

**Why the Router Exists**

The router exists so provider selection, failover, and (eventually) observability hooks have exactly one home. Today it does nothing more than forward `send_message`/`stream_message` calls to `GeminiProvider`, but that seam is deliberately in place *before* it's needed, so that adding real selection logic later (Phase 5) or failover logic (Phase 6) means changing one file, not several.

**Why `chat_service` Should Never Know Which Provider Is Active**

`chat_service.py`'s job is orchestration — fetching history, persisting messages, invoking memory and LLM layers. If it knew which provider was active, provider-specific assumptions would inevitably creep into the orchestration layer, and every new provider would risk requiring a `chat_service.py` change. By routing everything through `gemini_client.py` → `llm_router.py`, `chat_service.py` remains provider-agnostic by construction, not by convention.

**How This Supports Future Providers and Failover**

- **New providers (Phase 5):** each new vendor is a new module under `providers/` implementing the same `send`/`stream` contract; `llm_router.py` is the only place that needs to learn about it.
- **Failover (Phase 6):** because every provider call already funnels through one seam, retry/fallback ordering can be added inside `llm_router.py` without touching `gemini_client.py`, `chat_service.py`, or any provider module.

**Consequences**

- An extra function-call hop exists between `gemini_client.py` and `providers/gemini_provider.py` even though, today, it does no real work. This was a deliberate trade — a small amount of present-day indirection in exchange for provider selection and failover requiring no structural change later.
- Streaming/generator laziness through this hop was explicitly verified to be unchanged, since a router that eagerly consumed a generator would silently break streaming behavior.

---

## ADR-006 — Incremental Refactoring Strategy

**Decision**

Tutor Gojo's architecture evolves through a sequence of small, independently verified phases (memory engine built in isolation → wired into `chat_service` → Gemini logic extracted into a provider → router introduced) rather than through large, all-at-once rewrites.

**Context**

Every phase completed so far has touched code that a live tutoring session depends on. A large rewrite that changed memory handling and the LLM layer simultaneously would make it far harder to know which change caused a regression, and would leave the system in a broken state for longer if something went wrong partway through.

**Why Small, Independently Verified Phases**

- **Backward compatibility:** each phase preserves the public contracts the next phase depends on (e.g. `send_message`/`stream_message` keeping their exact signatures through both the provider extraction and the router introduction), so callers never have to change in step with internals.
- **Easy rollback:** a phase that turns out to be wrong can be reverted on its own, without unwinding unrelated changes bundled into the same rewrite.
- **Reduced risk:** each phase is small enough that its behavior can be fully understood and verified before the next one starts, rather than accumulating untested surface area across a large change.
- **Independent verification:** phases so far have each undergone their own equivalence check (e.g. Phase 2's ten-property audit, Phase 3's byte-for-byte behavioral comparison against a stub SDK) before being considered complete, which would not be practical if multiple phases were collapsed into one change.

**Consequences**

- Some intermediate states are deliberately not "finished" — for example, `llm_router.py` doing nothing but forwarding to `GeminiProvider` (ADR-005) is a genuine, shippable intermediate state, not a half-finished feature.
- Progress can look slower phase-by-phase than a single large rewrite might promise, but each phase leaves the system in a fully working, fully verified state — which a large rewrite cannot guarantee until it is entirely finished.

---

## ADR-007 — Documentation as Source of Truth

**Decision**

`ARCHITECTURE.md`, `ROADMAP.md`, and `DECISIONS.md` are treated as authoritative engineering documentation and must be kept synchronized with the actual implementation, updated in the same change that alters what they describe.

**Context**

A codebase that changes for many phases, by many contributors (including AI agents), will drift from any documentation that isn't actively maintained. Documentation that has drifted from reality is worse than no documentation, because it actively misleads whoever reads it next.

**Why These Three Documents Must Stay Synchronized**

- **`ARCHITECTURE.md`** describes the system *as it exists today* — its structure, module boundaries, and dependency rules. If it lags behind the code, contributors will build against a structure that no longer exists.
- **`ROADMAP.md`** describes what's already delivered and what's planned next, including the objectives and success criteria each future phase must meet. If it lags behind delivery, it becomes impossible to tell what's actually done.
- **`DECISIONS.md`** (this document) records why past decisions were made. Even as implementation details change, the reasoning captured here should remain a reliable reference for why the system looks the way it does — and new ADRs should be added whenever a comparably significant decision is made.

**Consequences**

- Every phase or architectural change that lands should include, in the same change: an `ARCHITECTURE.md` update if the system's structure changed, a `ROADMAP.md` status update if a phase's status changed, and a new ADR here if a significant new decision was made (not just an implementation detail).
- Phase 10 (Production Hardening) in `ROADMAP.md` explicitly includes a documentation review pass to catch and correct any drift that occurred despite this discipline.
