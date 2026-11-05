#!/usr/bin/env python3
# pwa-starter: none — this script is this repo's own
# /// script
# requires-python = ">=3.9"
# ///
"""Prove scripts/scrape_list.py reads a count from the shapes the list page actually uses, offline.

    python3 scripts/scrape_list.test.py

A wrong count ships as a confident dot and nothing downstream can tell (invariant 10), so these are
sentences from the page, and the answers were read off them by hand.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import scrape_list as sl                                # noqa: E402

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def entry(line):
    rows = sl.parse(line)[0]
    assert len(rows) == 1, rows
    return rows[0]["quartets"]


@case("a title list counts without ever saying quartet")
def titles():
    assert sl.count_of(" Arcadiana (1994), The Four Quarters (2010).", "X") == (2, "dated works")


@case("a whole title list parses through the entry line")
def titles_through_parse():
    assert entry("*[[Thomas Adès]] (born 1971): Arcadiana (1994), The Four Quarters (2010).") == 2


@case("a lifespan outside the colon form is not a work")
def lifespan_with_titles():
    line = "*[[X]] (born 1969). Meditation opus 43 (2013); Lullaby opus 81b (2018)."
    assert entry(line) == 2


@case("a lifespan alone is not one work")
def lifespan_alone():
    line = ("*[[X]] (born 1968) is perhaps the most prolific composer for the string quartet genre, "
            "with repertoires ranging from easy pieces to complex 20-minute quartets.")
    assert entry(line) is None


@case("a work dated as a range survives the lifespan being removed")
def range_dated_work():
    assert entry("*[[X]] (1900–1980). Aria (1950–1952).") == 1


@case("a bare number followed by as of, or up to")
def leading_number():
    assert sl.count_of(" Five as of 2008.", "X")[0] == 5
    assert sl.count_of(" Fourteen up to 2017.", "X")[0] == 14


@case("a number inside a title is not a count")
def number_in_title():
    assert sl.count_of(" 70 Chords for Terry (2005).", "X")[0] == 1


@case("an override can hold a dated entry at null")
def override_null():
    assert sl.count_of(" a set of Sonate a quattro (c. 1715–1725).", "Alessandro Scarlatti")[0] is None


@case("every override names an entry on the cached page")
def overrides_resolve():
    with open(sl.CACHE, encoding="utf-8") as f:
        titles = {r["title"] for r in sl.parse(f.read())[0]}
    assert not set(sl.OVERRIDE) - titles, set(sl.OVERRIDE) - titles


@case("a re-parse keeps the revision it was fetched at")
def offline_keeps_revid():
    with tempfile.TemporaryDirectory() as d:
        sl.CACHE, sl.OUT = os.path.join(d, "list.wiki"), os.path.join(d, "list.json")
        with open(sl.CACHE, "w", encoding="utf-8") as f:
            f.write("*[[X]] (born 1969): Two string quartets.\n")
        with open(sl.OUT, "w", encoding="utf-8") as f:
            json.dump({"revid": 7}, f)
        sys.argv = ["scrape_list.py", "--offline"]
        stdout, sys.stdout = sys.stdout, open(os.devnull, "w")
        try:
            assert sl.main() == 0
        finally:
            sys.stdout.close()
            sys.stdout = stdout
        with open(sl.OUT, encoding="utf-8") as f:
            assert json.load(f)["revid"] == 7


def main():
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            print("  ok   %s" % name)
        except AssertionError as e:
            failed += 1
            print("  FAIL %s: %s" % (name, e))
    print("%d of %d passed" % (len(CASES) - failed, len(CASES)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
