#!/usr/bin/env python3
"""EnglishLint statusline. Reads its own state.json (ignores the session
JSON Claude Code sends on stdin) and prints: a header line (streak/points/
aggregate counts), then due reviews and recent mistakes as inline colored
diffs laid out in a fixed grid — column count picked from real terminal
width, capped so a minimum row count still holds; total rows capped by
real terminal height. This is the one surface that shows mistake activity
now — chat responses stay clean."""
import difflib
import json
import os
import re
import socket
import subprocess
import sys
from datetime import date

from _common import STATE_PATH, slugify

ENGLISHLINT_DIR = STATE_PATH.parent

REPORT_PORT = 8931
REPORT_URL = f"http://localhost:{REPORT_PORT}/report/index.html"
# ~/.local/bin/elreport symlinks to scripts/serve-report.sh (see README's
# setup section) — short enough that report+run fit on one statusline line,
# unlike the full absolute path.
REPORT_SERVE_CMD = "!elreport"

AMBER = "\033[38;5;214m"
GREY = "\033[38;5;245m"
RED = "\033[31m"
GREEN = "\033[32m"
RESET = "\033[0m"

# Lines reserved for the header and for the rest of Claude Code's own UI
# (input box, hints, recent turns) so the mistake list doesn't try to eat
# the whole terminal just because LINES is tall.
RESERVED_LINES = 15
MIN_LIST_LINES = 5
MAX_LIST_LINES = 20

ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def visible_len(s: str) -> int:
    return len(ANSI_RE.sub("", s))


def ensure_report_server() -> None:
    """Best-effort: start the local live-report's static server in the
    background if nothing's already listening on REPORT_PORT, so the report
    is already reachable the moment you want it without running
    scripts/serve-report.sh by hand first. Never blocks noticeably (tiny
    connect timeout) and never raises — a failed spawn just means the URL
    fails to load the way any dead localhost link fails.

    Bound explicitly to loopback: state.json holds personal mistake
    history, and plain `python3 -m http.server` defaults to 0.0.0.0,
    which would serve it to anyone else on the same network."""
    try:
        with socket.create_connection(("127.0.0.1", REPORT_PORT), timeout=0.05):
            return
    except OSError:
        pass
    try:
        subprocess.Popen(
            ["python3", "-m", "http.server", str(REPORT_PORT), "--bind", "127.0.0.1"],
            cwd=str(ENGLISHLINT_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pass


def terminal_width(default: int = 80) -> int:
    """Claude Code sets COLUMNS/LINES to the real terminal size before
    running the statusline script (tput/ioctl don't work here since Claude
    Code captures stdout instead of connecting it to the terminal)."""
    raw = os.environ.get("COLUMNS", "")
    return int(raw) if raw.isdigit() else default


def terminal_lines(default: int = 24) -> int:
    raw = os.environ.get("LINES", "")
    return int(raw) if raw.isdigit() else default


def list_budget() -> int:
    """How many due+recent lines to show, based on real terminal height
    minus what the rest of Claude Code's UI needs, clamped to a sane
    range so a huge terminal doesn't turn the bar into a wall of text."""
    available = terminal_lines() - RESERVED_LINES - 2  # header + report line
    return max(min(available, MAX_LIST_LINES), MIN_LIST_LINES)


def _char_diff(wrong: str, correct: str) -> str:
    """Character-level diff between two single words: deleted letters red,
    inserted letters green, unchanged letters plain. No strikethrough:
    Warp's statusline renders the color but silently drops that
    attribute, so it was dead weight (confirmed live, not just a guess)."""
    sm = difflib.SequenceMatcher(None, list(wrong), list(correct))
    parts = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            parts.append(wrong[i1:i2])
        elif tag == "delete":
            parts.append(f"{RED}{wrong[i1:i2]}{RESET}")
        elif tag == "insert":
            parts.append(f"{GREEN}{correct[j1:j2]}{RESET}")
        elif tag == "replace":
            parts.append(f"{RED}{wrong[i1:i2]}{RESET}{GREEN}{correct[j1:j2]}{RESET}")
    return "".join(parts)


def _is_localized_edit(wrong: str, correct: str) -> bool:
    """True when wrong->correct is one small, contiguous edit against a
    shared base — 'word'->'words' (append) or 'write'->'wrote' (mid-word
    swap) — rather than a full rewrite or a reordering with no shared
    anchor, like 'do'->'are' or 'who'->'how': those read as scrambled
    nonsense at the character level and are clearer as two whole colored
    words instead."""
    ops = difflib.SequenceMatcher(None, list(wrong), list(correct)).get_opcodes()
    has_equal = any(tag == "equal" for tag, *_ in ops)
    non_equal = sum(1 for tag, *_ in ops if tag != "equal")
    return has_equal and non_equal <= 1


def diff_render(wrong: str, correct: str) -> str:
    """One inline colored diff. A single word (no spaces) is diffed at the
    character level. A phrase is diffed word by word; when that swaps
    exactly one word for one word, it's re-diffed at the character level
    too, but only if `_is_localized_edit` says the edit is localized —
    otherwise a full word-for-word swap (e.g. 'who'->'how' inside 'who
    many'->'how many') would scramble into unreadable interleaved letters."""
    if " " not in wrong and " " not in correct:
        return _char_diff(wrong, correct)

    w_words, c_words = wrong.split(" "), correct.split(" ")
    sm = difflib.SequenceMatcher(None, w_words, c_words)
    parts = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            parts.append(" ".join(w_words[i1:i2]))
        elif tag == "delete":
            parts.append(f"{RED}{' '.join(w_words[i1:i2])}{RESET}")
        elif tag == "insert":
            parts.append(f"{GREEN}{' '.join(c_words[j1:j2])}{RESET}")
        elif tag == "replace":
            if i2 - i1 == 1 and j2 - j1 == 1 and _is_localized_edit(w_words[i1], c_words[j1]):
                parts.append(_char_diff(w_words[i1], c_words[j1]))
            else:
                deleted = f"{RED}{' '.join(w_words[i1:i2])}{RESET}"
                inserted = f"{GREEN}{' '.join(c_words[j1:j2])}{RESET}"
                parts.append(deleted + " " + inserted)
    return " ".join(p for p in parts if p)


def _row_width(items: list[str], cols: int, prefix: str) -> int:
    widths = [0] * cols
    for i, item in enumerate(items):
        widths[i % cols] = max(widths[i % cols], visible_len(item))
    return len(prefix) + sum(widths) + (cols - 1) * 3  # 3 == len(" | ")


def best_column_count(items: list[str], width_budget: int, prefix: str, min_lines: int) -> int:
    """The most columns that both (a) fit width_budget, given each column
    padded to its own widest entry, and (b) still leave at least min_lines
    rows — more columns means fewer rows for the same item count, so a
    wide terminal doesn't win back the line count you asked for."""
    if not items:
        return 1
    n = len(items)
    max_cols_for_min_lines = 1
    for c in range(1, n + 1):
        if -(-n // c) >= min_lines:  # ceil(n / c) >= min_lines
            max_cols_for_min_lines = c
        else:
            break

    best = 1
    for c in range(1, max_cols_for_min_lines + 1):
        if _row_width(items, c, prefix) <= width_budget:
            best = c
        else:
            break
    return best


def build_grid(items: list[str], width_budget: int, max_lines: int, min_lines: int, prefix: str) -> list[str]:
    """Lay already-rendered mistake strings out as a fixed grid: same
    column count on every row, each column padded to its widest entry so
    the ' | ' separators line up down the page. Column count comes from
    best_column_count; total rows are capped at max_lines by simply not
    showing items that wouldn't fit (rather than shrinking the grid)."""
    if not items or max_lines <= 0:
        return []
    cols = best_column_count(items, width_budget, prefix, min_lines)
    items = items[: cols * max_lines]
    widths = [0] * cols
    for i, item in enumerate(items):
        widths[i % cols] = max(widths[i % cols], visible_len(item))
    sep = f" {GREY}|{RESET} "
    lines = []
    for start in range(0, len(items), cols):
        row = items[start : start + cols]
        cells = [
            item if i == len(row) - 1 else item + " " * max(0, widths[i] - visible_len(item))
            for i, item in enumerate(row)
        ]
        lines.append(prefix + sep.join(cells))
    return lines


def main() -> int:
    sys.stdin.read()  # drain stdin; we don't need the session JSON
    ensure_report_server()

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

    cards_by_id = state.get("cards", {})
    cards = cards_by_id.values()
    due = [
        card
        for card in cards
        if card.get("introduced") and card.get("next_review") and card["next_review"] <= today
    ]
    due.sort(key=lambda c: (c["box"], c["next_review"]))

    active = sum(1 for c in cards if c.get("introduced"))
    mastered = sum(1 for c in cards if c.get("box") == 5)
    queued = len(state.get("migration", {}).get("queue", []))
    reviews_today = state.get("reviews_today", {})
    reviewed_today = len(reviews_today.get("passed", [])) if reviews_today.get("date") == today else 0

    budget = max(terminal_width() - 2, 20)

    header = f"{AMBER}🔥 {streak}{RESET} · {points} pts"
    for count, label in (
        (len(due), "due"),
        (reviewed_today, "reviewed"),
        (active, "active"),
        (mastered, "mastered"),
        (queued, "queued"),
    ):
        if not count:
            continue
        addition = f" · {count} {label}"
        if visible_len(header) + len(addition) > budget:
            break  # narrower terminal: keep the highest-priority columns only
        header += addition

    # Claude Code's statusline strips/breaks OSC 8 hyperlinks (confirmed:
    # the identical escape sequence IS clickable as plain tool output, just
    # not from here) — so this is plain selectable text, not a fake link.
    # REPORT_SERVE_CMD is short (elreport, a PATH shortcut) specifically so
    # this fits on one line at normal widths.
    lines = [header]
    report_line = f"  {GREY}report:{RESET} {REPORT_URL}  {GREY}run:{RESET} {REPORT_SERVE_CMD}"
    if visible_len(report_line) <= budget:
        lines.append(report_line)

    def with_box(text: str, box) -> str:
        return f"{text}{AMBER}·b{box}{RESET}"

    items = [with_box(diff_render(c["wrong"], c["correct"]), c["box"]) for c in due]
    for item in state.get("recent", []):
        text = diff_render(item["wrong"], item["correct"])
        if item.get("kind") == "relapse":
            text = f"↺{text}"
        # recent entries don't store their own box (see push_recent in
        # on-stop.py) — look up the card's CURRENT box instead of a stale
        # catch-time snapshot, since it may have advanced or relapsed since.
        card_id = f"{slugify(item['wrong'])}__{slugify(item['correct'])}"
        box = cards_by_id.get(card_id, {}).get("box", "?")
        items.append(with_box(text, box))

    lines.extend(build_grid(items, budget, list_budget(), MIN_LIST_LINES, "  · "))

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
