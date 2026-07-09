"""
obsidian_backend.py - Obsidian-vault-backed educational memory storage
for Tutor Gojo (skeleton / interface stub - no storage logic yet).

Purpose
-------
This module is a future alternative to memory_database.py. Where
memory_database.py persists Tutor Gojo's 13 educational memory
categories as SQLite rows, this module will eventually persist them as
Markdown notes (with YAML frontmatter) inside an Obsidian vault -
Tutor Gojo's long-term "second brain," supporting narrative journal
entries, project pages, topic pages, and concept-to-concept linking
that a relational table can't naturally express.

Interface contract
-------------------
This module exists to satisfy the exact backend interface memory_service
expects from `_backend` (see the "Backend Interface Contract" block
documented at the top of memory_service.py). Every public function that
exists in memory_database.py is mirrored here with the identical name,
parameters, and defaults, so that memory_service can eventually swap
its `_backend` reference from `memory_database` to this module with no
change to memory_service.py itself and no change to any caller above
it (api.py, chat_service.py, lesson_recommender.py, learning_summary.py).

Status
------
This file is intentionally inert right now. No vault is read from or
written to. Every function below raises NotImplementedError. This is
scaffolding only - it establishes the shape of the future backend so
that implementation can proceed function-by-function later without
redesigning the interface each time.

Do NOT wire this module into memory_service.py or api.py yet. Do NOT
treat any placeholder configuration below as functional - it exists to
show where vault configuration will eventually live, not to configure
anything today.
"""


import pathlib
import sqlite3
import traceback
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Vault configuration (placeholders only - not implemented)
# ---------------------------------------------------------------------------
#
# These are placeholders for future configuration this backend will need
# once it actually reads/writes the vault. None of them are wired up or
# used by any function below yet.

# Root filesystem path to the Obsidian vault. Will eventually come from
# app configuration (mirroring how database.py resolves its SQLite file
# path), not be hardcoded.
VAULT_PATH = None

# Permanent sub-locations within the vault for each broad memory
# grouping (see memory_service.py's Backend Interface Contract for the
# 13-category breakdown), rooted under a single "Tutor Memory" folder.
# Single-note categories point at a specific .md file; multi-note
# categories point at a folder that will hold one note per item.
#
# "assessments" points at the "Assessments" folder - a multi-note
# category, one note per assessment (see Category 10 below), matching
# memory_database.py's append-only `assessments` table.
_TUTOR_MEMORY_DIR = "Tutor Memory"

NOTES_LOCATIONS = {
    "student_profile": f"{_TUTOR_MEMORY_DIR}/Student Profile.md",
    "topic_mastery": f"{_TUTOR_MEMORY_DIR}/Topic Mastery.md",
    "misconceptions": f"{_TUTOR_MEMORY_DIR}/Misconceptions.md",
    "strengths": f"{_TUTOR_MEMORY_DIR}/Strengths.md",
    "learning_preferences": f"{_TUTOR_MEMORY_DIR}/Learning Preferences.md",
    "coding_style_traits": f"{_TUTOR_MEMORY_DIR}/Coding Style.md",
    "mistake_patterns": f"{_TUTOR_MEMORY_DIR}/Mistake Patterns.md",
    "learning_journal": f"{_TUTOR_MEMORY_DIR}/Journal",
    "projects": f"{_TUTOR_MEMORY_DIR}/Projects",
    "assessments": f"{_TUTOR_MEMORY_DIR}/Assessments",
    "motivational_signals": f"{_TUTOR_MEMORY_DIR}/Motivation.md",
    "milestones": f"{_TUTOR_MEMORY_DIR}/Milestones",
    "curiosity_backlog": f"{_TUTOR_MEMORY_DIR}/Curiosity",
}


# ---------------------------------------------------------------------------
# Vault helper utilities (placeholders only - not implemented)
# ---------------------------------------------------------------------------
#
# Future internal helpers this backend will need - reading/writing
# Markdown+YAML notes, resolving a category to its vault location,
# generating/parsing frontmatter, etc. None of these exist yet; named
# here only to mark where that machinery will live.

def _resolve_vault_path(relative_path=None):
    """Resolve a path inside the configured Obsidian vault.

    With no argument, resolves the vault root itself. With
    `relative_path` given, resolves that path relative to the vault
    root and rejects it if the resolved location would fall outside
    the vault (e.g. via `..` components) - directory traversal is not
    permitted. Ensures the returned path's containing folder exists,
    creating it if necessary. Always returns a pathlib.Path.
    """
    print(f"[DEBUG] _resolve_vault_path: VAULT_PATH = {VAULT_PATH!r}")

    if VAULT_PATH is None:
        raise RuntimeError("VAULT_PATH is not configured.")

    vault_root = pathlib.Path(VAULT_PATH).resolve()
    print(f"[DEBUG] _resolve_vault_path: vault_root (resolved) = {vault_root}")

    if relative_path is None:
        vault_root.mkdir(parents=True, exist_ok=True)
        print(f"[DEBUG] _resolve_vault_path: no relative_path given, returning vault_root = {vault_root}")
        return vault_root

    target = (vault_root / relative_path).resolve()
    print(f"[DEBUG] _resolve_vault_path: relative_path = {relative_path!r} -> target (resolved) = {target}")
    if target != vault_root and vault_root not in target.parents:
        raise ValueError(f"Path escapes the configured vault: {relative_path!r}")

    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"[DEBUG] _resolve_vault_path: returning target = {target}")
    return target


def _read_note(path):
    """Return the raw text contents of the note at `path`, resolved
    safely within the vault. Returns an empty string if the note does
    not exist yet. UTF-8. Performs no parsing of the content."""
    resolved = _resolve_vault_path(path)
    if not resolved.exists():
        return ""
    return resolved.read_text(encoding="utf-8")


def _write_note(path, text):
    """Write `text` to the note at `path`, resolved safely within the
    vault. Creates any missing parent folders. Overwrites existing
    content if the note already exists. UTF-8. Returns nothing."""
    resolved = _resolve_vault_path(path)
    print(f"[DEBUG] _write_note: exact filename being written = {resolved}")
    print(f"[DEBUG] _write_note: parent directory = {resolved.parent}")
    print(f"[DEBUG] _write_note: parent directory exists? {resolved.parent.exists()}")
    try:
        resolved.write_text(text, encoding="utf-8")
        print(f"[DEBUG] _write_note: write_text() succeeded for {resolved}")
    except Exception:
        print(f"[DEBUG] _write_note: write_text() raised an exception while writing {resolved}")
        print("[DEBUG] Full traceback for the write_text() failure above:")
        traceback.print_exc()
        raise


# ---------------------------------------------------------------------------
# Tiny YAML frontmatter helpers (Student Profile only)
# ---------------------------------------------------------------------------
#
# Hand-written, deliberately minimal: the Student Profile note only ever
# holds top-level string fields and lists of strings, so a full YAML
# parser/serializer (and the PyYAML dependency it would require) isn't
# needed. Not intended for reuse by other categories without review.

_STUDENT_PROFILE_FIELDS = (
    "goals",
    "background",
    "preferred_languages",
    "domain_interests",
    "time_horizon",
)

def _yaml_quote(value):
    """Double-quote a scalar string, escaping backslashes and quotes."""
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _yaml_unquote(raw):
    """Reverse of `_yaml_quote`. Tolerates unquoted scalars too."""
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        inner = raw[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\")
    return raw


def _student_profile_note_path():
    """Vault-relative path to the single Student Profile note."""
    return pathlib.Path(NOTES_LOCATIONS["student_profile"])


def _serialize_student_profile(data):
    """Render a student-profile dict (str/list-of-str values only) as a
    Markdown note with YAML frontmatter and an empty body."""
    lines = ["---"]
    for key in _STUDENT_PROFILE_FIELDS:
        value = data.get(key)
        if value is None:
            lines.append(f"{key}:")
        elif isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {_yaml_quote(item)}")
        else:
            lines.append(f"{key}: {_yaml_quote(value)}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _parse_student_profile(text):
    """Parse a Student Profile note's YAML frontmatter back into a dict
    keyed by `_STUDENT_PROFILE_FIELDS`. Returns None if `text` has no
    frontmatter block."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    data = {key: None for key in _STUDENT_PROFILE_FIELDS}
    current_key = None

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("  - ") or line.startswith("- "):
            item = _yaml_unquote(line.split("- ", 1)[1])
            if current_key is not None:
                if not isinstance(data.get(current_key), list):
                    data[current_key] = []
                data[current_key].append(item)
            continue
        if ":" in line:
            key, _, rest = line.partition(":")
            key = key.strip()
            rest = rest.strip()
            if key not in data:
                current_key = None
                continue
            current_key = key
            if rest == "":
                data[key] = None
            elif rest == "[]":
                data[key] = []
            else:
                data[key] = _yaml_unquote(rest)

    return data


# ---------------------------------------------------------------------------
# Tiny YAML frontmatter helpers (Topic Mastery)
# ---------------------------------------------------------------------------
#
# The Topic Mastery note stores one row per unique (topic, subtopic)
# pair - mirroring memory_database.py's UNIQUE(topic, subtopic)
# constraint, where the same topic can have several rows (one per
# subtopic). The frontmatter is a top-level YAML list of mappings, one
# mapping per row. Reuses the generic `_yaml_quote` / `_yaml_unquote`
# scalar escaping helpers defined above; adds its own serialize/parse
# pair because the shape (a list of mappings) differs from the flat
# Student Profile note.

_TOPIC_MASTERY_ROW_FIELDS = (
    "topic",
    "subtopic",
    "mastery_level",
    "trend",
    "last_exercised",
    "updated_at",
)


def _topic_mastery_note_path():
    """Vault-relative path to the single Topic Mastery note."""
    return pathlib.Path(NOTES_LOCATIONS["topic_mastery"])


def _serialize_topic_mastery(rows):
    """Render a list of topic-mastery row dicts (one per (topic,
    subtopic) pair) as YAML frontmatter - a top-level list of mappings
    - with an empty body."""
    lines = ["---"]
    for row in rows:
        prefix = "- "
        for field in _TOPIC_MASTERY_ROW_FIELDS:
            value = row.get(field)
            if value is None:
                lines.append(f"{prefix}{field}:")
            else:
                lines.append(f"{prefix}{field}: {_yaml_quote(value)}")
            prefix = "  "
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _parse_topic_mastery(text):
    """Parse a Topic Mastery note's YAML frontmatter back into a list
    of row dicts, one per (topic, subtopic) pair. Returns [] if there's
    no frontmatter block (e.g. the note doesn't exist yet)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []

    rows = []
    current_row = None

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip():
            continue

        if line.startswith("- "):
            current_row = {field: None for field in _TOPIC_MASTERY_ROW_FIELDS}
            rows.append(current_row)
            field_line = line[2:]
        elif line.startswith("  ") and current_row is not None:
            field_line = line.strip()
        else:
            continue

        key, _, rest = field_line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if key in _TOPIC_MASTERY_ROW_FIELDS:
            current_row[key] = None if rest == "" else _yaml_unquote(rest)

    return rows


# ---------------------------------------------------------------------------
# Schema / initialization
# ---------------------------------------------------------------------------

def init_memory_database():
    """Create the vault's permanent folder structure: the "Tutor Memory"
    root, plus one subdirectory for each multi-note category (Journal,
    Projects, Milestones, Motivation, Curiosity). Single-note categories
    (Student Profile, Topic Mastery, etc.) live directly in "Tutor
    Memory" as files and get no directory of their own here. Creates
    directories only; no Markdown notes are written. Safe to call
    multiple times - directories that already exist are left untouched."""
    vault_root = _resolve_vault_path()
    (vault_root / _TUTOR_MEMORY_DIR).mkdir(parents=True, exist_ok=True)

    for location in NOTES_LOCATIONS.values():
        if location is None:
            continue
        relative = pathlib.Path(location)
        if relative.suffix == ".md":
            continue  # single-note category; file lives directly in Tutor Memory/
        (vault_root / relative).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 1. Student Profile
# ---------------------------------------------------------------------------

def get_student_profile():
    """Return the student profile as a dict, or None if no profile note
    exists yet in the vault."""
    text = _read_note(_student_profile_note_path())
    if not text.strip():
        return None
    return _parse_student_profile(text)


def update_student_profile(goals=None, background=None, preferred_languages=None,
                            domain_interests=None, time_horizon=None):
    """Create or update the Student Profile note. Any parameter left as
    None leaves the existing stored value untouched; passing a value
    overwrites just that field. Creates the note (and its YAML
    frontmatter) if it doesn't exist yet."""
    existing = get_student_profile() or {key: None for key in _STUDENT_PROFILE_FIELDS}

    supplied = {
        "goals": goals,
        "background": background,
        "preferred_languages": preferred_languages,
        "domain_interests": domain_interests,
        "time_horizon": time_horizon,
    }
    for key, value in supplied.items():
        if value is not None:
            existing[key] = value

    _write_note(_student_profile_note_path(), _serialize_student_profile(existing))


# ---------------------------------------------------------------------------
# 2. Topic Mastery Map
# ---------------------------------------------------------------------------

def update_topic_mastery(topic, subtopic="", mastery_level=None, trend=None, mark_exercised=False):
    """Create or update the mastery snapshot for a (topic, subtopic)
    pair - mirrors SQLite's UNIQUE(topic, subtopic) upsert exactly.

    - If no row exists yet for this exact (topic, subtopic) pair, a new
      row is created: `mastery_level` defaults to "not_started" and
      `trend` defaults to "stable" when not supplied; `last_exercised`
      is set only if `mark_exercised` is True (otherwise left as None).
    - If a row already exists for this pair, `mastery_level` and
      `trend` are only overwritten when a non-None value is supplied -
      passing None preserves the existing value. `last_exercised` is
      refreshed only when `mark_exercised` is True, otherwise preserved
      unchanged. `updated_at` is always refreshed.
    """
    text = _read_note(_topic_mastery_note_path())
    rows = _parse_topic_mastery(text) if text.strip() else []

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    existing_row = next(
        (row for row in rows if row["topic"] == topic and row["subtopic"] == subtopic),
        None,
    )

    if existing_row is None:
        rows.append({
            "topic": topic,
            "subtopic": subtopic,
            "mastery_level": mastery_level if mastery_level is not None else "not_started",
            "trend": trend if trend is not None else "stable",
            "last_exercised": now if mark_exercised else None,
            "updated_at": now,
        })
    else:
        if mastery_level is not None:
            existing_row["mastery_level"] = mastery_level
        if trend is not None:
            existing_row["trend"] = trend
        if mark_exercised:
            existing_row["last_exercised"] = now
        existing_row["updated_at"] = now

    _write_note(_topic_mastery_note_path(), _serialize_topic_mastery(rows))


def get_topic_mastery(topic=None):
    """Return topic mastery rows - always a list[dict], never a single
    dict and never None, mirroring memory_database.py exactly.

    - `topic` falsy (None or ""): every row, ordered by topic ASC then
      subtopic ASC.
    - `topic` truthy: every row for that topic (there may be several,
      one per subtopic), ordered by subtopic ASC.
    - No matching rows: [].
    """
    text = _read_note(_topic_mastery_note_path())
    rows = _parse_topic_mastery(text) if text.strip() else []

    if topic:
        matching = [row for row in rows if row["topic"] == topic]
        matching.sort(key=lambda row: row["subtopic"])
        return [dict(row) for row in matching]

    all_rows = sorted(rows, key=lambda row: (row["topic"], row["subtopic"]))
    return [dict(row) for row in all_rows]


# ---------------------------------------------------------------------------
# 3. Misconception Ledger
# ---------------------------------------------------------------------------
#
# The Misconception Ledger note stores one row per unique `name` -
# mirroring memory_database.py's UNIQUE(name) constraint on the
# misconceptions table. The frontmatter is a top-level YAML list of
# mappings, one mapping per row - same shape as Topic Mastery, but
# keyed by `name` instead of (topic, subtopic), and with two integer
# fields (`occurrence_count`, `correction_attempts`) that are written
# unquoted rather than through `_yaml_quote`/`_yaml_unquote`, since
# those must round-trip as ints (matching sqlite3's INTEGER column
# type) rather than strings.

_MISCONCEPTION_ROW_FIELDS = (
    "name",
    "topic",
    "subtopic",
    "occurrence_count",
    "correction_attempts",
    "status",
    "first_observed",
    "last_observed",
    "notes",
)

_MISCONCEPTION_INT_FIELDS = ("occurrence_count", "correction_attempts")


def _misconceptions_note_path():
    """Vault-relative path to the single Misconception Ledger note."""
    return pathlib.Path(NOTES_LOCATIONS["misconceptions"])


def _serialize_misconceptions(rows):
    """Render a list of misconception row dicts (one per unique `name`)
    as YAML frontmatter - a top-level list of mappings - with an empty
    body. Integer fields are written unquoted; everything else is
    quoted via `_yaml_quote`."""
    lines = ["---"]
    for row in rows:
        prefix = "- "
        for field in _MISCONCEPTION_ROW_FIELDS:
            value = row.get(field)
            if value is None:
                lines.append(f"{prefix}{field}:")
            elif field in _MISCONCEPTION_INT_FIELDS:
                lines.append(f"{prefix}{field}: {value}")
            else:
                lines.append(f"{prefix}{field}: {_yaml_quote(value)}")
            prefix = "  "
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _parse_misconceptions(text):
    """Parse a Misconception Ledger note's YAML frontmatter back into a
    list of row dicts, one per unique `name`. Returns [] if there's no
    frontmatter block (e.g. the note doesn't exist yet). Integer fields
    are parsed back to int; everything else via `_yaml_unquote`."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []

    rows = []
    current_row = None

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip():
            continue

        if line.startswith("- "):
            current_row = {field: None for field in _MISCONCEPTION_ROW_FIELDS}
            rows.append(current_row)
            field_line = line[2:]
        elif line.startswith("  ") and current_row is not None:
            field_line = line.strip()
        else:
            continue

        key, _, rest = field_line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if key in _MISCONCEPTION_ROW_FIELDS:
            if rest == "":
                current_row[key] = None
            elif key in _MISCONCEPTION_INT_FIELDS:
                current_row[key] = int(rest)
            else:
                current_row[key] = _yaml_unquote(rest)

    return rows


def record_misconception(name, topic=None, subtopic=None, notes=None):
    """Log an observed misconception, or bump its occurrence count and
    last_observed timestamp if it's already tracked - mirrors SQLite's
    UNIQUE(name) upsert exactly.

    - If no row exists yet for this `name`, a new row is created:
      `topic`, `subtopic`, and `notes` are stored as given (including
      None); `occurrence_count` starts at 1, `correction_attempts` at
      0, `status` at "active", and `first_observed`/`last_observed`
      are both set to now.
    - If a row already exists for this `name`, `topic` and `subtopic`
      are left untouched (not overwritten, even if different values
      are passed), `occurrence_count` is incremented by 1,
      `last_observed` is refreshed, and `notes` is only overwritten
      when a non-None value is supplied.
    """
    text = _read_note(_misconceptions_note_path())
    rows = _parse_misconceptions(text) if text.strip() else []

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    existing_row = next((row for row in rows if row["name"] == name), None)

    if existing_row is None:
        rows.append({
            "name": name,
            "topic": topic,
            "subtopic": subtopic,
            "occurrence_count": 1,
            "correction_attempts": 0,
            "status": "active",
            "first_observed": now,
            "last_observed": now,
            "notes": notes,
        })
    else:
        existing_row["occurrence_count"] = (existing_row["occurrence_count"] or 0) + 1
        existing_row["last_observed"] = now
        if notes is not None:
            existing_row["notes"] = notes

    _write_note(_misconceptions_note_path(), _serialize_misconceptions(rows))


def mark_misconception_resolved(name):
    """Mark a misconception as resolved without deleting its history.
    A no-op if no row exists for `name` (mirrors the SQLite UPDATE ...
    WHERE name = ? matching zero rows)."""
    text = _read_note(_misconceptions_note_path())
    rows = _parse_misconceptions(text) if text.strip() else []

    for row in rows:
        if row["name"] == name:
            row["status"] = "resolved"
            break

    _write_note(_misconceptions_note_path(), _serialize_misconceptions(rows))


def get_misconceptions(status=None):
    """Return tracked misconceptions, optionally filtered by status
    ('active' or 'resolved'), ordered by last_observed DESC. Always a
    list[dict], never None; [] if there are no matching rows."""
    text = _read_note(_misconceptions_note_path())
    rows = _parse_misconceptions(text) if text.strip() else []

    if status:
        matching = [row for row in rows if row["status"] == status]
    else:
        matching = list(rows)

    matching.sort(key=lambda row: row["last_observed"], reverse=True)
    return [dict(row) for row in matching]


# ---------------------------------------------------------------------------
# 4. Consolidated Strengths
# ---------------------------------------------------------------------------
#
# The Strengths note stores one row per unique `name` - mirroring
# memory_database.py's UNIQUE(name) constraint on the strengths table.
# Same shape and conventions as the Misconception Ledger: a top-level
# YAML list of mappings, one integer field (`demonstration_count`)
# written/parsed unquoted, everything else via `_yaml_quote`/
# `_yaml_unquote`.

_STRENGTH_ROW_FIELDS = (
    "name",
    "topic",
    "subtopic",
    "demonstration_count",
    "first_confirmed",
    "last_confirmed",
    "notes",
)

_STRENGTH_INT_FIELDS = ("demonstration_count",)


def _strengths_note_path():
    """Vault-relative path to the single Strengths note."""
    return pathlib.Path(NOTES_LOCATIONS["strengths"])


def _serialize_strengths(rows):
    """Render a list of strength row dicts (one per unique `name`) as
    YAML frontmatter - a top-level list of mappings - with an empty
    body. Integer fields are written unquoted; everything else is
    quoted via `_yaml_quote`."""
    lines = ["---"]
    for row in rows:
        prefix = "- "
        for field in _STRENGTH_ROW_FIELDS:
            value = row.get(field)
            if value is None:
                lines.append(f"{prefix}{field}:")
            elif field in _STRENGTH_INT_FIELDS:
                lines.append(f"{prefix}{field}: {value}")
            else:
                lines.append(f"{prefix}{field}: {_yaml_quote(value)}")
            prefix = "  "
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _parse_strengths(text):
    """Parse a Strengths note's YAML frontmatter back into a list of
    row dicts, one per unique `name`. Returns [] if there's no
    frontmatter block (e.g. the note doesn't exist yet). Integer
    fields are parsed back to int; everything else via
    `_yaml_unquote`."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []

    rows = []
    current_row = None

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip():
            continue

        if line.startswith("- "):
            current_row = {field: None for field in _STRENGTH_ROW_FIELDS}
            rows.append(current_row)
            field_line = line[2:]
        elif line.startswith("  ") and current_row is not None:
            field_line = line.strip()
        else:
            continue

        key, _, rest = field_line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if key in _STRENGTH_ROW_FIELDS:
            if rest == "":
                current_row[key] = None
            elif key in _STRENGTH_INT_FIELDS:
                current_row[key] = int(rest)
            else:
                current_row[key] = _yaml_unquote(rest)

    return rows


def record_strength(name, topic=None, subtopic=None, notes=None):
    """Log a demonstration of a consolidated strength, or bump its
    demonstration count if already tracked - mirrors SQLite's
    UNIQUE(name) upsert exactly.

    - If no row exists yet for this `name`, a new row is created:
      `topic`, `subtopic`, and `notes` are stored as given (including
      None); `demonstration_count` starts at 1, and
      `first_confirmed`/`last_confirmed` are both set to now.
    - If a row already exists for this `name`, `topic` and `subtopic`
      are left untouched (not overwritten, even if different values
      are passed), `demonstration_count` is incremented by 1,
      `last_confirmed` is refreshed, and `notes` is only overwritten
      when a non-None value is supplied.
    """
    text = _read_note(_strengths_note_path())
    rows = _parse_strengths(text) if text.strip() else []

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    existing_row = next((row for row in rows if row["name"] == name), None)

    if existing_row is None:
        rows.append({
            "name": name,
            "topic": topic,
            "subtopic": subtopic,
            "demonstration_count": 1,
            "first_confirmed": now,
            "last_confirmed": now,
            "notes": notes,
        })
    else:
        existing_row["demonstration_count"] = (existing_row["demonstration_count"] or 0) + 1
        existing_row["last_confirmed"] = now
        if notes is not None:
            existing_row["notes"] = notes

    _write_note(_strengths_note_path(), _serialize_strengths(rows))


def get_strengths(topic=None):
    """Return consolidated strengths, optionally filtered to one
    topic, ordered by last_confirmed DESC. Always a list[dict], never
    None; [] if there are no matching rows."""
    text = _read_note(_strengths_note_path())
    rows = _parse_strengths(text) if text.strip() else []

    if topic:
        matching = [row for row in rows if row["topic"] == topic]
    else:
        matching = list(rows)

    matching.sort(key=lambda row: row["last_confirmed"], reverse=True)
    return [dict(row) for row in matching]


# ---------------------------------------------------------------------------
# 5. Learning Preferences
# ---------------------------------------------------------------------------
#
# The Learning Preferences note stores one row per unique
# `preference_key` - mirroring memory_database.py's UNIQUE
# (preference_key) constraint. Same shape/conventions as the previous
# categories: a top-level YAML list of mappings, one integer field
# (`evidence_count`) written/parsed unquoted, everything else via
# `_yaml_quote`/`_yaml_unquote`.

_LEARNING_PREFERENCE_ROW_FIELDS = (
    "preference_key",
    "preference_value",
    "evidence_count",
    "notes",
    "updated_at",
)

_LEARNING_PREFERENCE_INT_FIELDS = ("evidence_count",)


def _learning_preferences_note_path():
    """Vault-relative path to the single Learning Preferences note."""
    return pathlib.Path(NOTES_LOCATIONS["learning_preferences"])


def _serialize_learning_preferences(rows):
    """Render a list of learning-preference row dicts (one per unique
    `preference_key`) as YAML frontmatter - a top-level list of
    mappings - with an empty body. Integer fields are written
    unquoted; everything else is quoted via `_yaml_quote`."""
    lines = ["---"]
    for row in rows:
        prefix = "- "
        for field in _LEARNING_PREFERENCE_ROW_FIELDS:
            value = row.get(field)
            if value is None:
                lines.append(f"{prefix}{field}:")
            elif field in _LEARNING_PREFERENCE_INT_FIELDS:
                lines.append(f"{prefix}{field}: {value}")
            else:
                lines.append(f"{prefix}{field}: {_yaml_quote(value)}")
            prefix = "  "
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _parse_learning_preferences(text):
    """Parse a Learning Preferences note's YAML frontmatter back into a
    list of row dicts, one per unique `preference_key`. Returns [] if
    there's no frontmatter block (e.g. the note doesn't exist yet).
    Integer fields are parsed back to int; everything else via
    `_yaml_unquote`."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []

    rows = []
    current_row = None

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip():
            continue

        if line.startswith("- "):
            current_row = {field: None for field in _LEARNING_PREFERENCE_ROW_FIELDS}
            rows.append(current_row)
            field_line = line[2:]
        elif line.startswith("  ") and current_row is not None:
            field_line = line.strip()
        else:
            continue

        key, _, rest = field_line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if key in _LEARNING_PREFERENCE_ROW_FIELDS:
            if rest == "":
                current_row[key] = None
            elif key in _LEARNING_PREFERENCE_INT_FIELDS:
                current_row[key] = int(rest)
            else:
                current_row[key] = _yaml_unquote(rest)

    return rows


def set_learning_preference(preference_key, preference_value, notes=None):
    """Create or update a single learning preference - mirrors
    SQLite's UNIQUE(preference_key) upsert exactly.

    - If no row exists yet for this `preference_key`, a new row is
      created: `preference_value` and `notes` are stored as given
      (including None for notes); `evidence_count` starts at 1, and
      `updated_at` is set to now.
    - If a row already exists for this `preference_key`,
      `preference_value` is always overwritten with the new value
      (unlike Strengths/Misconceptions, there is no COALESCE here -
      this mirrors memory_database.py's `preference_value =
      excluded.preference_value`), `evidence_count` is incremented by
      1, `notes` is only overwritten when a non-None value is
      supplied, and `updated_at` is always refreshed.
    """
    text = _read_note(_learning_preferences_note_path())
    rows = _parse_learning_preferences(text) if text.strip() else []

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    existing_row = next(
        (row for row in rows if row["preference_key"] == preference_key), None
    )

    if existing_row is None:
        rows.append({
            "preference_key": preference_key,
            "preference_value": preference_value,
            "evidence_count": 1,
            "notes": notes,
            "updated_at": now,
        })
    else:
        existing_row["preference_value"] = preference_value
        existing_row["evidence_count"] = (existing_row["evidence_count"] or 0) + 1
        if notes is not None:
            existing_row["notes"] = notes
        existing_row["updated_at"] = now

    _write_note(_learning_preferences_note_path(), _serialize_learning_preferences(rows))


def get_learning_preferences():
    """Return all tracked learning preferences, ordered by
    preference_key ASC. Always a list[dict], never None; [] if none
    are tracked yet."""
    text = _read_note(_learning_preferences_note_path())
    rows = _parse_learning_preferences(text) if text.strip() else []

    all_rows = sorted(rows, key=lambda row: row["preference_key"])
    return [dict(row) for row in all_rows]


# ---------------------------------------------------------------------------
# 6. Coding Style Fingerprint
# ---------------------------------------------------------------------------
#
# The Coding Style note stores one row per unique `trait_key` -
# mirroring memory_database.py's UNIQUE(trait_key) constraint. Same
# shape/conventions as the previous categories: a top-level YAML list
# of mappings, one integer field (`observed_count`) written/parsed
# unquoted, everything else via `_yaml_quote`/`_yaml_unquote`.

_CODING_STYLE_ROW_FIELDS = (
    "trait_key",
    "trait_value",
    "observed_count",
    "first_observed",
    "last_observed",
    "notes",
)

_CODING_STYLE_INT_FIELDS = ("observed_count",)


def _coding_style_traits_note_path():
    """Vault-relative path to the single Coding Style note."""
    return pathlib.Path(NOTES_LOCATIONS["coding_style_traits"])


def _serialize_coding_style_traits(rows):
    """Render a list of coding-style-trait row dicts (one per unique
    `trait_key`) as YAML frontmatter - a top-level list of mappings -
    with an empty body. Integer fields are written unquoted;
    everything else is quoted via `_yaml_quote`."""
    lines = ["---"]
    for row in rows:
        prefix = "- "
        for field in _CODING_STYLE_ROW_FIELDS:
            value = row.get(field)
            if value is None:
                lines.append(f"{prefix}{field}:")
            elif field in _CODING_STYLE_INT_FIELDS:
                lines.append(f"{prefix}{field}: {value}")
            else:
                lines.append(f"{prefix}{field}: {_yaml_quote(value)}")
            prefix = "  "
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _parse_coding_style_traits(text):
    """Parse a Coding Style note's YAML frontmatter back into a list
    of row dicts, one per unique `trait_key`. Returns [] if there's no
    frontmatter block (e.g. the note doesn't exist yet). Integer
    fields are parsed back to int; everything else via
    `_yaml_unquote`."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []

    rows = []
    current_row = None

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip():
            continue

        if line.startswith("- "):
            current_row = {field: None for field in _CODING_STYLE_ROW_FIELDS}
            rows.append(current_row)
            field_line = line[2:]
        elif line.startswith("  ") and current_row is not None:
            field_line = line.strip()
        else:
            continue

        key, _, rest = field_line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if key in _CODING_STYLE_ROW_FIELDS:
            if rest == "":
                current_row[key] = None
            elif key in _CODING_STYLE_INT_FIELDS:
                current_row[key] = int(rest)
            else:
                current_row[key] = _yaml_unquote(rest)

    return rows


def set_coding_style_trait(trait_key, trait_value, notes=None):
    """Create or update a single coding style trait - mirrors
    SQLite's UNIQUE(trait_key) upsert exactly.

    - If no row exists yet for this `trait_key`, a new row is created:
      `trait_value` and `notes` are stored as given (including None
      for notes); `observed_count` starts at 1, and
      `first_observed`/`last_observed` are both set to now.
    - If a row already exists for this `trait_key`, `trait_value` is
      always overwritten with the new value (no COALESCE - mirrors
      memory_database.py's `trait_value = excluded.trait_value`),
      `observed_count` is incremented by 1, `last_observed` is
      refreshed, `first_observed` is left untouched, and `notes` is
      only overwritten when a non-None value is supplied.
    """
    text = _read_note(_coding_style_traits_note_path())
    rows = _parse_coding_style_traits(text) if text.strip() else []

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    existing_row = next(
        (row for row in rows if row["trait_key"] == trait_key), None
    )

    if existing_row is None:
        rows.append({
            "trait_key": trait_key,
            "trait_value": trait_value,
            "observed_count": 1,
            "first_observed": now,
            "last_observed": now,
            "notes": notes,
        })
    else:
        existing_row["trait_value"] = trait_value
        existing_row["observed_count"] = (existing_row["observed_count"] or 0) + 1
        existing_row["last_observed"] = now
        if notes is not None:
            existing_row["notes"] = notes

    _write_note(_coding_style_traits_note_path(), _serialize_coding_style_traits(rows))


def get_coding_style_traits():
    """Return all tracked coding style traits, ordered by trait_key
    ASC. Always a list[dict], never None; [] if none are tracked
    yet."""
    text = _read_note(_coding_style_traits_note_path())
    rows = _parse_coding_style_traits(text) if text.strip() else []

    all_rows = sorted(rows, key=lambda row: row["trait_key"])
    return [dict(row) for row in all_rows]


# ---------------------------------------------------------------------------
# 7. Recurring Mistake Patterns
# ---------------------------------------------------------------------------
#
# The Mistake Patterns note stores one row per unique `description` -
# mirroring memory_database.py's UNIQUE(description) constraint. Same
# shape/conventions as the previous categories: a top-level YAML list
# of mappings, one integer field (`occurrence_count`) written/parsed
# unquoted, everything else via `_yaml_quote`/`_yaml_unquote`.

_MISTAKE_PATTERN_ROW_FIELDS = (
    "description",
    "topic",
    "occurrence_count",
    "trend",
    "first_observed",
    "last_observed",
    "notes",
)

_MISTAKE_PATTERN_INT_FIELDS = ("occurrence_count",)


def _mistake_patterns_note_path():
    """Vault-relative path to the single Mistake Patterns note."""
    return pathlib.Path(NOTES_LOCATIONS["mistake_patterns"])


def _serialize_mistake_patterns(rows):
    """Render a list of mistake-pattern row dicts (one per unique
    `description`) as YAML frontmatter - a top-level list of mappings
    - with an empty body. Integer fields are written unquoted;
    everything else is quoted via `_yaml_quote`."""
    lines = ["---"]
    for row in rows:
        prefix = "- "
        for field in _MISTAKE_PATTERN_ROW_FIELDS:
            value = row.get(field)
            if value is None:
                lines.append(f"{prefix}{field}:")
            elif field in _MISTAKE_PATTERN_INT_FIELDS:
                lines.append(f"{prefix}{field}: {value}")
            else:
                lines.append(f"{prefix}{field}: {_yaml_quote(value)}")
            prefix = "  "
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _parse_mistake_patterns(text):
    """Parse a Mistake Patterns note's YAML frontmatter back into a
    list of row dicts, one per unique `description`. Returns [] if
    there's no frontmatter block (e.g. the note doesn't exist yet).
    Integer fields are parsed back to int; everything else via
    `_yaml_unquote`."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []

    rows = []
    current_row = None

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip():
            continue

        if line.startswith("- "):
            current_row = {field: None for field in _MISTAKE_PATTERN_ROW_FIELDS}
            rows.append(current_row)
            field_line = line[2:]
        elif line.startswith("  ") and current_row is not None:
            field_line = line.strip()
        else:
            continue

        key, _, rest = field_line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if key in _MISTAKE_PATTERN_ROW_FIELDS:
            if rest == "":
                current_row[key] = None
            elif key in _MISTAKE_PATTERN_INT_FIELDS:
                current_row[key] = int(rest)
            else:
                current_row[key] = _yaml_unquote(rest)

    return rows


def record_mistake_pattern(description, topic=None, trend=None, notes=None):
    """Log an occurrence of a recurring mechanical mistake, or bump its
    occurrence count if already tracked - mirrors SQLite's
    UNIQUE(description) upsert exactly.

    - If no row exists yet for this `description`, a new row is
      created: `topic` and `notes` are stored as given (including
      None); `trend` defaults to "unknown" when not supplied;
      `occurrence_count` starts at 1, and
      `first_observed`/`last_observed` are both set to now.
    - If a row already exists for this `description`, `topic` is left
      untouched (not overwritten, even if a different value is
      passed), `occurrence_count` is incremented by 1, `trend` is only
      overwritten when a non-None value is supplied (passing None
      preserves the existing trend rather than resetting it to
      "unknown"), `last_observed` is refreshed, and `notes` is only
      overwritten when a non-None value is supplied.
    """
    text = _read_note(_mistake_patterns_note_path())
    rows = _parse_mistake_patterns(text) if text.strip() else []

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    existing_row = next(
        (row for row in rows if row["description"] == description), None
    )

    if existing_row is None:
        rows.append({
            "description": description,
            "topic": topic,
            "occurrence_count": 1,
            "trend": trend if trend is not None else "unknown",
            "first_observed": now,
            "last_observed": now,
            "notes": notes,
        })
    else:
        existing_row["occurrence_count"] = (existing_row["occurrence_count"] or 0) + 1
        if trend is not None:
            existing_row["trend"] = trend
        existing_row["last_observed"] = now
        if notes is not None:
            existing_row["notes"] = notes

    _write_note(_mistake_patterns_note_path(), _serialize_mistake_patterns(rows))


def get_mistake_patterns(topic=None):
    """Return recurring mistake patterns, optionally filtered to one
    topic, ordered by last_observed DESC. Always a list[dict], never
    None; [] if there are no matching rows."""
    text = _read_note(_mistake_patterns_note_path())
    rows = _parse_mistake_patterns(text) if text.strip() else []

    if topic:
        matching = [row for row in rows if row["topic"] == topic]
    else:
        matching = list(rows)

    matching.sort(key=lambda row: row["last_observed"], reverse=True)
    return [dict(row) for row in matching]


# ---------------------------------------------------------------------------
# 8. Learning Journal
# ---------------------------------------------------------------------------
#
# Unlike the categories above, Learning Journal is a *multi-note*
# category (NOTES_LOCATIONS["learning_journal"] points at the "Journal"
# folder, not a single .md file) - one note per journal entry, matching
# memory_database.py's append-only table (no upsert, no update/delete
# function exists for journal entries). Each note holds a flat YAML
# frontmatter mapping (like the Student Profile note), not a list of
# mappings, since one note = one row here.
#
# Entry notes are named with a zero-padded sequential index assigned
# at insertion time (e.g. "000001.md", "000002.md", ...), so sorting
# by filename ascending reproduces insertion order (oldest first).
# This lets get_journal_entries() reconstruct the same relative
# ordering for same-timestamp entries that a stable sort over
# memory_database.py's insertion-ordered table scan would produce.

_JOURNAL_ENTRY_FIELDS = (
    "session_id",
    "entry_date",
    "summary",
    "topics_covered",
    "is_turning_point",
    "unfinished_business",
)

# Stored/parsed as int (0 or 1), matching sqlite3's raw INTEGER column
# value - memory_database.py never coerces this to a Python bool.
_JOURNAL_INT_FIELDS = ("is_turning_point",)


def _journal_quote(value):
    """Quote a scalar for journal frontmatter, escaping backslashes,
    double quotes, and embedded newlines - in that order, in a single
    left-to-right pass - so free-form multiline text (summary,
    unfinished_business, topics_covered) always round-trips exactly
    while still occupying exactly one physical line in the note.

    Journal-local: intentionally separate from `_yaml_quote` (used by
    the other categories) rather than extending it, since those
    categories have no multiline requirement and must not change."""
    escaped = []
    for ch in str(value):
        if ch == "\\":
            escaped.append("\\\\")
        elif ch == '"':
            escaped.append('\\"')
        elif ch == "\n":
            escaped.append("\\n")
        else:
            escaped.append(ch)
    return f'"{"".join(escaped)}"'


def _journal_unquote(raw):
    """Reverse of `_journal_quote`. A single left-to-right scan (not a
    sequence of blind global replaces) so that escaped backslashes,
    escaped quotes, and escaped newlines can't be misinterpreted when
    they're adjacent to one another. Tolerates unquoted scalars too,
    for backward compatibility with notes written before this fix."""
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        inner = raw[1:-1]
        result = []
        i = 0
        n = len(inner)
        while i < n:
            ch = inner[i]
            if ch == "\\" and i + 1 < n and inner[i + 1] in ('n', '"', '\\'):
                nxt = inner[i + 1]
                result.append("\n" if nxt == "n" else nxt)
                i += 2
            else:
                result.append(ch)
                i += 1
        return "".join(result)
    return raw


def _journal_folder_path():
    """Vault-relative path to the Learning Journal folder."""
    return pathlib.Path(NOTES_LOCATIONS["learning_journal"])


def _journal_entry_note_paths():
    """Return vault-relative paths to all Learning Journal entry
    notes, sorted by filename ascending - i.e. insertion order, oldest
    first (see module note above)."""
    vault_root = _resolve_vault_path()
    folder = vault_root / _journal_folder_path()
    folder.mkdir(parents=True, exist_ok=True)
    return sorted(p.relative_to(vault_root) for p in folder.glob("*.md"))


def _serialize_journal_entry(row):
    """Render a single journal-entry row dict as YAML frontmatter - a
    flat top-level mapping, one note per entry - with an empty body."""
    lines = ["---"]
    for field in _JOURNAL_ENTRY_FIELDS:
        value = row.get(field)
        if value is None:
            lines.append(f"{field}:")
        elif field in _JOURNAL_INT_FIELDS:
            lines.append(f"{field}: {value}")
        else:
            lines.append(f"{field}: {_journal_quote(value)}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _parse_journal_entry(text):
    """Parse a single journal-entry note's YAML frontmatter back into
    a flat dict. Returns None if there's no frontmatter block."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    data = {field: None for field in _JOURNAL_ENTRY_FIELDS}

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip():
            continue
        if ":" not in line:
            continue

        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if key in _JOURNAL_ENTRY_FIELDS:
            if rest == "":
                data[key] = None
            elif key in _JOURNAL_INT_FIELDS:
                data[key] = int(rest)
            else:
                data[key] = _journal_unquote(rest)

    return data


def add_journal_entry(summary, session_id=None, topics_covered=None,
                       is_turning_point=False, unfinished_business=None):
    """Append a narrative entry to the learning journal. topics_covered
    should be pre-serialized to a JSON string by the caller, or None -
    matches memory_database.py exactly. Append-only: this always
    creates a new entry note; existing entries are never modified.
    `is_turning_point` is stored (and later returned) as an int, 1 or
    0, not a Python bool."""
    next_index = len(_journal_entry_note_paths()) + 1
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    row = {
        "session_id": session_id,
        "entry_date": now,
        "summary": summary,
        "topics_covered": topics_covered,
        "is_turning_point": 1 if is_turning_point else 0,
        "unfinished_business": unfinished_business,
    }

    entry_path = _journal_folder_path() / f"{next_index:06d}.md"
    _write_note(entry_path, _serialize_journal_entry(row))


def get_journal_entries(limit=50):
    """Return the most recent journal entries, newest first, limited
    to `limit` entries. A negative `limit` returns every entry
    (verified: SQLite's `LIMIT ?` bound to a negative integer applies
    no limit). `limit=None` raises sqlite3.IntegrityError - verified
    against memory_database.py, binding NULL to SQLite's `LIMIT ?`
    parameter does NOT mean "no limit"; it raises
    `sqlite3.IntegrityError: datatype mismatch`, i.e. this is a caller
    error, not a valid "unlimited" request. Otherwise always a
    list[dict], never None; [] if the journal is empty."""
    if limit is None:
        raise sqlite3.IntegrityError("datatype mismatch")

    entries = []
    for path in _journal_entry_note_paths():
        text = _read_note(path)
        if not text.strip():
            continue
        entry = _parse_journal_entry(text)
        if entry is not None:
            entries.append(entry)

    entries.sort(key=lambda row: row["entry_date"], reverse=True)

    if limit < 0:
        return entries
    return entries[:limit]


# ---------------------------------------------------------------------------
# 9. Projects & Applied Work
# ---------------------------------------------------------------------------
#
# Multi-note category (NOTES_LOCATIONS["projects"] points at the
# "Projects" folder, not a single .md file) - one note per project,
# matching memory_database.py's `projects` table. Unlike Learning
# Journal (append-only, no id ever handed back to a caller), this
# category supports in-place UPDATE by id, so - unlike Journal entries
# - the numeric id is itself part of the stored/returned data, not
# just a filename convenience.
#
# Notes are named with a zero-padded sequential index assigned at
# creation time (e.g. "000001.md", "000002.md", ...), matching
# AUTOINCREMENT id assignment order. update_project() rewrites a
# note's contents in place - the file is never renamed - so a note's
# filename/id stays a stable stand-in for SQLite's rowid, which is
# also never reassigned by UPDATE. That stability is what lets
# get_projects() reproduce SQLite's tie-break behavior for equal
# updated_at values (see Learning Journal's tie-break note above -
# same reasoning applies here).

_PROJECT_FIELDS = (
    "id",
    "name",
    "description",
    "status",
    "goals",
    "design_decisions",
    "next_steps",
    "started_at",
    "updated_at",
)

# Stored/parsed as int, matching sqlite3's raw INTEGER `id` column -
# memory_database.py never coerces this to anything else.
_PROJECT_INT_FIELDS = ("id",)


def _project_quote(value):
    """Quote a scalar for a project note, escaping backslashes, double
    quotes, and embedded newlines - in that order, in a single
    left-to-right pass - so free-form multiline text (description,
    goals, design_decisions, next_steps) always round-trips exactly
    while still occupying exactly one physical line in the note.

    Deliberately a separate function from `_journal_quote` (same
    logic, different category) rather than a shared import, matching
    this codebase's existing pattern of one small serialize/parse pair
    per category rather than cross-category reuse."""
    escaped = []
    for ch in str(value):
        if ch == "\\":
            escaped.append("\\\\")
        elif ch == '"':
            escaped.append('\\"')
        elif ch == "\n":
            escaped.append("\\n")
        else:
            escaped.append(ch)
    return f'"{"".join(escaped)}"'


def _project_unquote(raw):
    """Reverse of `_project_quote`. A single left-to-right scan (not a
    sequence of blind global replaces) so escaped backslashes, escaped
    quotes, and escaped newlines can't be misinterpreted when they're
    adjacent to one another. Tolerates unquoted scalars too."""
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        inner = raw[1:-1]
        result = []
        i = 0
        n = len(inner)
        while i < n:
            ch = inner[i]
            if ch == "\\" and i + 1 < n and inner[i + 1] in ('n', '"', '\\'):
                nxt = inner[i + 1]
                result.append("\n" if nxt == "n" else nxt)
                i += 2
            else:
                result.append(ch)
                i += 1
        return "".join(result)
    return raw


def _project_folder_path():
    """Vault-relative path to the Projects folder."""
    return pathlib.Path(NOTES_LOCATIONS["projects"])


def _project_note_paths():
    """Return vault-relative paths to all project notes, sorted by
    filename ascending - i.e. creation order, oldest first (see
    module note above)."""
    vault_root = _resolve_vault_path()
    folder = vault_root / _project_folder_path()
    folder.mkdir(parents=True, exist_ok=True)
    return sorted(p.relative_to(vault_root) for p in folder.glob("*.md"))


def _serialize_project(row):
    """Render a single project row dict as YAML frontmatter - a flat
    top-level mapping, one note per project - with an empty body."""
    lines = ["---"]
    for field in _PROJECT_FIELDS:
        value = row.get(field)
        if value is None:
            lines.append(f"{field}:")
        elif field in _PROJECT_INT_FIELDS:
            lines.append(f"{field}: {value}")
        else:
            lines.append(f"{field}: {_project_quote(value)}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _parse_project(text):
    """Parse a single project note's YAML frontmatter back into a flat
    dict. Returns None if there's no frontmatter block."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    data = {field: None for field in _PROJECT_FIELDS}

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip():
            continue
        if ":" not in line:
            continue

        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if key in _PROJECT_FIELDS:
            if rest == "":
                data[key] = None
            elif key in _PROJECT_INT_FIELDS:
                data[key] = int(rest)
            else:
                data[key] = _project_unquote(rest)

    return data


def create_project(name, description=None, goals=None):
    """Create a new project and return its id. `name` is NOT NULL in
    the SQLite schema - passing None here reproduces the same
    sqlite3.IntegrityError memory_database.py would raise, rather than
    silently writing an invalid note."""
    if name is None:
        raise sqlite3.IntegrityError("NOT NULL constraint failed: projects.name")

    next_id = len(_project_note_paths()) + 1
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    row = {
        "id": next_id,
        "name": name,
        "description": description,
        "status": "planning",
        "goals": goals,
        "design_decisions": None,
        "next_steps": None,
        "started_at": now,
        "updated_at": now,
    }

    note_path = _project_folder_path() / f"{next_id:06d}.md"
    _write_note(note_path, _serialize_project(row))
    return next_id


def update_project(project_id, status=None, design_decisions=None, next_steps=None):
    """Update mutable fields on an existing project. Only non-None
    fields are overwritten. `updated_at` always advances, even if
    every field argument is None - matches memory_database.py, whose
    UPDATE always sets updated_at = CURRENT_TIMESTAMP regardless of
    whether any other column actually changed. If `project_id` doesn't
    match any project, this is a silent no-op - matches SQLite's
    `UPDATE ... WHERE id = ?` affecting zero rows without error."""
    for path in _project_note_paths():
        text = _read_note(path)
        if not text.strip():
            continue
        row = _parse_project(text)
        if row is None or row.get("id") != project_id:
            continue

        if status is not None:
            row["status"] = status
        if design_decisions is not None:
            row["design_decisions"] = design_decisions
        if next_steps is not None:
            row["next_steps"] = next_steps
        row["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        _write_note(path, _serialize_project(row))
        return


def get_projects(status=None):
    """Return projects, optionally filtered by status, newest-updated
    first. Always a list[dict], never None; [] if there are no
    matching projects. `status` uses truthiness, not an is-None check
    - matching memory_database.py's `if status:` - so status="" is
    treated the same as status=None (no filter applied), not as a
    literal filter for an empty-string status value."""
    projects = []
    for path in _project_note_paths():
        text = _read_note(path)
        if not text.strip():
            continue
        row = _parse_project(text)
        if row is not None:
            projects.append(row)

    if status:
        projects = [p for p in projects if p["status"] == status]

    projects.sort(key=lambda p: p["updated_at"], reverse=True)
    return projects


# ---------------------------------------------------------------------------
# 10. Assessment History
# ---------------------------------------------------------------------------
#
# Multi-note category (NOTES_LOCATIONS["assessments"] points at the
# "Assessments" folder, not a single .md file) - one note per
# assessment, matching memory_database.py's `assessments` table.
# Append-only, like Learning Journal: memory_database.py has no
# update/delete function for assessments, so no note is ever rewritten
# after creation, and (as with Journal entries, and unlike Projects)
# the numeric id is never handed back to a caller or included in the
# returned rows - it's purely a filename convenience for reproducing
# insertion order.
#
# Notes are named with a zero-padded sequential index assigned at
# insertion time (e.g. "000001.md", "000002.md", ...), so sorting by
# filename ascending reproduces insertion order (oldest first) - same
# tie-break reasoning as Learning Journal for same-timestamp entries.

_ASSESSMENT_FIELDS = (
    "session_id",
    "topic",
    "subtopic",
    "assessment_type",
    "question",
    "student_answer",
    "expected_answer",
    "is_correct",
    "context_notes",
    "assessed_at",
)

# Stored/parsed as int (0 or 1) when not None, matching sqlite3's raw
# INTEGER column value - memory_database.py never coerces this to a
# Python bool. record_assessment resolves is_correct to None/0/1
# before it ever reaches serialization (see below), so the INT-field
# branch in _serialize_assessment only ever writes an int literal or
# (via the `value is None` check above it) an empty NULL marker.
_ASSESSMENT_INT_FIELDS = ("is_correct",)


def _assessment_quote(value):
    """Quote a scalar for an assessment note, escaping backslashes,
    double quotes, and embedded newlines - in that order, in a single
    left-to-right pass - so free-form multiline text (question,
    student_answer, expected_answer, context_notes) always round-trips
    exactly while still occupying exactly one physical line in the
    note.

    Deliberately a separate function from `_journal_quote` /
    `_project_quote` (same logic, different category), matching this
    codebase's existing pattern of one small serialize/parse pair per
    category rather than cross-category reuse."""
    escaped = []
    for ch in str(value):
        if ch == "\\":
            escaped.append("\\\\")
        elif ch == '"':
            escaped.append('\\"')
        elif ch == "\n":
            escaped.append("\\n")
        else:
            escaped.append(ch)
    return f'"{"".join(escaped)}"'


def _assessment_unquote(raw):
    """Reverse of `_assessment_quote`. A single left-to-right scan
    (not a sequence of blind global replaces) so escaped backslashes,
    escaped quotes, and escaped newlines can't be misinterpreted when
    they're adjacent to one another. Tolerates unquoted scalars too."""
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        inner = raw[1:-1]
        result = []
        i = 0
        n = len(inner)
        while i < n:
            ch = inner[i]
            if ch == "\\" and i + 1 < n and inner[i + 1] in ('n', '"', '\\'):
                nxt = inner[i + 1]
                result.append("\n" if nxt == "n" else nxt)
                i += 2
            else:
                result.append(ch)
                i += 1
        return "".join(result)
    return raw


def _assessments_folder_path():
    """Vault-relative path to the Assessments folder."""
    return pathlib.Path(NOTES_LOCATIONS["assessments"])


def _assessment_note_paths():
    """Return vault-relative paths to all assessment notes, sorted by
    filename ascending - i.e. insertion order, oldest first (see
    module note above)."""
    vault_root = _resolve_vault_path()
    folder = vault_root / _assessments_folder_path()
    folder.mkdir(parents=True, exist_ok=True)
    return sorted(p.relative_to(vault_root) for p in folder.glob("*.md"))


def _serialize_assessment(row):
    """Render a single assessment row dict as YAML frontmatter - a
    flat top-level mapping, one note per assessment - with an empty
    body."""
    lines = ["---"]
    for field in _ASSESSMENT_FIELDS:
        value = row.get(field)
        if value is None:
            lines.append(f"{field}:")
        elif field in _ASSESSMENT_INT_FIELDS:
            lines.append(f"{field}: {value}")
        else:
            lines.append(f"{field}: {_assessment_quote(value)}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _parse_assessment(text):
    """Parse a single assessment note's YAML frontmatter back into a
    flat dict. Returns None if there's no frontmatter block."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    data = {field: None for field in _ASSESSMENT_FIELDS}

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip():
            continue
        if ":" not in line:
            continue

        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if key in _ASSESSMENT_FIELDS:
            if rest == "":
                data[key] = None
            elif key in _ASSESSMENT_INT_FIELDS:
                data[key] = int(rest)
            else:
                data[key] = _assessment_unquote(rest)

    return data


def record_assessment(question, session_id=None, topic=None, subtopic=None,
                       assessment_type="quiz", student_answer=None,
                       expected_answer=None, is_correct=None, context_notes=None):
    """Log a single deliberate assessment (quiz/challenge/check).
    `question` is NOT NULL in the SQLite schema - passing None here
    reproduces the same sqlite3.IntegrityError memory_database.py
    would raise, rather than silently writing an invalid note.
    `is_correct` is resolved to None/1/0 up front (None stays None;
    any other value is coerced to 1 or 0 by truthiness) and stored
    that way - matches memory_database.py exactly. Append-only, like
    Learning Journal: always creates a new note; no id is returned."""
    if question is None:
        raise sqlite3.IntegrityError("NOT NULL constraint failed: assessments.question")

    next_index = len(_assessment_note_paths()) + 1
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    row = {
        "session_id": session_id,
        "topic": topic,
        "subtopic": subtopic,
        "assessment_type": assessment_type,
        "question": question,
        "student_answer": student_answer,
        "expected_answer": expected_answer,
        "is_correct": None if is_correct is None else (1 if is_correct else 0),
        "context_notes": context_notes,
        "assessed_at": now,
    }

    note_path = _assessments_folder_path() / f"{next_index:06d}.md"
    _write_note(note_path, _serialize_assessment(row))


def get_assessment_history(topic=None, limit=50):
    """Return recent assessments, newest first, optionally filtered to
    one topic. `topic` uses truthiness, not an is-None check - matching
    memory_database.py's `if topic:` - so topic="" is treated the same
    as topic=None (no filter applied), not as a literal filter for an
    empty-string topic value. A negative `limit` returns every
    matching assessment (verified: SQLite's `LIMIT ?` bound to a
    negative integer applies no limit). `limit=None` raises
    sqlite3.IntegrityError - empirically verified directly against
    sqlite3 (not inferred): binding NULL to SQLite's `LIMIT ?`
    parameter raises `sqlite3.IntegrityError: datatype mismatch`, not
    "no limit" and not TypeError. Otherwise always a list[dict], never
    None; [] if there's no matching history."""
    if limit is None:
        raise sqlite3.IntegrityError("datatype mismatch")

    entries = []
    for path in _assessment_note_paths():
        text = _read_note(path)
        if not text.strip():
            continue
        entry = _parse_assessment(text)
        if entry is not None:
            entries.append(entry)

    if topic:
        entries = [e for e in entries if e["topic"] == topic]

    entries.sort(key=lambda row: row["assessed_at"], reverse=True)

    if limit < 0:
        return entries
    return entries[:limit]


# ---------------------------------------------------------------------------
# 11. Motivational & Engagement Signals
# ---------------------------------------------------------------------------
#
# The Motivational Signals note stores one row per unique
# `pattern_description` - mirroring memory_database.py's
# UNIQUE(pattern_description) constraint on the motivational_signals
# table. Same shape and conventions as the Misconception Ledger and
# Consolidated Strengths: a top-level YAML list of mappings, one
# integer field (`occurrence_count`) written/parsed unquoted,
# everything else via `_yaml_quote`/`_yaml_unquote`.

_MOTIVATIONAL_SIGNAL_ROW_FIELDS = (
    "pattern_description",
    "signal_type",
    "topic",
    "occurrence_count",
    "first_observed",
    "last_observed",
    "notes",
)

_MOTIVATIONAL_SIGNAL_INT_FIELDS = ("occurrence_count",)


def _motivational_signals_note_path():
    """Vault-relative path to the single Motivational Signals note."""
    return pathlib.Path(NOTES_LOCATIONS["motivational_signals"])


def _serialize_motivational_signals(rows):
    """Render a list of motivational signal row dicts (one per unique
    `pattern_description`) as YAML frontmatter - a top-level list of
    mappings - with an empty body. Integer fields are written
    unquoted; everything else is quoted via `_yaml_quote`."""
    lines = ["---"]
    for row in rows:
        prefix = "- "
        for field in _MOTIVATIONAL_SIGNAL_ROW_FIELDS:
            value = row.get(field)
            if value is None:
                lines.append(f"{prefix}{field}:")
            elif field in _MOTIVATIONAL_SIGNAL_INT_FIELDS:
                lines.append(f"{prefix}{field}: {value}")
            else:
                lines.append(f"{prefix}{field}: {_yaml_quote(value)}")
            prefix = "  "
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _parse_motivational_signals(text):
    """Parse a Motivational Signals note's YAML frontmatter back into a
    list of row dicts, one per unique `pattern_description`. Returns
    [] if there's no frontmatter block (e.g. the note doesn't exist
    yet). Integer fields are parsed back to int; everything else via
    `_yaml_unquote`."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []

    rows = []
    current_row = None

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip():
            continue

        if line.startswith("- "):
            current_row = {field: None for field in _MOTIVATIONAL_SIGNAL_ROW_FIELDS}
            rows.append(current_row)
            field_line = line[2:]
        elif line.startswith("  ") and current_row is not None:
            field_line = line.strip()
        else:
            continue

        key, _, rest = field_line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if key in _MOTIVATIONAL_SIGNAL_ROW_FIELDS:
            if rest == "":
                current_row[key] = None
            elif key in _MOTIVATIONAL_SIGNAL_INT_FIELDS:
                current_row[key] = int(rest)
            else:
                current_row[key] = _yaml_unquote(rest)

    return rows


def record_motivational_signal(pattern_description, signal_type=None, topic=None, notes=None):
    """Log an observed motivational/engagement pattern, or bump its
    occurrence count if already tracked - mirrors SQLite's
    UNIQUE(pattern_description) upsert exactly.

    - If no row exists yet for this `pattern_description`, a new row
      is created: `signal_type`, `topic`, and `notes` are stored as
      given (including None); `occurrence_count` starts at 1, and
      `first_observed`/`last_observed` are both set to now.
    - If a row already exists for this `pattern_description`,
      `signal_type` and `topic` are left untouched (not overwritten,
      even if different values are passed), `occurrence_count` is
      incremented by 1, `last_observed` is refreshed, and `notes` is
      only overwritten when a non-None value is supplied (mirrors the
      SQL's `COALESCE(excluded.notes, notes)`).

    `pattern_description` is NOT NULL in the SQLite schema - passing
    None here reproduces the same sqlite3.IntegrityError
    memory_database.py would raise, rather than silently writing an
    invalid note.
    """
    if pattern_description is None:
        raise sqlite3.IntegrityError(
            "NOT NULL constraint failed: motivational_signals.pattern_description"
        )

    text = _read_note(_motivational_signals_note_path())
    rows = _parse_motivational_signals(text) if text.strip() else []

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    existing_row = next(
        (row for row in rows if row["pattern_description"] == pattern_description), None
    )

    if existing_row is None:
        rows.append({
            "pattern_description": pattern_description,
            "signal_type": signal_type,
            "topic": topic,
            "occurrence_count": 1,
            "first_observed": now,
            "last_observed": now,
            "notes": notes,
        })
    else:
        existing_row["occurrence_count"] = (existing_row["occurrence_count"] or 0) + 1
        existing_row["last_observed"] = now
        if notes is not None:
            existing_row["notes"] = notes

    _write_note(_motivational_signals_note_path(), _serialize_motivational_signals(rows))


def get_motivational_signals(signal_type=None):
    """Return motivational signals, optionally filtered by type
    ('frustration', 'confidence', 'engagement'), ordered by
    last_observed DESC. Always a list[dict], never None; [] if there
    are no matching rows. `signal_type` uses truthiness, not an
    is-None check - matching memory_database.py's `if signal_type:` -
    so signal_type="" is treated the same as signal_type=None (no
    filter applied), not as a literal filter for an empty-string
    value."""
    text = _read_note(_motivational_signals_note_path())
    rows = _parse_motivational_signals(text) if text.strip() else []

    if signal_type:
        matching = [row for row in rows if row["signal_type"] == signal_type]
    else:
        matching = list(rows)

    matching.sort(key=lambda row: row["last_observed"], reverse=True)
    return [dict(row) for row in matching]


# ---------------------------------------------------------------------------
# 12. Growth Trajectory & Milestones
# ---------------------------------------------------------------------------
#
# Multi-note category (NOTES_LOCATIONS["milestones"] points at the
# "Milestones" folder, not a single .md file) - one note per milestone,
# matching memory_database.py's `milestones` table. Append-only, like
# Learning Journal and Assessment History: memory_database.py has no
# update/delete function for milestones, so no note is ever rewritten
# after creation, and (as with Journal entries and Assessments) the
# numeric id is never handed back to a caller or included in the
# returned rows - it's purely a filename convenience for reproducing
# insertion order.
#
# Notes are named with a zero-padded sequential index assigned at
# insertion time (e.g. "000001.md", "000002.md", ...), so sorting by
# filename ascending reproduces insertion order (oldest first) - same
# tie-break reasoning as Learning Journal/Assessments for same-timestamp
# entries.

_MILESTONE_FIELDS = (
    "title",
    "description",
    "category",
    "achieved_at",
    "notes",
)


def _milestone_quote(value):
    """Quote a scalar for a milestone note, escaping backslashes,
    double quotes, and embedded newlines - in that order, in a single
    left-to-right pass - so free-form multiline text (title,
    description, notes) always round-trips exactly while still
    occupying exactly one physical line in the note.

    Deliberately a separate function from `_assessment_quote` /
    `_journal_quote` / `_project_quote` (same logic, different
    category), matching this codebase's existing pattern of one small
    serialize/parse pair per category rather than cross-category
    reuse."""
    escaped = []
    for ch in str(value):
        if ch == "\\":
            escaped.append("\\\\")
        elif ch == '"':
            escaped.append('\\"')
        elif ch == "\n":
            escaped.append("\\n")
        else:
            escaped.append(ch)
    return f'"{"".join(escaped)}"'


def _milestone_unquote(raw):
    """Reverse of `_milestone_quote`. A single left-to-right scan (not
    a sequence of blind global replaces) so escaped backslashes,
    escaped quotes, and escaped newlines can't be misinterpreted when
    they're adjacent to one another. Tolerates unquoted scalars too."""
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        inner = raw[1:-1]
        result = []
        i = 0
        n = len(inner)
        while i < n:
            ch = inner[i]
            if ch == "\\" and i + 1 < n and inner[i + 1] in ('n', '"', '\\'):
                nxt = inner[i + 1]
                result.append("\n" if nxt == "n" else nxt)
                i += 2
            else:
                result.append(ch)
                i += 1
        return "".join(result)
    return raw


def _milestones_folder_path():
    """Vault-relative path to the Milestones folder."""
    return pathlib.Path(NOTES_LOCATIONS["milestones"])


def _milestone_note_paths():
    """Return vault-relative paths to all milestone notes, sorted by
    filename ascending - i.e. insertion order, oldest first (see
    module note above)."""
    vault_root = _resolve_vault_path()
    folder = vault_root / _milestones_folder_path()
    folder.mkdir(parents=True, exist_ok=True)
    return sorted(p.relative_to(vault_root) for p in folder.glob("*.md"))


def _serialize_milestone(row):
    """Render a single milestone row dict as YAML frontmatter - a flat
    top-level mapping, one note per milestone - with an empty body."""
    lines = ["---"]
    for field in _MILESTONE_FIELDS:
        value = row.get(field)
        if value is None:
            lines.append(f"{field}:")
        else:
            lines.append(f"{field}: {_milestone_quote(value)}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _parse_milestone(text):
    """Parse a single milestone note's YAML frontmatter back into a
    flat dict. Returns None if there's no frontmatter block."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    data = {field: None for field in _MILESTONE_FIELDS}

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip():
            continue
        if ":" not in line:
            continue

        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if key in _MILESTONE_FIELDS:
            data[key] = None if rest == "" else _milestone_unquote(rest)

    return data


def add_milestone(title, description=None, category=None, notes=None):
    """Record a new milestone. Append-only - milestones are never
    updated or removed once logged. `title` is NOT NULL in the SQLite
    schema - passing None here reproduces the same
    sqlite3.IntegrityError memory_database.py would raise, rather than
    silently writing an invalid note. Always creates a new note; no id
    is returned."""
    if title is None:
        raise sqlite3.IntegrityError("NOT NULL constraint failed: milestones.title")

    next_index = len(_milestone_note_paths()) + 1
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    row = {
        "title": title,
        "description": description,
        "category": category,
        "achieved_at": now,
        "notes": notes,
    }

    note_path = _milestones_folder_path() / f"{next_index:06d}.md"
    _write_note(note_path, _serialize_milestone(row))


def get_milestones(limit=None):
    """Return milestones, newest first. `limit` uses truthiness, not
    an is-None check - matching memory_database.py's `if limit:` -
    so limit=None and limit=0 both mean "no limit" (all milestones
    returned). A negative limit also returns every milestone
    (verified: SQLite's `LIMIT ?` bound to a negative integer applies
    no limit, and memory_database.py's `if limit:` branch would pass a
    negative limit straight through to SQL). Otherwise always a
    list[dict], never None; [] if there are no milestones."""
    entries = []
    for path in _milestone_note_paths():
        text = _read_note(path)
        if not text.strip():
            continue
        entry = _parse_milestone(text)
        if entry is not None:
            entries.append(entry)

    entries.sort(key=lambda row: row["achieved_at"], reverse=True)

    if not limit or limit < 0:
        return entries
    return entries[:limit]


# ---------------------------------------------------------------------------
# 13. Curiosity Backlog
# ---------------------------------------------------------------------------
#
# Multi-note category (NOTES_LOCATIONS["curiosity_backlog"] points at the
# "Curiosity" folder) - one note per backlog entry, matching
# memory_database.py's `curiosity_backlog` table. Mutable, like Projects:
# `mark_curiosity_addressed` rewrites an entry's note in place rather than
# appending a new one.
#
# Notes are named with a zero-padded sequential index assigned at insertion
# time (e.g. "000001.md", "000002.md", ...), so sorting by filename
# ascending reproduces insertion order (oldest first) - same tie-break
# reasoning as Projects for same-timestamp entries.

_CURIOSITY_FIELDS = (
    "id",
    "question",
    "raised_in_session",
    "status",
    "raised_at",
    "addressed_at",
    "notes",
)

_CURIOSITY_INT_FIELDS = ("id",)


def _curiosity_quote(value):
    """Quote a scalar for a curiosity note, escaping backslashes, double
    quotes, and embedded newlines - in that order, in a single
    left-to-right pass - so free-form multiline text (question, notes)
    always round-trips exactly while still occupying exactly one physical
    line in the note.

    Deliberately a separate function from the other `_*_quote` helpers
    (same logic, different category), matching this codebase's existing
    pattern of one small serialize/parse pair per category rather than
    cross-category reuse."""
    escaped = []
    for ch in str(value):
        if ch == "\\":
            escaped.append("\\\\")
        elif ch == '"':
            escaped.append('\\"')
        elif ch == "\n":
            escaped.append("\\n")
        else:
            escaped.append(ch)
    return f'"{"".join(escaped)}"'


def _curiosity_unquote(raw):
    """Reverse of `_curiosity_quote`. A single left-to-right scan (not a
    sequence of blind global replaces) so escaped backslashes, escaped
    quotes, and escaped newlines can't be misinterpreted when they're
    adjacent to one another. Tolerates unquoted scalars too."""
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        inner = raw[1:-1]
        result = []
        i = 0
        n = len(inner)
        while i < n:
            ch = inner[i]
            if ch == "\\" and i + 1 < n and inner[i + 1] in ('n', '"', '\\'):
                nxt = inner[i + 1]
                result.append("\n" if nxt == "n" else nxt)
                i += 2
            else:
                result.append(ch)
                i += 1
        return "".join(result)
    return raw


def _curiosity_folder_path():
    """Vault-relative path to the Curiosity folder."""
    return pathlib.Path(NOTES_LOCATIONS["curiosity_backlog"])


def _curiosity_note_paths():
    """Return vault-relative paths to all curiosity-backlog notes, sorted
    by filename ascending - i.e. insertion order, oldest first (see
    module note above)."""
    vault_root = _resolve_vault_path()
    folder = vault_root / _curiosity_folder_path()
    folder.mkdir(parents=True, exist_ok=True)
    return sorted(p.relative_to(vault_root) for p in folder.glob("*.md"))


def _serialize_curiosity(row):
    """Render a single curiosity-backlog row dict as YAML frontmatter -
    a flat top-level mapping, one note per entry - with an empty body."""
    lines = ["---"]
    for field in _CURIOSITY_FIELDS:
        value = row.get(field)
        if value is None:
            lines.append(f"{field}:")
        elif field in _CURIOSITY_INT_FIELDS:
            lines.append(f"{field}: {value}")
        else:
            lines.append(f"{field}: {_curiosity_quote(value)}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _parse_curiosity(text):
    """Parse a single curiosity-backlog note's YAML frontmatter back into
    a flat dict. Returns None if there's no frontmatter block."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    data = {field: None for field in _CURIOSITY_FIELDS}

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip():
            continue
        if ":" not in line:
            continue

        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if key in _CURIOSITY_FIELDS:
            if rest == "":
                data[key] = None
            elif key in _CURIOSITY_INT_FIELDS:
                data[key] = int(rest)
            else:
                data[key] = _curiosity_unquote(rest)

    return data


def add_curiosity(question, raised_in_session=None, notes=None):
    """Log a deferred tangent/question the student raised. `question` is
    NOT NULL in the SQLite schema - passing None here reproduces the same
    sqlite3.IntegrityError memory_database.py would raise, rather than
    silently writing an invalid note. memory_database.py's INSERT never
    reads back `cursor.lastrowid`, so this returns None too, matching
    that (lack of a) return value."""
    if question is None:
        raise sqlite3.IntegrityError("NOT NULL constraint failed: curiosity_backlog.question")

    next_id = len(_curiosity_note_paths()) + 1
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    row = {
        "id": next_id,
        "question": question,
        "raised_in_session": raised_in_session,
        "status": "open",
        "raised_at": now,
        "addressed_at": None,
        "notes": notes,
    }

    note_path = _curiosity_folder_path() / f"{next_id:06d}.md"
    _write_note(note_path, _serialize_curiosity(row))


def mark_curiosity_addressed(curiosity_id):
    """Mark a curiosity-backlog entry as addressed. If `curiosity_id`
    doesn't match any entry, this is a silent no-op - matches SQLite's
    `UPDATE ... WHERE id = ?` affecting zero rows without error."""
    for path in _curiosity_note_paths():
        text = _read_note(path)
        if not text.strip():
            continue
        row = _parse_curiosity(text)
        if row is None or row.get("id") != curiosity_id:
            continue

        row["status"] = "addressed"
        row["addressed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        _write_note(path, _serialize_curiosity(row))
        return


def get_curiosity_backlog(status="open"):
    """Return curiosity-backlog entries, optionally filtered by status
    ('open' or 'addressed'), newest-raised first. `status` uses
    truthiness, not an is-None check - matching memory_database.py's
    `if status:` - so status=None or status="" returns every entry,
    unfiltered. Always a list[dict], never None; [] if there are no
    matching entries."""
    entries = []
    for path in _curiosity_note_paths():
        text = _read_note(path)
        if not text.strip():
            continue
        row = _parse_curiosity(text)
        if row is not None:
            entries.append(row)

    if status:
        entries = [e for e in entries if e["status"] == status]

    entries.sort(key=lambda e: e["raised_at"], reverse=True)
    return entries


if __name__ == "__main__":
    print("obsidian_backend.py loaded.")
    print("This is a skeleton only - every function raises NotImplementedError.")
    print("Mirrors the full public interface of memory_database.py.")
