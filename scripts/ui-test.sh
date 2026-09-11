#!/usr/bin/env bash
# Run scripts/ui.test.mjs against a real headless Chrome. Starts a server and a browser, runs the
# checks, tears both down. Screenshots land in a temp dir and the path is printed at the end.
#
#     scripts/ui-test.sh                     # quiet
#     KEEP=1 scripts/ui-test.sh              # keep the screenshots dir open for inspection
#     REQUIRE_BROWSER=1 scripts/ui-test.sh   # a platform it cannot run on is a FAILURE (CI)
#     OUT=<dir> scripts/ui-test.sh           # put the screenshots somewhere known in advance
#     CHROME=<path> scripts/ui-test.sh       # this browser, rather than whatever find_chrome picks
#     PORT=<n> CDP=<n> scripts/ui-test.sh    # pin the two ports, rather than deriving them
#     scripts/ui-test.sh --ports             # print the pair this checkout would use, and stop
#
# Needs node >= 22 (global WebSocket) and a Chromium. It SKIPS with exit 0 when no browser is
# installed, so it never fails a machine that simply doesn't have one — the service-worker suite
# (scripts/sw.test.mjs) is the one that must always run. On Linux it also wants `xvfb-run`; see
# the pointer note below for what fails without it.
#
# THAT SKIP IS RIGHT FOR A LAPTOP AND WRONG FOR A RUNNER, so `REQUIRE_BROWSER=1` turns it — and
# the two pointer warnings below — into failures. A CI job that quietly loses its Chrome would
# otherwise go GREEN having tested nothing, which is the one failure mode a green suite cannot
# tell you about. `.github/workflows/checks.yml` sets it in both jobs that reach here, including
# the ablate one, which arrives through ablate.py and can pass nothing but the environment.
set -uo pipefail
cd "$(dirname "$0")/.."

# TWO RUNS ON ONE MACHINE MUST NOT TAKE EACH OTHER DOWN. These were fixed at 8765/9333, and the
# clear below matches processes by PATTERN across the whole machine, so a second checkout starting
# up killed the first one's browser and server mid-run — the victim being the run that had done
# nothing wrong (#49). Both patterns embed the port, so distinct ports already did not cross-kill;
# what was missing was a distinct DEFAULT. Deriving it from the checkout's own path gives every
# worktree its own pair while keeping it the SAME on every run here, which is what lets the clear
# still reap a browser left over from an interrupted run in this one — the failure it exists for.
# `pwd -P`, so the same checkout reached through a symlink hashes to the same pair.
#
# 200 slots, so two worktrees CAN still land on one. That is why the pair is printed, why the
# clear says what it is clearing instead of doing it silently, and why both stay overridable.
SLOT=$(( $(pwd -P | cksum | awk '{print $1}') % 200 ))
PORT=${PORT:-$((8765 + SLOT))}
CDP=${CDP:-$((9333 + SLOT))}
# The two bands cannot overlap (8765-8964 against 9333-9532), so one run's server is never
# another's debug port — which would be the same cross-kill wearing a different number.

# Answered out of the path, before anything is started: how a human reads the pair off in order to
# decide what to pin, and how scripts/ui-test.test.py asks without a browser.
if [ "${1:-}" = "--ports" ]; then echo "PORT=$PORT CDP=$CDP"; exit 0; fi
echo "ui-test: server :$PORT, devtools :$CDP"

# EVERY PROBE BELOW IS BOUNDED, because a bare `curl` at one of these ports is not. What can be
# sitting on a derived port is anything at all, and a process that ACCEPTS the connection and then
# never replies hangs the request for as long as it likes — so the runner would stop before it
# started, printing nothing, which is the shape of failure this whole file argues against. Two
# seconds is far past a loopback answer and far short of a wait anybody would sit through.
answers() { curl -sf --connect-timeout 1 -m 2 "http://127.0.0.1:$1" >/dev/null 2>&1; }
# And HELD is a different question from ANSWERS: a squatter owes this script no particular reply.
# chromedriver — whose own default port 9515 is inside the derived band — 404s on /json/version,
# which `curl -sf` reports exactly as it reports an empty port, so a guard written on `answers`
# waves the one process it names through. A TCP connect is the question both clears actually ask.
listening() { python3 -c 'import socket,sys
s = socket.socket(); s.settimeout(1)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)' "$1" 2>/dev/null; }

# Overridable because CI has to know the path BEFORE the run in order to upload what a failure
# left there — `actions/upload-artifact` takes a path, not the one this script prints at the end.
# A DIRECTORY THIS SCRIPT DID NOT CREATE IS NEVER DELETED: cleanup below does `rm -rf "$OUT"`, and
# `OUT=$HOME scripts/ui-test.sh` must not be a way to lose a home directory. So an inherited one is
# only ever written into, and the caller who named it owns clearing it.
if [ -n "${OUT:-}" ]; then OWN=""; mkdir -p "$OUT"
else                       OUT=$(mktemp -d); OWN=1; fi

# THE TRAP IS INSTALLED HERE, NOT BESIDE THE BROWSER, because the exits in between are the ones
# with something to say: a mktemp'd $OUT was leaked by every one of them and its path printed by
# none, so the server log naming the port conflict sat in a directory nobody could find. The kills
# are guarded rather than ordered, since at this point there is nothing yet to kill.
rc=0
SERVER=""; BROWSER=""; XVFB=""
cleanup() {
  [ -n "$SERVER" ] && kill "$SERVER" 2>/dev/null
  if [ -n "$BROWSER" ]; then
    # Chrome is xvfb-run's CHILD, and killing the wrapper leaves it holding $CDP — which is
    # exactly the leftover browser the clear below exists for, arriving one run early.
    if [ -n "$XVFB" ]; then kill -- -"$BROWSER" 2>/dev/null   # the wrapper AND the Xvfb beside it
    else                    kill "$BROWSER" 2>/dev/null; fi
    pkill -f "remote-debugging-port=$CDP" 2>/dev/null
  fi
  # A FAILING RUN IS THE ONE WHOSE EVIDENCE YOU WANT, and it was the one throwing it away: this
  # deleted $OUT unless KEEP=1, so the screenshots, chrome.log and server.log survived only when
  # you had already guessed you would need them — and you guess that after the run, not before.
  # Nothing in the suite asserts on a PNG (it asserts the DOM, which is the better oracle); their
  # whole job is being LOOKED at afterwards. So a run with nothing to explain cleans up, and one
  # with something to explain keeps it and says where.
  if [ "${KEEP:-}" = "1" ] || [ "$rc" -ne 0 ] || [ -z "$OWN" ]; then echo "evidence: $OUT"
  else rm -rf "$OUT"; fi
}
trap cleanup EXIT

# Every stop below goes through here: the reason reaches the terminal AND $OUT, because in CI $OUT
# is the uploaded artifact and an empty one is indistinguishable from a broken upload path
# (`if-no-files-found: error`). A run that stops before it opens a browser has no other evidence.
die() { printf '%s\n' "$@" | tee "$OUT/ui-test.log"; rc=1; exit 1; }

# The three ways this platform can be unable to answer the question the suite is asking: no
# browser at all, the old headless shell (no pointer even under a display), and no X server (no
# pointer either). Each is a warning on a laptop and a failure under REQUIRE_BROWSER — see the
# header. Every call site precedes both the server and the EXIT trap, deliberately — see the note
# at the server launch — so exiting here has nothing to tear down.
required_or_warn() {
  [ -n "${REQUIRE_BROWSER:-}" ] || return 0
  die "ui-test: REQUIRE_BROWSER is set, so a platform this suite cannot run correctly on is a" \
      "         FAILURE here rather than a warning. Nothing above is a bug in the app."
}

find_chrome() {
  local c pw="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"
  # The full Chromium before chrome-headless-shell: only the full build takes a pointer from
  # Xvfb (see below), and Playwright installs either.
  #
  # GOOGLE-CHROME BEFORE CHROMIUM ON A PATH, because on Ubuntu `chromium` is a snap wrapper and
  # this order was chosen by nothing: the second CI run of this suite took /usr/bin/chromium,
  # printed three dbus errors and never opened its debug port inside 30s, while the first run
  # went 250/251 on the same image. A browser that starts sometimes is worse than one that never
  # does, and the vendor build is the one every other line here already assumes.
  for c in \
    "$pw"/chromium-*/chrome-linux/chrome \
    "$pw"/chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell \
    "$pw"/chromium-*/chrome-*/"Google Chrome for Testing.app"/Contents/MacOS/"Google Chrome for Testing" \
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    "$(command -v google-chrome || true)" "$(command -v google-chrome-stable || true)" \
    "$(command -v chromium || true)" "$(command -v chromium-browser || true)"
  do
    [ -n "$c" ] && [ -x "$c" ] && { echo "$c"; return 0; }
  done
  return 1
}

# An explicit browser wins over the search, for the machine whose install this list guesses wrong.
if [ -n "${CHROME:-}" ]; then
  [ -x "$CHROME" ] || die "ui-test: CHROME=$CHROME is not executable"
else
  CHROME=$(find_chrome) || {
    echo "ui-test: no Chromium found — skipping (this is not a failure)"
    required_or_warn
    exit 0
  }
fi
# WHICH BINARY RAN IS EVIDENCE, and it was missing from the one run that needed it: two CI runs of
# the same job behaved differently and the passing one had not said what it was using, so the
# difference could only be inferred. It is one line; print it always.
echo "ui-test: using $CHROME"

# A FRESH profile every run. sw.js serves the shell cache-first, so a reused profile keeps running
# the PREVIOUS edit's JS until V is bumped — you would be testing code you already changed.
# CLEARED rather than merely placed, because an inherited $OUT is not deleted at the end and is
# therefore RE-ENTERED by the next run that names it: `OUT=/tmp/ui` twice around an edit to
# chart.js would serve the first run's shell out of the second run's profile and pass. The freshness
# has to be a property of this line rather than of who owns the directory.
PROFILE="$OUT/profile"
rm -rf "$PROFILE"

# A browser left over from an interrupted run still holds $CDP. The new one then fails to bind and
# node connects to the OLD one -- which has the PREVIOUS build in its service-worker cache, so the
# suite silently tests code you already changed. That is the same trap the fresh profile exists to
# avoid, arriving by a different door; take the port before starting.
# ANYTHING ALREADY ON EITHER PORT IS ABOUT TO BE KILLED, and from here that leftover looks exactly
# like a process which has nothing to do with this suite: a live run in a worktree that derived the
# same slot, or a stranger — the bands are 200 wide and cover ports people use (8888 is Jupyter's
# default, 9515 is chromedriver's). Both are rare and neither may be silent. The kill frees the
# first and takes an innocent bystander down with the second, and either way the run that follows
# would be driving somebody else's server or browser.
for p in "$CDP" "$PORT"; do
  listening "$p" || continue
  echo "ui-test: something already holds $p — clearing it. If that is not this checkout's own"
  echo "         leftover, pin this run with PORT=<n> CDP=<n>."
done
pkill -f "remote-debugging-port=$CDP" 2>/dev/null
pkill -f "http.server $PORT" 2>/dev/null
# Wait for the port to actually close rather than for half a second: nothing to kill costs nothing,
# and a browser slow to die is waited for instead of raced (issue 48, the same shape as the
# readiness loop below).
for _ in $(seq 40); do
  listening "$CDP" || break
  sleep 0.1
done
# A port that never closed was never a leftover of OURS: the pkill matches a Chrome carrying this
# debug port and frees nothing else, so whatever is there is still there. Falling through is the
# trap the paragraph above argues against, arriving one door along — the new Chrome fails to bind,
# the readiness loop below succeeds against the FOREIGN endpoint, and node drives that instead.
# Nothing has been started yet, so stopping here has nothing to tear down (see the server launch).
if listening "$CDP"; then
  die "ui-test: $CDP is still held after 4s, so it is not a browser this run can clear — the" \
      "         pkill matches a Chrome carrying this debug port and frees nothing else, and" \
      "         chromedriver's own default (9515) is inside the derived band. Chrome would fail" \
      "         to bind and node would drive whatever IS there, so this stops: pin CDP=<n>."
fi

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
LAUNCH=("$CHROME" --headless)   # XVFB is initialised at the trap above, which reads it
# A DISPLAY IS NO USE TO A BINARY THAT CANNOT OPEN ONE. `chrome-headless-shell` is the old
# headless build and never makes an X connection, so it reports no pointer under Xvfb exactly as
# it does without — and `find_chrome` PREFERS it, because Playwright's cache is the first glob.
# Running it under the wrapper anyway is the worst of the three outcomes because it is the silent
# one: the warning below is suppressed (xvfb-run is installed), the fix looks to be in effect, and
# section 2 then fails saying the browser is headless while it is running under a display.
case "$CHROME" in
  *chrome-headless-shell|*headless_shell) HEADFUL="" ;;
  *)                                      HEADFUL=1  ;;
esac
if [ "$(uname)" = "Darwin" ]; then
  : # macOS reports (hover:hover) and (pointer:fine) unconditionally; there is nothing to arrange.
elif [ -z "$HEADFUL" ]; then
  echo "ui-test: ${CHROME##*/} is the old headless binary and reports no pointer even under a"
  echo "         display, so the hover checks will fail. Point find_chrome at a full Chrome or"
  echo "         Chromium to run them."
  required_or_warn
elif ! command -v xvfb-run >/dev/null 2>&1; then
  echo "ui-test: no xvfb-run — running headless, where this platform reports NO pointer."
  echo "         Expect 'the desktop viewport really reports a fine pointer' and the hover checks"
  echo "         that depend on it to fail. Install xvfb to run them."
  required_or_warn
else
  XVFB=1
  # A screen bigger than any viewport the suite sets, so nothing is clamped by it. Every section
  # overrides the viewport anyway; this is only the window Chrome opens in.
  # -f puts the X authority file in $OUT, which this script already owns and removes. Without it
  # xvfb-run mktemps a directory of its own and deletes it only from an EXIT trap that a signalled
  # shell never runs, so every run left one behind.
  LAUNCH=(xvfb-run -a -f "$OUT/Xauthority" --server-args="-screen 0 1920x1600x24" "$CHROME")
fi
# --disable-dev-shm-usage because a CI container's /dev/shm is typically 64MB and Chrome dies
# reaching past it, with the only symptom being a debug port that never opens.
#
# `set -m` gives the wrapper its own process group, which is the only handle cleanup has on the X
# server: xvfb-run is /bin/sh, an untrapped SIGTERM kills a shell WITHOUT running its EXIT trap,
# and Xvfb's own name carries no $CDP for the pkill to match. Killing the wrapper alone therefore
# left one X server and one /tmp/.X<n>-lock per run — and `-a` hides that by picking the next free
# display, so it accumulated on a laptop or a long-lived runner without anything going red.
# The server starts HERE, below the three checks above, and not before them: two of those call
# required_or_warn, which exits — and an exit between the launch and the EXIT trap below leaves a
# `python3 -m http.server` holding $PORT with nothing to reap it. The next run's pkill papers over
# that, but only if there is a next run, which in a container there is not.
# -u so the line below arrives: a redirected stdout is block-buffered, and python would hold
# "Serving HTTP" in a buffer until the process exited — i.e. exactly when it is no longer news.
python3 -u -m http.server "$PORT" --bind 127.0.0.1 >"$OUT/server.log" 2>&1 &
SERVER=$!
# A PORT THE SERVER COULD NOT TAKE IS THE WORST OUTCOME HERE, because the suite still RUNS: python
# exits on "Address already in use", node drives Chrome against whatever else is on that port, and
# 252 checks fail at a page this repo did not write — each one after a 4s settle(), with nothing
# on screen saying the server never started.
#
# THE ORACLE IS OUR SERVER'S OWN ANNOUNCEMENT, and nothing weaker survives the case it is for: a
# squatter that answers 200 satisfies any HTTP probe on the first iteration, while our python has
# not reached its bind yet — so `kill -0` still sees a live pid and the run goes on. A stranger
# cannot say this line for us; a python that never bound never prints it, and one whose wording
# changes fails CLOSED, into a message and the log rather than into a silent green run.
for _ in $(seq 40); do
  grep -q "^Serving HTTP" "$OUT/server.log" 2>/dev/null && break
  kill -0 "$SERVER" 2>/dev/null || break
  sleep 0.1
done
if ! grep -q "^Serving HTTP" "$OUT/server.log" 2>/dev/null; then
  die "ui-test: the server never took $PORT — something else is holding it, and the derived band" \
      "         covers ports people use (8888 is Jupyter's). Pin another with PORT=<n>." \
      "--- server.log ---" "$(cat "$OUT/server.log" 2>/dev/null || echo "(no server.log)")"
fi

[ -n "$XVFB" ] && set -m
"${LAUNCH[@]}" --disable-gpu --no-sandbox --hide-scrollbars --disable-dev-shm-usage \
  --no-first-run --no-default-browser-check --disable-search-engine-choice-screen \
  --remote-debugging-port="$CDP" --user-data-dir="$PROFILE" about:blank >"$OUT/chrome.log" 2>&1 &
BROWSER=$!
set +m

# 30s, not 10: a cold CI runner is slower than a warm laptop, and the old budget expired into a
# bare ECONNREFUSED from node with chrome.log already deleted by the EXIT trap — a failure that
# says only "the port is shut", never why. Say why.
READY=""
for _ in $(seq 120); do
  answers "$CDP/json/version" && { READY=1; break; }
  sleep 0.25
done
if [ -z "$READY" ]; then
  die "ui-test: chrome never opened its debug port on $CDP after 30s — this is a FAILURE," \
      "         not the no-browser skip. Using: $CHROME" \
      "--- chrome.log ---" "$(cat "$OUT/chrome.log" 2>/dev/null || echo "(no chrome.log)")"
fi

node scripts/ui.test.mjs "$CDP" "$OUT" "http://127.0.0.1:$PORT"
rc=$?
exit $rc
