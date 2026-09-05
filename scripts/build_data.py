#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Combine the three cached sources into composers.json, the one file the app fetches.

    data/list.json       scrape_list.py     roster + quartet counts + prose dates
    data/people.json     fetch_wikidata.py  canonical titles + P569/P570 birth and death
    data/pageviews.json  fetch_views.py     12 monthly view counts per article
                      -> composers.json

    python3 scripts/build_data.py

NOTHING HERE TOUCHES THE NETWORK. Every input is a committed cache, so the statistic below can be
changed and the dataset rebuilt offline, and the exact bytes that produced a deploy stay in git.

THE VIEW NUMBER IS A MEDIAN, NOT A MONTH. Dot size is the loudest channel on the chart and page
views are its noisiest input: a single month sits 12% off the 12-month median typically and 29% at
worst, August is a seasonal trough, and one composer has a month at 2.13x his own median. The
median ignores an anniversary or obituary spike rather than baking it in. min and max ship too, so
the detail panel can show the spread instead of implying a precision that isn't there.

WHAT "LIVING" MEANS NOW. It is `death is None` as of the last fetch_wikidata.py run — a fact about
today, from a structured claim. The old dataset inferred it by testing `birth + lifespan == 2014`
against a field that stored age-in-2014 for the living, which meant refreshing anything risked
silently reclassifying 139 people. That whole mechanism is gone.

UNKNOWNS STAY NULL. A composer whose count the page's prose doesn't state gets quartets: null and
is listed in the table but not plotted; an article with no page-view data gets views: null. The
alternative — carrying a 2014 number forward — silently mixes a pre-2015 measurement system into a
2026 dataset, and renders as a confident dot either way.
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

# Wikipedia's parenthetical qualifier is a URL disambiguator, not part of anybody's name, and every
# row on this chart is a composer already.
QUALIFIER = re.compile(r"\s*\((?:composer|musician|conductor|violinist|pianist|[^)]*musician)\)$", re.I)


def main():
    with open(LIST, encoding="utf-8") as f:
        listing = json.load(f)
    with open(PEOPLE, encoding="utf-8") as f:
        people = json.load(f)
    with open(VIEWS, encoding="utf-8") as f:
        pv = json.load(f)
    months, series = pv["months"], pv["series"]

    rows, seen, dropped = [], {}, []
    for e in listing["entries"]:
        title = e["title"]
        p = people.get(title, {})
        canon = p.get("canonical", title)
        birth, death = p.get("birth", e["birth"]), p.get("death", e["death"])
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
        row = [name, birth, death, e["quartets"], views, lo, hi]
        if canon in seen:
            prev = rows[seen[canon]]
            better = sum(x is not None for x in row) > sum(x is not None for x in prev)
            if better:
                rows[seen[canon]] = row
            dropped.append((title, "duplicate of %s" % canon))
            continue
        seen[canon] = len(rows)
        rows.append(row)

    rows.sort(key=lambda r: (r[1], r[0]))

    living = sum(1 for r in rows if r[2] is None)
    no_count = sum(1 for r in rows if r[3] is None)
    no_views = sum(1 for r in rows if r[4] is None)
    out = {
        "meta": {
            "generated": dt.date.today().isoformat(),
            "list_source": listing.get("source"),
            "list_revid": listing.get("revid"),
            "views_months": months,
            "views_stat": "median of %d monthly counts" % len(months),
            "views_note": "monthly English Wikipedia page views, a proxy for Anglophone familiarity",
            "dates_source": "Wikidata P569/P570",
        },
        "fields": ["name", "birth", "death", "quartets", "views", "views_lo", "views_hi"],
        "rows": rows,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)
        f.write("\n")

    print("wrote composers.json - %d composers, %d bytes" % (len(rows), os.path.getsize(OUT)))
    print("  living (no death date on Wikidata): %d" % living)
    print("  no quartet count (listed, not plotted): %d" % no_count)
    print("  no page-view data: %d" % no_views)
    print("  views: median of %s .. %s" % (months[0], months[-1]))
    if dropped:
        print("  dropped %d entries:" % len(dropped))
        for t, why in dropped:
            print("     %-34s %s" % (t, why))
    return 0


if __name__ == "__main__":
    sys.exit(main())
