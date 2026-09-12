#!/usr/bin/env python3
"""One-time (idempotent) import of the old kiro-helpers.sh english-log.md
"Repeat Mistakes" table into EnglishLint's state.json migration queue.

Usage: migrate.py /path/to/old/english-log.md

Read-only on the source file. Safe to re-run: entries already present in
state.json (as a card or already queued) are skipped.
"""
import json
import re
import sys
from pathlib import Path

STATE_PATH = Path.home() / ".claude" / "englishlint" / "state.json"

ROW_RE = re.compile(
    r'^\|\s*\d+\s*\|\s*'
    r'<span[^>]*>(?P<wrong>.*?)</span>\s*\|\s*'
    r'<span[^>]*>(?P<correct>.*?)</span>\s*\|\s*'
    r'(?P<times>\d+)\s*\|'
)


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")[:40] or "x"


def box_for_times(times: int) -> int:
    if times >= 5:
        return 1
    if times >= 2:
        return 2
    return 3


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {
        "version": 1,
        "streak": {"count": 0, "last_active_date": None},
        "points": {"total": 0},
        "cards": {},
        "migration": {"queue": [], "batch_size": 8, "last_import_date": None},
    }


def main():
    if len(sys.argv) != 2:
        print("Usage: migrate.py /path/to/old/english-log.md", file=sys.stderr)
        sys.exit(1)

    source = Path(sys.argv[1])
    lines = source.read_text(encoding="utf-8", errors="replace").splitlines()

    state = load_state()
    cards = state["cards"]
    queue = state["migration"]["queue"]
    known_ids = set(cards.keys()) | set(queue)

    found = []
    in_repeat_table = False
    for line in lines:
        if line.strip() == "## Repeat Mistakes":
            in_repeat_table = True
            continue
        if in_repeat_table and line.startswith("## "):
            break  # left the repeat-mistakes section
        m = ROW_RE.match(line)
        if not m:
            continue
        wrong = m.group("wrong").strip()
        correct = m.group("correct").strip()
        times = int(m.group("times"))
        found.append((wrong, correct, times))

    added, skipped = 0, 0
    for wrong, correct, times in found:
        card_id = f"{slugify(wrong)}__{slugify(correct)}"
        if card_id in known_ids:
            skipped += 1
            continue
        cards[card_id] = {
            "wrong": wrong,
            "correct": correct,
            "rule": "migrado del historial viejo",
            "box": box_for_times(times),
            "next_review": None,
            "times_seen": times,
            "introduced": False,
            "source": "migrated",
        }
        queue.append(card_id)
        known_ids.add(card_id)
        added += 1

    # Highest historical repeat count first: those are the words worth
    # reviewing soonest once they're introduced.
    queue.sort(key=lambda cid: -cards[cid]["times_seen"])
    state["migration"]["queue"] = queue

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    print(f"Imported {added} new cards, skipped {skipped} already known.")
    print(f"Queue size: {len(queue)} (introduced {sum(1 for c in cards.values() if c['introduced'])} so far).")


if __name__ == "__main__":
    main()
