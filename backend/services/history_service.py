"""
history_service.py - Read-side data access for Tutor Gojo's backend API.

Thin wrapper around database.py for everything that isn't an active chat
turn: listing sessions, fetching message history, and reading progress
stats. Keeps api.py from importing sqlite-adjacent code directly.
"""

import database


def list_sessions():
    """Return all chat sessions, most recently active first."""
    rows = database.get_all_sessions()
    return [
        {
            "session_id": session_id,
            "title": title,
            "topic": topic,
            "started_at": started_at,
            "message_count": message_count,
        }
        for session_id, title, topic, started_at, message_count in rows
    ]


def get_messages(session_id, limit=50):
    """Return chat history for a single session."""
    rows = database.get_chat_history(session_id, limit=limit)
    return [
        {"role": role, "content": content, "timestamp": timestamp}
        for role, content, timestamp in rows
    ]


def get_progress(topic=None):
    """Return learning progress, optionally filtered to one topic."""
    rows = database.get_progress(topic=topic)
    return [
        {
            "topic": t,
            "subtopic": subtopic,
            "level": level,
            "questions_asked": questions_asked,
            "questions_correct": questions_correct,
            "last_studied": last_studied,
        }
        for t, subtopic, level, questions_asked, questions_correct, last_studied in rows
    ]


def get_stats():
    """Return overall learning stats (used for the future dashboard)."""
    return database.get_stats()
