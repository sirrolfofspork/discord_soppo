"""
Load optional per-user background profiles from JSON (Discord user IDs as string keys).

Used at bot startup only; edit ``user_profiles.json`` and restart the bot to refresh.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default: ``user_profiles.json`` next to this package file
DEFAULT_PROFILES_PATH = Path(__file__).resolve().parent / "user_profiles.json"

# In-memory store: snowflake string -> profile fields
UserProfilesMap = dict[str, dict[str, Any]]


def load_user_profiles(path: Path | None = None) -> UserProfilesMap:
    """
    Load profiles from disk. Missing file -> empty dict.
    Invalid JSON or unreadable file -> log a warning and return empty dict.
    """
    file_path = path or DEFAULT_PROFILES_PATH
    if not file_path.is_file():
        logger.info("No user profiles file at %s (optional)", file_path)
        return {}

    try:
        raw_text = file_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.warning("Invalid JSON in %s: %s — continuing with no profiles", file_path, e)
        return {}
    except OSError as e:
        logger.warning("Could not read %s: %s — continuing with no profiles", file_path, e)
        return {}

    if not isinstance(data, dict):
        logger.warning("user_profiles.json must be a JSON object at the root — using no profiles")
        return {}

    out: UserProfilesMap = {}
    for key, value in data.items():
        if not isinstance(key, str) or not key.strip():
            continue
        if not isinstance(value, dict):
            logger.debug("Skipping profile key %r: value is not an object", key)
            continue
        out[key.strip()] = dict(value)

    logger.info("Loaded %d user profile(s) from %s", len(out), file_path)
    return out
