#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Refresh data/views.json from the Wikimedia Pageviews API, then rebuild composers.json.

The shipped numbers are a May 2014 snapshot — the same month the composer list was scraped. That
is fine as history (and the UI says so plainly), but "who do people actually read about" moves,
so this makes the number refreshable in one command instead of a scraping project.

    python3 scripts/fetch_views.py                 # the most recent COMPLETE month
    python3 scripts/fetch_views.py --month 2026-01
    python3 scripts/fetch_views.py --month 2026-01 --dry-run

Stdlib only, no pip packages — same rule as the other scripts here.

WHAT IT DOES NOT DO: re-scrape the composer list. The titles it queries are the keys already in
data/views.json, i.e. the 2014 article names. Wikipedia renames and merges articles, so expect a
handful of 404s on a modern run; they are reported by name and keep their previous value rather
than silently becoming zero — a zero would render as "obscure" in the chart, which is a lie of a
different kind than "stale". Fix a persistent 404 by renaming the key in data/views.json (and
adding an ALIASES entry in build_data.py if the composer-list spelling also differs).

AFTERWARDS: composers.json is a SHELL file in sw.js. Bump V or the new numbers never reach an
installed copy — see THE ONE RULE at the top of sw.js. scripts/sw-lint.py will remind you.
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VIEWS = os.path.join(ROOT, "data", "views.json")

API = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
       "en.wikipedia/all-access/user/{title}/monthly/{start}/{end}")
# The API rejects a generic agent. A contactable one is the documented etiquette, not a nicety.
UA = "quartet-composers/1.0 (https://github.com/jsundram/quartet-composers)"


def last_complete_month():
    first_of_this = dt.date.today().replace(day=1)
    prev = first_of_this - dt.timedelta(days=1)
    return "%04d-%02d" % (prev.year, prev.month)


def fetch(title, month, tries=3):
    stamp = month.replace("-", "") + "0100"
    url = API.format(title=urllib.parse.quote(title.replace(" ", "_"), safe=""),
                     start=stamp, end=stamp)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                items = json.load(r).get("items") or []
                return items[0]["views"] if items else 0
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None                       # no such article this month — caller keeps the old value
            if e.code in (429, 500, 502, 503) and attempt < tries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < tries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--month", default=last_complete_month(), help="YYYY-MM (default: last complete month)")
    ap.add_argument("--dry-run", action="store_true", help="fetch and report, write nothing")
    args = ap.parse_args()

    try:
        dt.datetime.strptime(args.month, "%Y-%m")
    except ValueError:
        print("--month must look like 2026-01", file=sys.stderr)
        return 2

    with open(VIEWS) as f:
        blob = json.load(f)
    titles = sorted(blob["views"])
    out, missing = {}, []

    for i, title in enumerate(titles, 1):
        n = fetch(title, args.month)
        if n is None:
            missing.append(title)
            out[title] = blob["views"][title]      # keep the old number rather than inventing a 0
        else:
            out[title] = n
        if i % 25 == 0 or i == len(titles):
            print("  %d/%d" % (i, len(titles)), end="\r", flush=True)
        time.sleep(0.06)                           # ~16 req/s; well inside the published limits
    print()

    if missing:
        print("%d titles had no data for %s (previous value kept):" % (len(missing), args.month))
        for t in missing:
            print("  " + t)

    if args.dry_run:
        print("dry run — data/views.json unchanged")
        return 0

    blob["month"] = args.month
    blob["views"] = out
    with open(VIEWS, "w") as f:
        json.dump(blob, f, indent=0)
    print("wrote data/views.json for %s" % args.month)

    os.system("%s %s" % (sys.executable, os.path.join(HERE, "build_data.py")))
    print("\nNow bump V in sw.js — composers.json is a precached SHELL file and will not otherwise "
          "reach an installed copy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
