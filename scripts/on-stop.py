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

# One line per tag TYPE per turn (not per mistake) — all mistakes caught in
# a turn are packed into a single "EnglishLint mistake: ..." line, items
# joined by " && " (shell-chain style), fields within an item by "|".
# Anchored to the WHOLE line (optionally backticked) so it only fires as its
# own line, never quoted mid-sentence as an example.
MISTAKE_LINE_RE = re.compile(r"^\s*`?EnglishLint mistake:\s*(?P<items>.+?)`?\s*$", re.MULTILINE)
REVIEW_LINE_RE = re.compile(r"^\s*`?EnglishLint review:\s*(?P<items>.+?)`?\s*$", re.MULTILINE)


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
        "recent": [],
        "reviews_today": {"date": None, "passed": []},
        "history": [],
    }


RECENT_MAX = 20


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


HISTORY_MAX_DAYS = 365


def log_daily_snapshot(state: dict, today: date) -> None:
    """Append one row/day to state['history'] so trend charts (mistakes
    over time, mastery over time) become possible once a few days have
    accumulated — nothing before today's first run of this function
    existed, since individual cards never recorded when they were caught."""
    history = state.setdefault("history", [])
    today_str = today.isoformat()
    if history and history[-1]["date"] == today_str:
        history.pop()  # overwrite today's row instead of duplicating it

    cards = state["cards"].values()
    box_dist = {str(i): 0 for i in range(1, 6)}
    for c in cards:
        box_dist[str(c.get("box", 1))] += 1

    history.append(
        {
            "date": today_str,
            "points": state["points"]["total"],
            "streak": state["streak"]["count"],
            "active": sum(1 for c in cards if c.get("introduced")),
            "mastered": box_dist["5"],
            "queued": len(state.get("migration", {}).get("queue", [])),
            "total_cards": len(state["cards"]),
            "box_dist": box_dist,
        }
    )
    del history[:-HISTORY_MAX_DAYS]


def push_recent(state: dict, wrong: str, correct: str, kind: str) -> None:
    state.setdefault("recent", []).insert(0, {"wrong": wrong, "correct": correct, "kind": kind})
    del state["recent"][RECENT_MAX:]


def apply_mistake(state: dict, today: date, wrong: str, correct: str, rule: str) -> None:
    card_id = f"{slugify(wrong)}__{slugify(correct)}"
    cards = state["cards"]
    if card_id in cards:
        card = cards[card_id]
        card["times_seen"] = card.get("times_seen", 1) + 1
        card["box"] = 1
        card["next_review"] = (today + timedelta(days=BOX_INTERVAL_DAYS[1])).isoformat()
        card["introduced"] = True
        push_recent(state, wrong, correct, "relapse")
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
        push_recent(state, wrong, correct, "new")


def apply_review(state: dict, today: date, card_id: str, outcome: str) -> None:
    card = state["cards"].get(card_id)
    if card is None:
        return
    if outcome == "pass":
        card["box"] = min(card.get("box", 1) + 1, 5)
        state["points"]["total"] += 10
        reviews_today = state.setdefault("reviews_today", {"date": None, "passed": []})
        if reviews_today.get("date") != today.isoformat():
            reviews_today["date"] = today.isoformat()
            reviews_today["passed"] = []
        reviews_today["passed"].append({"wrong": card["wrong"], "correct": card["correct"]})
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

    for line_match in MISTAKE_LINE_RE.finditer(message):
        for item in line_match.group("items").split("&&"):
            fields = [f.strip() for f in item.split("|")]
            if len(fields) == 3 and all(fields):
                wrong, correct, rule = fields
                apply_mistake(state, today, wrong, correct, rule)

    for line_match in REVIEW_LINE_RE.finditer(message):
        for item in line_match.group("items").split("&&"):
            card_id, _, outcome = item.strip().partition(":")
            card_id, outcome = card_id.strip(), outcome.strip()
            if card_id and outcome in ("pass", "fail"):
                apply_review(state, today, card_id, outcome)

    log_daily_snapshot(state, today)
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
