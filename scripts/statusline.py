#!/usr/bin/env python3
"""EnglishLint statusline. Reads its own state.json (ignores the session
JSON Claude Code sends on stdin) and prints up to ~10 lines: streak/points,
due reviews, recent mistakes, and today's passed reviews. This is the one
surface that shows mistake activity now — chat responses stay clean."""
import json
import sys
from datetime import date
from pathlib import Path

STATE_PATH = Path.home() / ".claude" / "englishlint" / "state.json"

AMBER = "\033[38;5;214m"
GREY = "\033[38;5;245m"
RED = "\033[31m"
GREEN = "\033[32m"
RESET = "\033[0m"

DUE_MAX = 2
RECENT_MAX = 5
PASSED_MAX = 2


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

    due = [
        card
        for card in state.get("cards", {}).values()
        if card.get("introduced") and card.get("next_review") and card["next_review"] <= today
    ]
    due.sort(key=lambda c: (c["box"], c["next_review"]))

    lines = [f"{AMBER}🔥 {streak}{RESET} · {points} pts" + (f" · {len(due)} repasos" if due else "")]

    for card in due[:DUE_MAX]:
        lines.append(f"  {GREY}repasar:{RESET} {RED}{card['wrong']}{RESET}→{GREEN}{card['correct']}{RESET}")

    for item in state.get("recent", [])[:RECENT_MAX]:
        color = AMBER if item.get("kind") == "relapse" else RED
        mark = "↺" if item.get("kind") == "relapse" else "·"
        lines.append(f"  {GREY}{mark}{RESET} {color}{item['wrong']}{RESET}→{GREEN}{item['correct']}{RESET}")

    reviews_today = state.get("reviews_today", {})
    if reviews_today.get("date") == today:
        for r in reviews_today.get("passed", [])[:PASSED_MAX]:
            lines.append(f"  {GREEN}✓ aprendiste:{RESET} {r['correct']}")

    print("\n".join(lines[:10]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
