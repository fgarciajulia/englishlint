#!/usr/bin/env python3
"""EnglishLint UserPromptSubmit hook.

Surfaces up to 2 due-for-review mistakes as additionalContext, so Claude
knows what's worth testing naturally in conversation today. ALSO scans
the user's just-submitted prompt text itself against every tracked
card's `correct` form — added because Claude kept missing a card's
correct phrasing when it showed up embedded naturally inside a longer
message (easy to catch in a standalone one-word message, easy to miss
when it's incidental to the actual point being made). This makes that
detection mechanical instead of relying on Claude noticing it mid-read.
Silent (no output) when there's nothing to surface. Never blocks the
prompt.
"""
import json
import re
import sys
from datetime import date

from _common import STATE_PATH

MAX_SURFACED = 2
MAX_MENTIONED = 4


# Single-word `correct` forms that are too common to mean anything if they
# appear in a message (nearly every message contains "the", "it", "is"...).
# Only single words are stoplisted — a multi-word phrase like "kind of
# chart" or "does that mean" is specific enough that coincidental matches
# are effectively impossible, no stoplist needed.
COMMON_WORDS = {
    "the", "it", "is", "a", "an", "to", "of", "in", "on", "at", "and", "or",
    "but", "for", "this", "that", "these", "those", "he", "she", "we", "you",
    "they", "i", "my", "your", "his", "her", "its", "our", "their", "am",
    "are", "was", "were", "be", "been", "being", "do", "does", "did", "have",
    "has", "had", "not", "no", "so", "if", "then", "than", "with", "from",
    "by", "as", "up", "out", "about", "into", "over", "after", "before",
    "there", "here", "now", "just", "also", "only", "very", "much", "more",
    "most", "one", "two", "new", "old", "all", "any", "each", "every",
    "some", "such", "own", "when", "how", "why", "what", "who", "which",
}


def find_mentioned_cards(prompt: str, cards: dict) -> list[tuple[str, dict]]:
    """Cards whose `correct` form appears verbatim (case-insensitive,
    whole-word-ish) in the prompt the user just submitted — skipping
    single common words (see COMMON_WORDS) since those are noise, not
    signal."""
    if not prompt:
        return []
    hits = []
    lowered = prompt.lower()
    for card_id, card in cards.items():
        correct = card.get("correct", "")
        if not correct:
            continue
        if " " not in correct and correct.lower() in COMMON_WORDS:
            continue
        if len(correct) <= 2:
            continue
        pattern = r"(?<![a-z0-9])" + re.escape(correct.lower()) + r"(?![a-z0-9])"
        if re.search(pattern, lowered):
            hits.append((card_id, card))
    return hits


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    if not STATE_PATH.exists():
        return 0
    try:
        state = json.loads(STATE_PATH.read_text())
    except json.JSONDecodeError:
        return 0

    cards = state.get("cards", {})
    today = date.today().isoformat()
    due = [
        (card_id, card)
        for card_id, card in cards.items()
        if card.get("introduced") and card.get("next_review") and card["next_review"] <= today
    ]
    due.sort(key=lambda pair: (pair[1]["box"], pair[1]["next_review"]))
    due = due[:MAX_SURFACED]

    prompt_text = payload.get("prompt") or ""
    due_ids = {card_id for card_id, _ in due}
    # Cards already in the due list are NOT excluded here: a due card is
    # only guaranteed to be *shown*, not noticed — the exact failure mode
    # mechanical detection exists to prevent in the first place (a due
    # card's correct form can sit in the due list turn after turn while its
    # box-1 owner keeps typing it correctly, because nothing ever credits
    # it without this check). Due-and-mentioned matches sort first so they
    # survive MAX_MENTIONED truncation ahead of merely-mentioned cards.
    mentioned = sorted(
        find_mentioned_cards(prompt_text, cards),
        key=lambda pair: pair[0] not in due_ids,
    )[:MAX_MENTIONED]

    if not due and not mentioned:
        return 0

    streak = state.get("streak", {}).get("count", 0)
    points = state.get("points", {}).get("total", 0)

    lines = [f"[EnglishLint] racha {streak} · {points} pts."]

    if due:
        lines.append("Repasos vencidos hoy:")
        for card_id, card in due:
            lines.append(
                f'- id={card_id}: "{card["wrong"]}" -> "{card["correct"]}" '
                f'(visto {card.get("times_seen", 1)} veces, caja {card["box"]})'
            )

    if mentioned:
        lines.append(
            "El usuario acaba de escribir la forma correcta de estas tarjetas en su "
            "propio mensaje (deteccion mecanica, no depende de que vos lo notes leyendo):"
        )
        for card_id, card in mentioned:
            lines.append(
                f'- id={card_id}: escribio "{card["correct"]}" (wrong original: '
                f'"{card["wrong"]}", caja {card["box"]})'
            )

    lines.append(
        "Si el uso es natural (no forzado), registralo. Al final de tu respuesta, "
        "agrega UNA sola linea (todos los repasos juntos, no una por repaso) con el "
        "formato: `EnglishLint review: <id>:pass && <id2>:fail`."
    )

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(lines),
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
