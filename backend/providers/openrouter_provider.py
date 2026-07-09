"""
providers.openrouter_provider - OpenRouter-specific configuration of the
shared OpenAI-compatible HTTP provider base.

All OpenRouter-agnostic-to-OpenAI-compatible HTTP behavior (session
lifecycle, message construction, history translation, generation-config
mapping, request sending, SSE stream parsing, error normalization) lives
in providers.http_provider_base.HTTPProviderBase. This module supplies
only what's actually OpenRouter-specific: the endpoint URL, the display
name used in error messages, the config keys used to look up the API key
and model, and the default model.

It knows nothing about the tutor's persona *content*, quiz generation,
code explanation, memory, routing, or any other provider - those live in
persona.py, tutor_features.py, memory_engine/*, and llm_router.py
respectively, and none of them change because this provider exists.

Mirrors providers.gemini_provider.GeminiProvider's public surface exactly
(inherited from HTTPProviderBase):
    send(message, history=None, use_search=False) -> str
    stream(message, history=None, use_search=False) -> Iterator[str]
so llm_router can dispatch to any provider identically.
"""

from providers.http_provider_base import HTTPProviderBase

# Settings keys are namespaced with "openrouter_" so switching the active
# provider back and forth never clobbers Gemini's or Groq's own settings
# (or vice versa) - all live side by side in the same
# get_setting(key, default) store, following the exact pattern
# GeminiProvider already uses for "model"/"level"/"teaching_intensity".


class OpenRouterProvider(HTTPProviderBase):
    """OpenRouter's send/stream contract, provided entirely by
    HTTPProviderBase - this class only declares OpenRouter's identity.
    """

    CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
    PROVIDER_NAME = "OpenRouter"
    API_KEY_SETTING = "openrouter_api_key"
    MODEL_SETTING = "openrouter_model"
    DEFAULT_MODEL = "openai/gpt-4o-mini"


# Module-level singleton - mirrors providers.gemini_provider's
# module-level cache, so behavior (one shared provider instance per
# process) is consistent across providers.
_provider = OpenRouterProvider()


def get_provider():
    """Returns the shared OpenRouterProvider instance."""
    return _provider
