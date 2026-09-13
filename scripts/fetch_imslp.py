#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Fetch every string quartet IMSLP holds, and the composer identities needed to join them.

    python3 scripts/fetch_imslp.py            # writes data/imslp.json
    python3 scripts/fetch_imslp.py --refresh  # ignore the cache and re-ask for everything

Four passes over two APIs, ~165 requests in total, all cached in data/imslp.json so a rebuild is
offline. Nothing here is refetched once it is in the cache; --refresh is the only way to re-ask.

WHAT COUNTS AS A QUARTET IS IMSLP'S OWN ANSWER, not a title match. IMSLP categorises every work
by scoring, and "Category:For 2 violins, viola, cello" IS the string quartet. Reading titles
instead would take "3 'Oxford' String Quartets" and miss the Grosse Fuge, which is a string
quartet that does not say so. The arrangement category is a SEPARATE category upstream — a
quartet transcription of an orchestral work is somebody else's music arranged for four players,
so it is fetched and kept apart rather than summed in.

THE JOIN IS STRUCTURED FROM BOTH SIDES AND MATCHES NO NAMES. An IMSLP work page is titled
"<work> (<Surname, Forename>)", where the parenthetical is verbatim the composer's own IMSLP
category; that category page carries {{Wikidata|Q…}} and {{wp|<article>}} in its wikitext, and
Wikidata carries the reverse pointer as P839. So a composer is joined by QID, an identifier both
sides agree on, and never by spelling. That matters more here than usual: IMSLP files people
under period spellings and diacritics of its own ("Hänsel, Peter"), our roster carries canonical
Wikipedia titles that change when the pipeline runs (invariant 4), and a surname match would hand
one composer another's catalogue silently — the same failure invariant 4 keeps the canonical
titles in a parallel list to avoid.

A PAGE IS A PUBLICATION ENTRY, NOT A QUARTET. "Sämtliche Streichquartette (Beethoven, Ludwig van)"
is one page holding sixteen, and Beethoven has 23 pages against 16 quartets. So the per-work
markers (has scores, has recordings, is a collection) are fetched too, and what this file reports
is pages — the count of quartets on IMSLP is not a number IMSLP states and must not be invented.

POLITENESS IS THE POINT: one request per second, one retry ladder, a User-Agent that says who to
complain to, and a cache that means a second run costs nothing. The heavy question (what
categories does each of 4,900 work pages carry) is asked with clcategories, which returns only
the four markers we asked about instead of the fifty a work page really has.
"""
import argparse
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PEOPLE = os.path.join(ROOT, "data", "people.json")
OUT = os.path.join(ROOT, "data", "imslp.json")

IMSLP_API = "https://imslp.org/api.php"
WD_API = "https://www.wikidata.org/w/api.php"
WIKI_API = "https://en.wikipedia.org/w/api.php"
UA = "quartet-composers/1.0 (jsundram@gmail.com; https://github.com/jsundram/quartet-composers)"

ORIG = "Category:For 2 violins, viola, cello"
ARR = "Category:For 2 violins, viola, cello (arr)"
# Asked per work page. clcategories turns "give me this page's categories" (fifty of them, mostly
# scanner and editor credits) into "is it in these four", which is the difference between a 40 MB
# crawl and a 2 MB one.
MARKERS = ["Category:Scores", "Category:Recordings", "Category:Collections",
           "Category:Pages with arrangements"]

# The general-information fields on a work page. Stored as the RAW lines rather than as a parse,
# for the reason the composer pages are: the first reader of this data will be wrong about
# something, and re-reading must not cost 37 requests. Only these lines are kept — a work page is
# mostly file blocks (scanner, uploader, plate number, one per edition), which is 10x the bytes and
# answers nothing asked here.
INFO_FIELDS = ("Work Title", "Alternative Title", "Opus/Catalogue Number", "Key",
               "Number of Movements/Sections", "Year/Date of Composition",
               "Year of First Publication", "Piece Style", "Page Type", "Instrumentation", "Tags")
INFO_LINE = re.compile(r"^\|\s*(" + "|".join(re.escape(f) for f in INFO_FIELDS) + r")\s*=(.*)$",
                       re.M)

BATCH = 50            # the titles= limit for an anonymous MediaWiki client
PAUSE = 1.0           # seconds between requests, to both APIs
TRIES = 5
BACKOFF = [2, 5, 15, 40]

TITLE = re.compile(r"^(.*) \(([^()]*)\)$")


def get(api, params):
    """One GET, with the retry ladder the rest of this pipeline uses. Never more than TRIES."""
    params = dict(params, format="json")
    url = api + "?" + urllib.parse.urlencode(params)
    for attempt in range(TRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
            # A MediaWiki error is a 200 carrying valid JSON, and a reply with no `query` block
            # answered nothing. Both have to look like failures here or the retry ladder never
            # fires and the caller reads "no such page" out of a hiccup.
            if "error" in data or "query" not in data:
                raise ValueError("no query block: %s" % json.dumps(data)[:200])
            return data
        # Broad on purpose. A truncated chunked response arrives as http.client.IncompleteRead,
        # which is neither a URLError nor a ValueError, so a narrow tuple let one dropped reply
        # end a 165-request crawl with a traceback and no cache file written.
        except (OSError, http.client.HTTPException, ValueError) as e:
            if attempt == TRIES - 1:
                raise
            wait = BACKOFF[min(attempt, len(BACKOFF) - 1)]
            print(f"    retry {attempt+1}/{TRIES-1} in {wait}s ({e})", file=sys.stderr)
            time.sleep(wait)
    raise AssertionError("unreachable")


def members(cat):
    """Every page in a category. MediaWiki 1.18 pages with query-continue, not continue."""
    out, cont = [], None
    while True:
        p = {"action": "query", "list": "categorymembers", "cmtitle": cat,
             "cmlimit": "500", "cmprop": "ids|title"}
        if cont:
            p["cmcontinue"] = cont
        d = get(IMSLP_API, p)
        out += d.get("query", {}).get("categorymembers", [])
        cont = d.get("query-continue", {}).get("categorymembers", {}).get("cmcontinue")
        print(f"  {cat}: {len(out)}", file=sys.stderr)
        if not cont:
            return out
        time.sleep(PAUSE)


def reported(d, prefix=""):
    """-> ({title: wikitext}, {every title the reply accounted for}).

    The second half is the point. Writing `got.get(title)` for each title in the BATCH records
    None — "this page does not exist" — for a title the wiki never mentioned, and `todo` filters
    on presence, so one malformed reply retires up to 50 composers until the next --refresh.
    MediaWiki names every requested title, `missing` for the ones that are not there, so a title
    absent from the reply has not been asked and must stay that way. Invariant 4 states the same
    rule for page views: a title that did not ANSWER is dropped rather than written.
    """
    q = d.get("query", {})
    got, seen = {}, set()
    for pg in q.get("pages", {}).values():
        title = pg.get("title", "")
        if prefix and not title.startswith(prefix):
            continue
        key = title[len(prefix):]
        seen.add(key)
        revs = pg.get("revisions")
        if revs:
            got[key] = revs[0]["*"]
    for norm in q.get("normalized", []):
        f, t = norm["from"][len(prefix):], norm["to"][len(prefix):]
        if t in seen:
            seen.add(f)
            if t in got:
                got[f] = got[t]
    return got, seen


def chunks(seq, n):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def fetch_works(cache):
    """The two instrumentation categories, kept apart. Composer key parsed off the title."""
    for key, cat in (("orig", ORIG), ("arr", ARR)):
        if cache["works"].get(key):
            print(f"  cached: {key} ({len(cache['works'][key])})", file=sys.stderr)
            continue
        rows = []
        for m in members(cat):
            hit = TITLE.match(m["title"])
            if not hit:
                # Every work page on IMSLP is "<work> (<composer>)"; one that is not is a
                # maintenance page that wandered in, and guessing a composer for it would be
                # inventing an attribution. Recorded, not dropped silently.
                rows.append({"id": m["pageid"], "title": m["title"], "composer": None})
                continue
            rows.append({"id": m["pageid"], "title": hit.group(1), "composer": hit.group(2)})
        cache["works"][key] = rows
        save(cache)
        time.sleep(PAUSE)


def fetch_markers(cache):
    """Has scores / has recordings / is a collection, for every work page, four at a time."""
    want = [w["title"] + " (" + w["composer"] + ")"
            for k in ("orig", "arr") for w in cache["works"][k] if w["composer"]]
    todo = [t for t in want if t not in cache["markers"]]
    print(f"  markers: {len(want)} works, {len(todo)} to ask", file=sys.stderr)
    for i, batch in enumerate(chunks(todo, BATCH)):
        d = get(IMSLP_API, {"action": "query", "prop": "categories",
                            "titles": "|".join(batch),
                            "clcategories": "|".join(MARKERS), "cllimit": "500"})
        pages = d.get("query", {}).get("pages", {})
        got = {}
        for p in pages.values():
            cats = {c["title"] for c in p.get("categories", [])}
            got[p.get("title")] = {
                "scores": "Category:Scores" in cats,
                "recordings": "Category:Recordings" in cats,
                "collection": "Category:Collections" in cats,
                "arrangements": "Category:Pages with arrangements" in cats,
            }
        # normalized[] maps what we asked to what the wiki calls it, so an underscore or a
        # capitalisation difference does not leave a title looking un-asked forever.
        for norm in d.get("query", {}).get("normalized", []):
            if norm["to"] in got:
                got[norm["from"]] = got[norm["to"]]
        for t in batch:
            if t in got:
                cache["markers"][t] = got[t]
        if i % 10 == 9:
            save(cache)
        print(f"\r  markers: {len(cache['markers'])}/{len(want)}", end="", file=sys.stderr)
        time.sleep(PAUSE)
    print(file=sys.stderr)
    save(cache)


def fetch_composers(cache):
    """Each IMSLP composer category page, cached as RAW WIKITEXT.

    Deliberately unparsed. The identity claims live in that text in more than one shape — two
    template names ({{#fte:person}} and {{#imslpcomposer:}}) and three ways of naming the
    Wikipedia article — and the first parser written for it read none of them correctly. Storing
    the parse would have meant re-asking IMSLP for 1,700 pages every time the reader improved;
    storing the text means the join is a pure function of a file on disk, which is the same split
    the rest of this pipeline draws between fetching and building."""
    want = sorted({w["composer"] for k in ("orig", "arr")
                   for w in cache["works"][k] if w["composer"]})
    todo = [c for c in want if c not in cache["wikitext"]]
    print(f"  composers: {len(want)} with quartets, {len(todo)} to ask", file=sys.stderr)
    for batch in chunks(todo, BATCH):
        d = get(IMSLP_API, {"action": "query", "prop": "revisions", "rvprop": "content",
                            "titles": "|".join("Category:" + c for c in batch)})
        pages = d.get("query", {}).get("pages", {})
        got = {}
        for p in pages.values():
            revs = p.get("revisions")
            if not revs:
                continue
            got[p["title"][len("Category:"):]] = revs[0]["*"]
        for norm in d.get("query", {}).get("normalized", []):
            f, t = norm["from"][len("Category:"):], norm["to"][len("Category:"):]
            if t in got:
                got[f] = got[t]
        for c in batch:
            cache["wikitext"][c] = got.get(c)    # None: the category page does not exist
        save(cache)
        print(f"\r  composers: {len(cache['wikitext'])}/{len(want)}", end="", file=sys.stderr)
        time.sleep(PAUSE)
    print(file=sys.stderr)


def fetch_wp(cache):
    """Resolve every Wikipedia article IMSLP names to its CANONICAL title and Wikidata item.

    This is what turns IMSLP's link into a key. Only 136 of the 1,770 composer pages state a QID
    directly, but 1,156 name a Wikipedia article — and an article title on IMSLP is whatever was
    typed when somebody added it, so it is routinely a redirect. Asking en.wikipedia with
    redirects=1 collapses those onto the title the article lives at today, and pageprops hands
    back the Wikidata item in the same reply, so the join downstream compares QIDs and never
    spellings. It is the same rule invariant 5 states for page views one direction over: resolve
    the title, because the API will happily answer for the redirect.
    """
    sys.path.insert(0, HERE)
    from build_imslp import parse_person        # the parser lives with the offline stage
    # BOTH caches. Reading only the composers who have a quartet left the 58 pages reached by
    # name guess with their Wikipedia links unresolved, so the join judged them on dates alone
    # when the page was naming its own article all along.
    seen = list(cache["wikitext"].values()) + list(cache["candidates"].values())
    titles = sorted({(parse_person(t) or {}).get("wp") for t in seen if t} - {None})
    todo = [t for t in titles if t not in cache["wp"]]
    print(f"  wikipedia: {len(titles)} articles named by IMSLP, {len(todo)} to resolve",
          file=sys.stderr)
    for batch in chunks(todo, BATCH):
        d = get(WIKI_API, {"action": "query", "titles": "|".join(batch), "redirects": "1",
                           "prop": "pageprops", "ppprop": "wikibase_item"})
        q = d.get("query", {})
        alias = {}
        for n in q.get("normalized", []):
            alias[n["from"]] = n["to"]
        for r in q.get("redirects", []):
            alias[r["from"]] = r["to"]
        pages = {p["title"]: p for p in q.get("pages", {}).values() if "title" in p}
        for t in batch:
            cur = t
            for _ in range(6):                  # normalize -> redirect -> (rarely) again
                if cur not in alias:
                    break
                cur = alias[cur]
            pg = pages.get(cur)
            if pg is None:
                continue                        # not mentioned in the reply: still un-asked
            cache["wp"][t] = None if "missing" in pg else {
                "title": pg["title"],
                "qid": pg.get("pageprops", {}).get("wikibase_item"),
            }
        save(cache)
        print(f"\r  wikipedia: {len(cache['wp'])}/{len(titles)}", end="", file=sys.stderr)
        time.sleep(PAUSE)
    print(file=sys.stderr)


def fetch_p839(cache):
    """The reverse pointer, from Wikidata, for OUR roster. It is the only thing that can tell a
    roster composer IMSLP holds but has no quartets by from one IMSLP has never heard of — the
    works crawl above can only ever see the composers who have a quartet."""
    people = json.load(open(PEOPLE, encoding="utf-8"))
    qids = sorted({v["qid"] for v in people.values() if v.get("qid")})
    todo = [q for q in qids if q not in cache["p839"]]
    print(f"  P839: {len(qids)} roster QIDs, {len(todo)} to ask", file=sys.stderr)
    for batch in chunks(todo, BATCH):
        d = get(WD_API, {"action": "wbgetentities", "ids": "|".join(batch), "props": "claims"})
        for qid, e in d.get("entities", {}).items():
            claims = e.get("claims", {}).get("P839", [])
            vals = [c["mainsnak"]["datavalue"]["value"] for c in claims
                    if c["mainsnak"].get("snaktype") == "value"]
            # An IMSLP ID is stored with underscores; the API and our titles use spaces.
            cache["p839"][qid] = [v.replace("_", " ") for v in vals] or None
        save(cache)
        print(f"\r  P839: {len(cache['p839'])}/{len(qids)}", end="", file=sys.stderr)
        time.sleep(PAUSE)
    print(file=sys.stderr)


def fetch_candidates(cache):
    """Look for the roster composers nothing above found, so that "not on IMSLP" is an ANSWER.

    The works crawl can only ever see a composer who has a quartet, and P839 only sees the ones
    somebody added it to — so without this pass, Samuel Barber (no public-domain works, plausibly
    absent) and a composer whose IMSLP page simply has no Wikipedia link are the same blank, and
    the app could not honestly say anyone is unrepresented. 583 of the 1,770 composer pages with
    a quartet state neither a QID nor an article, so this catches those too.
    """
    sys.path.insert(0, HERE)
    from build_imslp import candidates, parse_person
    from build_data import QUALIFIER

    people = json.load(open(PEOPLE, encoding="utf-8"))
    found = {q for q, v in cache["p839"].items() if v}
    for cat, text in cache["wikitext"].items():
        f = parse_person(text) or {}
        if f.get("qid"):
            found.add(f["qid"])
        r = cache["wp"].get(f.get("wp") or "") or {}
        if r.get("qid"):
            found.add(r["qid"])

    want = []
    for listed, v in people.items():
        if v.get("qid") in found:
            continue
        want += candidates(QUALIFIER.sub("", v.get("canonical") or listed))
    want = sorted(set(want))
    todo = [c for c in want if c not in cache["candidates"]]
    print(f"  candidates: {len(want)} guesses for the composers nothing found, "
          f"{len(todo)} to ask", file=sys.stderr)
    for batch in chunks(todo, BATCH):
        d = get(IMSLP_API, {"action": "query", "prop": "revisions", "rvprop": "content",
                            "titles": "|".join("Category:" + c for c in batch)})
        got, seen = reported(d, prefix="Category:")
        for c in batch:
            if c in seen:
                cache["candidates"][c] = got.get(c)
        save(cache)
        print(f"\r  candidates: {len(cache['candidates'])}/{len(want)}", end="", file=sys.stderr)
        time.sleep(PAUSE)
    print(file=sys.stderr)


def fetch_workinfo(cache, titles):
    """The general-information block for each work page: opus, catalogue number, page type.

    This is what makes a COUNT possible rather than only a page tally. A set page states the opus
    its members share ("Op.18") and an individual page states its own ("Op.18 No.1"), so the two
    can be reconciled instead of added — which is the double counting that makes a raw page count
    the wrong number for Beethoven by a factor of four.

    Asked only for the pages this roster can attribute, because the download is the expensive part
    of this crawl: a work page carries one file block per edition and the whole site would be
    ~25 MB against ~9 MB for these. Keyed by full title, so a later join that attributes more
    pages simply tops it up.
    """
    todo = [t for t in titles if t not in cache["workinfo"]]
    print(f"  work info: {len(titles)} attributable pages, {len(todo)} to ask", file=sys.stderr)
    for batch in chunks(todo, BATCH):
        d = get(IMSLP_API, {"action": "query", "prop": "revisions", "rvprop": "content",
                            "titles": "|".join(batch)})
        q = d.get("query", {})
        got = {}
        for pg in q.get("pages", {}).values():
            revs = pg.get("revisions")
            if not revs:
                continue
            keep = ["|%s=%s" % (k, v) for k, v in INFO_LINE.findall(revs[0]["*"])]
            got[pg["title"]] = "\n".join(keep)
        for norm in q.get("normalized", []):
            if norm["to"] in got:
                got[norm["from"]] = got[norm["to"]]
        for t in batch:
            if t in got:
                cache["workinfo"][t] = got[t]
        save(cache)
        print(f"\r  work info: {len(cache['workinfo'])}/{len(titles)}", end="", file=sys.stderr)
        time.sleep(PAUSE)
    print(file=sys.stderr)


def save(cache):
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, OUT)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--refresh", action="store_true", help="ignore the cache and re-ask")
    a = ap.parse_args()

    cache = {"works": {}, "markers": {}, "wikitext": {}, "wp": {},
             "p839": {}, "candidates": {}, "workinfo": {}}
    KEEP = set(cache) | {"categories"}
    if os.path.exists(OUT) and not a.refresh:
        loaded = json.load(open(OUT, encoding="utf-8"))
        # Only keys something still writes. `composers` held a PARSE — 1,771 entries of the first,
        # broken reader, dates null for every one of them — and update() preserved it through
        # every save after the parse moved to build_imslp.py. A stale answer nothing reads is a
        # trap for whoever opens the cache next.
        cache.update({k: v for k, v in loaded.items() if k in KEEP})
        for k in ("works", "markers", "wikitext", "wp", "p839", "candidates",
                  "workinfo"):
            cache.setdefault(k, {})

    fetch_works(cache)
    fetch_composers(cache)
    fetch_p839(cache)
    fetch_candidates(cache)
    fetch_wp(cache)
    fetch_markers(cache)

    # Which pages are attributable is build_imslp.py's answer, so ask it rather than keeping a
    # second copy of the join here.
    from build_imslp import attributable_titles
    fetch_workinfo(cache, attributable_titles(cache, ROOT))

    cache["categories"] = {"orig": ORIG, "arr": ARR}
    save(cache)
    n = sum(len(cache["works"][k]) for k in ("orig", "arr"))
    print(f"\n{OUT}: {n} work pages, {len(cache['wikitext'])} composers, "
          f"{sum(1 for v in cache['p839'].values() if v)} roster QIDs with an IMSLP id",
          file=sys.stderr)


if __name__ == "__main__":
    main()
