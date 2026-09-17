#!/usr/bin/env bash
# Enable this checkout's pre-commit hook, every session, without being asked.
#
# There is nothing to install here — this repo ships no dependencies and has no build step — so the
# one thing a fresh checkout needs is the thing git will not do for it: point core.hooksPath at
# .githooks. Sessions run in a container cloned from scratch, which is exactly the case that has
# been committing with the lints disabled.
#
# Synchronous and near-instant: it is one `git config`.
#
# `|| true`, and NOT exec: setup.sh exits nonzero on the one case it declines — a core.hooksPath
# somebody else set — because a clone whose lints will not run must not report success. That is the
# right answer for a person running it and the wrong one here, where a nonzero exit is a session
# that failed to start. The message it printed is still in this hook's log.
set -euo pipefail
bash "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}/scripts/setup.sh" || true
