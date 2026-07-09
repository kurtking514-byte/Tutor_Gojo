"""
memory_database.py - Educational Memory persistence layer for Tutor Gojo

Implements the schema and low-level persistence functions for the 13
long-term educational memory categories defined in the Phase 1 design
document ("Tutor Gojo — Educational Memory Blueprint"):

    1.  student_profile
    2.  topic_mastery
    3.  misconceptions        (Weak Concepts / Misconception Ledger)
    4.  strengths             (Consolidated Strengths)
    5.  learning_preferences
    6.  coding_style_traits   (Coding Style Fingerprint)
    7.  mistake_patterns      (Recurring Mistake Patterns)
    8.  learning_journal      (Session History narrative)
    9.  projects
    10. assessments           (Assessment / Quiz History)
    11. motivational_signals
    12. milestones            (Growth Trajectory & Milestones)
    13. curiosity_backlog

This module is deliberately scoped to schema + persistence only - the
same level as database.py. It does not define API routes, does not
build prompts, and is not wired into api.py's startup event; that
wiring (calling init_memory_database() alongside init_database(), and
exposing routes through a memory_service.py-style layer) is a separate,
later task.

Tutor Gojo is a single-user desktop app (see database.py), so none of
these tables carry a user/student foreign key - there is exactly one
implicit student, matching the rest of the schema.

Connection handling reuses database.get_connection() rather than
duplicating the config/get_db_path() wiring, so both modules always
point at the same SQLite file.
"""

from database import get_connection


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_memory_database():
    """Create all educational-memory tables if they don't exist. Call
    this alongside database.init_database() once this module is wired
    into the API's startup event (not done here - see module docstring)."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Student Profile - single implicit row (id is always 1). Static,
    # rarely-changing identity/context, not performance data.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS student_profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            goals TEXT,
            background TEXT,
            preferred_languages TEXT,   -- JSON-encoded list, e.g. '["Python", "JavaScript"]'
            domain_interests TEXT,      -- JSON-encoded list, e.g. '["web apps", "games"]'
            time_horizon TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Topic Mastery Map - current-state snapshot per topic/subtopic.
    # subtopic defaults to '' (not NULL) so UNIQUE(topic, subtopic) works
    # reliably - SQLite treats each NULL as distinct, which would break
    # the upsert-by-conflict pattern used in update_topic_mastery().
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS topic_mastery (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            subtopic TEXT NOT NULL DEFAULT '',
            mastery_level TEXT NOT NULL DEFAULT 'not_started',
                -- expected values: not_started | shaky | developing | comfortable | strong
            trend TEXT DEFAULT 'stable',
                -- expected values: improving | stable | plateaued | regressing
            last_exercised DATETIME,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(topic, subtopic)
        )
    """)

    # 3. Misconception Ledger - specific wrong mental models, tracked by
    # a normalized name. Distinct from mistake_patterns (mechanical
    # errors) - this is about incorrect beliefs, not slips.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS misconceptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            topic TEXT,
            subtopic TEXT,
            occurrence_count INTEGER DEFAULT 1,
            correction_attempts INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',   -- active | resolved
            first_observed DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_observed DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    """)

    # 4. Consolidated Strengths - mirror of misconceptions, held to a
    # stricter evidence bar (repeated demonstration, not a single success).
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS strengths (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            topic TEXT,
            subtopic TEXT,
            demonstration_count INTEGER DEFAULT 1,
            first_confirmed DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_confirmed DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    """)

    # 5. Learning Preferences - key/value pedagogical-delivery
    # preferences (how to teach), not performance data.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS learning_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            preference_key TEXT NOT NULL UNIQUE,
                -- e.g. 'explanation_style', 'pacing', 'feedback_style'
            preference_value TEXT NOT NULL,
                -- e.g. 'examples_first', 'fast', 'direct'
            evidence_count INTEGER DEFAULT 1,
            notes TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 6. Coding Style Fingerprint - key/value stylistic habits, purely
    # descriptive (not evaluative), distinct from mistake_patterns.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS coding_style_traits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trait_key TEXT NOT NULL UNIQUE,
                -- e.g. 'loop_vs_comprehension', 'function_length'
            trait_value TEXT NOT NULL,
                -- e.g. 'prefers_explicit_loops', 'tends_long_before_refactor'
            observed_count INTEGER DEFAULT 1,
            first_observed DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_observed DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    """)

    # 7. Recurring Mistake Patterns - mechanical/habitual errors, as
    # distinct from the conceptual misconceptions in table 3.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mistake_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL UNIQUE,
            topic TEXT,
            occurrence_count INTEGER DEFAULT 1,
            trend TEXT DEFAULT 'unknown',   -- improving | persisting | unknown
            first_observed DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_observed DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    """)

    # 8. Learning Journal - append-only narrative log, session by
    # session. session_id is a loose reference to sessions.session_id
    # (not a FK constraint, matching the rest of this codebase's style
    # of treating session_id as a plain text identifier).
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS learning_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            entry_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            summary TEXT NOT NULL,
            topics_covered TEXT,      -- JSON-encoded list
            is_turning_point INTEGER DEFAULT 0,
            unfinished_business TEXT
        )
    """)

    # 9. Projects & Applied Work - multi-session applied efforts,
    # organized around an artifact rather than the student directly.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'planning',
                -- planning | in_progress | paused | completed
            goals TEXT,
            design_decisions TEXT,
            next_steps TEXT,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 10. Assessment History - deliberate, structured checks, as
    # distinct from organic mistakes made during casual conversation.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            topic TEXT,
            subtopic TEXT,
            assessment_type TEXT DEFAULT 'quiz',   -- quiz | challenge | check
            question TEXT NOT NULL,
            student_answer TEXT,
            expected_answer TEXT,
            is_correct INTEGER,
            context_notes TEXT,
            assessed_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 11. Motivational & Engagement Signals - learning-relevant emotional
    # patterns only, never a clinical/diagnostic record.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS motivational_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_description TEXT NOT NULL UNIQUE,
            signal_type TEXT,    -- frustration | confidence | engagement
            topic TEXT,
            occurrence_count INTEGER DEFAULT 1,
            first_observed DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_observed DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    """)

    # 12. Growth Trajectory & Milestones - coarse-grained, infrequent,
    # multi-month markers. Append-only.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            category TEXT,   -- e.g. 'first_project', 'independent_debugging'
            achieved_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    """)

    # 13. Curiosity Backlog - deferred tangents, cleared when addressed.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS curiosity_backlog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            raised_in_session TEXT,
            status TEXT DEFAULT 'open',   -- open | addressed
            raised_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            addressed_at DATETIME,
            notes TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] Educational memory tables initialized successfully")


# ---------------------------------------------------------------------------
# 1. Student Profile
# ---------------------------------------------------------------------------

def get_student_profile():
    """Return the single student profile row, or None if never set."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT goals, background, preferred_languages, domain_interests,
               time_horizon, updated_at
        FROM student_profile WHERE id = 1
    """)
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    keys = ["goals", "background", "preferred_languages", "domain_interests",
            "time_horizon", "updated_at"]
    return dict(zip(keys, row))


def update_student_profile(goals=None, background=None, preferred_languages=None,
                            domain_interests=None, time_horizon=None):
    """Create or update the single student profile row. Only non-None
    fields are overwritten - callers can update one field at a time
    without needing to re-supply the rest."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO student_profile (id, goals, background, preferred_languages, domain_interests, time_horizon)
        VALUES (1, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            goals = COALESCE(excluded.goals, goals),
            background = COALESCE(excluded.background, background),
            preferred_languages = COALESCE(excluded.preferred_languages, preferred_languages),
            domain_interests = COALESCE(excluded.domain_interests, domain_interests),
            time_horizon = COALESCE(excluded.time_horizon, time_horizon),
            updated_at = CURRENT_TIMESTAMP
    """, (goals, background, preferred_languages, domain_interests, time_horizon))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# 2. Topic Mastery Map
# ---------------------------------------------------------------------------

def update_topic_mastery(topic, subtopic="", mastery_level=None, trend=None, mark_exercised=False):
    """Create or update the mastery snapshot for a topic/subtopic pair."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO topic_mastery (topic, subtopic, mastery_level, trend, last_exercised)
        VALUES (?, ?, COALESCE(?, 'not_started'), COALESCE(?, 'stable'),
                CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END)
        ON CONFLICT(topic, subtopic) DO UPDATE SET
            mastery_level = COALESCE(excluded.mastery_level, mastery_level),
            trend = COALESCE(excluded.trend, trend),
            last_exercised = CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE last_exercised END,
            updated_at = CURRENT_TIMESTAMP
    """, (topic, subtopic, mastery_level, trend, mark_exercised, mark_exercised))
    conn.commit()
    conn.close()


def get_topic_mastery(topic=None):
    """Return mastery snapshots, optionally filtered to one topic."""
    conn = get_connection()
    cursor = conn.cursor()
    if topic:
        cursor.execute("""
            SELECT topic, subtopic, mastery_level, trend, last_exercised, updated_at
            FROM topic_mastery WHERE topic = ? ORDER BY subtopic ASC
        """, (topic,))
    else:
        cursor.execute("""
            SELECT topic, subtopic, mastery_level, trend, last_exercised, updated_at
            FROM topic_mastery ORDER BY topic ASC, subtopic ASC
        """)
    rows = cursor.fetchall()
    conn.close()
    keys = ["topic", "subtopic", "mastery_level", "trend", "last_exercised", "updated_at"]
    return [dict(zip(keys, row)) for row in rows]


# ---------------------------------------------------------------------------
# 3. Misconception Ledger
# ---------------------------------------------------------------------------

def record_misconception(name, topic=None, subtopic=None, notes=None):
    """Log an observed misconception, or bump its occurrence count and
    last_observed timestamp if it's already tracked. `name` should be a
    normalized, consistent label for the same underlying misconception
    (e.g. always 'lists_copied_by_value', not a fresh sentence each time)
    so repeated observations correctly accumulate on one row."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO misconceptions (name, topic, subtopic, notes)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            occurrence_count = occurrence_count + 1,
            last_observed = CURRENT_TIMESTAMP,
            notes = COALESCE(excluded.notes, notes)
    """, (name, topic, subtopic, notes))
    conn.commit()
    conn.close()


def mark_misconception_resolved(name):
    """Mark a misconception as resolved without deleting its history."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE misconceptions SET status = 'resolved' WHERE name = ?
    """, (name,))
    conn.commit()
    conn.close()


def get_misconceptions(status=None):
    """Return tracked misconceptions, optionally filtered by status
    ('active' or 'resolved')."""
    conn = get_connection()
    cursor = conn.cursor()
    if status:
        cursor.execute("""
            SELECT name, topic, subtopic, occurrence_count, correction_attempts,
                   status, first_observed, last_observed, notes
            FROM misconceptions WHERE status = ? ORDER BY last_observed DESC
        """, (status,))
    else:
        cursor.execute("""
            SELECT name, topic, subtopic, occurrence_count, correction_attempts,
                   status, first_observed, last_observed, notes
            FROM misconceptions ORDER BY last_observed DESC
        """)
    rows = cursor.fetchall()
    conn.close()
    keys = ["name", "topic", "subtopic", "occurrence_count", "correction_attempts",
            "status", "first_observed", "last_observed", "notes"]
    return [dict(zip(keys, row)) for row in rows]


# ---------------------------------------------------------------------------
# 4. Consolidated Strengths
# ---------------------------------------------------------------------------

def record_strength(name, topic=None, subtopic=None, notes=None):
    """Log a demonstration of a consolidated strength, or bump its
    demonstration count if already tracked. Same normalized-name
    requirement as record_misconception()."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO strengths (name, topic, subtopic, notes)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            demonstration_count = demonstration_count + 1,
            last_confirmed = CURRENT_TIMESTAMP,
            notes = COALESCE(excluded.notes, notes)
    """, (name, topic, subtopic, notes))
    conn.commit()
    conn.close()


def get_strengths(topic=None):
    """Return consolidated strengths, optionally filtered to one topic."""
    conn = get_connection()
    cursor = conn.cursor()
    if topic:
        cursor.execute("""
            SELECT name, topic, subtopic, demonstration_count, first_confirmed, last_confirmed, notes
            FROM strengths WHERE topic = ? ORDER BY last_confirmed DESC
        """, (topic,))
    else:
        cursor.execute("""
            SELECT name, topic, subtopic, demonstration_count, first_confirmed, last_confirmed, notes
            FROM strengths ORDER BY last_confirmed DESC
        """)
    rows = cursor.fetchall()
    conn.close()
    keys = ["name", "topic", "subtopic", "demonstration_count", "first_confirmed", "last_confirmed", "notes"]
    return [dict(zip(keys, row)) for row in rows]


# ---------------------------------------------------------------------------
# 5. Learning Preferences
# ---------------------------------------------------------------------------

def set_learning_preference(preference_key, preference_value, notes=None):
    """Create or update a single learning preference. Bumps
    evidence_count on repeat writes of the same key, since a preference
    seen again is a stronger signal than one seen once."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO learning_preferences (preference_key, preference_value, notes)
        VALUES (?, ?, ?)
        ON CONFLICT(preference_key) DO UPDATE SET
            preference_value = excluded.preference_value,
            evidence_count = evidence_count + 1,
            notes = COALESCE(excluded.notes, notes),
            updated_at = CURRENT_TIMESTAMP
    """, (preference_key, preference_value, notes))
    conn.commit()
    conn.close()


def get_learning_preferences():
    """Return all tracked learning preferences."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT preference_key, preference_value, evidence_count, notes, updated_at
        FROM learning_preferences ORDER BY preference_key ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    keys = ["preference_key", "preference_value", "evidence_count", "notes", "updated_at"]
    return [dict(zip(keys, row)) for row in rows]


# ---------------------------------------------------------------------------
# 6. Coding Style Fingerprint
# ---------------------------------------------------------------------------

def set_coding_style_trait(trait_key, trait_value, notes=None):
    """Create or update a single coding style trait, bumping
    observed_count on repeat observations."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO coding_style_traits (trait_key, trait_value, notes)
        VALUES (?, ?, ?)
        ON CONFLICT(trait_key) DO UPDATE SET
            trait_value = excluded.trait_value,
            observed_count = observed_count + 1,
            last_observed = CURRENT_TIMESTAMP,
            notes = COALESCE(excluded.notes, notes)
    """, (trait_key, trait_value, notes))
    conn.commit()
    conn.close()


def get_coding_style_traits():
    """Return all tracked coding style traits."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT trait_key, trait_value, observed_count, first_observed, last_observed, notes
        FROM coding_style_traits ORDER BY trait_key ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    keys = ["trait_key", "trait_value", "observed_count", "first_observed", "last_observed", "notes"]
    return [dict(zip(keys, row)) for row in rows]


# ---------------------------------------------------------------------------
# 7. Recurring Mistake Patterns
# ---------------------------------------------------------------------------

def record_mistake_pattern(description, topic=None, trend=None, notes=None):
    """Log an occurrence of a recurring mechanical mistake, or bump its
    occurrence count if already tracked. `description` should be a
    normalized label, same convention as record_misconception()."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO mistake_patterns (description, topic, trend, notes)
        VALUES (?, ?, COALESCE(?, 'unknown'), ?)
        ON CONFLICT(description) DO UPDATE SET
            occurrence_count = occurrence_count + 1,
            trend = COALESCE(?, trend),
            last_observed = CURRENT_TIMESTAMP,
            notes = COALESCE(excluded.notes, notes)
    """, (description, topic, trend, notes, trend))
    conn.commit()
    conn.close()


def get_mistake_patterns(topic=None):
    """Return recurring mistake patterns, optionally filtered to one topic."""
    conn = get_connection()
    cursor = conn.cursor()
    if topic:
        cursor.execute("""
            SELECT description, topic, occurrence_count, trend, first_observed, last_observed, notes
            FROM mistake_patterns WHERE topic = ? ORDER BY last_observed DESC
        """, (topic,))
    else:
        cursor.execute("""
            SELECT description, topic, occurrence_count, trend, first_observed, last_observed, notes
            FROM mistake_patterns ORDER BY last_observed DESC
        """)
    rows = cursor.fetchall()
    conn.close()
    keys = ["description", "topic", "occurrence_count", "trend", "first_observed", "last_observed", "notes"]
    return [dict(zip(keys, row)) for row in rows]


# ---------------------------------------------------------------------------
# 8. Learning Journal
# ---------------------------------------------------------------------------

def add_journal_entry(summary, session_id=None, topics_covered=None,
                       is_turning_point=False, unfinished_business=None):
    """Append a narrative entry to the learning journal. topics_covered
    should be pre-serialized to a JSON string by the caller, or None."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO learning_journal
            (session_id, summary, topics_covered, is_turning_point, unfinished_business)
        VALUES (?, ?, ?, ?, ?)
    """, (session_id, summary, topics_covered, 1 if is_turning_point else 0, unfinished_business))
    conn.commit()
    conn.close()


def get_journal_entries(limit=50):
    """Return the most recent journal entries, newest first."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT session_id, entry_date, summary, topics_covered, is_turning_point, unfinished_business
        FROM learning_journal ORDER BY entry_date DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    keys = ["session_id", "entry_date", "summary", "topics_covered", "is_turning_point", "unfinished_business"]
    return [dict(zip(keys, row)) for row in rows]


# ---------------------------------------------------------------------------
# 9. Projects & Applied Work
# ---------------------------------------------------------------------------

def create_project(name, description=None, goals=None):
    """Create a new project and return its id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO projects (name, description, goals)
        VALUES (?, ?, ?)
    """, (name, description, goals))
    project_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return project_id


def update_project(project_id, status=None, design_decisions=None, next_steps=None):
    """Update mutable fields on an existing project. Only non-None
    fields are overwritten."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE projects SET
            status = COALESCE(?, status),
            design_decisions = COALESCE(?, design_decisions),
            next_steps = COALESCE(?, next_steps),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (status, design_decisions, next_steps, project_id))
    conn.commit()
    conn.close()


def get_projects(status=None):
    """Return projects, optionally filtered by status."""
    conn = get_connection()
    cursor = conn.cursor()
    if status:
        cursor.execute("""
            SELECT id, name, description, status, goals, design_decisions,
                   next_steps, started_at, updated_at
            FROM projects WHERE status = ? ORDER BY updated_at DESC
        """, (status,))
    else:
        cursor.execute("""
            SELECT id, name, description, status, goals, design_decisions,
                   next_steps, started_at, updated_at
            FROM projects ORDER BY updated_at DESC
        """)
    rows = cursor.fetchall()
    conn.close()
    keys = ["id", "name", "description", "status", "goals", "design_decisions",
            "next_steps", "started_at", "updated_at"]
    return [dict(zip(keys, row)) for row in rows]


# ---------------------------------------------------------------------------
# 10. Assessment History
# ---------------------------------------------------------------------------

def record_assessment(question, session_id=None, topic=None, subtopic=None,
                       assessment_type="quiz", student_answer=None,
                       expected_answer=None, is_correct=None, context_notes=None):
    """Log a single deliberate assessment (quiz/challenge/check)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO assessments
            (session_id, topic, subtopic, assessment_type, question,
             student_answer, expected_answer, is_correct, context_notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (session_id, topic, subtopic, assessment_type, question,
          student_answer, expected_answer,
          None if is_correct is None else (1 if is_correct else 0),
          context_notes))
    conn.commit()
    conn.close()


def get_assessment_history(topic=None, limit=50):
    """Return recent assessments, newest first, optionally filtered to one topic."""
    conn = get_connection()
    cursor = conn.cursor()
    if topic:
        cursor.execute("""
            SELECT session_id, topic, subtopic, assessment_type, question,
                   student_answer, expected_answer, is_correct, context_notes, assessed_at
            FROM assessments WHERE topic = ? ORDER BY assessed_at DESC LIMIT ?
        """, (topic, limit))
    else:
        cursor.execute("""
            SELECT session_id, topic, subtopic, assessment_type, question,
                   student_answer, expected_answer, is_correct, context_notes, assessed_at
            FROM assessments ORDER BY assessed_at DESC LIMIT ?
        """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    keys = ["session_id", "topic", "subtopic", "assessment_type", "question",
            "student_answer", "expected_answer", "is_correct", "context_notes", "assessed_at"]
    return [dict(zip(keys, row)) for row in rows]


# ---------------------------------------------------------------------------
# 11. Motivational & Engagement Signals
# ---------------------------------------------------------------------------

def record_motivational_signal(pattern_description, signal_type=None, topic=None, notes=None):
    """Log an observed motivational/engagement pattern, or bump its
    occurrence count if already tracked. `pattern_description` should be
    a normalized label, same convention as record_misconception()."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO motivational_signals (pattern_description, signal_type, topic, notes)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(pattern_description) DO UPDATE SET
            occurrence_count = occurrence_count + 1,
            last_observed = CURRENT_TIMESTAMP,
            notes = COALESCE(excluded.notes, notes)
    """, (pattern_description, signal_type, topic, notes))
    conn.commit()
    conn.close()


def get_motivational_signals(signal_type=None):
    """Return motivational signals, optionally filtered by type
    ('frustration', 'confidence', 'engagement')."""
    conn = get_connection()
    cursor = conn.cursor()
    if signal_type:
        cursor.execute("""
            SELECT pattern_description, signal_type, topic, occurrence_count,
                   first_observed, last_observed, notes
            FROM motivational_signals WHERE signal_type = ? ORDER BY last_observed DESC
        """, (signal_type,))
    else:
        cursor.execute("""
            SELECT pattern_description, signal_type, topic, occurrence_count,
                   first_observed, last_observed, notes
            FROM motivational_signals ORDER BY last_observed DESC
        """)
    rows = cursor.fetchall()
    conn.close()
    keys = ["pattern_description", "signal_type", "topic", "occurrence_count",
            "first_observed", "last_observed", "notes"]
    return [dict(zip(keys, row)) for row in rows]


# ---------------------------------------------------------------------------
# 12. Growth Trajectory & Milestones
# ---------------------------------------------------------------------------

def add_milestone(title, description=None, category=None, notes=None):
    """Record a new milestone. Append-only - milestones are never
    updated or removed once logged."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO milestones (title, description, category, notes)
        VALUES (?, ?, ?, ?)
    """, (title, description, category, notes))
    conn.commit()
    conn.close()


def get_milestones(limit=None):
    """Return milestones, newest first. limit=None returns all."""
    conn = get_connection()
    cursor = conn.cursor()
    if limit:
        cursor.execute("""
            SELECT title, description, category, achieved_at, notes
            FROM milestones ORDER BY achieved_at DESC LIMIT ?
        """, (limit,))
    else:
        cursor.execute("""
            SELECT title, description, category, achieved_at, notes
            FROM milestones ORDER BY achieved_at DESC
        """)
    rows = cursor.fetchall()
    conn.close()
    keys = ["title", "description", "category", "achieved_at", "notes"]
    return [dict(zip(keys, row)) for row in rows]


# ---------------------------------------------------------------------------
# 13. Curiosity Backlog
# ---------------------------------------------------------------------------

def add_curiosity(question, raised_in_session=None, notes=None):
    """Log a deferred tangent/question the student raised."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO curiosity_backlog (question, raised_in_session, notes)
        VALUES (?, ?, ?)
    """, (question, raised_in_session, notes))
    conn.commit()
    conn.close()


def mark_curiosity_addressed(curiosity_id):
    """Mark a curiosity-backlog entry as addressed."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE curiosity_backlog
        SET status = 'addressed', addressed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (curiosity_id,))
    conn.commit()
    conn.close()


def get_curiosity_backlog(status="open"):
    """Return curiosity-backlog entries, optionally filtered by status
    ('open' or 'addressed'). status=None returns all."""
    conn = get_connection()
    cursor = conn.cursor()
    if status:
        cursor.execute("""
            SELECT id, question, raised_in_session, status, raised_at, addressed_at, notes
            FROM curiosity_backlog WHERE status = ? ORDER BY raised_at DESC
        """, (status,))
    else:
        cursor.execute("""
            SELECT id, question, raised_in_session, status, raised_at, addressed_at, notes
            FROM curiosity_backlog ORDER BY raised_at DESC
        """)
    rows = cursor.fetchall()
    conn.close()
    keys = ["id", "question", "raised_in_session", "status", "raised_at", "addressed_at", "notes"]
    return [dict(zip(keys, row)) for row in rows]


if __name__ == "__main__":
    init_memory_database()
    print("\nEducational memory tables created:")
    print("- student_profile: static identity/context")
    print("- topic_mastery: current per-topic understanding snapshot")
    print("- misconceptions: tracked wrong mental models")
    print("- strengths: consolidated, demonstrated strengths")
    print("- learning_preferences: how the student likes to be taught")
    print("- coding_style_traits: descriptive coding habits/fingerprint")
    print("- mistake_patterns: recurring mechanical errors")
    print("- learning_journal: narrative session-by-session log")
    print("- projects: multi-session applied work")
    print("- assessments: deliberate quiz/challenge history")
    print("- motivational_signals: learning-relevant emotional patterns")
    print("- milestones: coarse-grained long-arc progress markers")
    print("- curiosity_backlog: deferred tangents and open questions")
