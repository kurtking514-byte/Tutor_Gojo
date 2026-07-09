"""
database.py - SQLite Database Manager for Tutor Gojo
Stores chat history, learning progress, and user stats.
Why SQLite? Zero setup, file-based, perfect for a single-user desktop app.
"""

import sqlite3
from datetime import datetime
from config import get_db_path


def get_connection():
    """Get a database connection."""
    return sqlite3.connect(get_db_path())


def init_database():
    """Create all tables if they don't exist. Called on app startup."""
    conn = get_connection()
    cursor = conn.cursor()

    # Chat messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,  -- 'user' or 'assistant'
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            has_code INTEGER DEFAULT 0,  -- 1 if message contains code blocks
            topic TEXT  -- detected topic (Python, JavaScript, etc.)
        )
    """)

    # Learning sessions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            title TEXT,
            topic TEXT,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
            message_count INTEGER DEFAULT 0
        )
    """)

    # Progress tracking table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            subtopic TEXT,
            level INTEGER DEFAULT 1,  -- 1=beginner, 2=intermediate, 3=advanced
            questions_asked INTEGER DEFAULT 0,
            questions_correct INTEGER DEFAULT 0,
            last_studied DATETIME,
            UNIQUE(topic, subtopic)
        )
    """)

    # Quizzes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            question TEXT NOT NULL,
            user_answer TEXT,
            correct_answer TEXT,
            is_correct INTEGER,
            asked_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] Database initialized successfully")


def create_session(session_id, title=None, topic=None):
    """Explicitly create a new (empty) session row. Used by the API's
    POST /session endpoint so the frontend gets a session_id to attach
    messages to before any message has been sent. save_message() still
    upserts sessions on its own for backward compatibility, so this is
    purely additive - no existing call site needs to change."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sessions (session_id, title, topic)
        VALUES (?, ?, ?)
        ON CONFLICT(session_id) DO NOTHING
    """, (session_id, title, topic))
    conn.commit()
    conn.close()


def save_message(session_id, role, content, topic=None):
    """Save a chat message to the database."""
    conn = get_connection()
    cursor = conn.cursor()

    # Detect if message has code blocks
    has_code = 1 if "```" in content else 0

    cursor.execute("""
        INSERT INTO messages (session_id, role, content, topic, has_code)
        VALUES (?, ?, ?, ?, ?)
    """, (session_id, role, content, topic, has_code))

    # Update session message count
    cursor.execute("""
        INSERT INTO sessions (session_id, last_active, message_count)
        VALUES (?, CURRENT_TIMESTAMP, 1)
        ON CONFLICT(session_id) DO UPDATE SET
            last_active = CURRENT_TIMESTAMP,
            message_count = message_count + 1
    """, (session_id,))

    conn.commit()
    conn.close()


def get_chat_history(session_id, limit=50):
    """Get recent messages from a session."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT role, content, timestamp FROM messages
        WHERE session_id = ?
        ORDER BY timestamp ASC
        LIMIT ?
    """, (session_id, limit))
    messages = cursor.fetchall()
    conn.close()
    return messages


def get_all_sessions():
    """Get list of all chat sessions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT session_id, title, topic, started_at, message_count
        FROM sessions
        ORDER BY last_active DESC
    """)
    sessions = cursor.fetchall()
    conn.close()
    return sessions


def update_progress(topic, subtopic=None, correct=None):
    """Update learning progress for a topic."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO progress (topic, subtopic, questions_asked, last_studied)
        VALUES (?, ?, 1, CURRENT_TIMESTAMP)
        ON CONFLICT(topic, subtopic) DO UPDATE SET
            questions_asked = questions_asked + 1,
            last_studied = CURRENT_TIMESTAMP
    """, (topic, subtopic))

    if correct is not None:
        cursor.execute("""
            UPDATE progress 
            SET questions_correct = questions_correct + ?
            WHERE topic = ? AND subtopic = ?
        """, (1 if correct else 0, topic, subtopic))

    conn.commit()
    conn.close()


def get_progress(topic=None):
    """Get learning progress. If topic is None, get all."""
    conn = get_connection()
    cursor = conn.cursor()

    if topic:
        cursor.execute("""
            SELECT topic, subtopic, level, questions_asked, questions_correct, last_studied
            FROM progress WHERE topic = ?
        """, (topic,))
    else:
        cursor.execute("""
            SELECT topic, subtopic, level, questions_asked, questions_correct, last_studied
            FROM progress ORDER BY last_studied DESC
        """)

    results = cursor.fetchall()
    conn.close()
    return results


def save_quiz(session_id, question, correct_answer):
    """Save a quiz question."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO quizzes (session_id, question, correct_answer)
        VALUES (?, ?, ?)
    """, (session_id, question, correct_answer))
    conn.commit()
    conn.close()


def get_stats():
    """Get overall learning stats."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM messages WHERE role = 'user'")
    total_messages = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM sessions")
    total_sessions = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM quizzes WHERE is_correct = 1")
    correct_quizzes = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM quizzes")
    total_quizzes = cursor.fetchone()[0]

    conn.close()

    return {
        "total_messages": total_messages,
        "total_sessions": total_sessions,
        "correct_quizzes": correct_quizzes,
        "total_quizzes": total_quizzes,
        "accuracy": (correct_quizzes / total_quizzes * 100) if total_quizzes > 0 else 0
    }


if __name__ == "__main__":
    init_database()
    print("\nDatabase tables created:")
    print("- messages: Chat history")
    print("- sessions: Conversation sessions")
    print("- progress: Learning progress tracking")
    print("- quizzes: Quiz questions and answers")
