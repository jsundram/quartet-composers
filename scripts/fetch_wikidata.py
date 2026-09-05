#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Resolve every composer to a canonical Wikipedia title + their Wikidata facts.

    python3 scripts/fetch_wikidata.py            # reads data/list.json, writes data/people.json

Three jobs in one pass, because they need the same batched MediaWiki lookup:

1. CANONICAL TITLES. Page views are counted per title, and a redirect is its own title with its
   own (tiny) count — asking for "Bela Bartok" returns 41 views instead of Béla Bartók's 14,330,
   with a 200 and no complaint. Everything downstream must use the canonical title, so it is
   resolved once here and cached.

2. BIRTH AND DEATH YEARS. The list page states dates in prose and is only as current as its last
   editor; Wikidata has them as structured claims (P569 born, P570 died) that a bot keeps fresh.
   This is what retires the old inferred "living in 2014" flag: a composer either has a death year
   or does not, as of today, rather than as of a decade-old snapshot.

3. SEX OR GENDER. P21, taken as Wikidata states it and labelled with Wikidata's own words. It is
   not a claim this project makes about anyone, and it is not inferred: a composer with no P21
   claim, or with no Wikidata item at all, gets null and stays null. Names and pronouns are NOT a
   fallback — a guess here is a guess about a person, and the whole point of reading a structured
   claim is that it is attributable to a source that can be corrected.

All three are cached in data/people.json, so re-running the rest of the pipeline needs no network.

WHERE THE TWO SOURCES DISAGREE the Wikidata value wins and the disagreement is reported, because a
silent divergence between the chart's dates and the page it links to is the kind of thing nobody
notices for years. Expect a handful: the list page lags Wikidata on recent deaths.

PRECISION IS KEPT. P569 can be precise to the day or only to the century; a "birth year" derived
from century precision is a guess. Anything coarser than year precision is dropped rather than
rounded, and the row falls back to the list page's prose date.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LIST = os.path.join(ROOT, "data", "list.json")
OUT = os.path.join(ROOT, "data", "people.json")

WIKI_API = "https://en.wikipedia.org/w/api.php"
WD_API = "https://www.wikidata.org/w/api.php"
UA = "quartet-composers/1.0 (https://github.com/jsundram/quartet-composers)"
BATCH = 50            # the titles=/ids= limit for an anonymous client
PAUSE = 0.15
TRIES = 5
BACKOFF = [2, 5, 15, 40]


def api(url, params):
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(url + "?" + q,
                                 headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(TRIES):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.load(r)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            if attempt == TRIES - 1:
                raise
            wait = BACKOFF[min(attempt, len(BACKOFF) - 1)]
            if isinstance(e, urllib.error.HTTPError):
                try:
                    wait = max(wait, int(e.headers.get("Retry-After", 0)))
                except (TypeError, ValueError):
                    pass
            time.sleep(wait)
    return {}


def resolve_titles(titles):
    """{given title: (canonical title, wikidata QID or None)} for everything that exists."""
    out = {}
    for i in range(0, len(titles), BATCH):
        chunk = titles[i:i + BATCH]
        d = api(WIKI_API, {"action": "query", "format": "json", "redirects": "1",
                           "prop": "pageprops", "ppprop": "wikibase_item",
                           "titles": "|".join(chunk)}).get("query", {})
        # given -> normalized -> redirect target, then confirm the endpoint is a real page.
        step = {}
        for m in d.get("normalized", []):
            step[m["from"]] = m["to"]
        for m in d.get("redirects", []):
            step[m["from"]] = m["to"]
        pages = {p["title"]: p for p in d.get("pages", {}).values() if "missing" not in p}
        for name in chunk:
            t = name
            for _ in range(4):                       # redirect chains are short; cap regardless
                if t in step and step[t] != t:
                    t = step[t]
                else:
                    break
            if t in pages:
                qid = pages[t].get("pageprops", {}).get("wikibase_item")
                out[name] = (t, qid)
        print("  titles %d/%d" % (min(i + BATCH, len(titles)), len(titles)), end="\r", flush=True)
        time.sleep(PAUSE)
    print()
    return out


def best_value(claims):
    """The datavalue of the highest-ranked usable claim, or None. Shared by every property read.

    RANK IS LOAD-BEARING, not metadata. Wikidata marks a value it knows to be wrong as
    `deprecated` rather than deleting it, so a naive claims[0] happily reads a value the community
    has already rejected. Tania León's item carries a deprecated P570 of 1996; she is alive and
    won the Pulitzer in 2021. Taking the first claim reported her as dead — the single worst thing
    this dataset could say about a living person.

    So: drop deprecated outright, prefer `preferred` over `normal`, and ignore novalue/somevalue
    snaks (which encode "known to have no value" / "value unknown" and carry no value at all).

    It lives in one function because the rule is one rule. P21 arrived after P569/P570 and the
    obvious way to add it was a second claims[0] read beside a correct one — which is how a fix
    stays fixed for exactly as long as nobody adds a property.
    """
    usable = [c for c in claims
              if c.get("rank") != "deprecated" and c.get("mainsnak", {}).get("snaktype") == "value"]
    if not usable:
        return None
    preferred = [c for c in usable if c.get("rank") == "preferred"]
    c = (preferred or usable)[0]
    try:
        return c["mainsnak"]["datavalue"]["value"]
    except (KeyError, TypeError):
        return None


def year_of(claims):
    """Year as an int, or None if there is no usable claim."""
    v = best_value(claims)
    if not isinstance(v, dict):
        return None
    # precision: 11 = day, 10 = month, 9 = year, 8 = decade, 7 = century. Below 9 the "year" is an
    # artifact of the encoding (a century claim serialises as +1700-00-00), not a fact.
    if v.get("precision", 0) < 9:
        return None
    t = v.get("time", "")
    if not t.startswith("+"):
        return None                                  # BCE; no composer here is, but don't guess
    try:
        return int(t[1:5])
    except ValueError:
        return None


# P21's value is an item, so the wire format is a QID and the label is ours to supply. These are
# Wikidata's own English labels, lowercased, and the map is deliberately not exhaustive: an item
# outside it keeps its QID (see gender_of), which is a value a human can look up and a check can
# catch, rather than a null that reads as "Wikidata doesn't say".
GENDERS = {
    "Q6581097": "male",
    "Q6581072": "female",
    "Q1097630": "intersex",
    "Q1052281": "trans woman",
    "Q2449503": "trans man",
    "Q48270": "non-binary",
    "Q48279": "third gender",
    "Q505371": "agender",
}


def gender_of(claims):
    """Wikidata's P21 value as a label, its raw QID if unmapped, or None.

    UNMAPPED IS NOT UNKNOWN. Falling back to None for a QID this file has never seen would file a
    real, stated value under "no data" — the one outcome that is wrong about a person rather than
    merely incomplete. So the QID goes through verbatim; validate.py fails on it, and the fix is a
    line in GENDERS rather than a mystery about who is missing from a filter.
    """
    v = best_value(claims)
    if not isinstance(v, dict):
        return None
    qid = v.get("id")
    return GENDERS.get(qid, qid) if qid else None


def fetch_facts(qids):
    """{qid: (birth_year, death_year, gender)}"""
    out = {}
    for i in range(0, len(qids), BATCH):
        chunk = qids[i:i + BATCH]
        d = api(WD_API, {"action": "wbgetentities", "format": "json",
                         "props": "claims", "ids": "|".join(chunk)}).get("entities", {})
        for qid, ent in d.items():
            claims = ent.get("claims", {})
            out[qid] = (year_of(claims.get("P569", [])), year_of(claims.get("P570", [])),
                        gender_of(claims.get("P21", [])))
        print("  claims %d/%d" % (min(i + BATCH, len(qids)), len(qids)), end="\r", flush=True)
        time.sleep(PAUSE)
    print()
    return out


def main():
    with open(LIST, encoding="utf-8") as f:
        entries = json.load(f)["entries"]
    titles = sorted({e["title"] for e in entries})

    print("resolving %d titles..." % len(titles))
    resolved = resolve_titles(titles)
    qids = sorted({q for _, q in resolved.values() if q})
    print("  %d resolved, %d with a Wikidata item" % (len(resolved), len(qids)))

    print("fetching birth/death/gender from Wikidata for %d items..." % len(qids))
    facts = fetch_facts(qids)

    people, disagree, no_wd = {}, [], []
    for e in entries:
        t = e["title"]
        canon, qid = resolved.get(t, (None, None))
        wb, wd_, g = facts.get(qid, (None, None, None)) if qid else (None, None, None)
        if qid is None or (wb is None and wd_ is None):
            no_wd.append(t)
        # Wikidata wins where both exist; the page is the fallback for the rest.
        birth = wb if wb is not None else e["birth"]
        death = wd_ if wd_ is not None else (e["death"] if wb is None else None)
        if wb is not None and e["birth"] is not None and wb != e["birth"]:
            disagree.append(("birth", t, e["birth"], wb))
        if wd_ is not None and e["death"] is not None and wd_ != e["death"]:
            disagree.append(("death", t, e["death"], wd_))
        people[t] = {"canonical": canon or t, "qid": qid, "birth": birth, "death": death,
                     "wd_birth": wb, "wd_death": wd_, "gender": g}

    # A death year Wikidata knows about and the page does not is the interesting case: it is
    # exactly the "still shown as living years after they died" bug this script exists to end.
    newly_dead = [t for t, p in people.items()
                  if p["wd_death"] and next(e["death"] for e in entries if e["title"] == t) is None]
    print("\nunresolved or no Wikidata dates: %d" % len(no_wd))
    print("date disagreements page vs Wikidata (Wikidata wins): %d" % len(disagree))
    for kind, t, page, wd_ in disagree[:12]:
        print("   %-6s %-30s page %s -> wikidata %s" % (kind, t, page, wd_))
    if len(disagree) > 12:
        print("   ... and %d more" % (len(disagree) - 12))
    print("\ndied since the list page last said otherwise: %d" % len(newly_dead))
    for t in newly_dead[:12]:
        print("   %-30s d. %s" % (t, people[t]["wd_death"]))

    # Printed as a tally rather than a single "women" number: an unmapped QID showing up here is
    # the one failure this property has, and it is invisible in a percentage.
    tally = {}
    for p_ in people.values():
        tally[p_["gender"]] = tally.get(p_["gender"], 0) + 1
    print("\nP21 sex or gender:")
    for g_, n in sorted(tally.items(), key=lambda kv: -kv[1]):
        note = "  <- not in GENDERS; add a label or validate.py will fail" \
               if g_ and g_ not in GENDERS.values() else ""
        print("   %-14s %d%s" % (g_ if g_ else "(none stated)", n, note))

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(people, f, ensure_ascii=False, indent=0, sort_keys=True)
    print("\nwrote data/people.json (%d, %d bytes)" % (len(people), os.path.getsize(OUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
