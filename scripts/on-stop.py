#!/usr/bin/env python3
"""EnglishLint Stop hook.

Reads the JSON Claude Code sends on stdin for the Stop event, pulls
`last_assistant_message`, and:
  - parses any `EnglishLint mistake|review` tag lines the assistant printed
  - updates points, Leitner box position, and next_review for each
  - bumps the daily streak
  - introduces the next batch of migrated old mistakes, once per day

Never blocks the turn: always exits 0.
"""
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

STATE_PATH = Path.home() / ".claude" / "englishlint" / "state.json"
BOX_INTERVAL_DAYS = {1: 1, 2: 3, 3: 7, 4: 14, 5: 30}

# Anchored to the WHOLE line (optionally wrapped in a single pair of
# backticks) so a tag only fires when it is its own line, never when it's
# quoted mid-sentence as an example (e.g. "the tag looks like `EnglishLint:
# mistake | wrong | correct | rule`" would NOT match — no text may precede
# or follow it on that line beyond optional backticks/whitespace).
MISTAKE_RE = re.compile(
    r"^\s*`?EnglishLint:\s*mistake\s*\|\s*(?P<wrong>[^|]+?)\s*\|\s*(?P<correct>[^|]+?)\s*\|\s*(?P<rule>[^|`]+?)`?\s*$",
    re.MULTILINE,
)
REVIEW_RE = re.compile(
    r"^\s*`?EnglishLint:\s*review\s*\|\s*(?P<id>[a-z0-9_]+)\s*\|\s*(?P<outcome>pass|fail)`?\s*$",
    re.MULTILINE,
)


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")[:40] or "x"


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except json.JSONDecodeError:
            pass
    return {
        "version": 1,
        "streak": {"count": 0, "last_active_date": None},
        "points": {"total": 0},
        "cards": {},
        "migration": {"queue": [], "batch_size": 8, "last_import_date": None},
    }


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    tmp.replace(STATE_PATH)


def bump_streak(state: dict, today: date) -> None:
    streak = state["streak"]
    last = streak.get("last_active_date")
    if last == today.isoformat():
        return
    if last is not None:
        last_date = date.fromisoformat(last)
        if (today - last_date).days == 1:
            streak["count"] += 1
        else:
            streak["count"] = 1
    else:
        streak["count"] = 1
    streak["last_active_date"] = today.isoformat()


def run_daily_import(state: dict, today: date) -> None:
    migration = state["migration"]
    if migration.get("last_import_date") == today.isoformat():
        return
    batch_size = migration.get("batch_size", 8)
    queue = migration.get("queue", [])
    cards = state["cards"]
    introduced = 0
    while queue and introduced < batch_size:
        card_id = queue.pop(0)
        card = cards.get(card_id)
        if card is None:
            continue
        card["introduced"] = True
        card["next_review"] = today.isoformat()
        introduced += 1
    migration["last_import_date"] = today.isoformat()


def apply_mistake(state: dict, today: date, wrong: str, correct: str, rule: str) -> None:
    card_id = f"{slugify(wrong)}__{slugify(correct)}"
    cards = state["cards"]
    if card_id in cards:
        card = cards[card_id]
        card["times_seen"] = card.get("times_seen", 1) + 1
        card["box"] = 1
        card["next_review"] = (today + timedelta(days=BOX_INTERVAL_DAYS[1])).isoformat()
        card["introduced"] = True
        # relapse: no points, this is a signal it's not learned yet
    else:
        cards[card_id] = {
            "wrong": wrong,
            "correct": correct,
            "rule": rule,
            "box": 1,
            "next_review": (today + timedelta(days=BOX_INTERVAL_DAYS[1])).isoformat(),
            "times_seen": 1,
            "introduced": True,
            "source": "new",
        }
        state["points"]["total"] += 5


def apply_review(state: dict, today: date, card_id: str, outcome: str) -> None:
    card = state["cards"].get(card_id)
    if card is None:
        return
    if outcome == "pass":
        card["box"] = min(card.get("box", 1) + 1, 5)
        state["points"]["total"] += 10
    else:
        card["box"] = 1
    card["next_review"] = (today + timedelta(days=BOX_INTERVAL_DAYS[card["box"]])).isoformat()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    message = payload.get("last_assistant_message") or ""
    today = date.today()

    state = load_state()
    bump_streak(state, today)
    run_daily_import(state, today)

    for m in MISTAKE_RE.finditer(message):
        apply_mistake(state, today, m.group("wrong").strip(), m.group("correct").strip(), m.group("rule").strip())

    for m in REVIEW_RE.finditer(message):
        apply_review(state, today, m.group("id"), m.group("outcome"))

    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
