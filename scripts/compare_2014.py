#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Diff the archived 2014 dataset against the current one, and say WHY each row moved.

    python3 scripts/compare_2014.py            # summary
    python3 scripts/compare_2014.py --full     # every changed row

This is a review tool, not part of the build. It exists because the 2014 snapshot is the only
independent check on a pipeline that now reads prose off a wiki page: a big move is either a
genuine twelve-year change or a parser mistake, and the two look identical in the output.

READ THE VIEW COLUMN WITH CARE — IT IS NOT A TREND. The pageviews API has no per-article data
before 2015-07, so the 2014 numbers came from a different measurement system entirely (the
pre-2015 dumps). They are archived for provenance and for exactly this kind of spot-check; they
are not plotted, and "down 30% since 2014" is not a claim this data can support. Quartet counts
and dates ARE comparable, because both are read from the same wiki page twelve years apart.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SUFFIX = re.compile(r"\s*\([^)]*\)$")


def fold(s):
    """Loose key for matching 2014's ASCII-stripped names to today's canonical ones.

    The 2014 scrape DELETED non-ASCII characters rather than transliterating, so "Lutosławski"
    became "Lutosawski" — dropping the letter, not replacing it. Folding today's names the same
    way is what lets the two sides meet.
    """
    import unicodedata
    s = SUFFIX.sub("", s).lower().replace("-", " ")   # "François-Joseph" vs "Francois Joseph"
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z ]", "", s).strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--full", action="store_true", help="list every changed row")
    args = ap.parse_args()

    with open(os.path.join(ROOT, "data", "composers-2014.json"), encoding="utf-8") as f:
        old_rows = json.load(f)
    with open(os.path.join(ROOT, "data", "views-2014.json"), encoding="utf-8") as f:
        old_views = json.load(f)["views"]
    with open(os.path.join(ROOT, "composers.json"), encoding="utf-8") as f:
        cur = json.load(f)

    ov = {fold(k): v for k, v in old_views.items()}
    old = {}
    for name, birth, life, q in old_rows:
        old[fold(name)] = {"name": name, "birth": birth, "quartets": q, "views": ov.get(fold(name))}
    new = {}
    # `*_` rather than naming every field: this tool compares four of them, and a schema addition
    # (gender was the first) should not stop a review script from running.
    for name, birth, death, q, views, *_ in cur["rows"]:
        new[fold(name)] = {"name": name, "birth": birth, "death": death,
                           "quartets": q, "views": views}

    gone = sorted(set(old) - set(new), key=lambda k: -(old[k]["quartets"] or 0))
    added = sorted(set(new) - set(old), key=lambda k: -(new[k]["views"] or 0))
    both = sorted(set(old) & set(new))

    print("2014: %d composers   now: %d   in both: %d" % (len(old), len(new), len(both)))
    print("dropped off the list: %d      newly listed: %d" % (len(gone), len(added)))

    print("\n== gone from the current Wikipedia list (2014 quartet count in brackets) ==")
    print("   These are the rows to look at before assuming data was lost: most are composers")
    print("   whose article was deleted or merged, which is also why they had no page views.")
    for k in gone:
        o = old[k]
        print("   %-30s [%s quartets, %s views in 2014]"
              % (o["name"], o["quartets"], o["views"] if o["views"] is not None else "?"))

    birth_diff = [(k, old[k]["birth"], new[k]["birth"]) for k in both
                  if old[k]["birth"] != new[k]["birth"]]
    q_diff = [(k, old[k]["quartets"], new[k]["quartets"]) for k in both
              if new[k]["quartets"] is not None and old[k]["quartets"] != new[k]["quartets"]]
    q_lost = [k for k in both if new[k]["quartets"] is None]

    print("\n== agreement on the comparable fields ==")
    print("   birth year:    %d/%d agree (%.1f%%)"
          % (len(both) - len(birth_diff), len(both), 100 * (len(both) - len(birth_diff)) / len(both)))
    print("   quartet count: %d/%d agree (%.1f%%), %d now unstated on the page"
          % (len(both) - len(q_diff) - len(q_lost), len(both),
             100 * (len(both) - len(q_diff) - len(q_lost)) / len(both), len(q_lost)))

    big = sorted(q_diff, key=lambda t: -abs((t[2] or 0) - (t[1] or 0)))
    print("\n== biggest quartet-count changes (2014 -> now) ==")
    print("   Each is either twelve years of editing or a parser mistake. Check the sentence in")
    print("   data/list.wiki before trusting a big one.")
    for k, o, n in (big if args.full else big[:20]):
        print("   %-30s %4s -> %-4s  (%+d)" % (new[k]["name"], o, n, (n or 0) - (o or 0)))
    if not args.full and len(big) > 20:
        print("   ... %d more (--full)" % (len(big) - 20))

    if birth_diff:
        print("\n== birth-year changes (Wikidata now wins over the 2014 prose) ==")
        for k, o, n in (birth_diff if args.full else birth_diff[:15]):
            print("   %-30s %s -> %s" % (new[k]["name"], o, n))
        if not args.full and len(birth_diff) > 15:
            print("   ... %d more (--full)" % (len(birth_diff) - 15))

    print("\n== newly listed since 2014, by current readership ==")
    for k in added[:15]:
        n = new[k]
        print("   %-30s b.%s  %s quartets  %s views/mo"
              % (n["name"], n["birth"], n["quartets"], n["views"]))
    print("   ... %d more" % max(0, len(added) - 15))
    return 0


if __name__ == "__main__":
    sys.exit(main())
