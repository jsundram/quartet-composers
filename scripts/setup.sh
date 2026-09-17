#!/usr/bin/env bash
# Enable this clone's pre-commit hook. Run once after cloning; safe to re-run.
#
#     scripts/setup.sh           # enable it
#     scripts/setup.sh --check   # is it enabled? exit 1 if not, and change nothing
#                                # anything else: exit 2, having done nothing
#
# WHY A SCRIPT AND NOT A LINE IN THE README. git will not let a repo point at its own hooks on
# clone — deliberately, since cloning must never run code the repo controls — so SOMETHING has to
# run once per checkout, and a README line is the something that gets read once and then not: every
# session in a fresh container has committed with the hook disabled.
#
# WHAT THAT COSTS IS NOT LISTED HERE. .githooks/pre-commit runs them and says what each one is for,
# so it is the copy that moves when the set does; enumerating them again is the drift this script
# exists to argue against, and this header carried two of it — a count that was wrong, and a claim
# that CI could not report these, written before the run that reports two of them.
#
# IT NEVER OVERWRITES A DIFFERENT ANSWER. A core.hooksPath already set is somebody's arrangement,
# and taking it over is a worse outcome than not being enabled — so it says so and exits NONZERO,
# because a clone whose lints will not run must not report success and nothing reads stderr. That
# is the one case where a plain run fails; enabling it, and finding it already enabled, both exit
# 0. .claude/hooks/session-start.sh swallows the code deliberately, since a session must not die
# over this — the message still reaches its log.
set -euo pipefail

WANT=".githooks"
cd "$(dirname "$0")/.."

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "setup: not a git checkout — nothing to enable" >&2
  exit 1
fi

# --local, not the effective value: a global core.hooksPath would read as enabled here and then not
# be, because it points somewhere else entirely.
cur="$(git config --local --get core.hooksPath || true)"

# MATCHED, not tested for equality. `[ "$1" = --check ] && check=1` reads every other argument as a
# plain run, so `-check`, a typo, or a future `--dry-run` took the write path — the one invocation
# whose entire promise is "change nothing" changing the clone, silently and with exit 0.
check=0
case "${1:-}" in
  "")       ;;
  --check)  check=1 ;;
  *) echo "setup: unknown argument \"$1\" — nothing done (try --check)" >&2; exit 2 ;;
esac

if [ "$cur" = "$WANT" ]; then
  echo "setup: pre-commit hook enabled ($WANT)"
  exit 0
fi

if [ -n "$cur" ]; then
  echo "setup: core.hooksPath is \"$cur\", not $WANT — leaving it as it is." >&2
  echo "       this clone's pre-commit lints will not run. See .githooks/pre-commit." >&2
  exit 1
fi

if [ "$check" = 1 ]; then
  echo "setup: pre-commit hook NOT enabled — run scripts/setup.sh" >&2
  exit 1
fi

git config --local core.hooksPath "$WANT"
# Names the DIRECTORY, not its contents: a list here is a second copy of .githooks/pre-commit's,
# and the reader's next step is to read that file anyway.
echo "setup: pre-commit hook enabled ($WANT) — see .githooks/pre-commit for what it runs"
