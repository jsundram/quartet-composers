#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Join data/composers_raw.json + data/views.json -> composers.json (the file the app ships).

Two source files, scraped separately in 2014, are keyed on names that DON'T quite match: the
pageview keys carry Wikipedia's disambiguation suffix ("George Onslow (composer)") while the
composer list does not. 28 of 477 rows join only after stripping it — an unstripped join silently
gives those composers zero views, which reads as "obscure" rather than "unjoined". Strip, join,
then assert the miss count so a future re-scrape can't quietly reintroduce the gap.

Four more join by an explicit alias below — Wikipedia's article title differs from the list's
spelling ("Vaclav Pichl" vs "Wenzel Pichl"). Kept as a visible table rather than a fuzzy matcher so
a wrong join is reviewable instead of plausible.

No Wikipedia URL is emitted: both source files ASCII-strip diacritics ("Antonin Dvorak"), so a
/wiki/<title> link is a coin flip on whether a redirect happens to exist. app.js builds a
Special:Search "go" URL from the name instead, which lands on the article when the title resolves
and on search results when it doesn't.

THE FIELD NAMED "lifespan" IS NOT ALWAYS A LIFESPAN. The 2014 scrape wrote `died - born` for the
dead and `2014 - born` for the living, in the same slot — so Mohammed Fairouz (b. 1985) carries a
29 that means "age", not "died at 29". 139 of 466 rows are like that. Coloring them on a lifespan
ramp would paint every living composer as tragically short-lived, so the join emits a `living`
flag (death year == the snapshot year) and the app gives those rows their own visual treatment
instead of a color on the ramp. The flag can't distinguish someone who actually died IN 2014 from
someone alive that year; the UI says "living in 2014" rather than "living" for exactly that reason.

Output is one denormalized file so index.html makes exactly one data fetch:

    {"meta": {...}, "fields": [...], "rows": [[name, birth, lifespan, quartets, views, living], ...]}

Run:  python3 scripts/build_data.py
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SUFFIX = re.compile(r"\s*\(composer\)$")

SOURCE = "https://en.wikipedia.org/wiki/List_of_string_quartet_composers"

# The year the COMPOSER LIST was scraped — which is what decides who was living, and is NOT the
# same thing as the month the page views cover once fetch_views.py has been run.
#
# This was a bug: the living check originally read the year off views.json's month, so the first
# `fetch_views.py` refresh would have compared 2026 against death years frozen in 2014, matched
# nobody, and silently reclassified all 139 living composers as having died in 2014 — putting them
# back on the lifespan ramp the flag exists to keep them off. data/composers_raw.json is a frozen
# 2014 artifact and fetch_views.py never touches it, so this constant only changes if the composer
# list itself is re-scraped. The assertion below is what makes that impossible to forget.
COMPOSERS_SCRAPED = 2014

# The 2014 scrape DELETED non-ASCII characters instead of transliterating them, so "Lutosławski"
# was stored as "Lutosawski" — a string that matches no Wikipedia article. It went unnoticed for a
# decade because the pageview file was mangled the same way, so the two agreed with each other
# while both disagreeing with Wikipedia; it only surfaced when fetch_views.py asked the live API
# and got nothing back for 23 titles. These seven are the ones a corrected spelling recovers (the
# other sixteen are articles that really are gone). Applied to the DISPLAY name too, so the table
# spells people's names correctly.
#
# "Johan Hoffmann" -> "Johann Hoffmann" is deliberately NOT here: the article exists and would
# join, but at 22 views with a name that several unrelated people share, asserting the identity is
# a guess. A stale number is better than a wrong person.
RENAMES = {
    "Ib Nrholm": "Ib Nørholm",
    "Mieczysaw Weinberg": "Mieczysław Weinberg",
    "Per Nrgard": "Per Nørgård",
    "Stanisaw Moniuszko": "Stanisław Moniuszko",
    "Witold Lutosawski": "Witold Lutosławski",
    "Vahktang Kakhidze": "Vakhtang Kakhidze",       # transposed letters, not a diacritic
    "David Johnstone (composer)": "David Johnstone",  # article dropped its disambiguator
}

# composer-list spelling -> pageview-file spelling, for the rows the suffix strip doesn't reach.
# Verified by hand against the article each name resolves to; a fifth entry belongs here only
# after the same check.
ALIASES = {
    "Vaclav Pichl": "Wenzel Pichl",
    "Sergei Ivanovich Taneyev": "Sergei Taneyev",
    "Richard Wilson": "Richard Edward Wilson",
    "Matthew Davidson": "Matthew de Lacey Davidson",
}


def main():
    with open(os.path.join(ROOT, "data", "composers_raw.json")) as f:
        composers = json.load(f)          # [name, birth_year, lifespan_years, quartet_count]
    with open(os.path.join(ROOT, "data", "views.json")) as f:
        blob = json.load(f)               # {"month": "YYYY-MM", "note": ..., "views": {title: n}}
    views = blob["views"]
    # The snapshot month travels with the numbers rather than living in a constant here, so a
    # refresh via scripts/fetch_views.py can't leave the UI claiming the wrong date. It also
    # decides who counts as "living": the source stores age-in-snapshot-year for the living.
    views_month = blob["month"]

    by_name = {SUFFIX.sub("", title): n for title, n in views.items()}
    # RENAMES already put the corrected spelling in data/views.json's keys, so the join finds them
    # directly; this only matters if someone restores an old views.json.
    for old, new in RENAMES.items():
        by_name.setdefault(SUFFIX.sub("", old), by_name.get(new, 0))

    rows, unjoined = [], []
    for name, birth, lifespan, quartets in composers:
        if quartets <= 0:                 # this is a chart about quartets; no quartets, no row
            continue
        name = RENAMES.get(name, name)    # correct the spelling before joining AND before display
        n = by_name.get(name, by_name.get(ALIASES.get(name, ""), None))
        if n is None:
            unjoined.append(name)
            n = 0
        living = 1 if birth + lifespan == COMPOSERS_SCRAPED else 0
        rows.append([name, birth, lifespan, quartets, n, living])

    # A re-scraped composer list with a stale COMPOSERS_SCRAPED yields zero living composers,
    # which looks like clean data and is not. ~30% of this list was living; fail loudly instead.
    living = sum(r[5] for r in rows)
    if living < len(rows) // 10:
        print("ERROR: only %d of %d composers read as living. data/composers_raw.json stores "
              "age-in-scrape-year for the living, so COMPOSERS_SCRAPED (%d) is probably wrong "
              "for this scrape." % (living, len(rows), COMPOSERS_SCRAPED), file=sys.stderr)
        return 1

    if unjoined:
        print("ERROR: %d composers did not join to a pageview row:" % len(unjoined), file=sys.stderr)
        for name in unjoined[:20]:
            print("  " + name, file=sys.stderr)
        return 1

    rows.sort(key=lambda r: (r[1], r[0]))
    out = {
        "meta": {
            "views_month": views_month,
            "views_note": blob.get("note", ""),
            # Deliberately separate from views_month: the UI must say "living in 2014" even when
            # the view counts are from last month.
            "scrape_year": COMPOSERS_SCRAPED,
            "source": SOURCE,
        },
        "fields": ["name", "birth", "lifespan", "quartets", "views", "living"],
        "rows": rows,
    }
    path = os.path.join(ROOT, "composers.json")
    with open(path, "w", encoding="utf-8") as f:
        # ensure_ascii=False: names carry ł/ø/á, and \uXXXX escapes triple their byte cost for no
        # benefit — the file is served as application/json; charset=utf-8.
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)
        f.write("\n")
    print("wrote composers.json — %d composers (%d living in %d), views for %s, %d bytes"
          % (len(rows), living, COMPOSERS_SCRAPED, views_month, os.path.getsize(path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
