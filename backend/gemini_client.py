"""
gemini_client.py - Backward-compatible facade over the Gemini provider.

Historically this module contained all Gemini SDK setup, model caching,
history translation, streaming/non-streaming calls, the tutor's persona
content, and the quiz/code-explanation features. That logic has been split
out so a future multi-provider router can be introduced later without
touching this module's public surface or any of its callers (chat_service.py
in particular):

- Gemini SDK mechanics (configuration, model caching, history translation,
  streaming, non-streaming, error handling, parameter mapping) now live in
  providers.gemini_provider.GeminiProvider.
- The tutor's persona/system-prompt content and generic generation defaults
  now live in persona.py.
- The quiz-generation and code-explanation features now live in
  tutor_features.py.
- send_message()/stream_message() now delegate through llm_router, which
  is the single dispatch point that will eventually decide which provider
  to call. Today it always dispatches to GeminiProvider - no conditional
  logic, fallback, retries, or additional providers exist yet.

Call chain for send/stream:
    gemini_client.send_message() / stream_message()
        -> llm_router.send_message() / stream_message()
            -> GeminiProvider.send() / stream()

Every function below keeps its original name, signature, and behavior - it
only forwards to the new locations. Existing callers (chat_service.py, or
anything else importing gemini_client) require no changes.
"""

from providers.gemini_provider import get_provider
import llm_router
from prompts import tutor_features


def configure_gemini():
    """Set up the Gemini API with the user's key."""
    get_provider().configure()


def build_system_prompt():
    """Build the system prompt with current settings."""
    return get_provider().build_system_prompt()


def create_model():
    """Get a cached Gemini model instance, rebuilding only if the API key,
    model name, level, or teaching intensity have changed since last call.
    """
    return get_provider().get_model()


def send_message(message, history=None, use_search=False):
    """Send a message to Gemini and get a full response (non-streaming).

    Delegates to llm_router, which currently always dispatches to
    GeminiProvider.
    """
    return llm_router.send_message(message, history=history, use_search=use_search)


def stream_message(message, history=None, use_search=False):
    """Stream a response from Gemini, yielding text chunks as they arrive.
    Use this in a background thread - iterate over the generator and update
    the UI on each chunk. The full response is the concatenation of all chunks.

    Delegates to llm_router, which currently always dispatches to
    GeminiProvider.
    """
    return llm_router.stream_message(message, history=history, use_search=use_search)


def generate_content(prompt):
    """Raw single-shot generation against the cached Gemini model. Used
    internally by tutor_features.generate_quiz; exposed here so feature
    modules never need to reach into the provider's model object directly.
    """
    return get_provider().generate_content(prompt)


def generate_quiz(topic, difficulty="medium"):
    """Generate a quiz question on a specific topic.

    Returns a dict with: question, options, correct_answer, explanation

    See tutor_features.generate_quiz for the prompt construction/parsing.
    """
    return tutor_features.generate_quiz(topic, difficulty=difficulty)


def explain_code(code, language="python"):
    """Ask Gojo to explain a piece of code.

    See tutor_features.explain_code for the prompt construction.
    """
    return tutor_features.explain_code(code, language=language)


if __name__ == "__main__":
    print("Gemini client loaded.")
    print("System prompt includes:")
    print("- Confident mentor personality")
    print("- Step-by-step teaching style")
    print("- Anime references (light)")
    print("- Tech-only guardrail")
    print("- Code formatting rules")
    print("Model is cached and reused across messages.")
