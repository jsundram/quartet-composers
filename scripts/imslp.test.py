#!/usr/bin/env python3
# pwa-starter: none — this script is this repo's own
# /// script
# requires-python = ">=3.9"
# ///
"""Prove the four pure judgements in scripts/build_imslp.py, offline.

    python3 scripts/imslp.test.py

NO NETWORK: `template_fields`, `parse_person`, `candidates` and `confirms` read strings, so the
whole file runs in CI beside the other suites.

WHY IT EXISTS. Every defect this join has had was a WRONG PARSE that looked like a missing row,
and a missing row on a 884-composer page looks like nothing at all. The first reader used a
line-anchored regex, so every date on IMSLP came back None — the person template packs three
fields onto one line. The second read the article title out of `[[wikipedia:{{#iflang:…}}]]` as
the literal string "{{", which took out Beethoven, Mozart, Haydn, Bach, Brahms and Dvorak: the
six biggest catalogues on the site, silently, while 1,100 lesser composers joined fine and the
totals looked healthy. Nothing crashed either time. The only symptom was a number being smaller
than it should have been, and there is no baseline that says what it should have been — which is
why each shape below is a case, and why the case is written against the wikitext IMSLP actually
serves rather than a tidied version of it.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import build_imslp as bi                                # noqa: E402

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


# ------------------------------------------------------------------ template_fields
@case("three fields on one line are three fields, not one whose value is the rest of the line")
def packed_line(_):
    # The whole reason dates read as None. |Born Year=1723|Born Month=12|Born Day=22 is what
    # IMSLP serves, and "^\|([^=|]+)=(.*)$" reads Born Year as "1723|Born Month=12|Born Day=22".
    f = bi.template_fields("{{#fte:person\n|Born Year=1723|Born Month=12|Born Day=22\n}}")
    assert f["Born Year"] == "1723", f
    assert f["Born Day"] == "22", f


@case("a pipe inside a nested template does not split a field")
def nested_pipe(_):
    f = bi.template_fields("{{#fte:person\n|Biography Link={{wp|Joseph Achron}}\n|Sex=male\n}}")
    assert f["Biography Link"] == "{{wp|Joseph Achron}}", f
    assert f["Sex"] == "male", f


# ------------------------------------------------------------------ parse_person / the article
@case("[[wikipedia:Title|…]] — the plain form, 1031 of the 1770 pages")
def plain_link(_):
    got = bi.parse_person("{{#imslpcomposer:\n"
                          "|Biography Link=[[wikipedia:Carl_Friedrich_Abel|Wikipedia]]\n}}")
    assert got["wp"] == "Carl Friedrich Abel", got


@case("[[wikipedia:{{#iflang:en=X |af=…}}]] — the switch with English FIRST (Beethoven, Mozart)")
def iflang_en_first(_):
    got = bi.parse_person("{{#fte:person\n|Biography Link=[[wikipedia:{{#iflang:"
                          "en=Ludwig van Beethoven\n |af=af:Ludwig van Beethoven\n"
                          " |ru=ru:Бетховен, Людвиг ван\n}}|Wikipedia]]\n}}")
    assert got["wp"] == "Ludwig van Beethoven", got


@case("[[wikipedia:{{#iflang:\\n |en=X …}}]] — the switch with English SECOND (Bach, Brahms)")
def iflang_en_second(_):
    # Same template, different whitespace, and the pattern that handles the case above does not
    # handle this one. Bach, Brahms and Dvorak are here; Beethoven and Mozart are in the case
    # above. A reader that gets either shape wrong loses the biggest catalogues on the site.
    got = bi.parse_person("{{#fte:person\n|Biography Link=[[wikipedia:{{#iflang:\n"
                          " |en=Johann Sebastian Bach\n |de=de:Johann Sebastian Bach\n"
                          "}}|Wikipedia]]\n}}")
    assert got["wp"] == "Johann Sebastian Bach", got


@case("an #iflang switch with NO English article yields no article, not the braces")
def iflang_no_english(_):
    # Carlos Ehrensperger is on de.wikipedia only. The failure this guards is not "we miss him" —
    # it is capturing "{{" and carrying it downstream as a title to look up.
    got = bi.parse_person("{{#fte:person\n|Biography Link=[[wikipedia:{{#iflang:\n"
                          "|de=de:Carlos Ehrensperger\n}}|Wikipedia]]\n}}")
    assert got["wp"] is None, got


@case("{{wp|X}} beats a Wikipedia URL that belongs to somebody else on the same page")
def other_persons_url(_):
    # Achron's page links his BROTHER's article in Extra Information. Reading the page instead of
    # the Biography Link field attributes Isidor's article to Joseph, and the QID that comes back
    # is a real person's — so the join succeeds and points at the wrong man.
    got = bi.parse_person(
        "{{#fte:person\n|Biography Link={{wp|Joseph Achron}} ; [http://x.org About]\n"
        "|Extra Information=His brother [https://en.wikipedia.org/wiki/Isidor_Achron Isidor].\n}}")
    assert got["wp"] == "Joseph Achron", got


@case("{{Wikidata|Q…}} is read, and a page without one says so")
def wikidata_claim(_):
    got = bi.parse_person("{{#imslpcomposer:\n|List Pages=*{{Wikidata|Q168539}}\n*{{viaf|764}}\n}}")
    assert got["qid"] == "Q168539", got
    assert bi.parse_person("{{#fte:person\n|Sex=male\n}}")["qid"] is None


@case("a date IMSLP states loosely is not a year")
def loose_year(_):
    # "c.1723" is a claim about a decade. Rounding it to 1723 would then be compared against
    # Wikidata by confirms() and could accept or reject a join on a number nobody asserted.
    got = bi.parse_person("{{#fte:person\n|Born Year=c.1723\n|Died Year=1787\n}}")
    assert got["born"] is None and got["died"] == 1787, got


# ------------------------------------------------------------------ candidates
@case("the particle stays with the forename, because IMSLP files it that way")
def particle(_):
    assert bi.candidates("Ludwig van Beethoven")[0] == "Beethoven, Ludwig van"


@case("a two-token surname is tried too")
def two_token_surname(_):
    assert "Vaughan Williams, Ralph" in bi.candidates("Ralph Vaughan Williams")


@case("a one-word name yields no guess at all")
def mononym(_):
    assert bi.candidates("Hildegard") == []


# ------------------------------------------------------------------ confirms
@case("agreeing dates confirm; a surname alone never does")
def dates_agree(_):
    assert bi.confirms(1900, 1990, {"born": 1900, "died": 1990})
    assert not bi.confirms(1900, 1990, {"born": None, "died": None})


@case("a page with no dates is not evidence, however well the name fits")
def no_dates_no_join(_):
    # Four of the five rejects in the shipped run are this: the IMSLP page exists under exactly
    # the right "Surname, Forename" and states nothing to check it against.
    assert not bi.confirms(1927, 2001, {"born": None, "died": None})


@case("being alive has to agree — a living page is not a match for a composer who died")
def alive_must_agree(_):
    # Gubaidulina: born 1931 on both sides, died 2025 on Wikidata, still living on IMSLP. The
    # birth year alone would accept it. Rejecting is the conservative call and it is REPORTED,
    # so a stale page is visible rather than absorbed.
    assert not bi.confirms(1931, 2025, {"born": 1931, "died": None})
    assert bi.confirms(1931, None, {"born": 1931, "died": None})
    assert not bi.confirms(1931, 2025, {"born": 1931, "died": None})   # no `today` given


@case("confirms() names the rule it used, so the audit can report which")
def confirms_reason(_):
    assert bi.confirms(1900, 1990, {"born": 1900, "died": 1990}) == "dates"
    assert bi.confirms(1931, 2025, {"born": 1931, "died": None}, today=2026) == "stale-death"


@case("IMSLP not knowing about a RECENT death is staleness, not disagreement")
def stale_death(_):
    # Gubaidulina's page is locked, states 1931 and no death, and she died in 2025. Without this
    # the join rejects an exact-birth, exact-name match on a page that simply has not been edited
    # since. The birth year must match EXACTLY here, not within the usual slack.
    assert bi.confirms(1931, 2025, {"born": 1931, "died": None}, today=2026)
    assert not bi.confirms(1931, 2025, {"born": 1932, "died": None}, today=2026)


@case("staleness is BOUNDED — a death long past is still a disagreement")
def stale_death_bounded(_):
    # Thomas Wilson died in 2001 and IMSLP calls him living. Twenty-five years is not a lag; a
    # score has plausibly been uploaded since, so the silence is evidence against the match.
    assert not bi.confirms(1927, 2001, {"born": 1927, "died": None}, today=2026)
    # And with no `today` the exception cannot fire at all.
    assert not bi.confirms(1931, 2025, {"born": 1931, "died": None})


@case("a year of slack is allowed, two is not")
def slack(_):
    assert bi.confirms(1733, 1806, {"born": 1734, "died": 1806})
    assert not bi.confirms(1733, 1806, {"born": 1738, "died": 1806})


@case("a Wikidata IMSLP id keeps its namespace, and the join must not")
def strip_namespace(_):
    # P839 says "Category:Stravinsky,_Igor"; a work title's parenthetical says
    # "Stravinsky, Igor". Comparing the two unstripped attaches no pages at all, and 0 quartets
    # is exactly the answer nobody questions for a 20th-century composer.
    assert bi.strip_ns("Category:Stravinsky, Igor") == "Stravinsky, Igor"
    assert bi.strip_ns("Stravinsky, Igor") == "Stravinsky, Igor"


# ------------------------------------------------------------------ catalogue counting
def page(title, op="", n="", typ=""):
    return (title, "|Opus/Catalogue Number=%s\n|Number of Movements/Sections=%s\n|Page Type=%s"
            % (op, n, typ))


def tally(*pages):
    """count_works over a throwaway composer whose pages are (title, info) pairs."""
    entry = {"cats": ["X, Y"], "works": [[t, i, 1, 0] for i, (t, _) in enumerate(pages)]}
    info = {t + " (X, Y)": raw for t, raw in pages}
    return bi.count_works(entry, info)


@case("a set page's shared opus expands and MERGES with its members' own pages")
def set_collides(_):
    # Beethoven: "6 String Quartets, Op.18" carries Op.18, the six individual pages carry
    # Op.18 No.1..6. Adding them gives 12 works for six pieces of music.
    got, _, _ = tally(page("6 String Quartets, Op.18", "Op.18", "6 quartets:", "Collection"),
                      *[page("String Quartet No.%d, Op.18 No.%d" % (i, i),
                             "Op.18 No.%d" % i, "4 movements:") for i in range(1, 7)])
    assert got == 6, got


@case("a work with ONE catalogue name still counts")
def single_alias_counts(_):
    # The union-find only saw ids it was asked to merge, so every page naming exactly one
    # catalogue number — which is most of them — was silently absent and Beethoven counted 0.
    assert tally(page("String Quartet No.10, Op.74", "Op.74", "4 movements:"))[0] == 1


@case("two catalogues for the same SET zip positionally, they do not add")
def positional_zip(_):
    # Boccherini pages name both an opus and a Gerard range. Counting them separately took his
    # catalogue from 75 works to 153.
    got, _, _ = tally(page("6 String Quartets, Op.24", "Op.24 ; G.183-188", "6 quartets",
                           "Collection"))
    assert got == 6, got


@case("two catalogues for one WORK are one work")
def alias_one_work(_):
    assert tally(page("String Quartet No.14, K.387", "K.387 ; Op.10 No.1", "4 movements"))[0] == 1


@case("a mixed-case catalogue prefix survives")
def mixed_case_prefix(_):
    # Fanny Hensel's field reads "HelH 277" (Hellwig-Unruh). str.title() lowercases every later
    # capital and printed "Helh.277" beside her one quartet — a catalogue nobody wrote. Only the
    # first letter is normalised now, which also stops WoO needing to be a special case.
    assert bi.work_ids("HelH 277") == [{"HelH.277"}], bi.work_ids("HelH 277")
    assert bi.work_ids("WoO 14") == [{"WoO.14"}], bi.work_ids("WoO 14")
    assert bi.work_ids("op.18 No.1") == [{"Op.18 No.1"}], bi.work_ids("op.18 No.1")


@case("a plural unit under a single catalogue number is MOVEMENTS, not works")
def pieces_are_not_works(_):
    # Dvorak's Echo of Songs, B.152, says "12 pieces". Expanding it invented eleven quartets and
    # took his count from 14 — which is exactly right — to 25.
    assert tally(page("Echo of Songs, B.152", "B.152", "12 pieces"))[0] == 1


@case("an untyped page whose TITLE counts quartets still expands")
def titled_set_expands(_):
    # Vachon Op.11 and both Kammel sets state the count in the title and leave Page Type blank,
    # so requiring the Collection type alone would undercount them by five works each.
    assert tally(page("6 String Quartets, Op.11", "Op.11", "6 quartets"))[0] == 6


@case("an anthology with no catalogue number is dropped, not added")
def anthology_dropped(_):
    # "Selected String Quartets" reprints works that already have pages of their own. Counting it
    # as one more work is the same double count the expansion exists to remove.
    got, loose, anth = tally(page("Selected String Quartets", "", "10 quartets:", "Collection"))
    assert (got, loose, anth) == (0, 0, 1), (got, loose, anth)


@case("a page with no catalogue number at all is one work")
def uncatalogued_is_one(_):
    assert tally(page("Adagio for String Quartet", "", "1"))[0] == 1


@case("a catalogue prefix carrying a DIGIT keeps it, instead of donating it as the number")
def digit_prefix(_):
    # {{K6|417b}} rewrites to "K6.417b". With no separator required and no digits allowed in the
    # prefix, that matched pre="K", num="6" — so EVERY Koechel-6 alternate on the site produced
    # the id "K.6", and the union-find merged ten distinct Mozart quartets into one. He shipped
    # 31 works instead of 41. Nothing crashed: a smaller plausible number is this parser's
    # failure mode.
    assert bi.work_ids("{{K6|417b}}") == [{"K6.417b"}], bi.work_ids("{{K6|417b}}")
    a = bi.work_ids("K.421 ; {{K6|417b}}")[0]
    b = bi.work_ids("K.428 ; {{K6|421b}}")[0]
    assert not (a & b), "two Koechel-6 alternates collided: %r %r" % (a, b)


@case("the PERSON template is parsed, not whichever template comes first")
def leading_banner(_):
    # A maintenance banner can precede it. Parsing that returns {}, losing the dates, the sex and
    # the Biography Link — and confirms() then rejects an exact match for "no dates" with no
    # symptom anywhere.
    got = bi.parse_person("{{MoreInfo|Arthur Boisseau|biographical information}}\n"
                          "{{#fte:person\n|Born Year=1845|Born Month=2\n|Died Year=1908\n"
                          "|Sex=male\n}}")
    assert (got["born"], got["died"], got["sex"]) == (1845, 1908, "male"), got


@case("Biography Link outranks the rest of the page for EVERY pattern, not just its own")
def scope_beats_pattern(_):
    # With the loops the other way round, pattern 1 ({{wp|…}}) searched over the whole page beat
    # pattern 2 inside Biography Link. Stravinsky's own article is behind an #iflang switch in
    # that field, so the reader returned "nl:Oeuvre van Igor Stravinsky" from further down.
    got = bi.parse_person(
        "{{#fte:person\n"
        "|Biography Link=[[wikipedia:{{#iflang:\n |en=Igor Stravinsky\n |fr=fr:Igor Stravinsky\n"
        "}}|Wikipedia]]\n"
        "|List Pages=*{{wp|nl:Oeuvre van Igor Stravinsky}}\n}}")
    assert got["wp"] == "Igor Stravinsky", got


@case("what to fetch work info for is derived from the CACHE, not from the last build's output")
def attributable_from_cache(_):
    # The first version read the shipped imslp.json, which fetch_imslp.py calls BEFORE that file
    # exists on a cold clone: it returned [], no catalogue fields were fetched, and every page
    # then read as uncatalogued — works_n silently equalled pages for the whole roster.
    people = json.load(open(os.path.join(ROOT, "data", "people.json"), encoding="utf-8"))
    qid = next(v["qid"] for v in people.values() if v.get("qid"))
    cache = {
        "works": {"orig": [{"id": 1, "title": "String Quartet No.1", "composer": "X, Y"},
                           {"id": 2, "title": "Nope", "composer": "Stranger, A"}],
                  "arr": []},
        "wikitext": {"X, Y": "{{#fte:person\n|List Pages=*{{Wikidata|%s}}\n}}" % qid,
                     "Stranger, A": "{{#fte:person\n|Sex=male\n}}"},
        "wp": {}, "p839": {},
    }
    assert bi.attributable_titles(cache) == ["String Quartet No.1 (X, Y)"], \
        bi.attributable_titles(cache)


def main():
    passed = failed = 0
    for name, fn in CASES:
        try:
            fn(None)
            print("  ok   - %s" % name)
            passed += 1
        except AssertionError as e:
            print("  FAIL - %s\n       %s" % (name, e))
            failed += 1
    print("\n%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
