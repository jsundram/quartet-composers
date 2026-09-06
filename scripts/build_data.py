#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Combine the three cached sources into the two files the app fetches.

    data/list.json       scrape_list.py     roster + quartet counts + prose dates
    data/people.json     fetch_wikidata.py  canonical titles + P569/P570 dates + P21 gender
    data/pageviews.json  fetch_views.py     every monthly view count the API has, per article
                      -> composers.json     the roster: one row per composer, one number for views
                      -> readership.json    the HISTORY: the whole monthly series, per composer

    python3 scripts/build_data.py

NOTHING HERE TOUCHES THE NETWORK. Every input is a committed cache, so the statistic below can be
changed and the dataset rebuilt offline, and the exact bytes that produced a deploy stay in git.

THE VIEW NUMBER IS A MEDIAN, NOT A MONTH. Dot size is the loudest channel on the chart and page
views are its noisiest input: a single month sits 12% off the 12-month median typically and 29% at
worst, August is a seasonal trough, and one composer has a month at 2.13x his own median. The
median ignores an anniversary or obituary spike rather than baking it in. min and max ship too, so
the detail panel can show the spread instead of implying a precision that isn't there.

AND IT IS TWELVE MONTHS, NOT THE WHOLE CACHE. fetch_views.py now caches everything back to
2015-07, but the chart's question is "how much read is this composer NOW", so the statistic is
still the median of the LAST TWELVE cached months (STAT_MONTHS). Widening it would quietly change
every dot on the chart and bake a 2016 readership into a 2026 picture — Kaija Saariaho's
all-history median is 2,340 against 2,840 for the last year, and her obituary month is 42,195.

WHY THE HISTORY IS A SECOND FILE. composers.json is a BOOT dependency: sw.js serves it before the
page can paint anything at all, and 884 monthly series is more than ten times the size of the
roster itself. The sparkline is the one thing in this app that nothing else needs, so it is the
one thing that loads on its own — precached like everything else, fetched after the first paint,
and simply absent if it never arrives. Keyed by DISPLAY name (what composers.json rows carry),
because that is what the app has in hand when it draws the panel.

WHAT "LIVING" MEANS NOW. It is `death is None` as of the last fetch_wikidata.py run — a fact about
today, from a structured claim. The old dataset inferred it by testing `birth + lifespan == 2014`
against a field that stored age-in-2014 for the living, which meant refreshing anything risked
silently reclassifying 139 people. That whole mechanism is gone.

UNKNOWNS STAY NULL. A composer whose count the page's prose doesn't state gets quartets: null and
is listed in the table but not plotted; an article with no page-view data gets views: null; a
composer with no P21 claim gets gender: null. The alternative — carrying a 2014 number forward —
silently mixes a pre-2015 measurement system into a 2026 dataset, and renders as a confident dot
either way. For gender the alternative would be worse still: the only way to fill that null is to
guess from a name, which is a guess about a person and is what invariant 10 exists to forbid.
"""
import datetime as dt
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LIST = os.path.join(ROOT, "data", "list.json")
PEOPLE = os.path.join(ROOT, "data", "people.json")
VIEWS = os.path.join(ROOT, "data", "pageviews.json")
OUT = os.path.join(ROOT, "composers.json")
HIST_OUT = os.path.join(ROOT, "readership.json")

# Wikipedia's parenthetical qualifier is a URL disambiguator, not part of anybody's name, and every
# row on this chart is a composer already.
QUALIFIER = re.compile(r"\s*\((?:composer|musician|conductor|violinist|pianist|[^)]*musician)\)$", re.I)

# How many of the cached months the headline view statistic is measured over. A year smooths the
# seasonal trough without reaching back into a readership that is no longer current.
STAT_MONTHS = 12


def main():
    with open(LIST, encoding="utf-8") as f:
        listing = json.load(f)
    with open(PEOPLE, encoding="utf-8") as f:
        people = json.load(f)
    with open(VIEWS, encoding="utf-8") as f:
        pv = json.load(f)
    history, series = pv["months"], pv["series"]
    # The statistic's window: the last twelve cached months. Not the whole cache — see the header.
    months = history[-STAT_MONTHS:]

    # canon_of survives the sort below; `seen` maps a canonical title to a row INDEX, and those
    # indices are meaningless the moment rows.sort() runs. Keying the history by NAME instead
    # (the sort is stable on nothing that changes it) is what keeps each series on its own
    # composer — validate.py's check_history caught this exact mix-up.
    rows, seen, dropped, canon_of = [], {}, [], {}
    for e in listing["entries"]:
        title = e["title"]
        p = people.get(title, {})
        canon = p.get("canonical", title)
        birth, death = p.get("birth", e["birth"]), p.get("death", e["death"])
        gender = p.get("gender")
        if birth is None:
            dropped.append((title, "no birth year"))
            continue
        if death is not None and death < birth:
            dropped.append((title, "death %s before birth %s" % (death, birth)))
            continue

        vals = [series.get(canon, {}).get(m) for m in months]
        vals = [v for v in vals if v is not None]
        if vals:
            views = int(statistics.median(vals))
            lo, hi = min(vals), max(vals)
        else:
            views = lo = hi = None

        name = QUALIFIER.sub("", canon)
        # Two list entries can resolve to one article (an alias and the real title). Keep the
        # richer row rather than letting the later one silently win.
        row = [name, birth, death, e["quartets"], views, lo, hi, gender]
        if canon in seen:
            prev = rows[seen[canon]]
            better = sum(x is not None for x in row) > sum(x is not None for x in prev)
            if better:
                rows[seen[canon]] = row
            dropped.append((title, "duplicate of %s" % canon))
            continue
        seen[canon] = len(rows)
        canon_of[name] = canon
        rows.append(row)

    rows.sort(key=lambda r: (r[1], r[0]))

    living = sum(1 for r in rows if r[2] is None)
    no_count = sum(1 for r in rows if r[3] is None)
    no_views = sum(1 for r in rows if r[4] is None)
    women = sum(1 for r in rows if r[7] == "female")
    no_gender = sum(1 for r in rows if r[7] is None)
    out = {
        "meta": {
            "generated": dt.date.today().isoformat(),
            "list_source": listing.get("source"),
            "list_revid": listing.get("revid"),
            "views_months": months,
            "views_stat": "median of %d monthly counts" % len(months),
            "views_note": "monthly English Wikipedia page views, a proxy for Anglophone familiarity",
            "dates_source": "Wikidata P569/P570",
            # Named in the footnote so the page says whose statement this is. It is Wikidata's
            # property, reported, not a claim this project makes about anyone.
            "gender_source": "Wikidata P21, \u201csex or gender\u201d",
        },
        "fields": ["name", "birth", "death", "quartets", "views", "views_lo", "views_hi",
                   "gender"],
        "rows": rows,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)
        f.write("\n")

    # readership.json: the same series, aligned to ONE month axis so two composers' sparklines are
    # comparable — a composer whose article is five years old draws a line over the right-hand
    # half of the box, which is the honest picture. A month with no datum is null, never zero:
    # "nobody read this" and "the article did not exist" are different facts (invariant 10), and
    # zero would draw the second as a crash to the floor.
    hist = {}
    for r in rows:
        got = series.get(canon_of[r[0]])
        if not got:
            continue
        vals = [got.get(m) for m in history]
        if any(v is not None for v in vals):
            hist[r[0]] = vals
    hout = {
        "meta": {
            "generated": dt.date.today().isoformat(),
            "note": "monthly English Wikipedia page views (agent=user) per composer, aligned to "
                    "`months`; null where the API has no datum for that month",
            "stat_months": STAT_MONTHS,
        },
        "months": history,
        "series": dict(sorted(hist.items())),
    }
    with open(HIST_OUT, "w", encoding="utf-8") as f:
        json.dump(hout, f, separators=(",", ":"), ensure_ascii=False)
        f.write("\n")

    print("wrote composers.json - %d composers, %d bytes" % (len(rows), os.path.getsize(OUT)))
    print("wrote readership.json - %d series x %d months, %d bytes"
          % (len(hist), len(history), os.path.getsize(HIST_OUT)))
    print("  living (no death date on Wikidata): %d" % living)
    print("  no quartet count (listed, not plotted): %d" % no_count)
    print("  no page-view data: %d" % no_views)
    print("  women (P21 female): %d; no P21 claim: %d" % (women, no_gender))
    print("  views: median of %s .. %s (%d months of %d cached)"
          % (months[0], months[-1], len(months), len(history)))
    if dropped:
        print("  dropped %d entries:" % len(dropped))
        for t, why in dropped:
            print("     %-34s %s" % (t, why))
    return 0


if __name__ == "__main__":
    sys.exit(main())
