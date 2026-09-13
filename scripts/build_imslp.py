#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Join IMSLP's string quartets onto this roster. Offline; reads only caches.

    python3 scripts/build_imslp.py            # writes imslp.json, prints the join audit
    python3 scripts/build_imslp.py --report   # audit only, writes nothing

data/imslp.json (the cache) + data/people.json + composers.json  ->  imslp.json (shipped)

THE JOIN IS BY QID AND IT IS CONFIRMED, NOT ASSUMED. Every IMSLP composer category page states
its own Wikidata item; every roster composer already has one (data/people.json). Matching those
two is the whole join, and it matches no strings a human chose. The Wikipedia article link
({{wp|…}}) is the SECOND source, used only where IMSLP has not filled in a QID, and it is
accepted only when the article title is one this roster already resolved to canonically — a
title IMSLP names that we have never seen is a composer we do not have, not a near-miss to
guess at.

EVERY ACCEPTED JOIN IS CHECKED AGAINST THE DATES, and a disagreement is REPORTED rather than
resolved. IMSLP and Wikidata are independent about birth and death years, so agreement is
evidence the identifier is pointing at the person we think it is, and a two-source agreement is
the only thing standing between this file and the invariant-5 failure one level up: handing a
composer somebody else's catalogue produces entirely plausible numbers and nothing goes red.
The dates are not overwritten here — composers.json's dates come from Wikidata (invariant 4)
and this file is not a second opinion about when anyone was born.

WHAT IS COUNTED IS PAGES, NOT QUARTETS, and the difference is not a rounding error. IMSLP's unit
is a publication entry: "Sämtliche Streichquartette (Beethoven, Ludwig van)" is one page holding
sixteen quartets, and Beethoven's 23 pages cover 16 quartets plus the Grosse Fuge, two
complete-edition collections and a fugue fragment. So the field this ships is `pages`, the noun
is "score pages on IMSLP", and nothing here claims to know how many quartets IMSLP has. Comparing
it against composers.json's `quartets` (which counts works, from Wikipedia prose) is comparing
two different units — the app may show both, and must not subtract one from the other.

NULL AND ZERO ARE DIFFERENT ANSWERS (invariant 10). `pages: 0` means IMSLP holds this composer
and none of their quartets; `null` means we could not establish who they are on IMSLP at all, and
that is unknown, not empty. A composer with no P839 on Wikidata and no quartet page on IMSLP is
indistinguishable from one IMSLP has never heard of, and this file says so rather than guessing.
"""
import argparse
import collections
import datetime
import json
import os
import re
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# IMPORTED, not copied. composers.json's row names are DISPLAY names — build_data.py strips the
# disambiguator, so the roster says "George Onslow" where Wikipedia says "George Onslow
# (composer)" (invariant 4). Indexing the roster by the canonical title therefore misses every
# composer who needed one, which is 27 of them and includes the fourth-biggest quartet catalogue
# on IMSLP. A second copy of that regex here would drift from the one that names the rows.
from build_data import QUALIFIER
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(ROOT, "data", "imslp.json")
PEOPLE = os.path.join(ROOT, "data", "people.json")
COMPOSERS = os.path.join(ROOT, "composers.json")
# An INTERMEDIATE, not a shipped file: nothing in the app reads it, and the shape the
# app will read is decided in issue #61. Living in data/ says so, and keeps the name
# clear of data/imslp.json, which is the scrape cache.
OUT = os.path.join(ROOT, "data", "imslp-join.json")
# The audit, as a FILE rather than as scrollback. Every number in it moves when the
# pipeline runs, so anything that reports coverage has to read it rather than quote it.
AUDIT = os.path.join(ROOT, "data", "imslp-audit.json")

# Bit flags per work page, so 4,000 rows cost bytes rather than four key names each. The legend
# ships in meta, because a bitmask nobody can read from the file is a number with no meaning.
SCORES, RECORDINGS, COLLECTION, ARRANGEMENTS = 1, 2, 4, 8
LEGEND = {"1": "has scores", "2": "has recordings", "4": "is a collection",
          "8": "has arrangements"}

DATE_SLACK = 1        # IMSLP and Wikidata disagree by a year on people born near a new year
# How recently a composer can have died for IMSLP's silence about it to read as staleness rather
# than as disagreement. IMSLP pages are edited when somebody uploads a score, not when somebody
# dies, and a locked page is not edited at all — Sofia Gubaidulina's states 1931 and no death, a
# year and a half after hers. The same lag is noted about the Wikipedia list page in
# fetch_wikidata.py. Bounded, because "IMSLP says alive" is real evidence for anyone who died
# long enough ago that a score has plausibly been uploaded since.
STALE_DEATH = 4


# Four ways an IMSLP page names the Wikipedia article, all of them in use today, counted over
# the 1,770 composer pages that have a quartet:
#   [[wikipedia:Carl_Friedrich_Abel|Wikipedia]]                                          1031
#   [[wikipedia:{{#iflang:en=Ludwig van Beethoven |af=af:… |zh=zh:…}}|Wikipedia]]         273
#   {{wp|Joseph Achron}}                                                                  146
#   [https://en.wikipedia.org/wiki/… …]                                                   few
# The #iflang switch is the one that matters and the one the first parser fell into: it names the
# article in sixty languages, and a pattern that stops at the first "|" or "#" captures the two
# braces and calls them a title. Beethoven, Mozart and Haydn — the three biggest catalogues on
# the site — all use it, so the failure took out exactly the rows anyone would check first.
# Wikidata is NOT the primary key here despite being the better one: only 136 of the 1,770 state
# {{Wikidata|Q…}} at all, so the Wikipedia article is what IMSLP actually gives us and the QID is
# recovered from it downstream (data/imslp.json "wp"), where en.wikipedia can be asked directly.
WP_PATTERNS = (
    # {{wp|Joseph Achron}}
    re.compile(r"\{\{\s*wp\s*\|\s*([^}|]+)", re.I),
    # [[wikipedia:{{#iflang:en=Ludwig van Beethoven |af=…}}|Wikipedia]]  and the other order,
    # [[wikipedia:{{#iflang:\n |en=Johann Sebastian Bach |de=…}}|Wikipedia]]. Both are live; Bach,
    # Brahms and Dvorak use the second, Beethoven and Mozart the first.
    re.compile(r"\[\[\s*(?:wikipedia|w)\s*:\s*\{\{\s*#iflang\s*:"
               r"(?:[^}]*?\|)?\s*en\s*=\s*([^|}\n]+)", re.I),
    # [[wikipedia:Carl_Friedrich_Abel|Wikipedia]]. "{" is excluded from the title so this cannot
    # fall through and capture the braces of an #iflang switch that has no English article in it
    # — Carlos Ehrensperger is on de.wikipedia only, and the honest answer there is no article.
    re.compile(r"\[\[\s*(?:wikipedia|w)\s*:\s*([^\]|}{\n#]+)", re.I),
    # [https://en.wikipedia.org/wiki/… …]
    re.compile(r"https?://en\.wikipedia\.org/wiki/([^\s\]|#?]+)", re.I),
)
QID_PATTERN = re.compile(r"\{\{\s*Wikidata\s*\|\s*(Q\d+)", re.I)
YEAR = re.compile(r"-?\d{1,4}")


def template_fields(text):
    """Split the outer {{…}} into |key=value pairs, honouring nesting.

    Not a line regex, which is what the first attempt used and why every date read as None: the
    person template packs three fields onto one line (|Born Year=1723|Born Month=12|Born Day=22),
    so a line-anchored match sees one field whose value is the rest of the line. Values also
    contain templates and links with pipes of their own ({{wp|Joseph Achron}}), so the split has
    to be at brace depth 1 and nowhere else.
    """
    # The person template, not the first one on the page. A maintenance banner can precede it —
    # "Boisseau, Arthur" opens with {{MoreInfo|...}} — and parsing that returns {} , losing the
    # dates, the sex and the Biography Link with no symptom. 36 cached pages state a Born Year
    # that the naive reader threw away.
    start = -1
    for marker in ("{{#fte:person", "{{#imslpcomposer:"):
        i = text.find(marker)
        if i >= 0 and (start < 0 or i < start):
            start = i
    if start < 0:
        start = text.find("{{")
    if start < 0:
        return {}
    parts, buf, depth, i = [], [], 0, start
    while i < len(text):
        two = text[i:i + 2]
        if two in ("{{", "[["):
            depth += 1
            buf.append(two)
            i += 2
            continue
        if two in ("}}", "]]"):
            depth -= 1
            if depth == 0:
                break
            buf.append(two)
            i += 2
            continue
        if text[i] == "|" and depth == 1:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(text[i])
        i += 1
    parts.append("".join(buf))
    out = {}
    for chunk in parts[1:]:                       # parts[0] is the template name
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            out.setdefault(k.strip(), v.strip())
    return out


def parse_person(text):
    """The identity claims a composer page makes about itself. Absent stays None: IMSLP leaves
    fields blank and "c.1723" is not a year, and neither is a fact to round into one."""
    if not text:
        return {}
    f = template_fields(text)

    def year(k):
        v = f.get(k, "")
        return int(v) if YEAR.fullmatch(v) else None

    # SCOPE is the outer loop, so anything stated in Biography Link beats anything found
    # elsewhere on the page. With the loops the other way round, pattern 1 searching the WHOLE
    # page outranked pattern 2 inside Biography Link: Stravinsky's own article is behind an
    # #iflang switch in that field, and the reader returned "nl:Oeuvre van Igor Stravinsky" from
    # further down instead. He joined anyway, but only because P839 happened to rescue him.
    wp = None
    for scope in (f.get("Biography Link", ""), text):
        for pat in WP_PATTERNS:
            hit = pat.search(scope)
            if hit:
                wp = urllib.parse.unquote(hit.group(1)).replace("_", " ").strip()
                break
        if wp:
            break
    q = QID_PATTERN.search(text)
    return {
        "qid": q.group(1) if q else None,
        "wp": wp,
        "born": year("Born Year"),
        "died": year("Died Year"),
        "sex": f.get("Sex") or None,
        "nationality": f.get("Nationality") or None,
    }


def candidates(name):
    """The IMSLP category names a roster composer could plausibly be filed under.

    IMSLP files people "Surname, Forename", and the particle falls out for free because IMSLP
    writes "Beethoven, Ludwig van" too. Two- and three-token surnames are tried as well, for
    Ralph Vaughan Williams and Carl Maria von Weber. A GUESS, and only ever a guess — confirms()
    below is what decides, and it decides on dates.
    """
    toks = name.split()
    out = []
    for k in (1, 2, 3):
        if k >= len(toks):
            break
        out.append(" ".join(toks[-k:]) + ", " + " ".join(toks[:-k]))
    return out


def confirms(birth, death, f, today=None):
    """Does this IMSLP page belong to this composer? Returns WHY, or None.

    IMSLP's dates are typed by IMSLP's editors and Wikidata's by Wikidata's, so agreement is
    evidence and a surname is not. This is the only rung of the join that starts from a spelling,
    so it is the only one that needs an alibi.

    Being alive normally has to agree: a page with no death year is not a match for a composer who
    died in 1978 — that is either a different person or a page so stale it proves nothing. The one
    exception is a death inside the last STALE_DEATH years, where IMSLP's silence is the expected
    lag rather than a contradiction, and then the birth year must match EXACTLY rather than within
    the usual slack. `today` is passed in rather than read from the clock, so the rule is a pure
    function of its arguments and a test can state the year it is asking about.
    """
    if birth is None or f.get("born") is None:
        return None
    if abs(f["born"] - birth) > DATE_SLACK:
        return None
    if (death is None) != (f.get("died") is None):
        if (death is not None and today is not None
                and today - death <= STALE_DEATH and f["born"] == birth):
            return "stale-death"
        return None
    if death is not None and abs(f["died"] - death) > DATE_SLACK:
        return None
    return "dates"


# ---------------------------------------------------------------- catalogue numbers
# What turns a page tally into a WORK count. IMSLP states a work's catalogue designation in
# `Opus/Catalogue Number`, and a set page states the one its members share: "6 String Quartets,
# Op.18" carries Op.18 while the six individual pages carry Op.18 No.1 through No.6. Expanding the
# set and merging by id makes those the same six works instead of twelve, which is the double
# counting that makes a raw page count wrong for Beethoven by a factor of four.
#
# THE COUNT IS OF WORKS IMSLP HAS, and it is still not the same question as composers.json's
# `quartets`, which is how many the composer WROTE, from Wikipedia prose. Coverage is the ratio and
# it is finally meaningful: Cambini reads 14 pages and 76 works against a stated 149.
TPL = re.compile(r"\{\{\s*([A-Za-z0-9]+)\s*\|\s*([^}|]+?)\s*\}\}")   # {{K6|417b}} -> K6.417b
TAG = re.compile(r"<[^>]+>")
NOTE = re.compile(r"\([^)]*\)")
LEAD = re.compile(r"^\s*(\d+)\b")
SETWORD = re.compile(r"quartet|quatuor|quartett", re.I)
# A unit word that means WORKS, against one that means parts of a single work. "12 pieces" under
# one B number is Echo of Songs, and reading it as twelve works invented eleven Dvorak quartets.
UNIT = re.compile(r"^\s*(\d+)\s+(?:quartet|quartett|quatuor|piece|work|st[uü]ck)", re.I)
MOVT = re.compile(r"^\s*(\d+)\s+(?:movement|section|act|dance|variation|volume)", re.I)
# A SEPARATOR between the prefix and the number is required, and the prefix may contain digits.
# Without both, "{{K6|417b}}" -> "K6.417b" matched pre="K", num="6" and every Koechel-6 alternate
# on the site produced the same id "K.6" — which the union-find then treated as one work, merging
# ten distinct Mozart quartets into one and shipping him 31 works instead of ~40. Nothing went red:
# a smaller plausible number is exactly this parser's failure mode.
REF = re.compile(r"""^(?P<pre>[A-Za-z][A-Za-z0-9]{0,7})[.\s]\s*
                      (?P<num>\d+[a-z]?)
                      (?:\s*[-\u2013]\s*(?P<to>\d+[a-z]?))?
                      (?:\s*Nos?\.\s*(?P<sub>\d+)(?:\s*[-\u2013]\s*(?P<subto>\d+))?)?""",
                 re.X | re.I)
INFO = re.compile(r"^\|\s*([^=\n]+?)\s*=(.*)$", re.M)


def info_fields(raw):
    return {k: v.strip() for k, v in INFO.findall(raw or "")}


def designations(raw):
    """The distinct catalogue names on one page. "K.387 ; Op.10 No.1" is one work named twice."""
    s = TPL.sub(lambda m: "%s.%s" % (m.group(1), m.group(2)), raw or "")
    s = NOTE.sub("", TAG.sub("", s))
    return [x.strip() for x in re.split(r";|/(?=\s*[A-Za-z]{1,7}\.?\s*\d)|,(?=\s*[A-Za-z]{1,7}\.?\s*\d)", s)
            if x.strip()]


def work_ids(raw, members=None):
    """-> a list of works, each a SET of ids that are aliases of one another.

    Alternate designations of the same music are zipped POSITIONALLY: the i-th work under one
    catalogue is the i-th under the other. Without that, "Op.24 ; G.183-188" counts as twelve
    works and Boccherini's catalogue comes out at 153 instead of 75. Designations that disagree
    about how many works are present cannot be aligned, so the longest wins and the shorter ones
    are dropped rather than added — guessing an alignment invents works.
    """
    lists = []
    for dg in designations(raw):
        m = REF.match(dg)
        if not m:
            continue
        # Only the FIRST letter is normalised. str.title() lowercases every later capital, which
        # turns Fanny Hensel's "HelH 277" (Hellwig-Unruh) into "Helh.277" — a catalogue nobody
        # wrote, printed next to her one quartet. It also made WoO a special case, which this is
        # not: "WoO 14" survives untouched.
        pre = m.group("pre")
        pre = pre[:1].upper() + pre[1:]
        num = m.group("num")
        if m.group("sub"):
            a = int(m.group("sub"))
            b = int(m.group("subto") or a)
            lists.append(["%s.%s No.%d" % (pre, num, n) for n in range(a, b + 1)])
        elif m.group("to"):
            a, b = int(re.sub(r"\D", "", num)), int(re.sub(r"\D", "", m.group("to")))
            lists.append(["%s.%d" % (pre, n) for n in range(a, b + 1)] if b >= a
                         else ["%s.%s" % (pre, num)])
        elif members and members > 1:
            lists.append(["%s.%s No.%d" % (pre, num, n) for n in range(1, members + 1)])
        else:
            lists.append(["%s.%s" % (pre, num)])
    if not lists:
        return []
    longest = max(len(x) for x in lists)
    return [set(g) for g in zip(*[x for x in lists if len(x) == longest])]


def members_of(title, f):
    """How many WORKS a page holds, or None for "one, or cannot tell".

    Expanding one catalogue number into N needs evidence that N works are really here. Two things
    count: IMSLP typing the page as a Collection, or a title that opens with a number and names
    quartets — "6 String Quartets, Op.11", which Vachon and Kammel both leave untyped.
    """
    if f.get("Page Type") != "Collection" and not (
            LEAD.match(title) and SETWORD.search(title)):
        return None
    n = f.get("Number of Movements/Sections", "")
    hit = UNIT.match(n)
    if hit:
        return int(hit.group(1))
    lead = LEAD.match(title)
    return int(lead.group(1)) if lead and not MOVT.match(n) else None


def count_works(entry, workinfo):
    """-> (works, uncatalogued, anthologies). Distinct works on this composer's quartet pages.

    A page with no catalogue number at all is one work, UNLESS IMSLP types it a Collection: an
    anthology with nothing to identify its contents ("Selected String Quartets") is a reprint of
    works catalogued elsewhere on the same composer's pages, and adding it would count them twice.
    """
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    loose = anthologies = 0
    for title, _id, _flags, ci in entry["works"]:
        f = info_fields(workinfo.get(title + " (" + entry["cats"][ci] + ")"))
        groups = work_ids(f.get("Opus/Catalogue Number", ""), members_of(title, f))
        if not groups:
            if f.get("Page Type") == "Collection":
                anthologies += 1
            else:
                loose += 1
            continue
        for g in groups:
            ids = sorted(g)
            find(ids[0])
            for other in ids[1:]:
                parent[find(ids[0])] = find(other)
    return len({find(x) for x in list(parent)}) + loose, loose, anthologies


def strip_ns(cat):
    """An IMSLP composer key, with the Category: namespace removed if it is there."""
    return cat[len("Category:"):] if cat.startswith("Category:") else cat


def roster_cats(cache):
    """Every IMSLP composer category an identifier ties to this roster.

    Derived from the CACHE and data/people.json only. The first version read the previous build's
    `imslp.json`, which fetch_imslp.py calls before that file exists on a cold clone: it returned
    [], no catalogue fields were fetched, and count_works then read every page as uncatalogued —
    `works_n` silently equalled `pages` for the whole roster, with nothing red and the documented
    one-line rebuild producing exactly that.

    Only the identifier rungs are used, not the date-confirmed name guess. This decides what to
    FETCH, so a superset costs a request and a subset costs a wrong number; the name guess only
    ever adds composers with no quartet pages, which have nothing to fetch.
    """
    people = json.load(open(PEOPLE, encoding="utf-8"))
    wanted = {v["qid"] for v in people.values() if v.get("qid")}
    # EVERY rung main() joins on, not just the QID ones. A composer joined by article TITLE has
    # quartet pages by construction — the works crawl is where they came from — so leaving those
    # rungs out here means their catalogue fields are never fetched and count_works reads all
    # their pages as uncatalogued: works_n silently equals pages. No join uses these two today,
    # which is exactly why the omission would sit unnoticed until one did.
    titles = set()
    for listed, v in people.items():
        canon = v.get("canonical") or listed
        titles.add(canon)
        titles.add(listed)
        titles.add(QUALIFIER.sub("", canon))
    out = set()
    for qid, cats in (cache.get("p839") or {}).items():
        if qid in wanted:
            out.update(strip_ns(c) for c in (cats or []))
    for cat, text in (cache.get("wikitext") or {}).items():
        f = parse_person(text) or {}
        r = (cache.get("wp") or {}).get(f.get("wp") or "") or {}
        if (f.get("qid") in wanted or r.get("qid") in wanted
                or (r.get("title") in titles) or (f.get("wp") in titles)):
            out.add(cat)
    return out


def attributable_titles(cache, root=ROOT):
    """Full page titles fetch_imslp.py should ask for work info about."""
    cats = roster_cats(cache)
    out = []
    for kind in ("orig", "arr"):
        for w in (cache.get("works") or {}).get(kind, []):
            if w.get("composer") in cats:
                out.append(w["title"] + " (" + w["composer"] + ")")
    return sorted(set(out))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", action="store_true", help="audit only; write nothing")
    a = ap.parse_args()

    cache = json.load(open(CACHE, encoding="utf-8"))
    facts = {c: parse_person(t) for c, t in cache["wikitext"].items()}
    wpmap = cache.get("wp", {})
    people = json.load(open(PEOPLE, encoding="utf-8"))
    comp = json.load(open(COMPOSERS, encoding="utf-8"))
    fields = comp["fields"]
    NAME, BIRTH, DEATH = fields.index("name"), fields.index("birth"), fields.index("death")
    VIEWS = fields.index("views")
    roster = {r[NAME]: r for r in comp["rows"]}

    # Two indexes into the roster, both built from identifiers rather than from spellings.
    by_qid, by_title = {}, {}
    for listed, v in people.items():
        canon = v.get("canonical") or listed
        name = QUALIFIER.sub("", canon)
        if name not in roster:
            continue
        if v.get("qid"):
            by_qid.setdefault(v["qid"], name)
        by_title.setdefault(canon, name)
        by_title.setdefault(listed, name)

    # ---- 1. every quartet page, grouped by its IMSLP composer key -------------------------
    pages = {}          # imslp cat -> list of [title, id, flags]
    unattributed = []
    for kind in ("orig", "arr"):
        for w in cache["works"][kind]:
            if not w["composer"]:
                unattributed.append(w["title"])
                continue
            full = w["title"] + " (" + w["composer"] + ")"
            m = cache["markers"].get(full) or {}
            # COLLECTION comes from the page's own `Page Type`, not from Category:Collections,
            # which holds 22 of the 4,926 pages and misses every one of Beethoven's complete
            # editions. Shipping the category's answer meant "17 Streichquartette" went out with
            # works=0 and nothing on the row to explain the zero. The category is the fallback
            # only where no work info was fetched.
            info = info_fields(cache.get("workinfo", {}).get(full))
            coll = (info.get("Page Type") == "Collection") if info else m.get("collection")
            flags = (SCORES if m.get("scores") else 0) | \
                    (RECORDINGS if m.get("recordings") else 0) | \
                    (COLLECTION if coll else 0) | \
                    (ARRANGEMENTS if m.get("arrangements") else 0)
            pages.setdefault(w["composer"], {"orig": [], "arr": []})[kind].append(
                [w["title"], w["id"], flags])

    # ---- 2. resolve each IMSLP composer to a roster composer ------------------------------
    matched = {}        # roster name -> list of imslp cats
    how = {}            # imslp cat -> "qid" | "wp"
    unmatched = []
    date_conflicts = []
    for cat in sorted(pages):
        f = facts.get(cat) or {}
        r = wpmap.get(f.get("wp") or "") or {}
        name = src = None
        # Strongest evidence first, and every rung is an identifier except the last. The QID an
        # IMSLP page states is best (both sides asserted it); the QID en.wikipedia returns for
        # the article IMSLP links is just as good and 7x more available; the canonical title is
        # the fallback for an article with no Wikidata item. The raw IMSLP spelling is last and
        # is still not a name MATCH — it only counts if it is a title this roster resolved.
        if f.get("qid") and f["qid"] in by_qid:
            name, src = by_qid[f["qid"]], "imslp-qid"
        elif r.get("qid") and r["qid"] in by_qid:
            name, src = by_qid[r["qid"]], "wp-qid"
        elif r.get("title") and r["title"] in by_title:
            name, src = by_title[r["title"]], "wp-title"
        elif f.get("wp") and f["wp"] in by_title:
            name, src = by_title[f["wp"]], "wp-raw"
        if not name:
            unmatched.append((cat, len(pages[cat]["orig"]),
                              f.get("qid") or (r.get("qid") or "-"), f.get("wp")))
            continue
        row = roster[name]
        for label, ours, theirs in (("birth", row[BIRTH], f.get("born")),
                                    ("death", row[DEATH], f.get("died"))):
            if ours is not None and theirs is not None and abs(ours - theirs) > DATE_SLACK:
                date_conflicts.append((name, cat, label, ours, theirs, src))
        matched.setdefault(name, []).append(cat)
        how[cat] = src

    # ---- 3. the roster composers IMSLP knows but has no quartets for ----------------------
    # Only P839 can see these: the works crawl above can only ever report a composer who has one.
    p839 = cache.get("p839", {})
    for listed, v in people.items():
        canon = QUALIFIER.sub("", v.get("canonical") or listed)
        if canon not in roster or canon in matched:
            continue
        # Wikidata states the IMSLP id WITH its namespace ("Category:Bach,_Maria") while a work
        # title's parenthetical is the bare key ("Bach, Maria"). Keeping the prefix meant a
        # composer joined only by P839 never matched the works crawl, so they read as "on IMSLP,
        # no quartets" while holding some: Stravinsky lost 3 pages, and 5 composers lost 15
        # between them. Silent, because 0 is a plausible answer for exactly these composers.
        cats = [strip_ns(c) for c in (p839.get(v.get("qid") or "") or [])]
        for cat in cats:
            matched.setdefault(canon, []).append(cat)
            how[cat] = "p839"

    # ---- 3b. the name guesses, accepted only where the dates confirm them ----------------
    cand = {c: parse_person(t) for c, t in cache.get("candidates", {}).items() if t}
    year = datetime.date.today().year
    rejected = []
    for listed, v in people.items():
        canon = QUALIFIER.sub("", v.get("canonical") or listed)
        if canon not in roster or canon in matched:
            continue
        row = roster[canon]
        qid = v.get("qid")
        for c in candidates(canon):
            f = cand.get(c)
            if not f:
                continue
            # The candidate page states its own identity too, and that outranks the guess that
            # found it: this rung was MISSING, so 58 pages reached by name had their Wikidata and
            # Wikipedia links ignored and were judged on dates alone.
            r = wpmap.get(f.get("wp") or "") or {}
            if (f.get("qid") and f["qid"] == qid) or (r.get("qid") and r["qid"] == qid):
                matched.setdefault(canon, []).append(c)
                how[c] = "cand-qid"
                break
            why = confirms(row[BIRTH], row[DEATH], f, today=year)
            if why:
                matched.setdefault(canon, []).append(c)
                how[c] = "name+" + why
                break
            rejected.append((canon, c, row[BIRTH], row[DEATH], f.get("born"), f.get("died"),
                             f.get("wp")))

    # ---- 4. write ------------------------------------------------------------------------
    out = {}
    for name, cats in sorted(matched.items()):
        works, arr = [], []
        for cat in cats:
            for t, i, fl in pages.get(cat, {}).get("orig", []):
                works.append([t, i, fl, cats.index(cat)])
            for t, i, fl in pages.get(cat, {}).get("arr", []):
                arr.append([t, i, fl, cats.index(cat)])
        works.sort(key=lambda w: w[0])
        arr.sort(key=lambda w: w[0])
        works_n, loose, anth = count_works(
            {"works": works, "cats": cats}, cache.get("workinfo", {}))
        out[name] = {
            "cats": cats,
            "how": [how[c] for c in cats],
            "pages": len(works),
            "works_n": works_n,
            "arr_pages": len(arr),
            "works": works,
            "arr": arr,
        }

    shipped = {
        "meta": {
            "generated": datetime.date.today().isoformat(),
            "source": "IMSLP (Petrucci Music Library), api.php",
            "categories": cache.get("categories", {}),
            "unit": ("`pages` counts IMSLP work PAGES; `works_n` counts distinct works "
                     "on them, expanding a set page by its shared opus and merging catalogue "
                     "numbers that name the same music. Neither is composers.json's `quartets`, "
                     "which is how many the composer WROTE, from Wikipedia prose."),
            "join": ("Wikidata QID stated by the IMSLP composer page, confirmed against birth "
                     "and death years; {{wp}} article title where IMSLP states no QID; P839 "
                     "for composers IMSLP holds with no quartet page"),
            "flags": LEGEND,
            # Stated as a RULE, not as a format string: the old
            # "https://imslp.org/wiki/{title}_({cat})" left spaces and non-ASCII unencoded, so a
            # consumer substituting into it built a broken URL for almost every page.
            "permalink": ("percent-encode `<title> (<cat>)` with spaces as underscores, "
                          "under https://imslp.org/wiki/"),
        },
        "composers": out,
    }

    # ---- 5. the audit --------------------------------------------------------------------
    n_pages = sum(len(v["orig"]) for v in pages.values())
    joined = [n for n, v in out.items() if v["pages"]]
    print(f"IMSLP quartet pages           {n_pages:>6}  in {len(pages)} composer categories")
    print(f"  attributable to this roster {sum(v['pages'] for v in out.values()):>6}"
          f"  across {len(joined)} of {len(roster)} composers")
    # Not shipped per composer, because today it is always equal to `pages` and a field that
    # duplicates another is a second thing to keep true. It stays a per-work FLAG and a line in
    # this audit, so the day IMSLP catalogues a quartet with no score attached, this says so
    # instead of the app quietly reporting a score that is not there.
    noscore = sum(1 for v in out.values() for w in v["works"] if not w[2] & SCORES)
    print(f"  with no score file          {noscore:>6}"
          f"  {'(so pages == scored; not shipped twice)' if not noscore else '<-- SHIP IT'}")
    print(f"  distinct WORKS on those pages "
          f"{sum(v['works_n'] for v in out.values()):>6}"
          f"  (sets expanded, catalogue numbers merged)")
    print(f"  arrangements (kept apart)   {sum(v['arr_pages'] for v in out.values()):>6}")
    print(f"roster composers on IMSLP     {len(out):>6}"
          f"  ({len(out) - len(joined)} with no quartet page)")
    print(f"roster composers unresolved   {len(roster) - len(out):>6}"
          f"  (null, not zero: we cannot say)")
    print(f"IMSLP composers off-roster    {len(unmatched):>6}"
          f"  ({sum(u[1] for u in unmatched)} pages, mostly composers this list omits)")
    if unattributed:
        print(f"work pages with no composer in the title: {len(unattributed)} {unattributed[:3]}")
    by = collections.Counter(how.values())
    print("join sources                  " +
          "  ".join(f"{k}={v}" for k, v in sorted(by.items(), key=lambda kv: -kv[1])))

    if date_conflicts:
        print(f"\nDATE DISAGREEMENTS ({len(date_conflicts)}) - reported, not resolved:")
        for name, cat, label, ours, theirs, src in date_conflicts[:20]:
            print(f"  {name:<32} {label} wikidata={ours} imslp={theirs}  [{cat}, via {src}]")

    if rejected:
        print(f"\nNAME GUESSES REJECTED ({len(rejected)}) - the page exists, the dates disagree:")
        for canon, c, b, d, ib, idd, wp in rejected[:12]:
            print(f"  {canon:<30} vs IMSLP {c:<28} "
                  f"{b}-{d if d else ''} against {ib}-{idd if idd else ''}")

    top = sorted((roster[n][VIEWS] or 0, n, out[n]["pages"]) for n in out)
    print("\nMost-read roster composers with NO quartet page on IMSLP:")
    for v, n, p in [t for t in reversed(top) if t[2] == 0][:10]:
        print(f"  {n:<34} {v:>9,} readers/mo")
    print("\nMost-read roster composers we could NOT place on IMSLP at all:")
    miss = sorted(((roster[n][VIEWS] or 0, n) for n in roster if n not in out), reverse=True)
    for v, n in miss[:10]:
        print(f"  {n:<34} {v:>9,} readers/mo")
    print("\nBiggest off-roster IMSLP quartet catalogues (composers this list does not have):")
    for cat, n, q, wp in sorted(unmatched, key=lambda u: -u[1])[:10]:
        print(f"  {cat:<34} {n:>4} pages   qid={q} wp={wp}")

    audit = {
        "generated": shipped["meta"]["generated"],
        "imslp_pages": n_pages,
        "imslp_composers": len(pages),
        "imslp_arr_pages": sum(len(v["arr"]) for v in pages.values()),
        "roster": len(roster),
        "attributable_pages": sum(v["pages"] for v in out.values()),
        "attributable_works": sum(v["works_n"] for v in out.values()),
        "attributable_arr": sum(v["arr_pages"] for v in out.values()),
        "placed": len(out),
        "placed_with_pages": len(joined),
        "placed_without_pages": len(out) - len(joined),
        "unplaced": len(roster) - len(out),
        "offroster_composers": len(unmatched),
        "offroster_pages": sum(u[1] for u in unmatched),
        "no_score_file": noscore,
        "sources": dict(by),
        "date_conflicts": [
            {"name": n, "cat": c, "field": lb, "wikidata": o, "imslp": t, "via": sr}
            for n, c, lb, o, t, sr in date_conflicts],
        "rejected": [
            {"name": n, "cat": c, "birth": b, "death": d, "imslp_born": ib,
             "imslp_died": idd, "imslp_wp": wp}
            for n, c, b, d, ib, idd, wp in rejected],
        "unattributed": unattributed,
        "offroster_top": [
            {"cat": c, "pages": n} for c, n, q, wp in
            sorted(unmatched, key=lambda u: -u[1])[:15]],
    }
    if a.report:
        return 0
    with open(AUDIT, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=1)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(shipped, f, separators=(",", ":"), ensure_ascii=False)
    print(f"\nwrote data/imslp-join.json - {len(out)} composers, "
          f"{os.path.getsize(OUT):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
