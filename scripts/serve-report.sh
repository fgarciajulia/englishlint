#!/usr/bin/env bash
# Serves the englishlint folder locally so report/index.html can fetch
# ../state.json live. A plain file:// open can't do this — browsers block
# a local page from fetching a sibling file (CORS on the file: origin) —
# so this exists purely to get state.json onto http:// instead.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PORT="${1:-8931}"
URL="http://localhost:${PORT}/report/index.html"

python3 -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null' EXIT

sleep 0.4
echo "Serving at $URL (Ctrl+C to stop)"
open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null || true
wait "$SERVER_PID"
