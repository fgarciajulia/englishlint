#!/usr/bin/env python3
"""Shared constants and state helpers used by every EnglishLint script.

Not a hook or CLI entry point itself — imported by the others. Python adds
each running script's own directory to sys.path, so on-stop.py/on-prompt.py/
statusline.py/migrate.py (all in this same scripts/ folder) can `import
_common` regardless of current working directory or how they're invoked.
"""
import json
import re
from pathlib import Path

STATE_PATH = Path.home() / ".claude" / "englishlint" / "state.json"


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")[:40] or "x"


def default_state() -> dict:
    """The canonical shape of a from-scratch state.json. Every script that
    might create one (on-stop.py's Stop hook, migrate.py's one-time import)
    reads this instead of keeping its own copy, so they can't quietly drift
    apart on which top-level keys a fresh state actually has."""
    return {
        "version": 1,
        "streak": {"count": 0, "last_active_date": None},
        "points": {"total": 0},
        "cards": {},
        "migration": {"queue": [], "batch_size": 8, "last_import_date": None},
        "recent": [],
        "reviews_today": {"date": None, "passed": []},
        "history": [],
    }


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except json.JSONDecodeError:
            pass
    return default_state()


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    tmp.replace(STATE_PATH)
