#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Prove a second run of the IMSLP crawl can still DISCOVER something.

    python3 scripts/fetch_imslp.test.py

NO NETWORK: `get` is stubbed against a dict-shaped wiki and the cache is a temp file, so this runs
anywhere and in CI.

WHY THIS FILE EXISTS. Every pass in fetch_imslp.py is a cache keyed by page title, and all but one
of them top up correctly — markers, work info, composer pages, Wikipedia resolution. The one that
does not top up is the one that DISCOVERS: the category crawl is the only place a work page or a
composer can enter this pipeline at all, and it used to return early on a warm cache. So a second
run printed `cached: orig (4215)`, asked the site nothing, and exited 0. A monthly run would have
found nothing new forever while reporting success (#62) — the same shape as a null no request
justified in data/pageviews.json, a "nothing to do" indistinguishable from "nothing exists".

That failure is invisible from inside a run. There is no baseline saying how many quartet pages
IMSLP should hold, every number in the cache stays plausible, and the only symptom is a file that
stops growing. So the property has to be asserted about the REQUESTS a run makes, which is what
these cases do: what a warm run asks for, what it declines to ask for, and that a page which
appeared between two runs reaches the passes downstream of the crawl.

The budget is the other half and is not decoration. This is a volunteer-funded server, the cold
crawl is ~238 requests, and the reason the fix is "always re-crawl" rather than "--refresh
monthly" is that re-asking everything would re-download megabytes of wikitext that has not
changed. A
case that only proved re-asking would be satisfied by --refresh.
"""
import gzip
import importlib.util
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


# ---- the wiki ---------------------------------------------------------------------------------

# Two composers, because the interesting property is a DIFFERENCE between them. Beethoven's page
# states a QID, so nothing about it is worth re-asking; Beach's states neither a QID nor an
# article, which is the one shape a volunteer can rescue and the only one this crawl re-reads.
BEETHOVEN = "{{#fte:person\n|Born Year=1770|Died Year=1827\n}}\n{{Wikidata|Q255}}\n"
BEACH = "{{#fte:person\n|Born Year=1867|Died Year=1944\n}}\n"
BEACH_LINKED = BEACH + "{{wp|Amy Beach}}\n"

BEETHOVEN_Q1 = "String Quartet No.1, Op.18 No.1 (Beethoven, Ludwig van)"
BEETHOVEN_Q2 = "String Quartet No.2, Op.18 No.2 (Beethoven, Ludwig van)"
BEACH_Q = "String Quartet, Op.89 (Beach, Amy Marcy)"

PEOPLE = {"Ludwig van Beethoven": {"canonical": "Ludwig van Beethoven", "qid": "Q255"},
          "Amy Beach": {"canonical": "Amy Beach", "qid": "Q235066"}}


class Wiki:
    """The four APIs fetch_imslp.py talks to, as dicts, recording every request.

    Deliberately literal about the reply SHAPES rather than convenient: `reported()` and the
    markers pass both turn on MediaWiki naming every title it was asked about, `missing` and all,
    and a stub that simply omitted the ones it had nothing for would make the cases agree with a
    reader that has the bug those two guards exist to stop.
    """

    def __init__(self, cats, pages, marks=None, wp=None, p839=None):
        self.cats = cats            # category title -> [full page title]
        self.page = 500             # cmlimit, so a listing longer than this needs continuing
        self.norm = {}              # requested title -> what MediaWiki answers under
        # A title the wiki refuses outright: it answers under `pages` with `invalid` and no
        # `missing`, which is a third shape the reader has to tell from the other two.
        self.bad = lambda t: any(ch in t for ch in "[]{}|")
        # ns -1 and -2. Tested BEFORE the interwiki split, because "Special:Random" has a colon
        # in its first token exactly as "de:Amy Beach" does and the wiki answers them differently.
        self.special = lambda t: t.split(":")[0] in ("Special", "Media")
        self.cont = "query-continue"     # the shape IMSLP sends today; MediaWiki >=1.26 sends
                                         # "continue" instead, and the walk has to follow both
        self.pages = pages          # IMSLP page title -> wikitext; absent = no such page
        self.marks = marks or {}    # IMSLP page title -> [marker category titles]
        self.wp = wp or {}          # en.wikipedia title -> QID; absent = no such article
        self.p839 = p839 or {}      # QID -> [IMSLP category name]
        self.asked = []
        self._ids, self._missing = {}, 0

    def pid(self, title):
        return self._ids.setdefault(title, 100 + len(self._ids))

    def _pages(self, entries):
        out = {}
        for title, body in entries:
            if body is None:
                self._missing += 1
                out[str(-self._missing)] = {"title": title, "missing": ""}
            elif "invalid" in body or "special" in body:
                # NO pageid: a title the wiki refuses is not a page, and handing the stub one
                # would let a reader that keys on `pageid` pass against a reply it never sees.
                self._missing += 1
                out[str(-self._missing)] = dict(body, title=title)
            else:
                out[str(self.pid(title))] = dict(body, pageid=self.pid(title), title=title)
        return {"query": {"pages": out}}

    def get(self, api, params):
        self.asked.append((api, dict(params)))
        if params.get("action") == "wbgetentities":
            return {"entities": {q: {"claims": {"P839": [
                {"mainsnak": {"snaktype": "value", "datavalue": {"value": v}}}
                for v in self.p839.get(q, [])]}} for q in params["ids"].split("|")}}
        titles = [t for t in params.get("titles", "").split("|") if t]
        if params.get("list") == "categorymembers":
            rows = self.cats[params["cmtitle"]]
            at = int(params.get("cmcontinue") or 0)
            d = {"query": {"categorymembers": [
                {"pageid": self.pid(t), "title": t} for t in rows[at:at + self.page]]}}
            if at + self.page < len(rows):
                # The two shapes nest differently, which is the whole reason a reader can miss
                # one: 1.18 puts the token under the list name, later versions do not.
                d[self.cont] = ({"categorymembers": {"cmcontinue": str(at + self.page)}}
                                if self.cont == "query-continue"
                                else {"cmcontinue": str(at + self.page), "continue": "-||"})
            return d
        if params.get("prop") == "pageprops":
            # MediaWiki answers under the NORMALIZED title and names the mapping in `normalized`,
            # so every reader here has to walk it forward — which is why the stub normalizes
            # rather than echoing. An interwiki title then comes back in its OWN block and never
            # under `pages`, measured against the live API, and that is the whole reason a reader
            # can skip it forever without noticing.
            canon = {t: self.norm.get(t, t) for t in titles}
            iw = {c for c in canon.values()
                  if ":" in c.split(" ")[0] and c not in self.wp
                  and not self.special(c) and not self.bad(c)}
            d = self._pages([
                (c, {"invalid": "", "invalidreason": "bad character"} if self.bad(c)
                 else {"ns": -1, "special": ""} if self.special(c)
                 else ({"pageprops": {"wikibase_item": self.wp[c]}} if c in self.wp else None))
                for c in dict.fromkeys(canon.values()) if c not in iw])
            if iw:
                d["query"]["interwiki"] = [{"title": c, "iw": c.split(":")[0]}
                                           for c in sorted(iw)]
            moved = [{"from": t, "to": c} for t, c in canon.items() if t != c]
            if moved:
                d["query"]["normalized"] = moved
            return d
        if params.get("prop") == "categories":
            return self._pages([
                (t, {"categories": [{"title": c} for c in self.marks.get(t, [])]}
                 if t in self.pages else None) for t in titles])
        if params.get("prop") == "revisions":
            return self._pages([
                (t, {"revisions": [{"*": self.pages[t]}]} if t in self.pages else None)
                for t in titles])
        raise AssertionError("the stub was asked something it does not model: %r" % (params,))


def wiki(orig=(BEETHOVEN_Q1, BEACH_Q), arr=()):
    """The fixture every case starts from: two composers, one quartet page each."""
    return Wiki(
        cats={"Category:For 2 violins, viola, cello": list(orig),
              "Category:For 2 violins, viola, cello (arr)": list(arr)},
        pages={"Category:Beethoven, Ludwig van": BEETHOVEN,
               "Category:Beach, Amy Marcy": BEACH,
               BEETHOVEN_Q1: "|Work Title=String Quartet No.1\n|Opus/Catalogue Number=Op.18/1\n",
               BEETHOVEN_Q2: "|Work Title=String Quartet No.2\n|Opus/Catalogue Number=Op.18/2\n",
               BEACH_Q: "|Work Title=String Quartet\n|Opus/Catalogue Number=Op.89\n"},
        marks={BEETHOVEN_Q1: ["Category:Scores"], BEETHOVEN_Q2: ["Category:Scores"],
               BEACH_Q: ["Category:Scores", "Category:Recordings"]},
        wp={"Amy Beach": "Q235066"},
        p839={"Q255": ["Beethoven,_Ludwig_van"]})     # underscores, the way Wikidata stores it


def roster(fi, **extra):
    """Rewrite the people file for this run. A case needing a composer with NO quartets adds one
    here: the works crawl cannot see them by construction, which is the whole reason the candidate
    pass exists."""
    with open(fi.PEOPLE, "w", encoding="utf-8") as f:
        json.dump(dict(PEOPLE, **extra), f)


def load(tmp, w):
    """A fresh copy of the module, pointed at a temp cache, with the network stubbed.

    Reloaded per case because main() is written against module-level paths — fine for a script,
    over-engineering to change for a test. build_imslp's own PEOPLE has to move too: fetch_imslp
    asks it which pages are attributable rather than keeping a second copy of the join.
    """
    spec = importlib.util.spec_from_file_location("fi", os.path.join(HERE, "fetch_imslp.py"))
    fi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fi)
    fi.OUT = os.path.join(tmp, "imslp-scrape.json")
    fi.PEOPLE = os.path.join(tmp, "people.json")
    fi.PAUSE = 0
    # The stub goes in at get(), because what almost every case asserts is WHICH requests a run
    # makes. The two about the retry guard want the real one and keep it here.
    fi._get, fi.get = fi.get, w.get
    with open(fi.PEOPLE, "w", encoding="utf-8") as f:
        json.dump(PEOPLE, f)
    sys.path.insert(0, HERE)
    import build_imslp
    build_imslp.PEOPLE = fi.PEOPLE
    return fi


def run(fi, argv=()):
    """Run main() and return (the cache it wrote, what it printed).

    It does NOT clear the request log — a case that wants one run's requests clears it itself,
    before the run it is asking about. Said here because the sentence that used to be here
    claimed the opposite, and a case written trusting it would read two runs' requests as one and
    pass without asserting anything.
    """
    argv_, out_, err_ = sys.argv, sys.stdout, sys.stderr
    sys.argv = ["fetch_imslp.py"] + list(argv)
    buf = io.StringIO()
    sys.stdout = sys.stderr = buf
    try:
        fi.main()
    finally:
        sys.argv, sys.stdout, sys.stderr = argv_, out_, err_
    with open(fi.OUT, encoding="utf-8") as f:
        return json.load(f), buf.getvalue()


class replies:
    """One canned HTTP reply, for the two cases that want get() itself rather than a stub of it.

    Patched at urlopen because the payload-block guard is the thing under test and a stub of
    get() is a stub of the guard. Restored in a finally: urllib.request is one module object for
    the whole process, so leaving it patched would reach the next case.
    """

    def __init__(self, fi, payload, encoding=None):
        self.n, self.payload, self.corrupt = 0, payload, False
        self.headers = {"Content-Encoding": encoding} if encoding else {}
        self.real = fi.urllib.request.urlopen
        self.fi = fi
        self.req = None
        def opened(req, timeout=None):
            self.req = req      # so a case can assert what was ASKED for
            return self
        fi.urllib.request.urlopen = opened

    def read(self):
        self.n += 1
        body = json.dumps(self.payload).encode("utf-8")
        if self.headers.get("Content-Encoding") != "gzip":
            return body
        out = bytearray(gzip.compress(body))
        if self.corrupt:
            # Byte 10 is the FIRST byte of the deflate stream — the gzip header is 10 bytes — and
            # corrupting it raises zlib.error ("invalid stored block lengths"). The choice is
            # load-bearing: measured over every single-byte flip of this blob, 95 raise
            # BadGzipFile and 2 EOFError, both already caught, and only 6 reach zlib.error. A
            # mutation picked at random would pass against a tuple that does not list it.
            out[10] ^= 0xFF
        return bytes(out)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def restore(self):
        self.fi.urllib.request.urlopen = self.real


def crawled(w):
    """The categories this run listed."""
    return [p["cmtitle"] for _api, p in w.asked if p.get("list") == "categorymembers"]


def read(w):
    """Every page title this run asked for the CONTENT of — composers, candidates, work info."""
    return [t for _api, p in w.asked if p.get("prop") == "revisions"
            for t in p["titles"].split("|")]


def marked(w):
    return [t for _api, p in w.asked if p.get("prop") == "categories"
            for t in p["titles"].split("|")]


def resolved(w):
    return [t for _api, p in w.asked if p.get("prop") == "pageprops"
            for t in p["titles"].split("|")]


def entities(w):
    """The QID batches asked of Wikidata."""
    return [p["ids"] for _api, p in w.asked if p.get("action") == "wbgetentities"]


def titles(cache, key="orig"):
    return {t + " (" + c + ")" for _id, t, c in cache["works"][key]}


# ---- the cases --------------------------------------------------------------------------------

@case("a warm run asks the category again")
def recrawls(fi, w):
    run(fi)
    w.asked.clear()
    _cache, log = run(fi)
    assert crawled(w) == [fi.ORIG, fi.ARR], (
        "a second run listed %r. The crawl is the only pass that can see a page nothing else "
        "knows the title of, so skipping it makes a monthly run a guaranteed no-op." % crawled(w))
    assert "cached:" not in log, "the early return is back:\n%s" % log


@case("a work page that appeared between runs reaches every pass downstream of the crawl")
def discovers_new_page(fi, w):
    run(fi)
    w.cats[fi.ORIG].append(BEETHOVEN_Q2)              # somebody uploaded a score this month
    w.asked.clear()
    cache, _log = run(fi)
    assert BEETHOVEN_Q2 in titles(cache), (
        "the new page never entered the listing: %r" % sorted(titles(cache)))
    assert BEETHOVEN_Q2 in cache["markers"], "no markers were fetched for the new page"
    assert BEETHOVEN_Q2 in cache["workinfo"], (
        "no work info was fetched for the new page, so count_works() reads it as uncatalogued")
    assert BEETHOVEN_Q1 not in marked(w) and BEETHOVEN_Q1 not in read(w), (
        "the pages already held were re-asked as well: %r. Discovery is meant to cost ~12 "
        "requests, not a second download of the whole cache." % read(w))


@case("a page that left the category leaves the listing")
def drops_removed_page(fi, w):
    # Padded well clear of MIN_KEEP: what this asserts is that the listing REPLACES, and it must
    # not start failing the day somebody raises the floor for a reason of its own.
    bulk = ["Quartet No.%d (Beethoven, Ludwig van)" % n for n in range(3, 11)]
    for t in bulk:
        w.pages[t] = "|Work Title=%s\n" % t
    w.cats[fi.ORIG] += bulk
    run(fi)
    w.cats[fi.ORIG].remove(BEACH_Q)                   # recategorised: it was never a quartet
    cache, _log = run(fi)
    assert BEACH_Q not in titles(cache), (
        "the listing merged instead of replacing: %r. The category is the live answer to what is "
        "in it, and a page that is out of it is not a quartet any more." % sorted(titles(cache)))
    # `is not None`, not truthiness: a page carrying none of the four markers caches as 0, which
    # is a real answer and a falsy one.
    assert cache["markers"].get(BEACH_Q) is not None, (
        "the markers for a departed page were discarded: nothing reads them, and throwing them "
        "away means paying for them again if it comes back")


@case("a crawl that fails leaves the cached listing alone")
def failed_crawl_keeps_listing(fi, w):
    run(fi)
    good = w.get

    def broken(api, params):
        if params.get("list") == "categorymembers":
            raise OSError("simulated 503 after five retries")
        return good(api, params)

    fi.get = broken
    try:
        run(fi)
    except OSError:
        pass
    else:
        raise AssertionError("a crawl that never answered was reported as a run that finished")
    with open(fi.OUT, encoding="utf-8") as f:
        cache = json.load(f)
    assert titles(cache) == {BEETHOVEN_Q1, BEACH_Q}, (
        "a dropped reply retired the pages it had not reached: %r. members() has to raise rather "
        "than return a short list, or the listing shrinks to whatever arrived." % sorted(
            titles(cache)))


@case("a composer page naming no identifier is asked again, and a link added since is followed")
def rescues_unidentified(fi, w):
    cache, _log = run(fi)
    assert cache["wikitext"]["Beach, Amy Marcy"] == BEACH, (
        "the fixture did not cache the unidentified page: %r"
        % (cache["wikitext"].get("Beach, Amy Marcy"),))
    assert BEACH_Q not in cache["workinfo"], (
        "a composer nothing could place had her pages fetched anyway — the fixture is not "
        "testing what the next assertion thinks it is")
    w.pages["Category:Beach, Amy Marcy"] = BEACH_LINKED
    w.asked.clear()
    cache, _log = run(fi)
    assert "Category:Beach, Amy Marcy" in read(w), (
        "a page stating no QID and no article was never re-read: %r. It is the only shape a "
        "volunteer can rescue, and no other pass looks at it." % read(w))
    assert cache["wikitext"]["Beach, Amy Marcy"] == BEACH_LINKED, "the new link was not stored"
    assert "Amy Beach" in resolved(w) and cache["wp"].get("Amy Beach")["qid"] == "Q235066", (
        "the article IMSLP now names was never resolved, so the join still has no key")
    assert BEACH_Q in cache["workinfo"], (
        "the rescue stopped at the identity: her quartet page is attributable now and its "
        "catalogue fields are what make a count possible")


@case("a composer page naming only an interwiki article is asked again too")
def interwiki_is_not_a_key(fi, w):
    # Most of the pages the monthly re-ask asks for name a {{wp|de:…}} instead — en.wikipedia has
    # no such title, and fetch_wp
    # resolved every one of them to nothing. They are as unplaced as a page naming nothing at
    # all — and reading the mere PRESENCE of a wp value as an identifier shut the one group that
    # needed asking out of the re-ask permanently.
    w.pages["Category:Beach, Amy Marcy"] = BEACH + "{{wp|de:Amy Beach}}\n"
    cache, _log = run(fi)
    assert not (cache["wp"].get("de:Amy Beach") or {}).get("qid"), (
        "the fixture's interwiki link resolved after all: %r" % (cache["wp"].get("de:Amy Beach"),))
    w.asked.clear()
    run(fi)
    assert "Category:Beach, Amy Marcy" in read(w), (
        "a page whose only link resolves to nothing was treated as joined: %r. Naming an article "
        "is not having a key, and nothing else will ever look at that page again." % read(w))


@case("a composer page already stating an identifier is never asked again")
def identified_is_not_reasked(fi, w):
    run(fi)
    w.asked.clear()
    run(fi)
    assert "Category:Beethoven, Ludwig van" not in read(w), (
        "a page joined by QID was re-downloaded: %r. That is 1.1 MB of wikitext for a spelling "
        "change nothing reads, against a volunteer-funded server." % read(w))


@case("a warm run asks for the absences and nothing else")
def warm_run_is_cheap(fi, w):
    # The budget half, and it is not decoration: re-asking everything is what --refresh is for,
    # and it costs megabytes of unchanged wikitext against a volunteer-funded server. What a warm run
    # may ask for is the categories, because that is where a new page appears, and the three
    # absences that a volunteer or a Wikidata editor can turn into answers.
    run(fi)
    w.asked.clear()
    run(fi)
    assert crawled(w) == [fi.ORIG, fi.ARR], (
        "the categories were not both listed: %r" % crawled(w))
    assert read(w) == ["Category:Beach, Amy Marcy",      # yields no key
                       "Category:Beach, Amy"], (        # a guess that found no page
        "a warm run asked for content it already holds, or stopped asking for an absence: %r"
        % read(w))
    assert entities(w) == ["Q235066"], (
        "P839 was re-asked for a QID already stating a claim, or stopped re-asking one stating "
        "none: %r" % entities(w))
    assert not marked(w) and not resolved(w), (
        "markers or Wikipedia titles were re-resolved: %r / %r" % (marked(w), resolved(w)))


@case("a P839 claim Wikidata did not state is asked again")
def p839_absence_is_reasked(fi, w):
    # This pass answers PRESENCE — it is the only thing that can tell a composer IMSLP holds with
    # no quartets from one IMSLP has never heard of. A large share of the roster's QIDs are stored
    # as None, and a None nobody re-asks is #62 one pass over: the editor who adds the claim is
    # never noticed and the composer reads as absent forever.
    cache, _log = run(fi)
    assert cache["p839"]["Q235066"] is None, (
        "the fixture already had a claim for her: %r" % (cache["p839"]["Q235066"],))
    w.p839["Q235066"] = ["Beach, Amy Marcy"]
    w.asked.clear()
    cache, _log = run(fi)
    assert cache["p839"]["Q235066"] == ["Beach, Amy Marcy"], (
        "a claim added since the last run was never asked for: %r"
        % (cache["p839"]["Q235066"],))
    assert entities(w) == ["Q235066"], (
        "the QIDs already stating a claim were re-asked as well: %r" % entities(w))
    assert BEACH_Q in cache["workinfo"], (
        "the new identifier placed her but nothing downstream followed: her quartet page is "
        "attributable now and its catalogue fields are what make a count possible")


@case("a candidate guess that found no page is asked again")
def candidate_absence_is_reasked(fi, w):
    # The composer with no quartets is invisible to the works crawl BY CONSTRUCTION, so this is
    # the only pass that can ever place them — and its answer for nearly every guess is "IMSLP has
    # no page by this name", which is exactly the answer a volunteer changes.
    roster(fi, **{"Samuel Barber": {"canonical": "Samuel Barber", "qid": "Q234151"}})
    cache, _log = run(fi)
    assert cache["candidates"]["Barber, Samuel"] is None, (
        "the fixture already had a page for him: %r" % (cache["candidates"]["Barber, Samuel"],))
    w.pages["Category:Barber, Samuel"] = "{{#fte:person\n|Born Year=1910\n}}\n{{Wikidata|Q234151}}\n"
    w.asked.clear()
    cache, _log = run(fi)
    assert "Category:Barber, Samuel" in read(w), (
        "a guess that came back empty was never asked again: %r. Nothing else looks for a "
        "composer with no quartets, so 'not on IMSLP' would be permanent." % read(w))
    assert cache["candidates"]["Barber, Samuel"], (
        "the page that appeared at the guessed title was not stored: %r"
        % (cache["candidates"]["Barber, Samuel"],))


@case("a Wikipedia article IMSLP names but does not exist is asked again")
def wp_absence_is_reasked(fi, w):
    # The fourth absence, and the one that decides whether the second can ever finish its job:
    # The composer pages above are re-downloaded every month precisely BECAUSE their link resolved
    # to nothing, so leaving the call that could change that answer un-rerun makes the re-ask
    # above unable to conclude anything. "Gubaidulina, Sofia" is the live shape — IMSLP names an
    # article that does not exist, and a redirect created since is all it would take.
    w.pages["Category:Beach, Amy Marcy"] = BEACH + "{{wp|Amy Marcy Beach}}\n"
    cache, _log = run(fi)
    assert cache["wp"].get("Amy Marcy Beach") is None, (
        "the fixture's article resolved after all: %r" % (cache["wp"].get("Amy Marcy Beach"),))
    w.wp["Amy Marcy Beach"] = "Q235066"               # a redirect created since
    w.asked.clear()
    cache, _log = run(fi)
    assert "Amy Marcy Beach" in resolved(w), (
        "a title that resolved to nothing was never asked again: %r" % resolved(w))
    assert (cache["wp"].get("Amy Marcy Beach") or {}).get("qid") == "Q235066", (
        "the redirect created since was not followed: %r" % (cache["wp"].get("Amy Marcy Beach"),))
    assert BEACH_Q in cache["workinfo"], (
        "resolving the title placed her but nothing downstream followed")


@case("a guessed page that exists but yields no key is asked again")
def candidate_without_key_is_reasked(fi, w):
    # The same rule fetch_composers uses, because these are the same kind of page — 7 in the
    # shipped cache exist and state nothing joinable, and build_imslp joins on this rung
    # (`cand-qid`), so a volunteer adding {{Wikidata|Q…}} to one is exactly what it is for.
    # Re-asking only the guesses that came back EMPTY would miss every one of them.
    roster(fi, **{"Samuel Barber": {"canonical": "Samuel Barber", "qid": "Q234151"}})
    w.pages["Category:Barber, Samuel"] = "{{#fte:person\n|Born Year=1910\n}}\n"
    cache, _log = run(fi)
    assert cache["candidates"]["Barber, Samuel"], (
        "the fixture's guessed page was not found: %r" % (cache["candidates"]["Barber, Samuel"],))
    w.pages["Category:Barber, Samuel"] += "{{Wikidata|Q234151}}\n"
    w.asked.clear()
    cache, _log = run(fi)
    assert "Category:Barber, Samuel" in read(w), (
        "a guessed page stating nothing joinable was never re-read: %r. It is the same page "
        "fetch_composers re-asks; only the pass that found it differs." % read(w))
    assert "Q234151" in (cache["candidates"]["Barber, Samuel"] or ""), (
        "the claim added since was not stored: %r" % (cache["candidates"]["Barber, Samuel"],))


@case("the request asks for gzip, and a gzipped reply is decoded")
def gzip_round_trip(fi, w):
    # urllib does not ask for it, and one pass here is enormous without it: wbgetentities has no
    # per-property filter, so asking 50 items for their P839 returns their complete claim sets —
    # 24.6 MB over one monthly run's re-asks, against 4.0 MB compressed. Both halves are
    # asserted, because asking without decoding is a crash and decoding without asking is a
    # header nobody sends.
    fi.TRIES = 1
    reads = replies(fi, {"query": {"pages": {}}}, encoding="gzip")
    try:
        d = fi._get(fi.IMSLP_API, {"action": "query", "titles": "X"})
    except (ValueError, OSError) as e:
        raise AssertionError("a gzipped reply was not decoded: %s" % e)
    finally:
        reads.restore()
    assert d == {"query": {"pages": {}}}, "the decoded reply was not returned: %r" % (d,)
    assert reads.req.get_header("Accept-encoding") == "gzip", (
        "the request never asked for compression, so a server that offers it will not: %r"
        % (dict(reads.req.headers),))


@case("an article on another wiki is recorded as an answer, not asked forever")
def interwiki_is_an_answer(fi, w):
    # 233 of the 236 titles stored as None are this shape, and en.wikipedia answers them in
    # `query.interwiki` and never under `pages` — so the resolve loop skipped them, nothing was
    # written, and re-asking an absence became a question no reply could ever settle, put every
    # month forever. That is the defect this whole branch is about, introduced by its own fix.
    w.pages["Category:Beach, Amy Marcy"] = BEACH + "{{wp|de:Amy Beach}}\n"
    cache, _log = run(fi)
    assert cache["wp"].get("de:Amy Beach") == {"title": None, "qid": None, "iw": "de"}, (
        "the API said this title belongs to another wiki and nothing was written down: %r"
        % (cache["wp"].get("de:Amy Beach", "<absent>"),))
    w.asked.clear()
    run(fi)
    assert "de:Amy Beach" not in resolved(w), (
        "a title no reply can ever settle was asked again: %r" % resolved(w))
    assert "Category:Beach, Amy Marcy" in read(w), (
        "recording the non-answer also retired the composer page, which is the one thing a "
        "volunteer CAN fix: %r" % read(w))


@case("an interwiki answer is recorded under the title that was ASKED for")
def interwiki_keyed_by_request(fi, w):
    # Every other write in fetch_wp walks `normalized` forward and stores under the BATCH title,
    # because that is what `todo` looks up — parse_person's reading of the wikitext. Keying the
    # interwiki answer by the reply's title instead puts it where nothing looks, and the title is
    # then re-asked every run forever with the answer never recordable: the defect the block was
    # added to fix, one key over. The 14 `en:` titles in the shipped cache resolved only because
    # `normalized` mapped them back, so normalization of these titles is not hypothetical.
    w.pages["Category:Beach, Amy Marcy"] = BEACH + "{{wp|:de:Amy Beach}}\n"
    w.norm = {":de:Amy Beach": "de:Amy Beach"}        # MediaWiki drops the leading colon
    cache, _log = run(fi)
    assert cache["wp"].get(":de:Amy Beach") == {"title": None, "qid": None, "iw": "de"}, (
        "the answer was filed under the reply's title, not the one asked for: %r"
        % {k: v for k, v in cache["wp"].items() if "Amy Beach" in k})
    w.asked.clear()
    run(fi)
    assert ":de:Amy Beach" not in resolved(w), (
        "a title that was answered for good is asked again every run: %r" % resolved(w))


@case("a title en.wikipedia will not hold is recorded as an answer that is not a key")
def unusable_title_is_not_a_key(fi, w):
    # WP_PATTERNS captures anything up to the closing brace, so both of these reach the resolver.
    # en.wikipedia answers `[[Amy Beach]]` with `invalid` and `Special:Random` with `special`
    # (ns -1) — under `pages`, neither carrying `missing` — so both used to be written as a
    # RESOLVED answer holding the bad string as their title. has_key() reads a bare title as a
    # key, so the composer page behind one was retired from the re-ask for good while the join
    # could never match it.
    # BOTH shapes in one case on purpose: the first fix enumerated `invalid` and `special` was
    # missed by it. What is asserted is the closed-world property — an article has a pageid, a
    # name that might become one says `missing`, and anything else is neither — so a sixth shape
    # MediaWiki adds later is covered without a sixth case.
    for bad in ("[[Amy Beach]]", "Special:Random"):
        w.pages["Category:Beach, Amy Marcy"] = BEACH + "{{wp|%s}}\n" % bad
        cache, _log = run(fi)
        got = cache["wp"].get(bad, "<absent>")
        assert isinstance(got, dict) and not got.get("qid") and not got.get("title"), (
            "%r was filed as an article: %r" % (bad, got))
        w.asked.clear()
        run(fi)
        assert "Category:Beach, Amy Marcy" in read(w), (
            "the composer page was retired over %r, which can never resolve: %r. That page is "
            "the one thing a volunteer can still fix." % (bad, read(w)))
        assert bad not in resolved(w), (
            "%r is asked again every run and no reply can settle it: %r" % (bad, resolved(w)))


@case("an article with no Wikidata item is a key, because the join uses the title")
def resolved_title_is_a_key(fi, w):
    # The two predicates introduced on this branch have to agree. fetch_wp holds ANY resolution
    # and stops re-asking; if has_key demanded the QID, a composer page whose article has no
    # Wikidata item would be re-downloaded every month forever with no call left that could ever
    # settle it. build_imslp joins on the title as its fallback rung, so the title is a key.
    w.pages["Category:Beach, Amy Marcy"] = BEACH + "{{wp|Amy Beach}}\n"
    w.wp["Amy Beach"] = None                          # the article exists; Wikidata does not know it
    cache, _log = run(fi)
    assert cache["wp"].get("Amy Beach") == {"title": "Amy Beach", "qid": None}, (
        "the fixture did not resolve to a title without a QID: %r" % (cache["wp"].get("Amy Beach"),))
    w.asked.clear()
    run(fi)
    assert "Amy Beach" not in resolved(w), (
        "a title already resolved was re-asked: %r" % resolved(w))
    assert "Category:Beach, Amy Marcy" not in read(w), (
        "her page is re-downloaded every month over a key the join would happily use, and "
        "nothing re-resolves the article, so nothing can ever stop it: %r" % read(w))


@case("a corrupted compressed body is retried, not a traceback")
def corrupt_gzip_is_retried(fi, w):
    # gzip made this reachable. Truncation raises EOFError and most corruption raises
    # gzip.BadGzipFile, which IS an OSError — which is how the rare one gets missed: corruption
    # inside the stream raises zlib.error, which subclasses Exception directly and would end a
    # 48-request crawl with a traceback instead of a retry.
    # Two tries and no backoff, so the ORACLE is whether a second read happened: a failure the
    # tuple catches is retried, one it does not ends the crawl on the first.
    fi.TRIES, fi.BACKOFF = 2, [0]
    reads = replies(fi, {"query": {"pages": {}}}, encoding="gzip")
    reads.corrupt = True
    try:
        fi._get(fi.IMSLP_API, {"action": "query", "titles": "X"})
    except Exception as e:
        assert reads.n == 2, (
            "a corrupted body escaped the retry ladder as %s after %d read: a 48-request crawl "
            "ends on a traceback where a retry was the whole point." % (type(e).__name__, reads.n))
    else:
        raise AssertionError("a corrupted body was returned as an answer")
    finally:
        reads.restore()


@case("a continuation token in the modern shape is followed")
def follows_both_continuations(fi, w):
    # IMSLP answers like MediaWiki 1.18 today and pages with `query-continue`; every version since
    # 1.26 sends `continue` instead. Reading only the old shape ends the walk normally after the
    # first page — no error, no exception — and since the crawl REPLACES the listing, that is the
    # one failure here that writes a wrong answer rather than none.
    w.cont, w.page = "continue", 1
    cache, _log = run(fi)
    assert titles(cache) == {BEETHOVEN_Q1, BEACH_Q}, (
        "the walk stopped at the first page of the listing: %r. It ends without raising, so the "
        "only symptom is a category that came back 12%% of its real size." % sorted(titles(cache)))


@case("a listing that came back short does not replace the one on record")
def short_crawl_is_refused(fi, w):
    # The floor, and the reason it is not redundant with the case above: the walk has more than
    # one way to end early and only one of them is a continuation shape somebody can fix. members()
    # raises on a transport failure, but a 200 that ends the walk SUCCEEDS, and against a pass that
    # replaces the listing that retires every page it did not reach — after which every pass below
    # tops up against the remains and nothing is ever red.
    bulk = ["Quartet No.%d (Beethoven, Ludwig van)" % n for n in range(3, 11)]
    for t in bulk:
        w.pages[t] = "|Work Title=%s\n" % t
    w.cats[fi.ORIG] += bulk
    cache, _log = run(fi)
    assert len(cache["works"]["orig"]) == 10, "the fixture did not cache ten pages"
    w.cats[fi.ORIG] = w.cats[fi.ORIG][:8]             # the walk comes back with eight of ten
    try:
        run(fi)
    except ValueError as e:
        assert "NOT replaced" in str(e), "the refusal does not say what it did: %s" % e
        assert "delete this category's entry" in str(e), (
            "the refusal offers no way through proportionate to the problem: %s. --refresh alone "
            "means re-asking everything to accept one category that legitimately shrank." % e)
    else:
        raise AssertionError(
            "a listing 80% of its cached size was written. The loss this guard is named for is "
            "not usually a big one: a walk that stops following the continuation returns ONE "
            "batch, and one batch is 500 pages whatever the category holds — 69% of `arr`.")
    with open(fi.OUT, encoding="utf-8") as f:
        cache = json.load(f)
    assert len(cache["works"]["orig"]) == 10, (
        "the short listing was saved before the floor was checked: %d pages left"
        % len(cache["works"]["orig"]))


@case("a reply that does not mention a composer does not blank the text already cached")
def unmentioned_is_not_blanked(fi, w):
    run(fi)
    good = w.get

    def drops_beach(api, params):
        d = good(api, params)
        if params.get("prop") == "revisions":
            d["query"]["pages"] = {k: v for k, v in d["query"]["pages"].items()
                                   if v.get("title") != "Category:Beach, Amy Marcy"}
        return d

    fi.get = drops_beach
    cache, _log = run(fi)
    assert cache["wikitext"]["Beach, Amy Marcy"] == BEACH, (
        "a malformed reply overwrote a page we hold with None: %r. Re-asking is what makes this "
        "reachable — before it, the worst a missing title cost was a composer never asked for."
        % (cache["wikitext"]["Beach, Amy Marcy"],))


@case("the P839 pass can read the reply Wikidata actually sends")
def entities_is_a_payload_block(fi, w):
    # wbgetentities answers `{"entities": …}` and carries no `query` at all, so a guard demanding
    # `query` of every reply spends the whole retry ladder and raises. It could not be caught by
    # running the pipeline: that cache was already full when the guard was written, and `todo` has
    # been empty on every run since — the first roster composer to arrive would have met it.
    fi.TRIES = 1
    reads = replies(fi, {"entities": {"Q255": {"claims": {}}}, "success": 1})
    try:
        d = fi._get(fi.WD_API, {"action": "wbgetentities", "ids": "Q255", "props": "claims"})
    except ValueError as e:
        # Caught and re-raised as a failure rather than allowed to propagate: ablate.py needs a
        # NAMED check to go red, and a suite that dies mid-run is INCONCLUSIVE, not proof.
        raise AssertionError("the reply Wikidata sends was read as an error: %s" % e)
    finally:
        reads.restore()
    assert d["entities"]["Q255"] == {"claims": {}}, "the Wikidata reply was not returned: %r" % (d,)
    assert reads.n == 1, "the reply was retried %d times before being accepted" % reads.n


@case("a reply with no payload block is still a failure")
def empty_reply_still_fails(fi, w):
    # The other half of the case above: the guard is meant to turn a 200 that answered nothing
    # into a retry, and widening it to let `entities` through must not widen it to let everything
    # through. Without this, deleting the guard passes the case above.
    fi.TRIES = 1
    reads = replies(fi, {"warnings": {"main": {}}})
    try:
        fi._get(fi.IMSLP_API, {"action": "query", "titles": "X"})
    except ValueError:
        pass
    else:
        raise AssertionError("a 200 carrying no answer was returned as one")
    finally:
        reads.restore()


def main():
    passed = failed = 0
    for name, fn in CASES:
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            w = wiki()
            try:
                fn(load(tmp, w), w)
                print("  ok   - %s" % name)
                passed += 1
            except AssertionError as e:
                print("  FAIL - %s\n       %s" % (name, e))
                failed += 1
            # Any other exception is reported as this case failing rather than allowed to end the
            # run. ablate.py needs a NAMED check to go red — a suite that dies mid-way is
            # INCONCLUSIVE, which proves nothing — and an ablated tree is exactly where a case
            # meets a cache key the old code never wrote.
            except Exception as e:
                print("  FAIL - %s\n       raised %s: %s" % (name, type(e).__name__, e))
                failed += 1
    print("\n%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
