#!/usr/bin/env python3
"""EnglishLint statusline. Reads its own state.json (ignores the session
JSON Claude Code sends on stdin) and prints up to ~10 lines: streak/points,
due reviews, recent mistakes, and today's passed reviews. This is the one
surface that shows mistake activity now — chat responses stay clean."""
import difflib
import json
import sys
from datetime import date
from pathlib import Path

STATE_PATH = Path.home() / ".claude" / "englishlint" / "state.json"

AMBER = "\033[38;5;214m"
GREY = "\033[38;5;245m"
RED = "\033[31m"
STRIKE = "\033[9m"
GREEN = "\033[32m"
RESET = "\033[0m"

DUE_MAX = 2
RECENT_MAX = 5
PASSED_MAX = 2


def diff_render(wrong: str, correct: str) -> str:
    """One inline line showing just what changed: word-level diff for
    phrases, character-level for single-word typos. Removed part in
    red+strikethrough, added part in green, unchanged part plain."""
    if " " in wrong or " " in correct:
        w_units, c_units, sep = wrong.split(" "), correct.split(" "), " "
    else:
        w_units, c_units, sep = list(wrong), list(correct), ""

    sm = difflib.SequenceMatcher(None, w_units, c_units)
    parts = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            parts.append(sep.join(w_units[i1:i2]))
        elif tag == "delete":
            parts.append(f"{RED}{STRIKE}{sep.join(w_units[i1:i2])}{RESET}")
        elif tag == "insert":
            parts.append(f"{GREEN}{sep.join(c_units[j1:j2])}{RESET}")
        elif tag == "replace":
            deleted = f"{RED}{STRIKE}{sep.join(w_units[i1:i2])}{RESET}"
            inserted = f"{GREEN}{sep.join(c_units[j1:j2])}{RESET}"
            parts.append(deleted + sep + inserted)
    return sep.join(p for p in parts if p) if sep else "".join(parts)


def main() -> int:
    sys.stdin.read()  # drain stdin; we don't need the session JSON

    if not STATE_PATH.exists():
        print(f"{GREY}EnglishLint: no data yet{RESET}")
        return 0

    try:
        state = json.loads(STATE_PATH.read_text())
    except json.JSONDecodeError:
        print(f"{GREY}EnglishLint: invalid state{RESET}")
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

    lines = [f"{AMBER}🔥 {streak}{RESET} · {points} pts" + (f" · {len(due)} due" if due else "")]

    for card in due[:DUE_MAX]:
        lines.append(f"  {GREY}review:{RESET} {diff_render(card['wrong'], card['correct'])}")

    for item in state.get("recent", [])[:RECENT_MAX]:
        mark = "↺" if item.get("kind") == "relapse" else "·"
        lines.append(f"  {GREY}{mark}{RESET} {diff_render(item['wrong'], item['correct'])}")

    reviews_today = state.get("reviews_today", {})
    if reviews_today.get("date") == today:
        for r in reviews_today.get("passed", [])[-PASSED_MAX:]:
            lines.append(f"  {GREEN}✓ learned:{RESET} {r['correct']}")

    print("\n".join(lines[:10]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
