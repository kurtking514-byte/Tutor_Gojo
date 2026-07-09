"""
memory_engine - foundation package for Tutor Gojo's next-generation
memory pipeline.

Status: SCAFFOLDING ONLY. Nothing in this package is wired into the
running application yet. chat_service.py, memory_service.py, and
obsidian_backend.py are untouched and continue to be the live code
path for reading/writing/formatting educational memory.

This package exists to let the new architecture (typed models, a
reader, a retriever, a ranker, and a prompt builder) be built and
reviewed incrementally, function-by-function, without risking any
change to current runtime behavior. Nothing here is imported by any
existing module.

Modules
-------
models         - Plain dataclasses describing the internal memory model
                 (one per category) plus two aggregates:
                 MemorySnapshot (everything) and MemoryContext (the
                 subset intended for the Gemini prompt).
reader         - MemoryReader: will eventually replace obsidian_backend
                 as the source of a MemorySnapshot. Placeholder only.
retrieval      - MemoryRetriever: will eventually replace the
                 get_memory_context() aggregation + ad-hoc filtering
                 currently spread across memory_service.py and
                 chat_service.py. Placeholder only.
ranking        - MemoryRanker: future home for relevance/recency
                 scoring logic that doesn't exist yet anywhere in the
                 current pipeline. Placeholder only.
prompt_builder - PromptBuilder: will eventually replace
                 chat_service._format_memory_context(). Placeholder
                 only.
"""
