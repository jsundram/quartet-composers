#!/usr/bin/env python3
# pwa-starter: none — this script is this repo's own
# /// script
# requires-python = ">=3.9"
# ///
"""Cache a monthly page-view SERIES per composer -> data/pageviews.json.

    python3 scripts/fetch_views.py                # top up through the last complete month
    python3 scripts/fetch_views.py --months 24    # widen the window
    python3 scripts/fetch_views.py --force        # refetch even months already cached
    python3 scripts/fetch_views.py --dry-run      # fetch and report, write nothing

WHY A SERIES AND NOT A NUMBER. Dot size is the most visually dominant channel on the chart and
page views are the noisiest input to it. Measured against a 12-month window, a single month is off
the median by 12% typically and 29% at worst, and August is a seasonal trough that every sampled
composer fell below. Philip Glass has a month at 2.13x his median. Sizing dots from one month
means a chunk of the picture is weather.

The fix costs nothing: `monthly` granularity returns EVERY month in the requested range from ONE
request, so twelve months of data is the same ~880 calls that one month was. build_data.py takes
the MEDIAN, which ignores a death-or-anniversary spike instead of baking it in permanently.

Storing the raw series rather than the computed statistic means the statistic can be changed
without touching the network, a refresh only fetches months it does not already have, and the app
can show a sparkline for free.

TITLES MUST BE CANONICAL. Views are counted per title and a redirect is its own title with its own
tiny count: asking for "Bela Bartok" returns 41 instead of Béla Bartók's 14,330, with a 200 and no
error. Canonical titles come from data/people.json (scripts/fetch_wikidata.py). Run that first.

WHAT THIS DOES NOT DO: re-scrape the composer list (scripts/scrape_list.py) or re-read birth and
death dates (scripts/fetch_wikidata.py).

AFTERWARDS: composers.json is precached in sw.js. Bump V or the new numbers reach the repo and
nobody's phone. scripts/sw-lint.py will remind you.
"""
import argparse
import calendar
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
PEOPLE = os.path.join(ROOT, "data", "people.json")
OUT = os.path.join(ROOT, "data", "pageviews.json")

API = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
       "en.wikipedia/all-access/user/{title}/monthly/{start}/{end}")
UA = "quartet-composers/1.0 (https://github.com/jsundram/quartet-composers)"

# Tuned against the real limiter, not the published headline rate: 0.06s/req drew a 429 about 300
# titles in. 0.15s (~7/s) runs the full list clean, and the whole job is ~2 minutes either way.
PAUSE = 0.15
TRIES = 5
BACKOFF = [2, 5, 15, 40]

# The API has no per-article data before this. Anything earlier came from a different measurement
# system (the pre-2015 dumps / stats.grok.se) and is NOT comparable to what this fetches — which
# is why the 2014 numbers are archived rather than plotted alongside these.
FLOOR = "2015-07"


def months_back(n, end=None):
    """The n complete months ending with `end` (default: the last complete month), as YYYY-MM."""
    if end is None:
        first_of_now = dt.date.today().replace(day=1)
        end = first_of_now - dt.timedelta(days=1)
    else:
        y, m = int(end[:4]), int(end[5:7])
        end = dt.date(y, m, calendar.monthrange(y, m)[1])
    out = []
    y, m = end.year, end.month
    for _ in range(n):
        out.append("%04d-%02d" % (y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return sorted(v for v in out if v >= FLOOR)


def stamps(months):
    """REST start/end covering the whole span. `monthly` needs a range that SPANS full months —
    passing the same first-of-month for both ends returns 400 'no full months between dates'."""
    sy, sm = int(months[0][:4]), int(months[0][5:7])
    ey, em = int(months[-1][:4]), int(months[-1][5:7])
    return ("%04d%02d0100" % (sy, sm),
            "%04d%02d%02d00" % (ey, em, calendar.monthrange(ey, em)[1]))


def fetch(title, months):
    """{'YYYY-MM': views} for one article. None means the article has no data at all (404)."""
    start, end = stamps(months)
    url = API.format(title=urllib.parse.quote(title.replace(" ", "_"), safe=""),
                     start=start, end=end)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(TRIES):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                items = json.load(r).get("items") or []
            return {"%s-%s" % (i["timestamp"][:4], i["timestamp"][4:6]): i["views"] for i in items}
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (429, 500, 502, 503) and attempt < TRIES - 1:
                wait = BACKOFF[min(attempt, len(BACKOFF) - 1)]
                try:                                  # honor Retry-After; it knows better
                    wait = max(wait, int(e.headers.get("Retry-After", 0)))
                except (TypeError, ValueError):
                    pass
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < TRIES - 1:
                time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
                continue
            raise
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--months", type=int, default=12, help="window length (default 12)")
    ap.add_argument("--end", help="last month of the window, YYYY-MM (default: last complete)")
    ap.add_argument("--force", action="store_true", help="refetch months already cached")
    ap.add_argument("--dry-run", action="store_true", help="write nothing")
    args = ap.parse_args()

    want = months_back(args.months, args.end)
    if not want:
        print("no months in range (the API has nothing before %s)" % FLOOR, file=sys.stderr)
        return 2

    with open(PEOPLE, encoding="utf-8") as f:
        people = json.load(f)
    titles = sorted({p["canonical"] for p in people.values()})

    cached = {"months": [], "series": {}}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            cached = json.load(f)
    series = cached.get("series", {})

    print("window %s .. %s (%d months), %d articles" % (want[0], want[-1], len(want), len(titles)))
    todo = []
    for t in titles:
        have = series.get(t, {})
        if args.force or any(m not in have for m in want):
            todo.append(t)
    print("  %d need fetching, %d already complete" % (len(todo), len(titles) - len(todo)))

    missing, failed = [], []
    for i, t in enumerate(todo, 1):
        try:
            got = fetch(t, want)
        except Exception as e:                        # noqa: BLE001 - any transport failure
            # NEVER let one title abort the run: a 429 at title 300 used to raise out of main()
            # and discard 300 good fetches.
            failed.append("%s (%s)" % (t, e))
            got = None
        if got is None:
            missing.append(t)
        else:
            series.setdefault(t, {}).update(got)
        if i % 25 == 0 or i == len(todo):
            print("  %d/%d" % (i, len(todo)), end="\r", flush=True)
        time.sleep(PAUSE)
    if todo:
        print()

    if missing:
        print("%d articles returned no data (no series stored):" % len(missing))
        for t in missing:
            print("   " + t)
    if failed:
        print("%d failed after %d retries - rerun to pick them up:" % (len(failed), TRIES))
        for t in failed:
            print("   " + t)

    covered = sum(1 for t in titles if all(m in series.get(t, {}) for m in want))
    print("\n%d/%d articles have the full %d-month window" % (covered, len(titles), len(want)))

    if args.dry_run:
        print("dry run - data/pageviews.json unchanged")
        return 0

    out = {
        "fetched": dt.date.today().isoformat(),
        "months": want,
        "note": "monthly English Wikipedia page views (agent=user), by canonical article title",
        "series": {k: dict(sorted(v.items())) for k, v in sorted(series.items())},
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0)
    print("wrote data/pageviews.json (%d articles, %d bytes)" % (len(series), os.path.getsize(OUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
