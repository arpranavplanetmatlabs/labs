"""
settings_store.py — Persistent key-value settings backed by settings.json.

Stores system-level config (API keys, feature flags) that the user can
update at runtime via the Settings UI. Not for research data.
Priority: env var > settings.json > hardcoded default.
"""

import json
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_SETTINGS_FILE = Path(__file__).parent / "data" / "settings.json"

# Keys with their defaults
_DEFAULTS = {
    "tavily_api_key": "",
    "web_search_enabled": False,
}


def _load() -> dict:
    try:
        if _SETTINGS_FILE.exists():
            with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"[Settings] Could not load settings.json: {e}")
    return {}


def _save(data: dict):
    try:
        _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"[Settings] Could not save settings.json: {e}")


def get_all() -> dict:
    """Return all settings, merging defaults < file < env vars."""
    stored = _load()
    result = dict(_DEFAULTS)
    result.update(stored)

    # Env vars take priority
    if os.environ.get("TAVILY_API_KEY"):
        result["tavily_api_key"] = os.environ["TAVILY_API_KEY"]
    if os.environ.get("WEB_SEARCH_ENABLED", "").lower() in ("1", "true", "yes"):
        result["web_search_enabled"] = True

    return result


def get(key: str, default=None):
    """Get a single setting value."""
    return get_all().get(key, default)


def update(updates: dict) -> dict:
    """Update settings with the given dict and persist to disk. Returns new state."""
    stored = _load()
    stored.update(updates)
    _save(stored)
    return get_all()


def get_tavily_api_key() -> str:
    return get("tavily_api_key", "")


def is_web_search_enabled() -> bool:
    return bool(get("web_search_enabled", False))
