"""
providers.gemini_provider - Gemini-specific implementation of the tutor's
LLM provider contract.

Contains ONLY Gemini SDK concerns:
  - authentication/configuration (genai.configure)
  - model/client caching
  - translating generic conversation history into Gemini's chat format
  - issuing streaming/non-streaming requests
  - normalizing Gemini's errors
  - mapping provider-agnostic generation defaults onto Gemini's exact
    parameter names

It knows nothing about the tutor's persona *content*, quiz generation, code
explanation, or any other provider - those live in persona.py and
tutor_features.py respectively, and stay identical no matter which provider
is active.

PERFORMANCE NOTES (unchanged from the original gemini_client.py):
- The GenerativeModel instance is cached and reused across messages instead
  of being rebuilt on every call. It's only rebuilt if the API key, model
  name, level, or teaching intensity actually change.
- Conversation history is sent via Gemini's native chat history mechanism
  (start_chat) instead of being hand-glued into the prompt string.
- The compiled system prompt is passed as system_instruction (set once per
  model object) rather than re-concatenated into every message.
"""

import os
import threading

import google.generativeai as genai
from config import get_api_key, get_setting

from prompts.persona import build_system_prompt, GENERATION_DEFAULTS, MAX_HISTORY_TURNS


class GeminiProvider:
    """Thread-safe, cached wrapper around the Gemini SDK.

    Public surface mirrors the provider-agnostic contract callers rely on:
    send(message, history) -> str and stream(message, history) -> Iterator[str].
    """

    def __init__(self):
        self._model_lock = threading.Lock()
        self._cached_model = None
        self._cached_key = None

    # ------------------------------------------------------------------
    # Configuration / model caching (Gemini-specific)
    # ------------------------------------------------------------------

    def _resolve_api_key(self):
        """Resolve the API key, preferring the GEMINI_API_KEY environment
        variable (used for Render/server deployments where no
        ~/.tutor_gojo/config.json exists) and falling back to the existing
        config.get_api_key() behavior for local desktop usage.
        """
        return os.getenv("GEMINI_API_KEY") or get_api_key()

    def _current_cache_key(self):
        """Settings that, if changed, require a new model object."""
        return (
            self._resolve_api_key(),
            get_setting("model", "gemini-2.5-flash"),
            get_setting("level", "beginner"),
            get_setting("teaching_intensity", "patient"),
        )

    def configure(self):
        """Set up the Gemini API with the user's key."""
        api_key = self._resolve_api_key()
        if not api_key:
            raise ValueError("No API key configured. Please run the setup wizard first.")
        genai.configure(api_key=api_key)

    def build_system_prompt(self):
        """Fetch the current persona settings and compile them into the
        persona module's system prompt template.

        Persona *content* lives in persona.py; only the Gemini-specific
        settings lookup happens here, since only this provider needs to
        know these particular setting keys exist.
        """
        intensity = get_setting("teaching_intensity", "patient")
        level = get_setting("level", "beginner")
        return build_system_prompt(level, intensity)

    def _map_generation_config(self):
        """Maps the provider-agnostic generation defaults onto Gemini's
        SDK parameter names.

        Currently a 1:1 mapping, since Gemini's parameter names happen to
        match the generic ones - kept as its own step so a future provider
        with different parameter names doesn't need this logic duplicated
        or reasoned about elsewhere.
        """
        return dict(GENERATION_DEFAULTS)

    def get_model(self):
        """Get a cached Gemini model instance, rebuilding only if the API
        key, model name, level, or teaching intensity have changed since
        last call. Thread-safe, since messages are sent from background
        threads.
        """
        key = self._current_cache_key()

        # Fast path: no lock needed just to read and compare
        if self._cached_model is not None and self._cached_key == key:
            return self._cached_model

        with self._model_lock:
            # Re-check after acquiring the lock in case another thread
            # already rebuilt it
            if self._cached_model is not None and self._cached_key == key:
                return self._cached_model

            api_key = key[0]
            if not api_key:
                raise ValueError("No API key configured. Please run the setup wizard first.")

            genai.configure(api_key=api_key)

            model_name = key[1]
            system_prompt = self.build_system_prompt()

            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system_prompt,
                generation_config=self._map_generation_config(),
            )

            self._cached_model = model
            self._cached_key = key
            return model

    # ------------------------------------------------------------------
    # History translation (Gemini-specific)
    # ------------------------------------------------------------------

    def _format_history(self, history):
        """Convert the generic [(role, content), ...] tuples into the
        {"role": "user"/"model", "parts": [...]} dicts the Gemini SDK
        expects, trimmed to the most recent MAX_HISTORY_TURNS turn-pairs.
        """
        if not history:
            return []

        trimmed = history[-(MAX_HISTORY_TURNS * 2):]
        formatted = []
        for role, content in trimmed:
            gemini_role = "model" if role == "assistant" else "user"
            formatted.append({"role": gemini_role, "parts": [content]})
        return formatted

    # ------------------------------------------------------------------
    # Error handling (Gemini-specific)
    # ------------------------------------------------------------------

    def _raise_friendly_error(self, e):
        error_msg = str(e).lower()
        if "api_key" in error_msg or "invalid" in error_msg:
            raise ValueError(f"API key issue: {str(e)}")
        raise ValueError(f"Gemini error: {str(e)}")

    # ------------------------------------------------------------------
    # Request construction / streaming / non-streaming (Gemini-specific)
    # ------------------------------------------------------------------

    def send(self, message, history=None, use_search=False):
        """Send a message to Gemini and get a full response (non-streaming)."""
        model = self.get_model()
        chat_history = self._format_history(history)

        try:
            chat = model.start_chat(history=chat_history)
            response = chat.send_message(message)
            return response.text
        except Exception as e:
            self._raise_friendly_error(e)

    def stream(self, message, history=None, use_search=False):
        """Stream a response from Gemini, yielding text chunks as they
        arrive. Use this in a background thread - iterate over the
        generator and update the UI on each chunk. The full response is
        the concatenation of all chunks.
        """
        model = self.get_model()
        chat_history = self._format_history(history)

        try:
            chat = model.start_chat(history=chat_history)
            response = chat.send_message(message, stream=True)
            for chunk in response:
                # chunk.text can be empty/None on the final metadata chunk
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            self._raise_friendly_error(e)

    def generate_content(self, prompt):
        """Raw single-shot generation (no chat history), used by feature
        helpers - e.g. quiz generation - that need a plain completion
        rather than a conversational turn. Still benefits from the cached
        model's persona system_instruction.
        """
        model = self.get_model()
        return model.generate_content(prompt)


# Module-level singleton - mirrors the previous module-level cache in
# gemini_client.py, so behavior (one cached model per process) is
# unchanged.
_provider = GeminiProvider()


def get_provider():
    """Returns the shared GeminiProvider instance."""
    return _provider
