"""
providers - LLM provider implementations.

Each provider module in this package exposes the same small contract:

    send(message, history=None, use_search=False) -> str
    stream(message, history=None, use_search=False) -> Iterator[str]

so that a future router can dispatch to any of them without callers
(chat_service.py, tutor_features.py, etc.) needing to change.

Currently only providers.gemini_provider exists. This phase intentionally
does not add routing, fallback, or additional providers.
"""
