#!/usr/bin/env python3
# pwa-starter: none — this script is this repo's own
# /// script
# requires-python = ">=3.9"
# ///
"""Bring the page-view data up to the last complete month, or do nothing.

    python3 scripts/refresh.py            # top up if a month has completed since the last build
    python3 scripts/refresh.py --check    # say whether one is due; exit 1 if it is, touch nothing
    python3 scripts/refresh.py --force    # run the stages even if the data is already current

WHY THIS EXISTS. The readership numbers go stale silently: nothing on the page looks wrong when
the medians are eight months old, it just quietly stops being a chart about now. Running the
pipeline by hand is four commands and a version bump, which is exactly the sort of chore that does
not happen. .github/workflows/refresh.yml runs this on the 3rd of each month and opens a PR when
it changes something.

WHAT MAKES IT A NO-OP. Not a timestamp, and not "have I run this month" — the question that
actually matters is whether composers.json already covers the last COMPLETE month, which is the
newest month the pageviews API can answer for. If it does, there is nothing to fetch and this
exits 0 having touched nothing, so running it daily costs one file read. If it does not, the
window has moved and every stage below is needed.

WHAT IT DOES NOT DECIDE. It does not re-scrape the composer list or re-read Wikidata: those change
for editorial reasons, not on a schedule, and a roster that grows by three composers overnight
with nobody looking is how a bad parse ships. Readership is the one input that is stale purely
because time passed.

THE VERSION BUMP IS PART OF THE JOB. composers.json and readership.json are precached, so new
numbers that ship without a new V in sw.js reach the repo and nobody's installed copy. That is
invariant 1, and forgetting it is the single most common way this app has "not updated".
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def last_complete_month(today=None):
    """The newest month the pageviews API can answer for, as YYYY-MM."""
    today = today or dt.date.today()
    first = today.replace(day=1)
    end = first - dt.timedelta(days=1)
    return "%04d-%02d" % (end.year, end.month)


def current_window_end():
    """The last month composers.json's statistic covers, or None if it has never been built."""
    try:
        with open(os.path.join(ROOT, "composers.json"), encoding="utf-8") as f:
            months = (json.load(f).get("meta") or {}).get("views_months") or []
        return months[-1] if months else None
    except (OSError, ValueError):
        return None


def bump_version():
    """Increment the numeric tail of sw.js's V. Returns the new value, or None if it didn't move.

    Only the tail: sw-lint.py checks that app.js's VER_PREFIX still matches the STEM, so renaming
    that half here would break the version tag in the header silently."""
    path = os.path.join(ROOT, "sw.js")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    # Anchored to the declaration, like sw-lint.py's own reader: sw.js's comments cite version
    # names as examples, so a first-match-anywhere scan would rewrite a comment.
    m = re.search(r'(const V\s*=\s*")([^"]*?)(\d+)(";)', src)
    if not m:
        return None
    new = "%s%s%d%s" % (m.group(1), m.group(2), int(m.group(3)) + 1, m.group(4))
    with open(path, "w", encoding="utf-8") as f:
        f.write(src[:m.start()] + new + src[m.end():])
    return m.group(2) + str(int(m.group(3)) + 1)


def run(*cmd):
    print("\n$ %s" % " ".join(cmd))
    out = subprocess.run([sys.executable, os.path.join(HERE, cmd[0])] + list(cmd[1:]),
                         cwd=ROOT, text=True)
    return out.returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="report only; exit 1 if a refresh is due")
    ap.add_argument("--force", action="store_true", help="run even if already current")
    args = ap.parse_args()

    want, have = last_complete_month(), current_window_end()
    due = have != want
    print("last complete month %s; composers.json covers through %s" % (want, have or "(nothing)"))

    if args.check:
        print("refresh %s" % ("DUE" if due else "not needed"))
        return 1 if due else 0
    if not due and not args.force:
        print("up to date — nothing fetched, nothing written")
        return 0

    # fetch_views.py is the only stage that touches the network, and it only asks for months it
    # does not already hold. build_data.py then rebuilds BOTH shipped files from the caches.
    for stage in (("fetch_views.py",), ("build_data.py",), ("validate.py",)):
        rc = run(*stage)
        if rc != 0:
            print("\n%s failed (exit %d) — nothing was version-bumped" % (stage[0], rc),
                  file=sys.stderr)
            return rc

    # Only after validate.py passes: a bumped V that ships a dataset the gate rejected is worse
    # than a stale one, because it pushes the bad numbers to every installed copy.
    #
    # Outside a git checkout there is nothing to compare against, so the bump happens — a spurious
    # generation costs one re-download, while a missed one is invariant 1's failure and reaches
    # nobody.
    git = subprocess.run(["git", "-C", ROOT, "status", "--porcelain",
                          "composers.json", "readership.json", "data/pageviews.json"],
                         capture_output=True, text=True)
    if git.returncode == 0 and not git.stdout.strip():
        print("\nthe data did not actually change — no version bump")
        return 0
    v = bump_version()
    print("\nbumped sw.js V to %s — precached files changed, so installed copies need a new "
          "generation to see them" % v)
    return 0


if __name__ == "__main__":
    sys.exit(main())
