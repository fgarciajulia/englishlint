#!/usr/bin/env python3
"""Set the statusline's minimized flag. Dispatches on how it was invoked
(argv[0]'s basename) so two symlinks can share this one file without
needing separate scripts:
  ~/.local/bin/elmin -> minimize
  ~/.local/bin/elmax -> restore (maximize)
Run directly under its own name, it toggles instead (fallback for anyone
invoking set-minimize.py itself rather than through a symlink).
"""
import sys
from pathlib import Path

from _common import load_state, save_state


def main() -> int:
    invoked_as = Path(sys.argv[0]).name
    state = load_state()
    if invoked_as == "elmin":
        minimized = True
    elif invoked_as == "elmax":
        minimized = False
    else:
        minimized = not state.get("ui_minimized", False)
    state["ui_minimized"] = minimized
    save_state(state)
    print("EnglishLint bar minimized." if minimized else "EnglishLint bar restored.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
