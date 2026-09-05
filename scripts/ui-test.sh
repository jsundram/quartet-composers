#!/usr/bin/env bash
# Run scripts/ui.test.mjs against a real headless Chrome. Starts a server and a browser, runs the
# checks, tears both down. Screenshots land in a temp dir and the path is printed at the end.
#
#     scripts/ui-test.sh            # quiet
#     KEEP=1 scripts/ui-test.sh     # keep the screenshots dir open for inspection
#
# Needs node >= 22 (global WebSocket) and a Chromium. It SKIPS with exit 0 when no browser is
# installed, so it never fails a machine that simply doesn't have one — the service-worker suite
# (scripts/sw.test.mjs) is the one that must always run.
set -uo pipefail
cd "$(dirname "$0")/.."

PORT=${PORT:-8765}
CDP=${CDP:-9333}
OUT=$(mktemp -d)

find_chrome() {
  local c
  for c in \
    "$HOME/.cache/ms-playwright"/chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell \
    "$HOME/.cache/ms-playwright"/chromium-*/chrome-*/"Google Chrome for Testing.app"/Contents/MacOS/"Google Chrome for Testing" \
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    "$(command -v chromium || true)" "$(command -v chromium-browser || true)" \
    "$(command -v google-chrome || true)"
  do
    [ -n "$c" ] && [ -x "$c" ] && { echo "$c"; return 0; }
  done
  return 1
}

CHROME=$(find_chrome) || { echo "ui-test: no Chromium found — skipping (this is not a failure)"; exit 0; }

# A FRESH profile every run. sw.js serves the shell cache-first, so a reused profile keeps running
# the PREVIOUS edit's JS until V is bumped — you would be testing code you already changed.
PROFILE="$OUT/profile"

# A browser left over from an interrupted run still holds $CDP. The new one then fails to bind and
# node connects to the OLD one -- which has the PREVIOUS build in its service-worker cache, so the
# suite silently tests code you already changed. That is the same trap the fresh profile exists to
# avoid, arriving by a different door; take the port before starting.
pkill -f "remote-debugging-port=$CDP" 2>/dev/null
pkill -f "http.server $PORT" 2>/dev/null
sleep 0.5

python3 -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 &
SERVER=$!
"$CHROME" --headless --disable-gpu --no-sandbox --hide-scrollbars \
  --remote-debugging-port="$CDP" --user-data-dir="$PROFILE" about:blank >"$OUT/chrome.log" 2>&1 &
BROWSER=$!
cleanup() { kill "$SERVER" "$BROWSER" 2>/dev/null; [ "${KEEP:-}" = "1" ] || rm -rf "$OUT"; }
trap cleanup EXIT

for _ in $(seq 40); do
  curl -sf "http://127.0.0.1:$CDP/json/version" >/dev/null 2>&1 && break
  sleep 0.25
done

node scripts/ui.test.mjs "$CDP" "$OUT" "http://127.0.0.1:$PORT"
rc=$?
[ "${KEEP:-}" = "1" ] && echo "screenshots: $OUT"
exit $rc
