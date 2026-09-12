#!/usr/bin/env python3
"""EnglishLint UserPromptSubmit hook.

Surfaces up to 2 due-for-review mistakes as additionalContext, so Claude
knows what's worth testing naturally in conversation today. Silent (no
output) when nothing is due. Never blocks the prompt.
"""
import json
import sys
from datetime import date
from pathlib import Path

STATE_PATH = Path.home() / ".claude" / "englishlint" / "state.json"
MAX_SURFACED = 2


def main() -> int:
    if not STATE_PATH.exists():
        return 0
    try:
        state = json.loads(STATE_PATH.read_text())
    except json.JSONDecodeError:
        return 0

    today = date.today().isoformat()
    due = [
        (card_id, card)
        for card_id, card in state.get("cards", {}).items()
        if card.get("introduced") and card.get("next_review") and card["next_review"] <= today
    ]
    if not due:
        return 0

    due.sort(key=lambda pair: (pair[1]["box"], pair[1]["next_review"]))
    due = due[:MAX_SURFACED]

    streak = state.get("streak", {}).get("count", 0)
    points = state.get("points", {}).get("total", 0)

    lines = [f"[EnglishLint] racha {streak} · {points} pts. Repasos vencidos hoy:"]
    for card_id, card in due:
        lines.append(
            f'- id={card_id}: "{card["wrong"]}" -> "{card["correct"]}" '
            f'(visto {card.get("times_seen", 1)} veces, caja {card["box"]})'
        )
    lines.append(
        "Si surge una oportunidad natural en la charla de probar alguno de estos "
        "(usarlo vos mismo, o pedirle al usuario que lo use), haganlo sin forzar la "
        "conversacion. Al final de tu respuesta, agrega una linea por cada repaso probado: "
        "`EnglishLint: review | <id> | pass` o `| fail`."
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
