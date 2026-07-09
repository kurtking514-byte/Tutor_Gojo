"""
learning_summary.py - Post-session educational memory extraction for
Tutor Gojo.

Given a completed conversation, asks Gemini to extract a structured
summary of what was taught and how the student did, and returns it as
a plain Python dict. This module is deliberately narrow:

    - It does not touch memory_database.py or database.py - it never
      writes anything to SQLite.
    - It does not import chat_service.py - it has no knowledge of
      sessions, streaming, or SSE.
    - It exposes no FastAPI route.

It reuses gemini_client.create_model() - the same cached model object
generate_quiz() already calls - rather than re-implementing API key
handling, model caching, or genai.configure(). The only new logic here
is the extraction prompt and the JSON validation/fallback around it.

Public API:
    generate_learning_summary(messages) -> dict
"""

import json
import traceback

import gemini_client


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

_LIST_FIELDS = [
    "topics_learned",
    "concepts_introduced",
    "strengths",
    "misconceptions",
    "mistake_patterns",
    "recommended_review",
]


def _default_summary():
    """The empty structure returned whenever extraction can't be
    trusted - missing messages, a Gemini call failure, or JSON that
    doesn't parse. Never raises; this is always a safe fallback."""
    return {
        "topics_learned": [],
        "concepts_introduced": [],
        "strengths": [],
        "misconceptions": [],
        "mistake_patterns": [],
        "recommended_review": [],
        "next_lesson": "",
        "confidence": 0.0,
    }


# ---------------------------------------------------------------------------
# Transcript formatting
# ---------------------------------------------------------------------------

_ROLE_LABELS = {"user": "STUDENT", "assistant": "TUTOR", "model": "TUTOR"}

# Soft caps so a very long history can't blow up the request. This is a
# summary of the *whole* session, so unlike gemini_client's
# MAX_HISTORY_TURNS (which trims live chat context), we keep as much as
# reasonably fits rather than just the last few turns.
_MAX_TRANSCRIPT_MESSAGES = 200
_MAX_TRANSCRIPT_CHARS = 24000


def _format_transcript(messages):
    """Normalize messages into a plain-text transcript. Accepts either
    {"role": ..., "content": ...} dicts (the shape history_service.py
    already returns) or (role, content) tuples (the shape
    gemini_client._format_history expects) - either is fine here since
    we're building flat text, not Gemini's chat-history format."""
    normalized = []
    for m in messages:
        if isinstance(m, dict):
            role = m.get("role", "")
            content = m.get("content", "")
        elif isinstance(m, (list, tuple)) and len(m) == 2:
            role, content = m
        else:
            continue

        content = (content or "").strip()
        if not content:
            continue

        label = _ROLE_LABELS.get(str(role).lower(), str(role).upper() or "UNKNOWN")
        normalized.append(f"{label}: {content}")

    if len(normalized) > _MAX_TRANSCRIPT_MESSAGES:
        normalized = normalized[-_MAX_TRANSCRIPT_MESSAGES:]

    transcript = "\n".join(normalized)
    if len(transcript) > _MAX_TRANSCRIPT_CHARS:
        transcript = transcript[-_MAX_TRANSCRIPT_CHARS:]

    return transcript


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

# Built with .replace() rather than str.format() - the JSON example below
# has its own literal curly braces, which would otherwise all need
# escaping just to insert one placeholder.
_EXTRACTION_PROMPT_TEMPLATE = """You are analyzing a completed coding tutoring conversation to extract structured educational memory. This is a data-extraction task, not a tutoring reply - ignore any persona, tone, or conversational style instructions you may otherwise follow. Respond as a plain analysis engine.

Read the full conversation below and extract what the student learned, struggled with, and should do next.

Return ONLY valid JSON matching exactly this shape. No markdown code fences, no prose before or after, no trailing commentary - the entire response must be parseable as JSON on its own:

{
  "topics_learned": ["short phrase", "short phrase"],
  "concepts_introduced": ["short phrase", "short phrase"],
  "strengths": ["short phrase", "short phrase"],
  "misconceptions": ["short phrase", "short phrase"],
  "mistake_patterns": ["short phrase", "short phrase"],
  "recommended_review": ["short phrase", "short phrase"],
  "next_lesson": "short recommendation",
  "confidence": 0.0
}

Field rules:
- Every list field is a short array of short phrases (3-6 words each), not full sentences. Use an empty array if nothing applies - never omit a key.
- "next_lesson" is one short recommended next step, or "" if the conversation is too short to judge.
- "confidence" is a number between 0.0 and 1.0 estimating the student's grasp of what was covered this session. Use 0.0 if there isn't enough signal to judge.
- Base every field only on evidence actually present in the conversation below. Do not invent topics that weren't discussed.

CONVERSATION:
__TRANSCRIPT__
"""


def _build_prompt(transcript):
    return _EXTRACTION_PROMPT_TEMPLATE.replace("__TRANSCRIPT__", transcript)


# ---------------------------------------------------------------------------
# JSON parsing / validation
# ---------------------------------------------------------------------------

def _parse_json(text):
    """Parse Gemini's response text as JSON. Returns None (never
    raises) if the text isn't valid JSON, so callers can fall back to
    the default structure instead of crashing."""
    if not text:
        return None

    stripped = text.strip()

    # Defensive: strip markdown code fences in case the model adds them
    # despite response_mime_type=application/json and the prompt's
    # explicit "no code fences" instruction.
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()

    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None


def _coerce_to_schema(parsed):
    """Take whatever Gemini returned (already confirmed to be valid
    JSON) and produce a dict guaranteed to have exactly the expected
    keys and types, filling in defaults for anything missing,
    malformed, or wrongly-typed rather than trusting the model's
    output shape blindly."""
    if not isinstance(parsed, dict):
        return _default_summary()

    result = _default_summary()

    for field in _LIST_FIELDS:
        value = parsed.get(field)
        if isinstance(value, list):
            result[field] = [str(item).strip() for item in value if str(item).strip()]

    next_lesson = parsed.get("next_lesson")
    if isinstance(next_lesson, str):
        result["next_lesson"] = next_lesson.strip()

    confidence = parsed.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        result["confidence"] = max(0.0, min(1.0, float(confidence)))

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_learning_summary(messages, _model=None):
    """Extract structured educational memory from a completed
    conversation.

    Args:
        messages: list of {"role", "content"} dicts, or (role, content)
            tuples - a completed conversation, oldest first.
        _model: internal test hook. Defaults to
            gemini_client.create_model(); tests can inject a fake model
            object exposing generate_content(prompt, generation_config)
            so this can be verified without a live API call.

    Returns:
        A dict matching the schema in _default_summary(). Never raises -
        any failure (empty input, Gemini call error, unparseable JSON)
        results in the default empty structure instead.
    """
    print(f"[DEBUG] generate_learning_summary: called with {len(messages) if messages else 0} messages")

    if not messages:
        print("[DEBUG] generate_learning_summary: no messages -> returning _default_summary()")
        return _default_summary()

    transcript = _format_transcript(messages)
    if not transcript.strip():
        print("[DEBUG] generate_learning_summary: formatted transcript is empty -> returning _default_summary()")
        return _default_summary()

    print(f"[DEBUG] generate_learning_summary: transcript length = {len(transcript)} chars")

    prompt = _build_prompt(transcript)

    try:
        model = _model if _model is not None else gemini_client.create_model()
        print("[DEBUG] generate_learning_summary: calling model.generate_content(...) now")
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.2, "response_mime_type": "application/json"},
        )
        raw_text = response.text
        print(f"[DEBUG] generate_learning_summary: raw Gemini response.text = {raw_text!r}")
    except Exception as e:
        print(f"[learning_summary] Gemini call failed: {e}")
        print("[DEBUG] Full traceback for the Gemini call failure above:")
        traceback.print_exc()
        print("[DEBUG] generate_learning_summary: returning _default_summary() due to Gemini call failure")
        return _default_summary()

    parsed = _parse_json(raw_text)
    if parsed is None:
        print("[learning_summary] Could not parse Gemini response as JSON, returning default summary")
        print("[DEBUG] generate_learning_summary: returning _default_summary() due to JSON parse failure")
        return _default_summary()

    result = _coerce_to_schema(parsed)
    print(f"[DEBUG] generate_learning_summary: coerced result = {result!r}")
    return result


if __name__ == "__main__":
    print("learning_summary.py loaded.")
    print("Public function: generate_learning_summary(messages) -> dict")
    print("Reuses gemini_client.create_model(); writes nothing to SQLite.")
