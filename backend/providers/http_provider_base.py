"""
providers.http_provider_base - Shared base for OpenAI-compatible HTTP LLM
providers (OpenRouter, Groq, and any future vendor exposing an OpenAI-style
chat-completions endpoint).

This module exists purely to eliminate the duplication that an architecture
audit found between OpenRouterProvider and GroqProvider: once endpoint URL,
display name, and setting keys are factored out, the two providers were
byte-for-byte identical in every method body (session lifecycle, message
construction, history translation, generation-config mapping, request
sending, and SSE stream parsing). That shared behavior now lives here,
exactly once.

HTTPProviderBase owns:
  - requests.Session lifecycle/caching
  - message construction (system prompt + history + current message)
  - history translation (generic [(role, content), ...] -> OpenAI-style
    {"role": ..., "content": ...} dicts)
  - generation-config mapping (persona.GENERATION_DEFAULTS -> OpenAI-style
    parameter names)
  - request sending, both non-streaming and streaming (SSE parsing)
  - friendly error normalization

A subclass provides only vendor identity via class attributes:
    CHAT_COMPLETIONS_URL - the vendor's OpenAI-compatible endpoint
    PROVIDER_NAME        - display name used in error/log strings
                            (e.g. "Groq", "OpenRouter")
    API_KEY_SETTING       - config.get_setting() key for the API key
    MODEL_SETTING         - config.get_setting() key for the model name
    DEFAULT_MODEL         - model name used when MODEL_SETTING is unset

This base class is NOT itself a provider: it has no get_provider()
function, is not registered in llm_router's registry, and cannot be
selected by name. It is infrastructure shared by providers, the same
role persona.py plays for persona content - subclasses are the actual
providers.

Like every provider, it knows nothing about the tutor's persona *content*,
quiz generation, code explanation, memory, or routing - those live in
persona.py, tutor_features.py, memory_engine/*, and llm_router.py
respectively.

Public contract inherited by subclasses (unchanged from before this
refactor):
    send(message, history=None, use_search=False) -> str
    stream(message, history=None, use_search=False) -> Iterator[str]
"""

import json
import threading

import requests

from config import get_setting

from prompts.persona import build_system_prompt, GENERATION_DEFAULTS, MAX_HISTORY_TURNS


class HTTPProviderBase:
    """Thread-safe base wrapper around an OpenAI-compatible HTTP
    chat-completions API.

    Subclasses must set CHAT_COMPLETIONS_URL, PROVIDER_NAME,
    API_KEY_SETTING, MODEL_SETTING, and DEFAULT_MODEL as class attributes.

    Like the OpenRouter/Groq providers before this refactor, there is no
    local SDK model object to cache - every call is a stateless HTTP
    request - so this class holds no request-level cache. The lock exists
    only to protect against concurrent access to the lazily-created
    requests.Session.
    """

    CHAT_COMPLETIONS_URL = None
    PROVIDER_NAME = None
    API_KEY_SETTING = None
    MODEL_SETTING = None
    DEFAULT_MODEL = None

    def __init__(self):
        self._lock = threading.Lock()
        self._session = None

    # ------------------------------------------------------------------
    # Configuration (shared)
    # ------------------------------------------------------------------

    def _get_api_key(self):
        return get_setting(self.API_KEY_SETTING, None)

    def _get_model_name(self):
        return get_setting(self.MODEL_SETTING, self.DEFAULT_MODEL)

    def _require_api_key(self):
        """Fetches the API key, raising the same friendly error every
        subclass's send()/stream() has always raised if it's missing.
        """
        api_key = self._get_api_key()
        if not api_key:
            raise ValueError(
                f"No {self.PROVIDER_NAME} API key configured. Please run "
                f"the setup wizard first."
            )
        return api_key

    def configure(self):
        """Validate that an API key is available. Vendors covered by this
        base have no SDK-level "configure" call to make (auth is a
        per-request header), so this just fails fast and clearly if the
        key is missing, the same moment GeminiProvider.configure() would.
        """
        if not self._get_api_key():
            raise ValueError(
                f"No {self.PROVIDER_NAME} API key configured. Please set "
                f"'{self.API_KEY_SETTING}' in the setup wizard/settings "
                f"before selecting the {self.PROVIDER_NAME.lower()} provider."
            )

    def build_system_prompt(self):
        """Fetch the current persona settings and compile them into the
        persona module's system prompt template.

        Identical settings lookup across every provider - persona
        *content* still lives entirely in persona.py.
        """
        intensity = get_setting("teaching_intensity", "patient")
        level = get_setting("level", "beginner")
        return build_system_prompt(level, intensity)

    def _map_generation_config(self):
        """Maps the provider-agnostic generation defaults onto this
        vendor's (OpenAI-compatible) parameter names.

        Only maps keys that are actually present in GENERATION_DEFAULTS,
        so this stays correct even if persona.py's default set changes -
        it never invents a parameter the vendor wasn't asked to use.
        """
        defaults = dict(GENERATION_DEFAULTS)
        mapped = {}
        if "temperature" in defaults:
            mapped["temperature"] = defaults["temperature"]
        if "top_p" in defaults:
            mapped["top_p"] = defaults["top_p"]
        # Gemini's max_output_tokens is OpenAI-compatible APIs' max_tokens.
        if "max_output_tokens" in defaults:
            mapped["max_tokens"] = defaults["max_output_tokens"]
        return mapped

    # ------------------------------------------------------------------
    # History translation (shared)
    # ------------------------------------------------------------------

    def _format_history(self, history):
        """Convert the generic [(role, content), ...] tuples into the
        {"role": "user"/"assistant", "content": ...} dicts every
        OpenAI-compatible endpoint expects, trimmed to the most recent
        MAX_HISTORY_TURNS turn-pairs - same trim window GeminiProvider
        uses, so switching providers doesn't change how much history is
        sent.
        """
        if not history:
            return []

        trimmed = history[-(MAX_HISTORY_TURNS * 2):]
        formatted = []
        for role, content in trimmed:
            mapped_role = "assistant" if role == "assistant" else "user"
            formatted.append({"role": mapped_role, "content": content})
        return formatted

    def _build_messages(self, message, history):
        """Assembles the full OpenAI-style messages array: system prompt,
        then translated history, then the current user message.
        """
        messages = [{"role": "system", "content": self.build_system_prompt()}]
        messages.extend(self._format_history(history))
        messages.append({"role": "user", "content": message})
        return messages

    def _headers(self, api_key):
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _get_session(self):
        """Lazily creates and reuses one requests.Session per process for
        connection pooling - the HTTP-layer equivalent of GeminiProvider
        caching its model object, without caching anything that depends
        on mutable settings (api key/model are re-read per request, so a
        setting change takes effect on the very next call).
        """
        if self._session is not None:
            return self._session
        with self._lock:
            if self._session is None:
                self._session = requests.Session()
            return self._session

    # ------------------------------------------------------------------
    # Error handling (shared)
    # ------------------------------------------------------------------

    def _raise_friendly_error(self, e):
        status_code = getattr(getattr(e, "response", None), "status_code", None)
        error_msg = str(e).lower()
        if status_code in (401, 403) or "api_key" in error_msg or "unauthorized" in error_msg:
            raise ValueError(f"{self.PROVIDER_NAME} API key issue: {str(e)}")
        raise ValueError(f"{self.PROVIDER_NAME} error: {str(e)}")

    # ------------------------------------------------------------------
    # Request construction / streaming / non-streaming (shared)
    # ------------------------------------------------------------------

    def send(self, message, history=None, use_search=False):
        """Send a message and get a full response (non-streaming)."""
        api_key = self._require_api_key()

        payload = {
            "model": self._get_model_name(),
            "messages": self._build_messages(message, history),
            **self._map_generation_config(),
        }

        try:
            response = self._get_session().post(
                self.CHAT_COMPLETIONS_URL,
                headers=self._headers(api_key),
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            self._raise_friendly_error(e)

    def stream(self, message, history=None, use_search=False):
        """Stream a response, yielding text chunks as they arrive over
        server-sent events. Use this in a background thread - iterate
        over the generator and update the UI on each chunk. The full
        response is the concatenation of all chunks - identical contract
        to GeminiProvider.stream().
        """
        api_key = self._require_api_key()

        payload = {
            "model": self._get_model_name(),
            "messages": self._build_messages(message, history),
            "stream": True,
            **self._map_generation_config(),
        }

        try:
            response = self._get_session().post(
                self.CHAT_COMPLETIONS_URL,
                headers=self._headers(api_key),
                json=payload,
                stream=True,
                timeout=60,
            )
            response.raise_for_status()
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                decoded = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                if not decoded.startswith("data:"):
                    continue
                data_str = decoded[len("data:"):].strip()
                if data_str == "[DONE]":
                    break
                chunk = json.loads(data_str)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    yield content
        except Exception as e:
            self._raise_friendly_error(e)
