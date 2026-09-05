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

TITLES ARE RESOLVED FIRST, AND THAT STEP IS THE WHOLE BALL GAME. Pageviews are counted PER TITLE,
and a redirect is its own title with its own (tiny) count. The 2014 scrape stored ASCII-stripped
names — "Bela Bartok", "Camille Saint-Saens" — which exist on Wikipedia as redirects. Asking the
pageviews API for those returns the handful of hits that arrived through the redirect, not the
article's traffic: Bartók came back as 41 views instead of 14,330, a 350x undercount that looks
exactly like a composer nobody reads. It does not 404, so nothing complains.

So every name goes through the MediaWiki API with redirects=1 first (batched 50 at a time, ~10
requests for the whole list), and pageviews are requested for the CANONICAL title. The resolved
title is stored in data/views.json's "titles" map and becomes the composer's display name, which
is how the table ends up spelling Dvořák correctly.

WHAT IT DOES NOT DO: re-scrape the composer list. Names, birth/death years and quartet counts come
from data/composers_raw.json, a frozen May 2014 artifact, and nothing here touches it — so a
composer added to Wikipedia's list since 2014 is still absent, and someone who died since 2014
still has no death year. Only the view counts and the spelling of names are refreshed.

A name the API cannot resolve keeps its previous value rather than silently becoming zero — a zero
renders as "obscure" in the chart, which is a lie of a different kind than "stale".

AFTERWARDS: composers.json is a SHELL file in sw.js. Bump V or the new numbers never reach an
installed copy — see THE ONE RULE at the top of sw.js. scripts/sw-lint.py will remind you.
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
VIEWS = os.path.join(ROOT, "data", "views.json")
COMPOSERS = os.path.join(ROOT, "data", "composers_raw.json")

API = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
       "en.wikipedia/all-access/user/{title}/monthly/{start}/{end}")
WIKI_API = "https://en.wikipedia.org/w/api.php"
BATCH = 50                      # MediaWiki's titles= limit for an anonymous client
# The API rejects a generic agent. A contactable one is the documented etiquette, not a nicety.
UA = "quartet-composers/1.0 (https://github.com/jsundram/quartet-composers)"

# Politeness, tuned against the real limiter rather than the published headline rate. 0.06s/req
# (~16/s) drew a 429 about 300 titles in; 0.15s (~7/s) runs the full list clean. The whole job is
# under two minutes either way, so there is nothing to win by pushing it.
PAUSE = 0.15
TRIES = 5
BACKOFF = [2, 5, 15, 40]        # seconds, used when the response carries no Retry-After


def last_complete_month():
    first_of_this = dt.date.today().replace(day=1)
    prev = first_of_this - dt.timedelta(days=1)
    return "%04d-%02d" % (prev.year, prev.month)


def resolve(names):
    """{name: canonical Wikipedia title} for every name the API can place.

    Two different corrections happen here and both matter. `normalized` fixes capitalization and
    underscores; `redirects` follows "Bela Bartok" -> "Béla Bartók". A name with no article comes
    back under `pages` with a "missing" key and is simply left out of the result — the caller keeps
    whatever it had.
    """
    out = {}
    for i in range(0, len(names), BATCH):
        chunk = names[i:i + BATCH]
        q = urllib.parse.urlencode({
            "action": "query", "format": "json", "redirects": "1",
            "titles": "|".join(chunk),
        })
        req = urllib.request.Request(WIKI_API + "?" + q,
                                     headers={"User-Agent": UA, "Accept": "application/json"})
        for attempt in range(TRIES):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.load(r).get("query", {})
                break
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
                if attempt == TRIES - 1:
                    raise
                time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])

        # Chase name -> normalized -> redirect, in that order, then confirm the endpoint exists.
        step = {}
        for m in data.get("normalized", []):
            step[m["from"]] = m["to"]
        for m in data.get("redirects", []):
            step[m["from"]] = m["to"]
        real = {p["title"] for p in data.get("pages", {}).values() if "missing" not in p}
        for name in chunk:
            t = name
            for _ in range(4):                      # redirect chains are short; cap anyway
                if t in step and step[t] != t:
                    t = step[t]
                else:
                    break
            if t in real:
                out[name] = t
        print("  resolved %d/%d" % (min(i + BATCH, len(names)), len(names)), end="\r", flush=True)
        time.sleep(PAUSE)
    print()
    return out


def month_range(month):
    """(start, end) REST timestamps covering exactly the given YYYY-MM.

    `monthly` granularity wants a range that SPANS a full month, not one that names it: passing
    the same first-of-month stamp for both ends returns 400 "no full months between dates". So
    end is the LAST day of the month, not the first of the next — using the next month's first
    would return two items (the second an incomplete current month) and invite an off-by-one.
    """
    y, m = int(month[:4]), int(month[5:7])
    last = calendar.monthrange(y, m)[1]
    return "%04d%02d0100" % (y, m), "%04d%02d%02d00" % (y, m, last)


def fetch(title, month, tries=TRIES):
    want = month.replace("-", "") + "0100"
    start, end = month_range(month)
    url = API.format(title=urllib.parse.quote(title.replace(" ", "_"), safe=""),
                     start=start, end=end)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                items = json.load(r).get("items") or []
                # Match the timestamp rather than taking items[0]: a widened range would
                # otherwise silently attribute another month's traffic to this one.
                for it in items:
                    if it.get("timestamp") == want:
                        return it["views"]
                return 0
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None                       # no such article this month — caller keeps the old value
            if e.code in (429, 500, 502, 503) and attempt < tries - 1:
                # Honor Retry-After when the limiter sends one; it knows better than a guess.
                wait = BACKOFF[min(attempt, len(BACKOFF) - 1)]
                try:
                    wait = max(wait, int(e.headers.get("Retry-After", 0)))
                except (TypeError, ValueError):
                    pass
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < tries - 1:
                time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
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

    with open(VIEWS, encoding="utf-8") as f:
        blob = json.load(f)
    with open(COMPOSERS, encoding="utf-8") as f:
        composers = json.load(f)

    # Names come from the COMPOSER LIST, not from views.json's own keys. Deriving the work list
    # from the file being rewritten made the set of titles self-perpetuating: a wrong key stayed
    # wrong forever because it was the only record of what to ask for.
    import build_data                                  # RENAMES lives there; one source of truth
    names = sorted({build_data.RENAMES.get(c[0], c[0]) for c in composers if c[3] > 0})
    raw_of = {build_data.RENAMES.get(c[0], c[0]): c[0] for c in composers if c[3] > 0}

    # Resolve the DISAMBIGUATED title where one is known. Handing the bare name to the resolver
    # is what put the second President of the United States on this chart.
    probe = {n: build_data.DISAMBIG.get(n, n) for n in names}
    print("resolving %d titles through the MediaWiki API..." % len(names))
    resolved = resolve(sorted(set(probe.values())))
    canon = {n: resolved[probe[n]] for n in names if probe[n] in resolved}
    unresolved = [n for n in names if n not in canon]
    changed = {n: t for n, t in canon.items() if t != n}
    print("  %d resolved, %d changed spelling, %d unresolved" % (len(canon), len(changed), len(unresolved)))

    prev = blob.get("views", {})
    out, missing = {}, []
    titles = names

    failed = []
    print("fetching %s page views..." % args.month)
    for i, name in enumerate(titles, 1):
        title = canon.get(name, name)
        # NEVER let one title abort the run. A 429 at title 300 used to raise straight out of
        # main() and discard 300 good fetches — losing several minutes of somebody else's rate
        # limit to recover nothing. Retries are exhausted inside fetch(); if it still fails, keep
        # the previous number and carry on, then report both lists at the end.
        try:
            n = fetch(title, args.month) if name in canon else None
        except Exception as e:                     # noqa: BLE001 - any transport failure, same handling
            failed.append("%s (%s)" % (title, e))
            n = None
        key = raw_of.get(name, name)               # views stay keyed by the COMPOSER-LIST name
        if n is None:
            if not failed or not failed[-1].startswith(title):
                missing.append(title)
            out[key] = prev.get(key, prev.get(name, prev.get(title, 0)))
        else:
            out[key] = n
        if i % 25 == 0 or i == len(titles):
            print("  %d/%d" % (i, len(titles)), end="\r", flush=True)
        time.sleep(PAUSE)
    print()

    if missing:
        print("%d titles had no data for %s (previous value kept):" % (len(missing), args.month))
        for t in missing:
            print("  " + t)
    if failed:
        print("%d titles failed after %d retries (previous value kept) — rerun to pick them up:"
              % (len(failed), TRIES))
        for t in failed:
            print("  " + t)

    if args.dry_run:
        print("dry run — data/views.json unchanged")
        return 0

    blob["month"] = args.month
    # The resolved title is what makes the NEXT run correct, and what build_data.py uses as the
    # display name. Keyed by composer-list name, same as views.
    blob["titles"] = {raw_of.get(n, n): t for n, t in sorted(canon.items())}
    blob["views"] = dict(sorted(out.items()))
    with open(VIEWS, "w", encoding="utf-8") as f:
        json.dump(blob, f, indent=0, ensure_ascii=False)
    print("wrote data/views.json for %s" % args.month)

    os.system("%s %s" % (sys.executable, os.path.join(HERE, "build_data.py")))
    print("\nNow bump V in sw.js — composers.json is a precached SHELL file and will not otherwise "
          "reach an installed copy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
