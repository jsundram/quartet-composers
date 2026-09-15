#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Combine the cached sources into the three files the app fetches.

    data/list.json         scrape_list.py   roster + quartet counts + prose dates
    data/people.json       fetch_wikidata.py  canonical titles + P569/P570 dates + P21 gender
    data/pageviews.json    fetch_views.py   every monthly view count the API has, per article
    data/imslp-join.json   build_imslp.py   the IMSLP catalogue, joined to this roster
                      -> composers.json     the roster: one row per composer, one number for views
                      -> readership.json    the HISTORY: the whole monthly series, per composer
                      -> imslp-works.json   the WORK PAGES IMSLP holds, per composer

    python3 scripts/build_data.py

WHERE THE ROSTER IS DECIDED, AND WHY IT IS DECIDED HERE. build_rows() below is the one place that
turns the caches into rows — which entries are dropped, which two collapse into one, what order
they ship in. build_imslp.py calls it as well rather than reading composers.json, because it now
runs BEFORE this file and reading its output would be a cycle. That is not merely how the cycle is
broken: a second reduction of the same caches would be a second opinion about who is on this list,
and the join would be matching composers that the roster does not contain.

NOTHING HERE TOUCHES THE NETWORK. Every input is a committed cache, so the statistic below can be
changed and the dataset rebuilt offline, and the exact bytes that produced a deploy stay in git.

THE VIEW NUMBER IS A MEDIAN, NOT A MONTH. Dot size is the loudest channel on the chart and page
views are its noisiest input: a typical month sits a tenth off the year's median, August is a
seasonal trough, and a spiky article can run several times its own median in one month. The
median ignores an anniversary or obituary spike rather than baking it in. min and max ship too, so
the detail panel can show the spread instead of implying a precision that isn't there.

AND IT IS TWELVE MONTHS, NOT THE WHOLE CACHE. fetch_views.py now caches everything back to
2015-07, but the chart's question is "how much read is this composer NOW", so the statistic is
still the median of the LAST TWELVE cached months (STAT_MONTHS). Widening it would quietly change
every dot on the chart and bake a 2016 readership into a 2026 picture — Kaija Saariaho's
all-history median is not the readership she has now, and her obituary month dwarfs both.

WHY THE HISTORY IS A SECOND FILE. composers.json is a BOOT dependency: sw.js serves it before the
page can paint anything at all, and a decade of monthly counts per composer is many times the size
of the roster itself. The sparkline is the one thing in this app that nothing else needs, so it is
the one thing that loads on its own — precached like everything else, fetched after the first
paint, and simply absent if it never arrives. Keyed by DISPLAY name (what composers.json rows carry),
because that is what the app has in hand when it draws the panel.

WHAT "LIVING" MEANS NOW. It is `death is None` as of the last fetch_wikidata.py run — a fact about
today, from a structured claim. The old dataset inferred it by testing `birth + lifespan == 2014`
against a field that stored age-in-2014 for the living, which meant refreshing anything risked
silently reclassifying everyone it recorded as alive. That whole mechanism is gone.

UNKNOWNS STAY NULL. A composer whose count the page's prose doesn't state gets quartets: null and
is listed in the table but not plotted; an article with no page-view data gets views: null; a
composer with no P21 claim gets gender: null. The alternative — carrying a 2014 number forward —
silently mixes a pre-2015 measurement system into a 2026 dataset, and renders as a confident dot
either way. For gender the alternative would be worse still: the only way to fill that null is to
guess from a name, which is a guess about a person and is what invariant 10 exists to forbid.
"""
import collections
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
JOIN = os.path.join(ROOT, "data", "imslp-join.json")
OUT = os.path.join(ROOT, "composers.json")
HIST_OUT = os.path.join(ROOT, "readership.json")
WORKS_OUT = os.path.join(ROOT, "imslp-works.json")

# Wikipedia's parenthetical qualifier is a URL disambiguator, not part of anybody's name, and every
# row on this chart is a composer already.
QUALIFIER = re.compile(r"\s*\((?:composer|musician|conductor|violinist|pianist|[^)]*musician)\)$", re.I)

# How many of the cached months the headline view statistic is measured over. A year smooths the
# seasonal trough without reaching back into a readership that is no longer current.
STAT_MONTHS = 12


class BuildError(Exception):
    """A cache that cannot be read the way the pipeline expects.

    Raised rather than sys.exit()'d because build_imslp.py calls build_rows() too and owns its own
    exit code and its own diagnostic; a helper that kills the process decides that for it.
    """


def imslp_cat(name):
    """The IMSLP category a display name reduces to — "Beethoven, Ludwig van".

    IMSLP files people Surname, Forename, and the particle falls out for free because IMSLP writes
    "Beethoven, Ludwig van" too. It holds for most of the composers IMSLP has; the rest are
    transliterations and fuller forenames nothing can derive, and they ship their category verbatim
    (see main()). NOTHING TRUSTS THIS RULE: a row gets the derived form only where the reduction
    reproduces the category the scrape actually found, validate.py re-derives every one of them
    against the scrape cache, and app.js restates the one line in JS with ui.test.mjs pinning the
    hrefs that come out of it.
    """
    toks = name.split()
    return toks[-1] + ", " + " ".join(toks[:-1]) if len(toks) > 1 else name


def build_rows():
    """The roster, in the order composers.json ships it.

    -> (rows, canons, history, series, listing). `rows` carry the BASE fields only — main() appends
    the IMSLP columns. `canons` runs parallel to rows (see the note inside) and `history`/`series`
    are data/pageviews.json's two halves, so a caller can reach a composer's own months.
    """
    with open(LIST, encoding="utf-8") as f:
        listing = json.load(f)
    with open(PEOPLE, encoding="utf-8") as f:
        people = json.load(f)
    with open(VIEWS, encoding="utf-8") as f:
        pv = json.load(f)
    history, series = pv["months"], pv["series"]
    # The statistic's window: the last twelve cached months. Not the whole cache — see the header.
    months = history[-STAT_MONTHS:]
    # Every series is a flat array aligned to `history` (fetch_views.py). Checked rather than
    # assumed: a mis-aligned array silently reads one composer's months as another's, and the
    # numbers that come out are plausible — which is the failure mode this whole pipeline is
    # arranged against.
    bad = [t for t, a in series.items() if not isinstance(a, list) or len(a) != len(history)]
    if bad:
        raise BuildError(
            "data/pageviews.json: %d series are not aligned to its %d months (%s). Rerun "
            "scripts/fetch_views.py, which rewrites the cache in the current form."
            % (len(bad), len(history), ", ".join(bad[:3])))

    # canons runs parallel to rows and is REORDERED WITH IT below. `seen` maps a canonical title to
    # a row INDEX, and those indices are meaningless the moment the rows are sorted — that mix-up
    # handed 673 composers someone else's history and validate.py's check_history caught it. The
    # obvious repair, a {display name: canonical title} map, has the same bug one step further out:
    # QUALIFIER strips the disambiguator, so "John Adams (composer)" and a bare "John Adams" — the
    # exact pair invariant 5 is about — collapse to one key and the second silently wins.
    rows, seen, dropped, canons = [], {}, [], []
    for e in listing["entries"]:
        title = e["title"]
        p = people.get(title, {})
        # `canon` may be None (unresolved), so `key` identifies the row instead — two unresolved
        # entries must not collapse into one `seen` slot — and the series lookup finds nothing
        # rather than a stale entry filed under the raw title.
        canon = p.get("canonical")
        key = canon or title
        birth, death = p.get("birth", e["birth"]), p.get("death", e["death"])
        gender = p.get("gender")
        if birth is None:
            dropped.append((title, "no birth year"))
            continue
        if death is not None and death < birth:
            dropped.append((title, "death %s before birth %s" % (death, birth)))
            continue

        # The stat window is the TAIL of the axis, so it is the tail of every aligned array.
        vals = [v for v in (series.get(canon) or [])[-STAT_MONTHS:] if v is not None]
        if vals:
            views = int(statistics.median(vals))
            lo, hi = min(vals), max(vals)
        else:
            views = lo = hi = None

        name = QUALIFIER.sub("", key)
        # Two list entries can resolve to one article (an alias and the real title). Keep the
        # richer row rather than letting the later one silently win.
        row = [name, birth, death, e["quartets"], views, lo, hi, gender]
        if key in seen:
            prev = rows[seen[key]]
            better = sum(x is not None for x in row) > sum(x is not None for x in prev)
            if better:
                rows[seen[key]] = row
            dropped.append((title, "duplicate of %s" % key))
            continue
        seen[key] = len(rows)
        canons.append(canon)
        rows.append(row)

    order = sorted(range(len(rows)), key=lambda i: (rows[i][1], rows[i][0]))
    rows = [rows[i] for i in order]
    canons = [canons[i] for i in order]

    # Two rows that print the same name cannot both be in readership.json, which is keyed by the
    # name the app has in hand when it draws the panel — one would silently overwrite the other's
    # decade of history. validate.py errors on it too (a shared link would be ambiguous), but the
    # build has to stop HERE or it writes the bad file first and the diagnostic points downstream.
    dupes = sorted(n for n, c in collections.Counter(r[0] for r in rows).items() if c > 1)
    if dupes:
        raise BuildError(
            "%d display names are shared by more than one row (%s) — QUALIFIER collapsed two "
            "canonical titles into one name; the history file cannot key them apart."
            % (len(dupes), ", ".join(dupes[:3])))

    if dropped:
        print("  dropped %d entries:" % len(dropped))
        for t, why in dropped:
            print("     %-34s %s" % (t, why))
    return rows, canons, history, series, listing


def main():
    try:
        rows, canons, history, series, listing = build_rows()
    except BuildError as e:
        print(e, file=sys.stderr)
        return 1
    months = history[-STAT_MONTHS:]

    # The IMSLP columns, joined onto the roster by DISPLAY NAME because that is the key
    # build_imslp.py matched on — it called build_rows() above for exactly these names.
    try:
        with open(JOIN, encoding="utf-8") as f:
            joined = json.load(f)
        join, flags = joined["composers"], joined["meta"]["flags"]
    except (OSError, ValueError, KeyError):
        print("cannot read data/imslp-join.json — run scripts/build_imslp.py first; it now comes "
              "BEFORE this stage so composers.json can carry the IMSLP columns.", file=sys.stderr)
        return 1
    orphans = sorted(set(join) - {r[0] for r in rows})
    if orphans:
        print("%d composers in data/imslp-join.json are not rows here (%s) — the join was built "
              "against a different roster; rerun scripts/build_imslp.py."
              % (len(orphans), ", ".join(orphans[:3])), file=sys.stderr)
        return 1
    # One category per composer, because one is all the shipped shape can carry: composers.json
    # holds a single `imslp_cat` and imslp-works.json's rows build their URLs from it. The join has
    # never produced a second, and if it does the honest move is to stop — a link pointing at the
    # wrong one of a composer's two categories is the kind of plausible wrongness invariant 4 is
    # arranged against, not something to pick a winner for here.
    twos = sorted(n for n, e in join.items() if len(e["cats"]) != 1)
    if twos:
        print("%d composers have other than one IMSLP category (%s) — composers.json carries one "
              "per row and imslp-works.json builds its URLs from it, so this shape cannot ship "
              "them." % (len(twos), ", ".join(twos[:3])), file=sys.stderr)
        return 1
    for r in rows:
        e = join.get(r[0])
        if e is None:
            # NOT PLACED, which is not the same as having nothing (invariant 10 / TODO's three
            # answers). `0` is what the table prints either way, by decision — but a null category
            # is what says there is nowhere to link, and the count cannot carry that.
            r.extend([0, None])
        else:
            cat = e["cats"][0]
            r.extend([e["works_n"], "" if imslp_cat(r[0]) == cat else cat])

    living = sum(1 for r in rows if r[2] is None)
    no_count = sum(1 for r in rows if r[3] is None)
    no_views = sum(1 for r in rows if r[4] is None)
    women = sum(1 for r in rows if r[7] == "female")
    no_gender = sum(1 for r in rows if r[7] is None)
    # One date across all three files. Two internally consistent files built from different runs is
    # the drift nothing in the app can see, which is check_history()'s lesson one file further out.
    today = dt.date.today().isoformat()
    out = {
        "meta": {
            "generated": today,
            "list_source": listing.get("source"),
            "list_revid": listing.get("revid"),
            "views_months": months,
            # The WINDOW, not a count of values. A composer whose article moved inside it has a
            # null at the month of the move (invariant 15), so her median is over eleven — and a
            # sentence built from this one goes into the provenance line verbatim.
            "views_stat": "median of up to %d monthly counts" % len(months),
            "views_note": "monthly English Wikipedia page views, a proxy for Anglophone familiarity",
            "dates_source": "Wikidata P569/P570",
            # Named in the footnote so the page says whose statement this is. It is Wikidata's
            # property, reported, not a claim this project makes about anyone.
            "gender_source": "Wikidata P21, \u201csex or gender\u201d",
            "imslp_source": "IMSLP (Petrucci Music Library), instrumentation category "
                            "\u201cFor 2 violins, viola, cello\u201d",
            # Said out loud in the file, because `imslp` sits one column from `quartets` and the
            # two count different things: what IMSLP HOLDS against what the composer WROTE.
            "imslp_unit": "distinct works on the quartet pages IMSLP holds, catalogue numbers "
                          "merged; not how many quartets the composer wrote",
        },
        "fields": ["name", "birth", "death", "quartets", "views", "views_lo", "views_hi",
                   "gender", "imslp", "imslp_cat"],
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
    for r, canon in zip(rows, canons):
        vals = series.get(canon)
        if vals and any(v is not None for v in vals):
            hist[r[0]] = list(vals)
    hout = {
        "meta": {
            "generated": today,
            "note": "monthly English Wikipedia page views (agent=user) per composer, aligned to "
                    "`months`; null where the API has no datum for that month, and null at the "
                    "month an article was moved, which belongs to neither of its titles. A month "
                    "before a move is counted under the title the article held then, so a rename "
                    "is not drawn as a step",
            "stat_months": STAT_MONTHS,
        },
        "months": history,
        "series": dict(sorted(hist.items())),
    }
    with open(HIST_OUT, "w", encoding="utf-8") as f:
        json.dump(hout, f, separators=(",", ":"), ensure_ascii=False)
        f.write("\n")

    # imslp-works.json: the PAGES behind the count, re-keyed from the join onto the display name
    # the app has in hand — exactly what readership.json does, and for the same reason. SHELL but
    # not BOOT (sw.js): it is fetched after the first paint and the page loses nothing if it never
    # arrives. A composer IMSLP holds with no quartet page is simply absent, the way a composer
    # with no months is absent from readership.json: an empty list is bytes that say nothing the
    # row's own `imslp: 0` does not already say.
    works = {}
    for r in rows:
        e = join.get(r[0])
        if e and e["works"]:
            works[r[0]] = [[t, n, ids, fl] for t, _pid, fl, _ci, n, ids in e["works"]]
    wout = {
        "meta": {
            "generated": today,
            "source": "IMSLP (Petrucci Music Library)",
            # The rule, not a format string: an earlier version of the join shipped
            # "https://imslp.org/wiki/{title}_({cat})" and a consumer substituting into it built a
            # broken URL for almost every page, spaces and all.
            "permalink": "percent-encode `<title> (<cat>)` with spaces as underscores, under "
                         "https://imslp.org/wiki/ — `<cat>` is the row's imslp_cat in "
                         "composers.json, derived as `Surname, Forename` where it is empty",
            "works_note": "`works` is how many distinct works the page holds; 0 marks an anthology "
                          "dropped from the composer's total for reprinting works that already "
                          "have pages of their own",
            # Carried through from the join rather than restated. A bitmask whose legend is a copy
            # is a number that can quietly start meaning something else.
            "flags": flags,
        },
        "fields": ["title", "works", "ids", "flags"],
        "works": dict(sorted(works.items())),
    }
    with open(WORKS_OUT, "w", encoding="utf-8") as f:
        json.dump(wout, f, separators=(",", ":"), ensure_ascii=False)
        f.write("\n")

    placed = sum(1 for r in rows if r[9] is not None)
    print("wrote composers.json - %d composers, %d bytes" % (len(rows), os.path.getsize(OUT)))
    print("wrote readership.json - %d series x %d months, %d bytes"
          % (len(hist), len(history), os.path.getsize(HIST_OUT)))
    print("wrote imslp-works.json - %d composers, %d pages, %d bytes"
          % (len(works), sum(len(v) for v in works.values()), os.path.getsize(WORKS_OUT)))
    print("  on IMSLP: %d composers (%d with a quartet page); %d categories stated verbatim"
          % (placed, len(works), sum(1 for r in rows if r[9])))
    print("  living (no death date on Wikidata): %d" % living)
    print("  no quartet count (listed, not plotted): %d" % no_count)
    print("  no page-view data: %d" % no_views)
    print("  women (P21 female): %d; no P21 claim: %d" % (women, no_gender))
    print("  views: median of %s .. %s (%d months of %d cached)"
          % (months[0], months[-1], len(months), len(history)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
