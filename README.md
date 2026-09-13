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
   naturally. Also scans the user's own just-submitted message against every
   tracked card's `correct` form (skipping common single words like "the"/
   "it" — see `COMMON_WORDS` — so it doesn't fire on everything) and surfaces
   real matches too: added because a correct word embedded naturally inside
   a longer message was easy for Claude to miss while reading for content,
   unlike a standalone one-word test message. Makes that detection
   mechanical instead of dependent on Claude noticing mid-read.
4. **`scripts/statusline.py`** — a global statusline. Header line is
   `🔥 streak · points pts` plus whichever of these are currently non-zero:
   `N due`, `N reviewed` (today), `N active` (cards in rotation),
   `N mastered` (box 5), `N queued` (migration backlog) — zero-value columns
   are omitted so the line doesn't fill with noise, and the whole header
   drops lower-priority columns first if it wouldn't fit `COLUMNS`. Below
   that: due reviews and recent mistakes (each an inline colored diff —
   word-level for phrases, character-level for single-word typos, deleted
   part red / inserted part green, no strikethrough since Warp renders
   color but drops that attribute) laid out as a fixed grid — same column
   count every row, each column padded to its widest entry so the ` | `
   separators line up down the page. Column count is picked automatically
   (`best_column_count`) as the most columns that both fit real terminal
   width (`COLUMNS`) and still leave at least `MIN_LIST_LINES` rows — more
   columns means fewer rows for the same mistake count, so a wide terminal
   doesn't win back rows you asked to keep. Total rows are further capped
   by real terminal height (`LINES`, via `list_budget`), clamped to a sane
   range so a huge terminal doesn't turn the bar into a wall of text. No
   per-line metadata, no "today's passed reviews" section: what's still a
   mistake matters more than what's already learned. `!elmin` collapses
   the bar to just the header line (handy when you want the space back);
   `!elmax` restores the full grid.
5. **`scripts/migrate.py`** — one-time (idempotent) importer for the old
   `english-log.md` "Repeat Mistakes" table. Run once per old log you want
   to fold in; re-running is safe, it skips anything already known.
6. **`report/index.html`** — a local, live dashboard: box distribution,
   composition (not-started/learning/mastered), a times-seen histogram, a
   progress-over-time trend (needs a few days of `history` to draw — see
   below), and a searchable/sortable table of every mistake. Reads
   `../state.json` straight off disk and re-fetches it every 4s, so it's
   always current — no regenerating or republishing anything. Can't be
   opened directly as a `file://` path (browsers block a local page from
   fetching a sibling file); run `scripts/serve-report.sh` and it opens the
   right `http://localhost` URL for you. There's also a separately
   published snapshot version (an Artifact) for viewing outside this
   machine — that one needs manual regeneration + republishing each time
   you want it current, since a hosted page can't reach your local disk.

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
- **Daily history**: `on-stop.py` appends one snapshot a day (points, streak,
  active/mastered/queued counts, box distribution) to `state["history"]`,
  kept for `HISTORY_MAX_DAYS` (365) days — added so the report's trend chart
  has something to plot once enough days accumulate. Nothing before the day
  this was added exists; individual cards never recorded when they were
  first caught.

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

# 4. (optional) short `elreport` shortcut for manually (re)starting the
#    report server — requires ~/.local/bin (or another dir on PATH):
ln -sf ~/.claude/englishlint/scripts/serve-report.sh ~/.local/bin/elreport

# 5. (optional) `elmin`/`elmax` shortcuts to collapse the statusline to
#    just the header line, and restore it back to the full grid — both
#    symlink the same script, which dispatches on which name it was
#    invoked as:
ln -sf ~/.claude/englishlint/scripts/set-minimize.py ~/.local/bin/elmin
ln -sf ~/.claude/englishlint/scripts/set-minimize.py ~/.local/bin/elmax
```

`state.json` is gitignored — it's per-machine runtime data, not code. See
`state.example.json` for its shape.

## Known limitations (v0)

- No file locking: two Claude Code sessions ending a turn at the exact same
  instant could race on `state.json`. Low stakes, not worth the complexity
  yet.
- The "review" mechanic depends on Claude noticing a natural opportunity to
  test a due word — there's no forced quiz.
