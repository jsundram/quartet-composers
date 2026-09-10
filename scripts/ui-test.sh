#!/usr/bin/env bash
# Run scripts/ui.test.mjs against a real headless Chrome. Starts a server and a browser, runs the
# checks, tears both down. Screenshots land in a temp dir and the path is printed at the end.
#
#     scripts/ui-test.sh            # quiet
#     KEEP=1 scripts/ui-test.sh     # keep the screenshots dir open for inspection
#
# Needs node >= 22 (global WebSocket) and a Chromium. It SKIPS with exit 0 when no browser is
# installed, so it never fails a machine that simply doesn't have one — the service-worker suite
# (scripts/sw.test.mjs) is the one that must always run. On Linux it also wants `xvfb-run`; see
# the pointer note below for what fails without it.
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
# Wait for the port to actually close rather than for half a second: nothing to kill costs nothing,
# and a browser slow to die is waited for instead of raced (issue 48, the same shape as the
# readiness loop below).
for _ in $(seq 40); do
  curl -sf "http://127.0.0.1:$CDP/json/version" >/dev/null 2>&1 || break
  sleep 0.1
done

python3 -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 &
SERVER=$!

# WHETHER A POINTER EXISTS IS A PLATFORM FACT, and it decides the lens, the hover previews and the
# detail panel's reserved height — eight of the nine checks that failed on #43's CI run. macOS
# reports `(hover:hover) and (pointer:fine)` unconditionally, so a Mac has never seen this; a
# HEADLESS Linux Chrome reports no pointing device at all, chart.js's `TOUCH` comes out true, and
# those checks fail at a layout the app is right to be drawing (#50). CDP cannot fix it from
# inside — `Emulation.setEmulatedMedia`'s feature list accepts `hover` and `pointer`, returns
# success, and ignores them — and `--blink-settings` is worse than useless: it holds until the
# first `setTouchEmulationEnabled`, whose restore then clobbers the pointer type for every page in
# the browser, so one phone section would poison every desktop section after it. A virtual X
# display gives Chrome a REAL pointer, which survives a touch toggle because it is what the touch
# emulator restores TO. So: Xvfb where there is one, plain headless where there is not, and the
# suite asserts which it got rather than assuming.
LAUNCH=("$CHROME" --headless)
if [ "$(uname)" != "Darwin" ] && command -v xvfb-run >/dev/null 2>&1; then
  # A screen bigger than any viewport the suite sets, so nothing is clamped by it. Every section
  # overrides the viewport anyway; this is only the window Chrome opens in.
  LAUNCH=(xvfb-run -a --server-args="-screen 0 1920x1600x24" "$CHROME")
elif [ "$(uname)" != "Darwin" ]; then
  echo "ui-test: no xvfb-run — running headless, where this platform reports NO pointer."
  echo "         Expect 'the desktop viewport really reports a fine pointer' and the hover checks"
  echo "         that depend on it to fail. Install xvfb to run them."
fi
# --disable-dev-shm-usage because a CI container's /dev/shm is typically 64MB and Chrome dies
# reaching past it, with the only symptom being a debug port that never opens.
"${LAUNCH[@]}" --disable-gpu --no-sandbox --hide-scrollbars --disable-dev-shm-usage \
  --no-first-run --no-default-browser-check --disable-search-engine-choice-screen \
  --remote-debugging-port="$CDP" --user-data-dir="$PROFILE" about:blank >"$OUT/chrome.log" 2>&1 &
BROWSER=$!
# Chrome is xvfb-run's CHILD, and killing the wrapper leaves it holding $CDP — which is exactly
# the leftover browser the pkill above exists to clear, arriving one run early.
cleanup() {
  kill "$SERVER" "$BROWSER" 2>/dev/null
  pkill -f "remote-debugging-port=$CDP" 2>/dev/null
  [ "${KEEP:-}" = "1" ] || rm -rf "$OUT"
}
trap cleanup EXIT

# 30s, not 10: a cold CI runner is slower than a warm laptop, and the old budget expired into a
# bare ECONNREFUSED from node with chrome.log already deleted by the EXIT trap — a failure that
# says only "the port is shut", never why. Say why.
READY=""
for _ in $(seq 120); do
  curl -sf "http://127.0.0.1:$CDP/json/version" >/dev/null 2>&1 && { READY=1; break; }
  sleep 0.25
done
if [ -z "$READY" ]; then
  echo "ui-test: chrome never opened its debug port on $CDP after 30s — this is a FAILURE,"
  echo "         not the no-browser skip. Using: $CHROME"
  echo "--- chrome.log ---"
  cat "$OUT/chrome.log" 2>/dev/null || echo "(no chrome.log)"
  exit 1
fi

node scripts/ui.test.mjs "$CDP" "$OUT" "http://127.0.0.1:$PORT"
rc=$?
[ "${KEEP:-}" = "1" ] && echo "screenshots: $OUT"
exit $rc
