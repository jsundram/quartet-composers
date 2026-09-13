#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Fetch every string quartet IMSLP holds, and the composer identities needed to join them.

    python3 scripts/fetch_imslp.py            # writes data/imslp.json
    python3 scripts/fetch_imslp.py --refresh  # ignore the cache and re-ask for everything

Four passes over two APIs, ~238 requests for a COLD crawl, all cached in data/imslp.json so a
rebuild is offline. A WARM run costs 48 and re-asks exactly two kinds of thing: the instrumentation
categories, because they are the only place a new work page can appear, and every ABSENCE — a
composer page yielding no key, a P839 claim Wikidata does not state, a guessed category with no
page behind it, an article IMSLP names that does not exist. Those are the answers a volunteer or a
Wikidata editor changes, and a cache that never re-asks them cannot tell "nothing to do" from
"nothing exists". An absence NOTHING can change is not one of them and is written down as an answer
instead — see the interwiki handling in fetch_wp, which is 233 of the 236. Everything else tops up
by page title and --refresh is the only way to make it re-ask, which is what keeps 3.5 MB of
unchanged wikitext off a volunteer-funded server. That is what makes a monthly run possible — the
earlier rule, "nothing is refetched once it is in the cache", meant a second run reported
`cached: orig (4215)` and discovered nothing, forever, while exiting 0 (#62).

WHAT IS DELIBERATELY NOT RE-ASKED, because the list above reads as complete and is not: the
per-work MARKERS and the WORK INFO. Both are mutable — a page gains Category:Recordings when
somebody uploads one, and a catalogue number gets corrected — so a stale `recordings: false` is a
wrong answer no run can notice, which is the same shape as everything above. They are left alone on
COST: 99 and 38 requests against the 48 a whole warm run spends, and work info is 740 KB of the
cache. The absences above are re-asked because each is cheap AND decides whether a composer can be
placed at all; a marker only decorates a composer already placed. Worth reconsidering if the app
ever draws one.

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
import gzip
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)     # build_imslp holds the readers; imported lazily, below
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
# How much of a cached listing a re-crawl has to bring back before it is allowed to replace it.
# It is TIGHT because the failure it catches is not usually a big loss. A walk that stops
# following the continuation returns one batch, and one batch is `cmlimit` pages whatever the
# category holds: 500 of `orig`'s 4,215 is 12% and would trip anything, but 500 of `arr`'s 722 is
# 69% and sailed straight through the 0.5 this started at — 222 arrangement pages retired in
# silence by the guard written to stop exactly that. So the question it asks is "did this come
# back whole", not "did this survive", and a curated category twenty years in the making does not
# lose a tenth of itself in a month. --refresh is the way through if IMSLP ever does gut one.
MIN_KEEP = 0.9


def get(api, params):
    """One GET, with the retry ladder the rest of this pipeline uses. Never more than TRIES."""
    params = dict(params, format="json")
    url = api + "?" + urllib.parse.urlencode(params)
    for attempt in range(TRIES):
        try:
            # GZIP, because urllib does not ask for it and one pass here is enormous without
            # it. Measured on wikidata: `wbgetentities&props=claims` has no per-property filter,
            # so asking 50 items for their P839 returns their COMPLETE claim sets — 49 KB per
            # composer, 24.6 MB for the 485 the monthly run re-asks, against 4.0 MB compressed.
            # It is the cheapest pass here by requests and by far the dearest by bytes, and the
            # same header takes ~1 MB of composer wikitext off IMSLP, which is the server the
            # politeness paragraph above is actually about. Decoded only when the server SAYS it
            # compressed, so a host that ignores the header changes nothing.
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
            data = json.loads(body.decode("utf-8"))
            # A MediaWiki error is a 200 carrying valid JSON, and a reply with no payload block
            # answered nothing. Both have to look like failures here or the retry ladder never
            # fires and the caller reads "no such page" out of a hiccup. WHICH block is named by
            # the action: wbgetentities answers with `entities` and carries no `query` at all, so
            # demanding `query` of every reply turned the P839 pass into five retries and a
            # traceback. It has never fired, because that cache was already full when the guard
            # was written and `todo` has been empty on every run since — a monthly run would have
            # met it the first time the roster gained a composer.
            block = "entities" if params.get("action") == "wbgetentities" else "query"
            if "error" in data or block not in data:
                raise ValueError("no %s block: %s" % (block, json.dumps(data)[:200]))
            return data
        # Broad on purpose. A truncated chunked response arrives as http.client.IncompleteRead,
        # which is neither a URLError nor a ValueError, so a narrow tuple let one dropped reply
        # end a 238-request crawl with a traceback and no cache file written.
        # EOFError and zlib.error are in the tuple for the gzip above, and neither is an OSError:
        # a TRUNCATED compressed body raises EOFError, and corruption inside the stream raises
        # zlib.error, which subclasses Exception directly. Most corruption does surface as
        # gzip.BadGzipFile, which IS an OSError — which is exactly how a rare one gets missed.
        # Either would end the crawl with a traceback instead of a retry, the same failure
        # IncompleteRead was added for.
        except (OSError, http.client.HTTPException, ValueError, EOFError, zlib.error) as e:
            if attempt == TRIES - 1:
                raise
            wait = BACKOFF[min(attempt, len(BACKOFF) - 1)]
            print(f"    retry {attempt+1}/{TRIES-1} in {wait}s ({e})", file=sys.stderr)
            time.sleep(wait)
    raise AssertionError("unreachable")


def members(cat):
    """Every page in a category, following the continuation in EITHER shape.

    IMSLP answers like MediaWiki 1.18 today, which pages with `query-continue`; every version
    since 1.26 sends `continue` instead unless asked for the old one. Reading only the old shape
    means the walk ends normally after the first 500 of 4,215 — no error, no exception, just a
    listing that is 12% of the category. fetch_works() REPLACES what it gets, so a silent short
    walk is the one failure here that writes a wrong answer rather than none, which is why this
    reads both and why there is a floor over there as well.
    """
    out, cont = [], None
    while True:
        p = {"action": "query", "list": "categorymembers", "cmtitle": cat,
             "cmlimit": "500", "cmprop": "ids|title"}
        if cont:
            p["cmcontinue"] = cont
        d = get(IMSLP_API, p)
        out += d.get("query", {}).get("categorymembers", [])
        cont = (d.get("query-continue", {}).get("categorymembers", {}).get("cmcontinue")
                or d.get("continue", {}).get("cmcontinue"))
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


def has_key(text, resolved):
    """Does a composer page yield something the join can use — a QID, or an article that RESOLVES?

    The test for whether re-asking a page could ever change anything, and the two passes that hold
    composer wikitext (fetch_composers, fetch_candidates) share it rather than each deciding.
    NAMING an article is not having a key: 203 of the 797 pages the monthly re-ask asks for
    name a non-English interwiki
    ({{wp|de:Hans Erich Apostel}}), en.wikipedia has no such title, and roster_cats cannot match
    one against a roster title either — they are as unplaced as a page naming nothing at all.
    `resolved` is last run's answers, since fetch_wp runs after both callers: an article named for
    the first time this month is re-read once more next month and keyed after that.
    """
    from build_imslp import parse_person
    f = parse_person(text) or {}
    r = resolved.get(f.get("wp") or "") or {}
    # A resolved TITLE counts, not only a QID: build_imslp joins on it as the fallback rung for
    # an article with no Wikidata item. Requiring the QID here made this disagree with the one
    # predicate it has to match — fetch_wp holds any resolution and stops re-asking, so such a
    # composer page would have been re-downloaded every month forever with no call left that
    # could ever settle it. Nothing in the shipped cache is that shape; both predicates were
    # written on this branch and should not have to be lucky.
    return bool(f.get("qid") or r.get("qid") or r.get("title"))


def chunks(seq, n):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def fetch_works(cache):
    """The two instrumentation categories, kept apart. Composer key parsed off the title.

    ALWAYS RE-CRAWLED, warm cache or not. This is the only pass that DISCOVERS — every other one
    is keyed by page title and tops up correctly, so none of them can see a page this never
    listed. Returning early on a cached listing made a second run print `cached: orig (4215)` and
    stop, which is a "nothing to do" indistinguishable from "nothing exists": a monthly run would
    have found nothing new forever and reported success doing it (#62). It is also the cheapest
    pass here, 11 requests against the ~238 a cold crawl costs.

    The listing REPLACES rather than merges, because the category is the live answer to what is in
    it. The caches below are keyed by title and keep their entry for a page that left, which is
    right: nothing downstream reads a page the listing no longer names, and re-asking for it after
    it comes back would be a request for an answer already on disk.

    Nothing is written unless the crawl came back whole, and that takes two guards rather than
    one. members() raises after its retry ladder rather than returning a short list, so a dropped
    reply retires nothing. The other way to come back short is to SUCCEED early — a walk whose
    continuation token went unrecognised ends normally with 500 of 4,215 pages and no error at
    all — and against a pass that replaces the listing that would retire the rest and leave every
    pass below topping up against the remains. MIN_KEEP is the floor for that; --refresh is the
    way through if IMSLP ever does gut a category for real.
    """
    for key, cat in (("orig", ORIG), ("arr", ARR)):
        was = {w["id"] for w in cache["works"].get(key) or []}
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
        now = {w["id"] for w in rows}
        if was and len(now) < MIN_KEEP * len(was):
            raise ValueError(
                "%s came back with %d pages against %d cached. A category does not lose a tenth "
                "of itself in a month, so this is a walk that ended early looking like an "
                "answer — the listing was NOT replaced. Check the continuation shape in "
                "members() first. If the loss is REAL, delete this category's entry from "
                "works in %s and re-run: the crawl then has nothing to compare against and "
                "writes what it finds. --refresh would do it too, at the price of re-asking "
                "everything else as well." % (cat, len(now), len(was), OUT))
        cache["works"][key] = rows
        # What the run DISCOVERED, which is the whole reason this pass re-runs. A warm run that
        # prints (0 new, 0 gone) has asked and been told nothing changed; the line it replaced
        # said "cached" and meant nobody asked.
        print(f"  {key}: {len(rows)} pages ({len(now - was)} new, {len(was - now)} gone)",
              file=sys.stderr)
        save(cache)
        time.sleep(PAUSE)


def fetch_markers(cache):
    """Has scores / has recordings / is a collection, for every work page, four at a time."""
    want = [w["title"] + " (" + w["composer"] + ")"
            for k in ("orig", "arr") for w in cache["works"][k] if w["composer"]]
    todo = [t for t in want if t not in cache["markers"]]
    print(f"  markers: {len(want)} works, {len(todo)} to ask", file=sys.stderr)
    done = 0
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
        done += len(batch)
        print(f"\r  markers: {done}/{len(todo)} asked", end="", file=sys.stderr)
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
    the rest of this pipeline draws between fetching and building.

    THE ONE PASS THAT RE-ASKS, and only for the pages that yield no KEY. One already stating
    {{Wikidata|Q…}}, or naming an article that resolved, is joined by that identifier and
    re-downloading it monthly buys a spelling change nothing reads. One yielding neither is
    exactly what a volunteer adding either would rescue, and no other pass can find out — the
    works crawl lists the page whether or not it has grown a link. So those are asked again on
    every run, ~16 requests (#62). A category page that does not exist counts as one of them: one
    that was missing last month may exist now.

    NAMING AN ARTICLE IS NOT HAVING A KEY, and reading it as one excluded the group that most
    needed asking. Most of the pages that yield no key name a non-English interwiki instead —
    {{wp|de:Hans Erich Apostel}}; en.wikipedia has no such title, fetch_wp resolves every one of
    them to nothing, and roster_cats cannot match them against a roster title either. has_key()
    above states the count, once. They are as unplaced as a page
    naming nothing at all, and they were the one group permanently shut out of the re-ask.
    Resolution is last run's answer, since fetch_wp runs after this pass: an article named for the
    first time this month is re-read once more next month and keyed after that."""
    want = sorted({w["composer"] for k in ("orig", "arr")
                   for w in cache["works"][k] if w["composer"]})
    todo = [c for c in want
            if c not in cache["wikitext"] or not has_key(cache["wikitext"][c], cache["wp"])]
    new = sum(1 for c in todo if c not in cache["wikitext"])
    print(f"  composers: {len(want)} with quartets, {len(todo)} to ask "
          f"({new} new, {len(todo) - new} still yielding no key)", file=sys.stderr)
    done = 0
    for batch in chunks(todo, BATCH):
        d = get(IMSLP_API, {"action": "query", "prop": "revisions", "rvprop": "content",
                            "titles": "|".join("Category:" + c for c in batch)})
        # reported(), not got.get(c), now that this pass RE-asks: a title the reply never
        # accounted for used to be written as None, and overwriting a page we already hold with
        # "this page does not exist" loses the identity claim it was making. Unasked has to stay
        # unasked — the rule reported() states, and the one invariant 4 states for page views.
        got, seen = reported(d, prefix="Category:")
        for c in batch:
            if c in seen:
                cache["wikitext"][c] = got.get(c)   # None: the category page does not exist
        save(cache)
        # Against `todo`, not against the cache: on a warm run the cache already holds every
        # composer before the first batch returns, so counting it printed 1771/1771 throughout
        # and a stalled crawl looked exactly like a finished one.
        done += len(batch)
        print(f"\r  composers: {done}/{len(todo)} asked", end="", file=sys.stderr)
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
    from build_imslp import parse_person        # the parser lives with the offline stage
    # BOTH caches. Reading only the composers who have a quartet left the 58 pages reached by
    # name guess with their Wikipedia links unresolved, so the join judged them on dates alone
    # when the page was naming its own article all along.
    seen = list(cache["wikitext"].values()) + list(cache["candidates"].values())
    titles = sorted({(parse_person(t) or {}).get("wp") for t in seen if t} - {None})
    # A TITLE THAT RESOLVED TO NOTHING IS RE-ASKED, and it is the fourth absence: the composer
    # pages above are re-downloaded every month precisely BECAUSE their only link resolved to
    # nothing,
    # so leaving the one call that could change that answer un-rerun made the re-ask above unable
    # to finish its own job. "Gubaidulina, Sofia" is the shape — IMSLP names an article that does
    # not exist, and a redirect created since is all it would take.
    # BUT ONLY THREE OF THE 236 ARE THAT SHAPE. The other 233 are interwiki ({{wp|de:Hans Erich
    # Apostel}}), and en.wikipedia answers those in `query.interwiki` and never under `pages` —
    # so the loop below skipped them, nothing was written, and re-asking them was a question no
    # reply could ever settle, put every month forever. They are recorded from that block now, as
    # an ANSWER rather than a gap: a title on another wiki is not one this API will ever hold.
    # ~1 request after the first run cleans them up. A title that RESOLVED is not re-asked either;
    # a canonical title is an identifier here, and where a page MOVE would matter is page views,
    # which invariant 15 answers for separately.
    todo = [t for t in titles if not cache["wp"].get(t)]
    new = sum(1 for t in todo if t not in cache["wp"])
    print(f"  wikipedia: {len(titles)} articles named by IMSLP, {len(todo)} to resolve "
          f"({new} new, {len(todo) - new} still resolving to nothing)", file=sys.stderr)
    done = 0
    for batch in chunks(todo, BATCH):
        d = get(WIKI_API, {"action": "query", "titles": "|".join(batch), "redirects": "1",
                           "prop": "pageprops", "ppprop": "wikibase_item"})
        q = d.get("query", {})
        elsewhere = {iw["title"]: iw.get("iw") for iw in q.get("interwiki", [])}
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
            if cur in elsewhere:
                # Stored with no title and no qid, so every reader already treating a wp entry as
                # `... or {}` sees exactly what it saw before; what changes is that the entry
                # EXISTS, which is how `todo` tells "nothing there yet" from "not ours to answer".
                # Keyed by `t`, the title we ASKED for, like every other write in this loop:
                # `todo` looks up what parse_person read out of the wikitext, and MediaWiki answers
                # under the NORMALIZED form. Keying it by the reply's title filed the answer where
                # nothing looks and left the title re-asked forever, which is the exact thing
                # recording it is for. Not hypothetical — the 14 `en:` titles in this cache
                # resolved only because `normalized` mapped them back, and a decomposed umlaut or
                # a leading colon normalizes the same way.
                cache["wp"][t] = {"title": None, "qid": None, "iw": elsewhere[cur]}
                continue
            pg = pages.get(cur)
            if pg is None:
                continue                        # not mentioned in the reply: still un-asked
            if "missing" in pg:
                cache["wp"][t] = None       # no article YET; one created since would resolve
            elif "pageid" in pg:
                cache["wp"][t] = {"title": pg["title"],
                                  "qid": pg.get("pageprops", {}).get("wikibase_item")}
            else:
                # Neither an article nor a name that could become one. WP_PATTERNS captures
                # anything up to the closing brace, so `{{wp|[[Amy Beach]]}}` arrives with
                # `invalid` and `{{wp|Special:Random}}` with `special` (ns -1 and -2) — both under
                # `pages`, neither carrying `missing`, so both used to be written as a RESOLVED
                # answer holding the bad string as their title. has_key() reads a bare title as a
                # key, so the composer page behind one was retired from the re-ask for good while
                # the join could never match it.
                # The test is CLOSED-WORLD on purpose: `special` was missed by the commit that
                # fixed `invalid`, because that one enumerated shapes. An article has a pageid and
                # a name that might become one says `missing`; everything else, including whatever
                # MediaWiki adds next, is this. Recorded like an interwiki — an answer, because no
                # reply will ever change it, and keyless, because it is not one.
                cache["wp"][t] = {"title": None, "qid": None,
                                  "unusable": pg.get("invalidreason") or "not an article title"}
        save(cache)
        done += len(batch)
        print(f"\r  wikipedia: {done}/{len(todo)} asked", end="", file=sys.stderr)
        time.sleep(PAUSE)
    print(file=sys.stderr)


def fetch_p839(cache):
    """The reverse pointer, from Wikidata, for OUR roster. It is the only thing that can tell a
    roster composer IMSLP holds but has no quartets by from one IMSLP has never heard of — the
    works crawl above can only ever see the composers who have a quartet.

    NO CLAIM IS RE-ASKED, because this pass answers PRESENCE and absence is the answer that can
    change. 485 of the 884 roster QIDs are stored as None — Wikidata states no P839 for them —
    and a `None` nobody re-asks is #62's own defect one pass over: an editor adding the claim
    would never be noticed, and the composer would read as "not on IMSLP" forever. It costs ~10
    requests. A claim we HOLD is not re-asked: it is an identifier, not a fact that ages."""
    people = json.load(open(PEOPLE, encoding="utf-8"))
    qids = sorted({v["qid"] for v in people.values() if v.get("qid")})
    todo = [q for q in qids if not cache["p839"].get(q)]
    new = sum(1 for q in todo if q not in cache["p839"])
    print(f"  P839: {len(qids)} roster QIDs, {len(todo)} to ask "
          f"({new} new, {len(todo) - new} still stating none)", file=sys.stderr)
    done = 0
    for batch in chunks(todo, BATCH):
        d = get(WD_API, {"action": "wbgetentities", "ids": "|".join(batch), "props": "claims"})
        for qid, e in d.get("entities", {}).items():
            claims = e.get("claims", {}).get("P839", [])
            vals = [c["mainsnak"]["datavalue"]["value"] for c in claims
                    if c["mainsnak"].get("snaktype") == "value"]
            # An IMSLP ID is stored with underscores; the API and our titles use spaces.
            cache["p839"][qid] = [v.replace("_", " ") for v in vals] or None
        save(cache)
        done += len(batch)
        print(f"\r  P839: {done}/{len(todo)} asked", end="", file=sys.stderr)
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
    # A GUESS THAT YIELDS NO KEY IS RE-ASKED, on has_key() — the same rule fetch_composers uses,
    # because these are the same kind of page and build_imslp joins on them (`cand-qid`). `want`
    # is re-derived every run, so a composer rescued above drops out of it; what stays is the 470
    # guesses stored as None ("IMSLP has no page by this name") and the 7 whose page EXISTS and
    # states no identifier — 3 of which build_imslp nonetheless places, on DATES, a rung has_key
    # cannot see for want of a roster row to confirm against. Re-asking those 3 buys nothing and is
    # accepted rather than called correct: they ride inside a batch already going out.
    # The other answers here are ones a volunteer changes, and leaving them was #62's
    # defect in the pass whose entire purpose is making "not on IMSLP" an ANSWER — not covered by
    # the works crawl, which cannot see a composer with no quartets by construction. ~10 requests.
    todo = [c for c in want
            if c not in cache["candidates"]
            or not has_key(cache["candidates"][c], cache["wp"])]
    new = sum(1 for c in todo if c not in cache["candidates"])
    print(f"  candidates: {len(want)} guesses for the composers nothing found, "
          f"{len(todo)} to ask ({new} new, {len(todo) - new} still yielding no key)",
          file=sys.stderr)
    done = 0
    for batch in chunks(todo, BATCH):
        d = get(IMSLP_API, {"action": "query", "prop": "revisions", "rvprop": "content",
                            "titles": "|".join("Category:" + c for c in batch)})
        got, seen = reported(d, prefix="Category:")
        for c in batch:
            if c in seen:
                cache["candidates"][c] = got.get(c)
        save(cache)
        done += len(batch)
        print(f"\r  candidates: {done}/{len(todo)} asked", end="", file=sys.stderr)
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
    done = 0
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
        done += len(batch)
        print(f"\r  work info: {done}/{len(todo)} asked", end="", file=sys.stderr)
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
