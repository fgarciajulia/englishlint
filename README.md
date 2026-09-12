# EnglishLint

A personal English-coaching system for daily Claude Code sessions: mistakes
get corrected inline (as before), but now also tracked with points, a daily
streak, and Leitner-style spaced repetition — global, across every project,
always visible in the statusline.

Replaces an older, project-scoped Kiro rule (`english-check.md` +
`c1-english-comments.md` + a `kiro-helpers.sh english` subcommand) that only
worked inside one repo and had no memory of past mistakes.

## How it works

1. **`config/CLAUDE.md.snippet`** — appended to `~/.claude/CLAUDE.md`. Tells
   Claude to correct English mistakes inline and tag each one with a fixed,
   parseable line (`EnglishLint: mistake | wrong | correct | rule`), and to
   naturally test due reviews when the conversation allows it.
2. **`scripts/on-stop.py`** — a global `Stop` hook. Reads the tag lines from
   the turn's last assistant message, updates points/streak/Leitner state in
   `state.json`, and introduces a small batch of migrated old mistakes each
   calendar day (never all at once).
3. **`scripts/on-prompt.py`** — a global `UserPromptSubmit` hook. Surfaces up
   to 2 due reviews as context so Claude knows what to work into conversation
   naturally.
4. **`scripts/statusline.py`** — a global statusline. Shows `🔥 streak ·
   points pts · N repasos` in the Claude Code UI on every turn.
5. **`scripts/migrate.py`** — one-time (idempotent) importer for the old
   `english-log.md` "Repeat Mistakes" table. Run once per old log you want
   to fold in; re-running is safe, it skips anything already known.

## Mechanics

- **New mistake caught**: +5 pts, added to the deck in Leitner box 1.
- **Same mistake caught again** (relapse): no points, box resets to 1 — a
  relapse is a signal it isn't learned yet, not something to reward.
- **Due review passed**: +10 pts, box advances (max 5).
- **Due review failed**: box resets to 1.
- **Boxes → review interval**: 1→1 day, 2→3 days, 3→7 days, 4→14 days, 5→30
  days.
- **Streak**: +1 for any day with at least one recorded interaction; breaks
  after a full day with none.

Values above are a starting point, not final — tune `BOX_INTERVAL_DAYS` and
the point constants in `on-stop.py` freely.

## Setup on a new machine

```bash
git clone <this-repo> ~/.claude/englishlint
chmod +x ~/.claude/englishlint/scripts/*.py

# 1. Merge config/settings-snippet.json into ~/.claude/settings.json
#    (replace YOURNAME with your actual home directory user)

# 2. Append config/CLAUDE.md.snippet to ~/.claude/CLAUDE.md

# 3. (optional) import an old english-log.md "Repeat Mistakes" table:
python3 ~/.claude/englishlint/scripts/migrate.py /path/to/old/english-log.md
```

`state.json` is gitignored — it's per-machine runtime data, not code. See
`state.example.json` for its shape.

## Known limitations (v0)

- No file locking: two Claude Code sessions ending a turn at the exact same
  instant could race on `state.json`. Low stakes, not worth the complexity
  yet.
- The "review" mechanic depends on Claude noticing a natural opportunity to
  test a due word — there's no forced quiz.
