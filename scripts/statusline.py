#!/usr/bin/env python3
"""EnglishLint statusline. Reads its own state.json (ignores the session
JSON Claude Code sends on stdin) and prints one compact line."""
import json
import sys
from datetime import date
from pathlib import Path

STATE_PATH = Path.home() / ".claude" / "englishlint" / "state.json"

AMBER = "\033[38;5;214m"
GREY = "\033[38;5;245m"
RESET = "\033[0m"


def main() -> int:
    sys.stdin.read()  # drain stdin; we don't need the session JSON

    if not STATE_PATH.exists():
        print(f"{GREY}EnglishLint: sin datos todavia{RESET}")
        return 0

    try:
        state = json.loads(STATE_PATH.read_text())
    except json.JSONDecodeError:
        print(f"{GREY}EnglishLint: estado invalido{RESET}")
        return 0

    streak = state.get("streak", {}).get("count", 0)
    points = state.get("points", {}).get("total", 0)
    today = date.today().isoformat()
    due = sum(
        1
        for card in state.get("cards", {}).values()
        if card.get("introduced") and card.get("next_review") and card["next_review"] <= today
    )

    due_part = f" · {due} repaso{'s' if due != 1 else ''}" if due else ""
    print(f"{AMBER}🔥 {streak}{RESET} · {points} pts{due_part}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
