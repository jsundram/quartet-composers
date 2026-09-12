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
crawl is ~165 requests, and the reason the fix is "always re-crawl" rather than "--refresh
monthly" is that re-asking everything would download 3.5 MB of wikitext that has not changed. A
case that only proved re-asking would be satisfied by --refresh.
"""
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
            return self._pages([
                (t, {"pageprops": {"wikibase_item": self.wp[t]}} if t in self.wp else None)
                for t in titles])
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


def load(tmp, w):
    """A fresh copy of the module, pointed at a temp cache, with the network stubbed.

    Reloaded per case because main() is written against module-level paths — fine for a script,
    over-engineering to change for a test. build_imslp's own PEOPLE has to move too: fetch_imslp
    asks it which pages are attributable rather than keeping a second copy of the join.
    """
    spec = importlib.util.spec_from_file_location("fi", os.path.join(HERE, "fetch_imslp.py"))
    fi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fi)
    fi.OUT = os.path.join(tmp, "imslp.json")
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


def run(fi, w=None, argv=()):
    """Run main() and return (the cache it wrote, what it printed). Clears the request log after."""
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

    def __init__(self, fi, payload):
        self.n, self.payload = 0, payload
        self.real = fi.urllib.request.urlopen
        self.fi = fi
        fi.urllib.request.urlopen = lambda req, timeout=None: self

    def read(self):
        self.n += 1
        return json.dumps(self.payload).encode("utf-8")

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


def titles(cache, key="orig"):
    return {w["title"] + " (" + w["composer"] + ")" for w in cache["works"][key]}


# ---- the cases --------------------------------------------------------------------------------

@case("a warm run asks the category again")
def recrawls(fi, w):
    run(fi, w)
    w.asked.clear()
    _cache, log = run(fi, w)
    assert crawled(w) == [fi.ORIG, fi.ARR], (
        "a second run listed %r. The crawl is the only pass that can see a page nothing else "
        "knows the title of, so skipping it makes a monthly run a guaranteed no-op." % crawled(w))
    assert "cached:" not in log, "the early return is back:\n%s" % log


@case("a work page that appeared between runs reaches every pass downstream of the crawl")
def discovers_new_page(fi, w):
    run(fi, w)
    w.cats[fi.ORIG].append(BEETHOVEN_Q2)              # somebody uploaded a score this month
    w.asked.clear()
    cache, _log = run(fi, w)
    assert BEETHOVEN_Q2 in titles(cache), (
        "the new page never entered the listing: %r" % sorted(titles(cache)))
    assert BEETHOVEN_Q2 in cache["markers"], "no markers were fetched for the new page"
    assert BEETHOVEN_Q2 in cache["workinfo"], (
        "no work info was fetched for the new page, so count_works() reads it as uncatalogued")
    assert BEETHOVEN_Q1 not in marked(w) and BEETHOVEN_Q1 not in read(w), (
        "the pages already held were re-asked as well: %r. Discovery is meant to cost ~12 "
        "requests, not a second 3.5 MB download." % read(w))


@case("a page that left the category leaves the listing")
def drops_removed_page(fi, w):
    # Padded well clear of MIN_KEEP: what this asserts is that the listing REPLACES, and it must
    # not start failing the day somebody raises the floor for a reason of its own.
    bulk = ["Quartet No.%d (Beethoven, Ludwig van)" % n for n in range(3, 11)]
    for t in bulk:
        w.pages[t] = "|Work Title=%s\n" % t
    w.cats[fi.ORIG] += bulk
    run(fi, w)
    w.cats[fi.ORIG].remove(BEACH_Q)                   # recategorised: it was never a quartet
    cache, _log = run(fi, w)
    assert BEACH_Q not in titles(cache), (
        "the listing merged instead of replacing: %r. The category is the live answer to what is "
        "in it, and a page that is out of it is not a quartet any more." % sorted(titles(cache)))
    assert cache["markers"].get(BEACH_Q), (
        "the markers for a departed page were discarded: nothing reads them, and throwing them "
        "away means paying for them again if it comes back")


@case("a crawl that fails leaves the cached listing alone")
def failed_crawl_keeps_listing(fi, w):
    run(fi, w)
    good = w.get

    def broken(api, params):
        if params.get("list") == "categorymembers":
            raise OSError("simulated 503 after five retries")
        return good(api, params)

    fi.get = broken
    try:
        run(fi, w)
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
    cache, _log = run(fi, w)
    assert cache["wikitext"]["Beach, Amy Marcy"] == BEACH, (
        "the fixture did not cache the unidentified page: %r"
        % (cache["wikitext"].get("Beach, Amy Marcy"),))
    assert BEACH_Q not in cache["workinfo"], (
        "a composer nothing could place had her pages fetched anyway — the fixture is not "
        "testing what the next assertion thinks it is")
    w.pages["Category:Beach, Amy Marcy"] = BEACH_LINKED
    w.asked.clear()
    cache, _log = run(fi, w)
    assert "Category:Beach, Amy Marcy" in read(w), (
        "a page stating no QID and no article was never re-read: %r. It is the only shape a "
        "volunteer can rescue, and no other pass looks at it." % read(w))
    assert cache["wikitext"]["Beach, Amy Marcy"] == BEACH_LINKED, "the new link was not stored"
    assert "Amy Beach" in resolved(w) and cache["wp"]["Amy Beach"]["qid"] == "Q235066", (
        "the article IMSLP now names was never resolved, so the join still has no key")
    assert BEACH_Q in cache["workinfo"], (
        "the rescue stopped at the identity: her quartet page is attributable now and its "
        "catalogue fields are what make a count possible")


@case("a composer page naming only an interwiki article is asked again too")
def interwiki_is_not_a_key(fi, w):
    # 204 of the cached pages name a {{wp|de:…}}, en.wikipedia has no such title, and fetch_wp
    # resolved every one of them to nothing. They are as unplaced as a page naming nothing at
    # all — and reading the mere PRESENCE of a wp value as an identifier shut the one group that
    # needed asking out of the re-ask permanently.
    w.pages["Category:Beach, Amy Marcy"] = BEACH + "{{wp|de:Amy Beach}}\n"
    cache, _log = run(fi, w)
    assert cache["wp"]["de:Amy Beach"] is None, (
        "the fixture's interwiki link resolved after all: %r" % (cache["wp"]["de:Amy Beach"],))
    w.asked.clear()
    run(fi, w)
    assert "Category:Beach, Amy Marcy" in read(w), (
        "a page whose only link resolves to nothing was treated as joined: %r. Naming an article "
        "is not having a key, and nothing else will ever look at that page again." % read(w))


@case("a composer page already stating an identifier is never asked again")
def identified_is_not_reasked(fi, w):
    run(fi, w)
    w.asked.clear()
    run(fi, w)
    assert "Category:Beethoven, Ludwig van" not in read(w), (
        "a page joined by QID was re-downloaded: %r. That is 1.1 MB of wikitext for a spelling "
        "change nothing reads, against a volunteer-funded server." % read(w))


@case("a warm run with nothing new asks for nothing but the categories and the unplaced")
def warm_run_is_cheap(fi, w):
    run(fi, w)
    w.asked.clear()
    run(fi, w)
    assert crawled(w) == [fi.ORIG, fi.ARR], (
        "the categories were not both listed: %r" % crawled(w))
    assert read(w) == ["Category:Beach, Amy Marcy"], (
        "a run that discovered nothing still asked for content: %r" % read(w))
    assert not marked(w) and not resolved(w), (
        "markers or Wikipedia titles were re-resolved: %r / %r" % (marked(w), resolved(w)))
    assert not [p for _a, p in w.asked if p.get("action") == "wbgetentities"], (
        "P839 was re-asked for QIDs already on record")


@case("a continuation token in the modern shape is followed")
def follows_both_continuations(fi, w):
    # IMSLP answers like MediaWiki 1.18 today and pages with `query-continue`; every version since
    # 1.26 sends `continue` instead. Reading only the old shape ends the walk normally after the
    # first page — no error, no exception — and since the crawl REPLACES the listing, that is the
    # one failure here that writes a wrong answer rather than none.
    w.cont, w.page = "continue", 1
    cache, _log = run(fi, w)
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
    cache, _log = run(fi, w)
    assert len(cache["works"]["orig"]) == 10, "the fixture did not cache ten pages"
    w.cats[fi.ORIG] = [BEETHOVEN_Q1]                  # the walk comes back with one of ten
    try:
        run(fi, w)
    except ValueError as e:
        assert "NOT replaced" in str(e), "the refusal does not say what it did: %s" % e
    else:
        raise AssertionError("a listing that lost nine tenths of its pages was written anyway")
    with open(fi.OUT, encoding="utf-8") as f:
        cache = json.load(f)
    assert len(cache["works"]["orig"]) == 10, (
        "the short listing was saved before the floor was checked: %d pages left"
        % len(cache["works"]["orig"]))


@case("a reply that does not mention a composer does not blank the text already cached")
def unmentioned_is_not_blanked(fi, w):
    run(fi, w)
    good = w.get

    def drops_beach(api, params):
        d = good(api, params)
        if params.get("prop") == "revisions":
            d["query"]["pages"] = {k: v for k, v in d["query"]["pages"].items()
                                   if v.get("title") != "Category:Beach, Amy Marcy"}
        return d

    fi.get = drops_beach
    cache, _log = run(fi, w)
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
    print("\n%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
