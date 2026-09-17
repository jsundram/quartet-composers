#!/usr/bin/env bash
# Enable this checkout's pre-commit hook, every session, without being asked.
#
# There is nothing to install here — this repo ships no dependencies and has no build step — so the
# one thing a fresh checkout needs is the thing git will not do for it: point core.hooksPath at
# .githooks. Sessions run in a container cloned from scratch, which is exactly the case that has
# been committing with the lints disabled.
#
# Synchronous and near-instant: it is one `git config`. setup.sh is idempotent and reports rather
# than failing when somebody has set core.hooksPath deliberately, so this never blocks a session.
set -euo pipefail
exec bash "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}/scripts/setup.sh"
