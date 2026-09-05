#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Scrape Wikipedia's List of string quartet composers -> data/list.json.

This replaces the frozen May 2014 scrape for three of the four data elements: the composer roster,
the quartet counts, and the birth/death years. (Page views come from scripts/fetch_views.py; exact
dates are refined from Wikidata by scripts/fetch_wikidata.py.)

    python3 scripts/scrape_list.py            # fetch the page, then parse
    python3 scripts/scrape_list.py --offline  # re-parse the cached copy, no network
    python3 scripts/scrape_list.py --report   # print every entry the count parser could not read

The wikitext is cached at data/list.wiki so parser work needs no network and so the exact revision
that produced a dataset stays reviewable.

THE PAGE IS PROSE, NOT A TABLE. Each entry looks like:

    *[[Joseph Haydn]] (1732-1809): Wrote [[...|sixty-eight string quartets]] (some of which ...

so the count has to be read out of a sentence, and the sentence is written by whoever last edited
it. Seven rules cover 791 of 885 entries; the rest return null rather than a guess, because a wrong
count is worse than a missing one — it lands on the chart as a confident dot, while a null lands in
the table and is honest.

VALIDATION, measured two ways, because the obvious one is misleading:

  1. AGAINST A HAND-AUDIT OF 30 RANDOM ENTRIES (the real measure — accuracy against the page):
     25 exactly right, 4 correctly null (the entry never states or implies a number), 1 arguable
     (Czerny's "at least 20 and as many as 40" is read as 40). Rerun it any time:
         python3 scripts/audit_counts.py

  2. AGAINST THE 2014 SCRAPE — useful for row matching, MISLEADING for counts. Birth year agrees
     98.2% on the 448 composers in both, which is the check worth having: it proves rows are being
     matched to the same human independent of anything the count parser does. Quartet counts agree
     only ~74%, but that is mostly twelve years of editing rather than parser error — Wanhal went
     from 53 to "Over seventy string quartets", Ellerton from 20 to "Some 100". Reproducing 2014
     is NOT the goal; the page today is the source of truth. See scripts/compare_2014.py.

KNOWN LIMITATIONS, in the order they cost accuracy:
  - The parser reads quantities, not meaning. Paganini's entry says "Fifteen string quartets for
    violin, viola, guitar and cello, as well as three traditional string quartets" — the fifteen
    are guitar quartets and the honest count is three. Those need a human: see OVERRIDE.
  - A range ("at least 20 and as many as 40") yields the number the regex reaches first, not a
    considered choice between the bounds.
  - An entry that enumerates works without ever using the word "quartet" ("VSTO (1993).") returns
    null. Counting its dated titles would usually be right, but the same rule would also count
    "(1907-1949)" as a work, so it stays off.

NOT WORTH TRYING: Wikidata as a structured replacement. Beethoven's quartets are modelled as plain
"musical work/composition" with no genre linking them to the string quartet, so they are findable
only by their English label — as heuristic as this, with far worse coverage for obscure composers.
A SPARQL count of P31/P136 = string quartet returns four composers for the entire corpus.
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(ROOT, "data", "list.wiki")
OUT = os.path.join(ROOT, "data", "list.json")
PAGE = "List of string quartet composers"
API = "https://en.wikipedia.org/w/api.php"
UA = "quartet-composers/1.0 (https://github.com/jsundram/quartet-composers)"

# ---------------------------------------------------------------- number words
_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
         "fifteen sixteen seventeen eighteen nineteen").split()
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
         "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
WORDS = {w: i for i, w in enumerate(_ONES)}
WORDS.update(_TENS)
for _t, _tv in _TENS.items():
    for _i, _w in enumerate(_ONES[1:10], 1):
        WORDS["%s-%s" % (_t, _w)] = _tv + _i
        WORDS["%s %s" % (_t, _w)] = _tv + _i
WORDS.update({"a": 1, "an": 1, "single": 1, "hundred": 100, "one hundred": 100, "a hundred": 100})
NUMWORD = "|".join(sorted((re.escape(k) for k in WORDS), key=len, reverse=True))


def to_int(tok):
    tok = tok.lower().replace("–", "-")
    return int(tok) if tok.isdigit() else WORDS.get(tok)


# ---------------------------------------------------------------- count parsing
# Adjectives that legitimately sit between the number and the noun ("four PUBLISHED quartets").
# A whitelist, not \w+: a greedy gap happily matches "three years later ... quartets".
ADJ = (r"(?:published|unpublished|surviving|complete|completed|numbered|unnumbered|extant|known|"
       r"mature|early|late|brilliant|full|other|further|additional|remaining|string)")
QUART = r"(?:quartets?|quartettos?|quartetten|quartettes?|quatuors?)"
HEDGE = r"(?:approximately|about|at least|more than|over|some|around|nearly|roughly)?"

# Ordered, most specific first. "string quartets" must beat a bare "quartets": Boccherini's entry
# names 91 string quartets AND 125 string quintets in one sentence.
PATTERNS = [
    (re.compile(r"\b%s\s*(%s|\d+)\s+(?:%s\s+){0,2}string %s\b" % (HEDGE, NUMWORD, ADJ, QUART), re.I),
     "N string quartets"),
    (re.compile(r"\b(?:wrote|composed|left|produced)\s+%s\s*(%s|\d+)\s+(?:%s\s+){0,2}%s\b"
                % (HEDGE, NUMWORD, ADJ, QUART), re.I), "wrote N quartets"),
    (re.compile(r"\b%s\s*(%s|\d+)\s+(?:%s\s+){0,2}%s\b" % (HEDGE, NUMWORD, ADJ, QUART), re.I),
     "N quartets"),
    # "Four works for string quartet:", "Four pieces for string quartet" - the noun is singular
    # because it names the ENSEMBLE, not the works, so none of the patterns above can see it.
    (re.compile(r"\b(%s|\d+)\s+(?:%s\s+)?(?:works?|pieces?|compositions?|movements? for)\s+for\s+string quartet"
                % (NUMWORD, ADJ), re.I), "N works for string quartet"),
]

# The section heading already says "string quartet composers", so many entries drop the noun:
# "Thirteen (1907-1949)." or "Two, both in 1957." Anchored to the start of the description so it
# cannot pick up a stray year or opus number from mid-sentence.
LEADING = re.compile(r"^\s*%s\s*(%s|\d{1,3})\s*(?:[,.;:(]|\s+(?:in|both|of|for|from|covering|written)\b)"
                     % (HEDGE, NUMWORD), re.I)
# "No 1 (1912), No 2 (1917), ... No 6 (1927)" - the highest number reached is the count. Max rather
# than a tally, because these lists are sometimes out of order or skip an unpublished number.
NUMBERED = re.compile(r"\bNos?\.?\s*(\d{1,3})\b")
PLURAL = re.compile(r"\b(?:quartets|quartettos|quartetten|quartettes|quatuors)\b", re.I)
# A parenthetical containing a year — i.e. a dated work in an enumeration.
DATED_WORK = re.compile(r"\([^)]*\b(?:1[5-9]|20)\d\d[^)]*\)")
SINGULAR = re.compile(r"\b(?:quartet|quartetto|quartette|quatuor)\b", re.I)

# Entries where the sentence states a number that is NOT the string-quartet count. Read by hand,
# listed here so the parser's confident-but-wrong answer never ships. Keep the reason.
OVERRIDE = {
    # "Fifteen string quartets for violin, viola, guitar and cello, as well as three traditional
    # string quartets" - the fifteen are guitar quartets.
    "Niccolò Paganini": 3,
}


def count_of(desc, title):
    if title in OVERRIDE:
        return OVERRIDE[title], "hand-checked"
    for pat, tag in PATTERNS:
        m = pat.search(desc)
        if m:
            v = to_int(m.group(1))
            if v is not None:
                return v, tag
    m = LEADING.match(desc)
    if m:
        v = to_int(m.group(1))
        if v is not None and 0 < v <= 200:
            return v, "leading number"
    nums = [int(x) for x in NUMBERED.findall(desc)]
    if len(nums) >= 2 and max(nums) <= 200:
        return max(nums), "numbered series"
    # A description that names a quartet in the SINGULAR and never in the plural USUALLY describes
    # exactly one: "String Quartet in G major (1837)." is a complete entry.
    #
    # But not when the entry ENUMERATES works by title. John Zorn's lists eight named pieces and
    # says "string quartet" once, in passing; Christian Wolff's lists eight; Ingram Marshall's
    # four. Reading those as 1 was not a small error - it planted five composers on the y=1 line
    # who belong well above it. An enumeration is recognisable without understanding it: several
    # dated works, or semicolons separating titles. Those return null and land in the table
    # instead of the chart, because "unknown" is honest and "one" is a fabrication.
    if not PLURAL.search(desc) and SINGULAR.search(desc):
        enumerated = len(DATED_WORK.findall(desc)) >= 2 or ";" in desc
        if not enumerated:
            return 1, "singular"

    # Enumerations: "Comodo et amabile for String Quartet (1924), Poem for String Quartet (1926),
    # Combined Carols for String Quartet (1941)." No number is stated anywhere, but three works
    # are. Counting the dated titles recovers a fifth of the entries this parser otherwise gives
    # up on, and it is the LAST rule so it can never override an explicitly stated count.
    #
    # A parenthetical CONTAINING a year, not one that starts with a digit: Isidora Zebeljan's
    # reads "(in Memory of Gustav Mahler, 2005)" and "(2009-2011)", and only the looser test sees
    # both. It undercounts an entry that dates only some of its works — better than null, and
    # never a confident overcount.
    if SINGULAR.search(desc) or PLURAL.search(desc):
        works = len(DATED_WORK.findall(desc))
        if 0 < works <= 200:
            return works, "dated works"
    return None, None


# ---------------------------------------------------------------- line parsing
def clean(line):
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", line, flags=re.S)
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", s)      # [[A|B]] -> B
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)               # [[A]]   -> A
    s = re.sub(r"\{\{[^}]*\}\}", " ", s)
    s = s.replace("''", "")
    return s


# The LINK is matched on the raw line, before clean() dissolves the brackets. Doing it the other
# way round breaks on titles that carry their own parentheses — clean() turns
# [[Salvatore Pappalardo (composer)]] into bare text, and "(composer)" then looks like the dates.
LINK = re.compile(r"^\*\s*\[\[([^\]|]+?)(?:\|([^\]]*))?\]\](.*)$")
# Take the first parenthetical that actually LOOKS like dates rather than assuming it is the first
# one present. Entries vary: a native-language alias can precede it ("*[[Franz Krommer]] /
# Frantisek Kramar (1759-1831):"), and one entry opens with a work instead ("One string quartet
# (1900)"), where no parenthetical is dates at all and Wikidata has to supply them.
PAREN = re.compile(r"\(([^)]*)\)")
DEAD = re.compile(r"^\s*(?:c\.\s*)?(\d{4})\??\s*[–\-]\s*(?:c\.\s*)?(\d{4})\??")
ALIVE = re.compile(r"^\s*born\s+(?:in\s+)?(\d{4})")


def dates_in(rest):
    """(birth, death) from the first date-shaped parenthetical; (None, None) if there isn't one."""
    for m in PAREN.finditer(rest):
        inner = m.group(1)
        d = DEAD.match(inner)
        if d:
            return int(d.group(1)), int(d.group(2))
        a = ALIVE.match(inner)
        if a:
            return int(a.group(1)), None
    return None, None


def parse(wikitext):
    body = re.sub(r"<ref[^>]*>.*?</ref>", "", wikitext, flags=re.S)
    body = re.sub(r"<ref[^>]*/>", "", body)
    rows, no_count, no_parse, no_dates = [], [], [], []
    for line in body.split("\n"):
        if not line.startswith("*[["):
            continue
        lm = LINK.match(line)
        if not lm:
            no_parse.append(line[:120])
            continue
        title, rest = lm.group(1).strip(), lm.group(3)
        c = clean(line)
        birth, death = dates_in(clean(rest))
        if birth is None:
            # Not fatal: scripts/fetch_wikidata.py fills birth/death from P569/P570, which is a
            # better source anyway. Only a row still lacking a birth year after that is unusable.
            no_dates.append(title)
        desc = c.split("):", 1)[1] if "):" in c else clean(rest).lstrip(" :")
        n, how = count_of(desc, title)
        if n is None:
            no_count.append((title, desc.strip()[:110]))
        rows.append({"title": title, "birth": birth, "death": death,
                     "quartets": n, "how": how})
    return rows, no_count, no_parse, no_dates


# ---------------------------------------------------------------- fetch
def fetch_wikitext():
    # prop=wikitext alone does not return revid, and provenance matters for a scraped dataset:
    # "which revision produced these numbers" is the first question anyone asks about a diff.
    q = urllib.parse.urlencode({"action": "parse", "format": "json",
                                "prop": "wikitext|revid", "page": PAGE})
    req = urllib.request.Request(API + "?" + q,
                                 headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.load(r)
    if "error" in d:
        raise SystemExit("MediaWiki error: %s" % d["error"])
    wikitext = d["parse"]["wikitext"]["*"]
    revid = d["parse"].get("revid")
    if revid is None:
        q2 = urllib.parse.urlencode({"action": "query", "format": "json", "prop": "revisions",
                                     "rvprop": "ids|timestamp", "titles": PAGE})
        r2 = urllib.request.Request(API + "?" + q2, headers={"User-Agent": UA})
        with urllib.request.urlopen(r2, timeout=30) as r:
            pages = json.load(r)["query"]["pages"]
        for pg in pages.values():
            revs = pg.get("revisions") or [{}]
            revid = revs[0].get("revid")
    return wikitext, revid


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true", help="parse data/list.wiki, do not fetch")
    ap.add_argument("--report", action="store_true", help="list every entry with no parsed count")
    args = ap.parse_args()

    revid = None
    if args.offline:
        if not os.path.exists(CACHE):
            print("no cached wikitext at data/list.wiki - run without --offline once", file=sys.stderr)
            return 1
        wikitext = open(CACHE, encoding="utf-8").read()
    else:
        wikitext, revid = fetch_wikitext()
        with open(CACHE, "w", encoding="utf-8") as f:
            f.write(wikitext)
        print("fetched %s (revid %s, %d bytes) -> data/list.wiki" % (PAGE, revid, len(wikitext)))

    rows, no_count, no_parse, no_dates = parse(wikitext)
    counted = sum(1 for r in rows if r["quartets"] is not None)
    print("parsed %d entries: %d with a quartet count, %d without, %d lines unreadable"
          % (len(rows), counted, len(no_count), len(no_parse)))
    print("  living per the page (no death year): %d" % sum(1 for r in rows if r["death"] is None))
    if no_dates:
        print("  no dates on the page (Wikidata must supply them): %d - %s"
              % (len(no_dates), ", ".join(no_dates)))

    if args.report:
        print("\n-- entries with no parseable count (they get quartets: null) --")
        for t, d in no_count:
            print("   %-32s %s" % (t, d))
        if no_parse:
            print("\n-- lines the entry regex could not read --")
            for line in no_parse:
                print("   %s" % line)
        if OVERRIDE:
            print("\n-- hand-checked overrides (parser was confidently wrong) --")
            for t, v in OVERRIDE.items():
                print("   %-32s -> %d" % (t, v))

    out = {
        "source": "https://en.wikipedia.org/wiki/" + PAGE.replace(" ", "_"),
        "revid": revid,
        "entries": rows,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0)
    print("wrote data/list.json (%d entries, %d bytes)" % (len(rows), os.path.getsize(OUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
