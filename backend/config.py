"""
config.py - Configuration Manager for Tutor Gojo
Handles API keys, user settings, and app preferences.
Why separate file? So the UI and AI logic never touch the filesystem directly.
"""

import json
import os
from pathlib import Path

# App data directory (where config and DB live)
APP_DIR = Path.home() / ".tutor_gojo"
CONFIG_FILE = APP_DIR / "config.json"
DB_FILE = APP_DIR / "gojo_data.db"
VAULT_DIR = APP_DIR / "vault"  # Default Obsidian vault location for educational memory

# Default settings
DEFAULTS = {
    "api_key": "",
    "theme": "dark",
    "accent_color": "#6B5CE7",  # Gojo purple
    "font_size": 14,
    "teaching_intensity": "patient",  # patient | accelerated
    "model": "gemini-2.5-flash",  # Default Gemini model
    "first_run": True,
    "username": "Student",
    "auto_save_history": True,
    "search_grounding": True,  # Use Google Search for live docs
    "vault_path": str(VAULT_DIR),  # Obsidian vault root for educational memory storage
}


def ensure_app_dir():
    """Create app directory if it doesn't exist."""
    APP_DIR.mkdir(parents=True, exist_ok=True)


def load_config():
    """Load config from file or return defaults."""
    ensure_app_dir()
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
            # Merge with defaults (handles new keys added in updates)
            merged = DEFAULTS.copy()
            merged.update(saved)
            return merged
    return DEFAULTS.copy()


def save_config(config):
    """Save config to file."""
    ensure_app_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_api_key():
    """Get the Gemini API key."""
    return load_config().get("api_key", "")


def set_api_key(key):
    """Save the Gemini API key."""
    config = load_config()
    config["api_key"] = key.strip()
    config["first_run"] = False
    save_config(config)


def get_db_path():
    """Get the SQLite database file path."""
    ensure_app_dir()
    return str(DB_FILE)


def get_vault_path():
    """Get the Obsidian vault root path used for educational memory
    storage. Falls back to the default vault location under APP_DIR if
    not set in the saved config."""
    ensure_app_dir()
    return load_config().get("vault_path", str(VAULT_DIR))


def update_setting(key, value):
    """Update a single setting."""
    config = load_config()
    config[key] = value
    save_config(config)


def get_setting(key, default=None):
    """Get a single setting value."""
    return load_config().get(key, default)


if __name__ == "__main__":
    # Quick test
    print("Config dir:", APP_DIR)
    print("Current config:", load_config())
