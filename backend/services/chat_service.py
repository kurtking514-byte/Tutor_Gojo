"""
chat_service.py - Chat orchestration for Tutor Gojo's backend API.

This is the home for logic that used to live inside main.py's Flet
"send message" handler: given a session_id and a user message, pull
recent history, stream a response from Gemini, and persist both the
user's message and the assistant's full reply to the database.

api.py should never call gemini_client or database directly for chat
turns - it should only call into this module.
"""

import dataclasses
import re
import traceback
import uuid
from pprint import pprint

import database
import gemini_client
import learning_summary
from services import memory_service

from memory_engine.reader import MemoryLoadError, MemoryReader
from memory_engine.retrieval import MemoryRetriever
from memory_engine.ranking import MemoryRanker
from memory_engine.prompt_builder import PromptBuilder

# How many recent messages (not turn-pairs) to pull from the DB and hand
# to gemini_client as history. gemini_client further trims this itself
# (MAX_HISTORY_TURNS), so this just needs to be a reasonable upper bound
# on what we fetch from SQLite per request.
HISTORY_FETCH_LIMIT = 20

# Separate, larger limit used only for post-turn memory extraction.
# HISTORY_FETCH_LIMIT above is deliberately small for the *live* Gemini
# prompt (cost/latency per request); learning_summary.py summarizes the
# whole session after the fact, and already soft-caps its own input
# (_MAX_TRANSCRIPT_MESSAGES = 200), so this matches that cap rather than
# reusing the live-chat constant.
MEMORY_HISTORY_LIMIT = 200

# Regex used only to pull the numeric confidence value back out of a
# journal entry's free-text summary (chat_service._update_learning_memory
# writes "Confidence this session: X.XX" into that text - it isn't stored
# as its own structured field anywhere in memory_service/memory_database).
# Best-effort only: if the text format ever changes, we just omit the
# confidence line from the memory prompt rather than erroring.
_CONFIDENCE_RE = re.compile(r"Confidence this session:\s*([0-9]*\.?[0-9]+)")

# Phase 7B (Observability, ROADMAP.md): metadata-only snapshot of the
# most recently completed _get_memory_prompt() execution. Holds exactly
# one snapshot (the latest) - never a history of past turns - and is
# overwritten in full on every call to _get_memory_prompt(), including
# on both of its error paths. Contains only booleans/counts describing
# what happened during the pipeline run; never conversation text,
# prompt content, or any memory-category content.
_last_memory_diagnostics = {
    "memory_load_succeeded": False,
    "retrieval_executed": False,
    "ranking_executed": False,
    "retrieved_item_count": 0,
    "ranked_item_count": 0,
    "prompt_produced": False,
}


def _count_context_items(context):
    """Read-only counting helper used only for diagnostics: sums the
    length of every list-valued field on a memory_engine context object
    (MemoryContext, or anything with the same shape), without reading,
    copying, or storing any of the actual list contents - only their
    lengths. Returns 0 for None or for any object with no list fields.
    """
    if context is None:
        return 0
    total = 0
    for f in dataclasses.fields(context):
        value = getattr(context, f.name, None)
        if isinstance(value, list):
            total += len(value)
    return total

def new_session_id():
    """Generate a fresh session id."""
    return uuid.uuid4().hex


def create_session(title=None, topic=None):
    """Create a brand new chat session and return its id."""
    session_id = new_session_id()
    database.create_session(session_id, title=title, topic=topic)
    return session_id


def _get_recent_history(session_id):
    """Fetch recent messages for a session, formatted as the
    [(role, content), ...] tuples gemini_client expects.
    """
    rows = database.get_chat_history(session_id, limit=HISTORY_FETCH_LIMIT)
    # rows are (role, content, timestamp) - gemini_client only wants (role, content)
    return [(role, content) for role, content, _ts in rows]


def _detect_topic(message):
    """Very lightweight topic tagging for messages, mirroring the kind of
    detection the original app could plug in. Kept simple/optional - this
    is not used to alter AI behavior, only to tag rows for the progress
    dashboard. Returns None if nothing obvious is detected.
    """
    lowered = message.lower()
    topic_keywords = {
        "Python": ["python", "django", "flask", "pandas"],
        "JavaScript": ["javascript", "js ", "node", "react", "typescript"],
        "SQL": ["sql", "database", "query", "sqlite", "postgres"],
        "HTML/CSS": ["html", "css", "flexbox", "grid layout"],
    }
    for topic, keywords in topic_keywords.items():
        if any(kw in lowered for kw in keywords):
            return topic
    return None


def _should_store_summary(summary):
    """Quality gate applied once per turn, before any memory_service
    writes happen in _update_learning_memory. If this returns False,
    nothing for this turn is persisted - no topic mastery update, no
    strength/misconception/mistake-pattern records, no journal entry.

    Each check below is independently sufficient to reject the summary;
    it must clear every one of them to be considered storage-worthy:
      - has no content in any of its list fields at all
      - (catch-all) no educational signal anywhere in the summary

    NOTE: confidence and next_lesson are intentionally NOT gating
    conditions here. Per learning_summary.py's extraction prompt,
    `confidence` estimates the *student's grasp* of the session's
    material, not whether the extraction itself is reliable - a
    struggling or early-session student can legitimately produce a low
    or 0.0 confidence score alongside perfectly valid topics_learned/
    strengths/misconceptions/mistake_patterns. Similarly, `next_lesson`
    is a forward-looking recommendation unrelated to whether those
    fields were validly observed this session, and the prompt itself
    allows it to be "" for short conversations. Gating storage on
    either previously caused fully-populated, correctly-extracted
    summaries to be silently discarded in full. Both values are still
    preserved in the summary/journal exactly as before - they're just
    no longer used to veto unrelated memory writes.
    """
    list_fields = (
        "topics_learned", "concepts_introduced", "strengths",
        "misconceptions", "mistake_patterns", "recommended_review",
    )

    # Nothing in any list field - clearly nothing worth remembering.
    if not any(summary.get(field) for field in list_fields):
        print(
            "[DEBUG] _should_store_summary -> False "
            f"(reason: every list field is empty: { {f: summary.get(f) for f in list_fields} })"
        )
        return False

    # Catch-all, mirrors the "any signal at all" check this function
    # replaces - kept in case summary grows fields beyond list_fields.
    has_signal = any([
        summary.get("topics_learned"),
        summary.get("concepts_introduced"),
        summary.get("strengths"),
        summary.get("misconceptions"),
        summary.get("mistake_patterns"),
        summary.get("recommended_review"),
        summary.get("next_lesson"),
    ])
    if not has_signal:
        print(
            "[DEBUG] _should_store_summary -> False "
            f"(reason: catch-all has_signal check failed; next_lesson={summary.get('next_lesson')!r})"
        )
        return False

    print("[DEBUG] _should_store_summary -> True")
    return True


def _get_latest_journal_entry():
    """Fetch just the newest journal entry, for the dedup check below.
    Returns None if there isn't one yet - callers should treat that as
    "nothing to be a duplicate of".
    """
    entries = memory_service.get_journal_entries(limit=1)
    return entries[0] if entries else None


def _is_duplicate_journal_entry(new_topics, new_strengths, new_misconceptions, new_text, latest_entry):
    """Deterministic (no fuzzy/AI similarity) check for whether writing
    a new journal entry would just restate the newest existing one.

    memory_database's learning_journal rows only store `summary` (free
    text) and `topics_covered` (a JSON list) - there's no structured
    per-entry strengths/misconceptions column, and adding one would mean
    changing memory_database.py's schema, which is out of scope here.
    So the four checks below use only what's actually available on a
    journal row:
      - identical summary text (case/whitespace-insensitive)
      - identical topics_covered set
      - every new strength name already appears in the latest entry's
        summary text
      - every new misconception name already appears in the latest
        entry's summary text
    The strengths/misconceptions checks are intentionally conservative -
    they can under-detect (miss a duplicate whose name never made it
    into journal text) but won't over-detect and silently drop a
    genuinely new entry.
    """
    if latest_entry is None:
        return False

    latest_summary = (latest_entry.get("summary") or "").strip().lower()
    new_text_norm = (new_text or "").strip().lower()
    if latest_summary and latest_summary == new_text_norm:
        return True

    latest_topics = set(latest_entry.get("topics_covered") or [])
    if new_topics and latest_topics and set(new_topics) == latest_topics:
        return True

    if new_strengths and all(name.lower() in latest_summary for name in new_strengths):
        return True

    if new_misconceptions and all(name.lower() in latest_summary for name in new_misconceptions):
        return True

    return False


def _update_learning_memory(session_id):
    """Best-effort educational memory update, called only after an
    assistant response has successfully completed - never during
    streaming, never after a failed/interrupted response (callers are
    responsible for that gating; see stream_chat/send_chat_message).

    Pulls the session's conversation, extracts a structured summary via
    learning_summary.generate_learning_summary(), and persists it
    through memory_service's existing functions only - never touches
    memory_database.py directly.

    Any failure here (DB read, Gemini extraction, memory_service write)
    is logged and swallowed. This must never interrupt or fail the
    chat turn it's attached to.
    """
    print(f"[DEBUG] _update_learning_memory: starting for session_id={session_id!r}")
    try:
        rows = database.get_chat_history(session_id, limit=MEMORY_HISTORY_LIMIT)
        messages = [{"role": role, "content": content} for role, content, _ts in rows]
        print(f"[DEBUG] _update_learning_memory: fetched {len(messages)} messages from history")

        print("[DEBUG] _update_learning_memory: calling learning_summary.generate_learning_summary() now")
        summary = learning_summary.generate_learning_summary(messages)
        print("[DEBUG] _update_learning_memory: generate_learning_summary() returned")
        print(f"[DEBUG] summary = {summary!r}")

        gate_result = _should_store_summary(summary)
        print(f"[DEBUG] _update_learning_memory: _should_store_summary(summary) = {gate_result}")

        if not gate_result:
            # Quality gate failed (see _should_store_summary): no
            # populated list fields at all - nothing worth persisting,
            # not an error.
            print("[DEBUG] _update_learning_memory: gate failed, returning without any memory_service writes")
            return

        for topic in summary["topics_learned"]:
            print(f"[DEBUG] about to call memory_service.update_topic_mastery(topic={topic!r}, mark_exercised=True)")
            memory_service.update_topic_mastery(topic, mark_exercised=True)

        for name in summary["misconceptions"]:
            print(f"[DEBUG] about to call memory_service.record_misconception(name={name!r})")
            memory_service.record_misconception(name)

        for name in summary["strengths"]:
            print(f"[DEBUG] about to call memory_service.record_strength(name={name!r})")
            memory_service.record_strength(name)

        for description in summary["mistake_patterns"]:
            print(f"[DEBUG] about to call memory_service.record_mistake_pattern(description={description!r})")
            memory_service.record_mistake_pattern(description)

        journal_notes = []
        if summary["concepts_introduced"]:
            journal_notes.append("New concepts: " + ", ".join(summary["concepts_introduced"]))
        if summary["recommended_review"]:
            journal_notes.append("Recommended review: " + ", ".join(summary["recommended_review"]))
        journal_notes.append(f"Confidence this session: {summary['confidence']:.2f}")
        journal_text = " | ".join(journal_notes)

        # Journal dedup only applies here - topic mastery, strengths,
        # misconceptions, and mistake patterns above are already written
        # regardless of whether the journal entry itself turns out to be
        # a duplicate of the newest one.
        latest_entry = _get_latest_journal_entry()
        is_duplicate = _is_duplicate_journal_entry(
            new_topics=summary["topics_learned"],
            new_strengths=summary["strengths"],
            new_misconceptions=summary["misconceptions"],
            new_text=journal_text,
            latest_entry=latest_entry,
        )
        print(f"[DEBUG] _update_learning_memory: _is_duplicate_journal_entry(...) = {is_duplicate}")
        if is_duplicate:
            print("[DEBUG] _update_learning_memory: duplicate journal entry detected, skipping add_journal_entry")
            return

        print(
            "[DEBUG] about to call memory_service.add_journal_entry("
            f"journal_text={journal_text!r}, session_id={session_id!r}, "
            f"topics_covered={summary['topics_learned']!r}, "
            f"unfinished_business={(summary['next_lesson'] or None)!r})"
        )
        memory_service.add_journal_entry(
            journal_text,
            session_id=session_id,
            topics_covered=summary["topics_learned"],
            unfinished_business=summary["next_lesson"] or None,
        )
        print("[DEBUG] _update_learning_memory: completed all writes for this turn")
    except Exception as e:
        print(f"[chat_service] Learning memory update failed, continuing chat normally: {e}")
        print("[DEBUG] Full traceback for the exception above:")
        traceback.print_exc()


def _extract_latest_confidence(journal_entries):
    """Best-effort: scan journal entries (assumed most-recent-first, per
    memory_service.get_journal_entries' "recent journal entries" contract)
    for the newest one that has a parseable confidence value embedded in
    its summary text. Returns None if nothing is found - callers must
    treat that as "omit the confidence line", not an error.
    """
    for entry in journal_entries or []:
        match = _CONFIDENCE_RE.search(entry.get("summary") or "")
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


def _format_memory_context(memory):
    """Convert the dict returned by memory_service.get_memory_context()
    into a compact, human-readable block to prepend - invisibly to the
    user - to the message sent to Gemini. Returns "" if there's nothing
    worth including (e.g. a brand-new student with no history yet).

    Deliberately only reads keys/fields; never writes anything, and never
    raises - any missing/oddly-shaped field is just skipped so a partial
    or evolving memory schema can't break the chat turn.
    """
    lines = []

    strengths = [s.get("name") for s in (memory.get("strengths") or []) if s.get("name")]
    if strengths:
        lines.append("Strong Topics:")
        lines.extend(f"- {name}" for name in strengths)
        lines.append("")

    weak_topics = [
        row.get("topic")
        for row in (memory.get("topic_mastery") or [])
        if row.get("topic") and row.get("mastery_level") in ("not_started", "shaky")
    ]
    if weak_topics:
        lines.append("Weak Topics:")
        lines.extend(f"- {topic}" for topic in weak_topics)
        lines.append("")

    mistakes = [m.get("description") for m in (memory.get("mistake_patterns") or []) if m.get("description")]
    if mistakes:
        lines.append("Recurring Mistakes:")
        lines.extend(f"- {desc}" for desc in mistakes)
        lines.append("")

    preferences = []
    for pref in (memory.get("learning_preferences") or []):
        text = pref.get("preference_value") or pref.get("preference_key")
        if text:
            preferences.append(text)
    if preferences:
        lines.append("Learning Preferences:")
        lines.extend(f"- {pref}" for pref in preferences)
        lines.append("")

    recent_topics = []
    for entry in (memory.get("recent_journal_entries") or []):
        for topic in entry.get("topics_covered") or []:
            if topic and topic not in recent_topics:
                recent_topics.append(topic)
    if recent_topics:
        lines.append("Recent Topics:")
        lines.extend(f"- {topic}" for topic in recent_topics[:10])
        lines.append("")

    confidence = _extract_latest_confidence(memory.get("recent_journal_entries"))
    if confidence is not None:
        lines.append("Current Confidence:")
        lines.append(f"{confidence:.2f}")
        lines.append("")

    if not lines:
        return ""

    body = "\n".join(lines).rstrip()
    return f"=== STUDENT LEARNING PROFILE ===\n\n{body}\n\n=== END PROFILE ==="


def _get_memory_prompt(message):
    """Best-effort fetch of the student's educational memory via the new
    memory_engine pipeline:

        MemoryReader.load_snapshot()
              -> MemoryRetriever.retrieve(snapshot, message)
              -> MemoryRanker.rank(context, message)
              -> PromptBuilder.build(ranked_context)

    This function only orchestrates that pipeline - it contains no
    retrieval, ranking, or formatting logic of its own; all of that
    lives in memory_engine.

    Never raises: MemoryLoadError (the expected failure mode when a
    memory category can't be loaded) results in an empty memory prompt
    so the chat turn can proceed without it. Any other, unexpected
    exception is logged with a full traceback (not silently ignored)
    and likewise results in an empty memory prompt, so a bug in the new
    pipeline can't take down a chat turn.
    """
    global _last_memory_diagnostics
    # Phase 7B (Observability): plain metadata collected alongside the
    # existing pipeline calls below - no new retrieval/ranking logic,
    # no change to what's returned or which exceptions are caught. This
    # dict replaces _last_memory_diagnostics wholesale in the `finally`
    # block below, on every path (success or either except branch), so
    # a diagnostics snapshot is always exactly consistent with what
    # actually happened during this call.
    diagnostics = {
        "memory_load_succeeded": False,
        "retrieval_executed": False,
        "ranking_executed": False,
        "retrieved_item_count": 0,
        "ranked_item_count": 0,
        "prompt_produced": False,
    }
    try:
        snapshot = MemoryReader().load_snapshot()
        diagnostics["memory_load_succeeded"] = True

        context = MemoryRetriever().retrieve(snapshot, message)
        diagnostics["retrieval_executed"] = True
        diagnostics["retrieved_item_count"] = _count_context_items(context)

        ranked_context = MemoryRanker().rank(context, message)
        diagnostics["ranking_executed"] = True
        diagnostics["ranked_item_count"] = _count_context_items(ranked_context)

        memory_prompt = PromptBuilder().build(ranked_context)
        diagnostics["prompt_produced"] = bool(memory_prompt)
        print("===== MEMORY PROMPT (memory_engine) =====")
        print(memory_prompt)
        print("==========================================")
        return memory_prompt
    except MemoryLoadError as e:
        print(f"[chat_service] Memory snapshot load failed, continuing without it: {e}")
        return ""
    except Exception:
        print("[chat_service] Unexpected error building memory prompt via memory_engine, continuing without it:")
        traceback.print_exc()
        return ""
    finally:
        _last_memory_diagnostics = diagnostics


def _augment_message_with_memory(message):
    """Prepend the hidden student-memory profile block to `message`, for
    the Gemini call only.

    Important: this augmented string is only ever passed to
    gemini_client - it is never what gets saved to the database and
    never what the user sees. Callers must keep using the original
    `message` for database.save_message and for anything shown/returned
    to the frontend.
    """
    memory_prompt = _get_memory_prompt(message)
    if not memory_prompt:
        return message
    return f"{memory_prompt}\n\n{message}"


def stream_chat(session_id, message):
    """Generator: persists the user's message, streams the assistant's
    reply chunk-by-chunk from Gemini (preserving the exact streaming
    behavior verified in gemini_client.stream_message), and persists the
    full assistant reply once streaming completes.

    Yields plain text chunks - api.py is responsible for wrapping them
    in the SSE wire format.
    """
    topic = _detect_topic(message)

    # Persist the user's turn before calling Gemini, and build history
    # from what was already in the DB (so we don't duplicate this message
    # into the context we send).
    history = _get_recent_history(session_id)
    database.save_message(session_id, "user", message, topic=topic)

    # augmented_message carries the hidden memory-profile block for
    # Gemini's benefit only; `message` (unmodified) is what's already
    # been persisted above and what the user already sees.
    augmented_message = _augment_message_with_memory(message)

    print("===== AUGMENTED MESSAGE =====")
    print(augmented_message)
    print("=============================")

    full_response_parts = []
    stream_completed = False
    try:
        for chunk in gemini_client.stream_message(augmented_message, history=history):
            full_response_parts.append(chunk)
            yield chunk
        # Only reached if the loop above exhausted naturally - not on a
        # client disconnect or an exception raised mid-stream, both of
        # which skip straight to `finally` below without hitting this line.
        stream_completed = True
    finally:
        # Persist whatever was generated even if the client disconnected
        # mid-stream, so history stays consistent with what the user saw.
        full_response = "".join(full_response_parts)
        if full_response:
            database.save_message(session_id, "assistant", full_response, topic=topic)
            if topic:
                database.update_progress(topic)
            # Educational memory update: only after a genuinely completed,
            # successful response - never on a partial/disconnected stream.
            if stream_completed:
                _update_learning_memory(session_id)


def send_chat_message(session_id, message):
    """Non-streaming equivalent of stream_chat, for callers that don't
    need progressive output (kept for parity with gemini_client.send_message).
    """
    topic = _detect_topic(message)
    history = _get_recent_history(session_id)
    database.save_message(session_id, "user", message, topic=topic)

    # augmented_message carries the hidden memory-profile block for
    # Gemini's benefit only; `message` (unmodified) is what's already
    # been persisted above and what the user already sees.
    augmented_message = _augment_message_with_memory(message)

    print("===== AUGMENTED MESSAGE =====")
    print(augmented_message)
    print("=============================")

    reply = gemini_client.send_message(augmented_message, history=history)

    database.save_message(session_id, "assistant", reply, topic=topic)
    if topic:
        database.update_progress(topic)
    # Reaching this point means gemini_client.send_message() returned
    # without raising, i.e. this was a successful response.
    _update_learning_memory(session_id)
    return reply


def get_memory_diagnostics():
    """Phase 7B (Observability, ROADMAP.md): read-only snapshot describing
    the most recently completed memory-pipeline execution (the latest
    call to _get_memory_prompt(), across either stream_chat() or
    send_chat_message()).

    Returns a plain, JSON-serializable dict of metadata only:
        {
            "memory_load_succeeded": bool,
            "retrieval_executed": bool,
            "ranking_executed": bool,
            "retrieved_item_count": int,
            "ranked_item_count": int,
            "prompt_produced": bool,
        }

    Contains no conversation text, no prompt content, no memory-category
    content, and no other user data - only booleans/counts already known
    while the pipeline was running. Holds exactly one snapshot (the
    latest turn's) rather than any history; before the first memory
    pipeline execution in this process, every field is at its default
    (False/0).

    Read-only and deterministic: returns a fresh copy of the module-level
    snapshot each call, so mutating the returned dict never affects
    diagnostics state, and repeated calls with no intervening chat turn
    return identical output.
    """
    return dict(_last_memory_diagnostics)
