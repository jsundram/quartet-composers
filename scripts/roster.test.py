#!/usr/bin/env python3
# pwa-starter: none — this script is this repo's own
# /// script
# requires-python = ">=3.9"
# ///
"""Prove scripts/roster.py's decisions, and build_rows()'s respect for them, offline.

    python3 scripts/roster.test.py

NO NETWORK. The dossier's Wikipedia history lookups are the one networked part and are not under
test; everything that decides who ships is.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import build_data                                       # noqa: E402
try:
    import roster                                       # noqa: E402
except ImportError:                                     # ablate.py runs this against a base without it
    roster = None

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def entry(title, quartets=4, birth=1800, death=1870):
    return {"title": title, "birth": birth, "death": death, "quartets": quartets, "how": None}


PEOPLE = {
    "Old Name": {"canonical": "Old Name", "qid": "Q1"},
    "New Name": {"canonical": "New Name", "qid": "Q1"},
    "Fidelis Zitterbart": {"canonical": "Fidelis Zitterbart", "qid": "Q91947993", "birth": 1845,
                           "death": 1915, "wd_birth": 1845, "wd_death": 1915, "gender": "male"},
}


# ------------------------------------------------------------------ record
@case("a newcomer is recorded as NO, and nobody already decided is touched")
def newcomer_is_no(_):
    got, added, _ = roster.record([entry("A"), entry("Fidelis Zitterbart")], PEOPLE,
                                  {"A": True, "B": False})
    assert got == {"A": True, "B": False, "Fidelis Zitterbart": False}, got
    assert added == ["Fidelis Zitterbart"], added


@case("a rename carries the decision of the title it replaced, by Wikidata item")
def rename_inherits(_):
    got, added, renamed = roster.record([entry("New Name")], PEOPLE, {"Old Name": True})
    assert got["New Name"] is True and not added, (got, added)
    assert renamed == [("Old Name", "New Name")], renamed


@case("newcomers are counted from the base list; a rename and a departure are not newcomers")
def since_base(_):
    new, renamed, gone = roster.newcomers([entry("New Name"), entry("Fidelis Zitterbart")],
                                          [entry("Old Name"), entry("Left")], PEOPLE)
    assert new == ["Fidelis Zitterbart"], new
    assert renamed == [("Old Name", "New Name")], renamed
    assert gone == ["Left"], gone


# ------------------------------------------------------------------ the boxes
@case("ticked, unticked and capital-X boxes read; a box without a marker is not a decision")
def boxes(_):
    body = ("- [x] **Include A** <!-- roster: A -->\n"
            "- [ ] **Include Béla B** <!-- roster: Béla B -->\n"
            "* [X] Include C <!-- roster: C -->\n"
            "- [x] an ordinary task\n")
    assert roster.ticks(body) == {"A": True, "Béla B": False, "C": True}, roster.ticks(body)


@case("a box can decide only a newcomer, never somebody already on the roster")
def body_reaches_newcomers_only(_):
    got, changed = roster.apply({"A": True, "N": False}, {"A": False, "N": True}, {"N"})
    assert got == {"A": True, "N": True}, got
    assert changed == [("N", True)], changed


@case("the dossier's own box, once ticked, reads back as a yes for its title")
def round_trip(_):
    f = roster.facts("Fidelis Zitterbart", entry("Fidelis Zitterbart", quartets=125),
                     PEOPLE["Fidelis Zitterbart"], {}, None,
                     [["Giuseppe Cambini", 1746, 1825, 149, 900, 0, 0, "male"]])
    lines = roster.dossier(f, None, {}, False)
    body = "\n".join(lines).replace("- [ ]", "- [x]")
    assert roster.ticks(body) == {"Fidelis Zitterbart": True}, roster.ticks(body)


# ------------------------------------------------------------------ the flags
@case("a count near the top of the roster is flagged, and names who holds the record")
def big_count(_):
    rows = [["Giuseppe Cambini", 1746, 1825, 149, 900, 0, 0, "male"]] + \
           [["X%d" % i, 1800, 1850, 4, 10, 0, 0, "male"] for i in range(20)]
    f = roster.facts("Fidelis Zitterbart", entry("Fidelis Zitterbart", quartets=125),
                     PEOPLE["Fidelis Zitterbart"], {}, None, rows)
    assert f["q_rank"] == 2, f["q_rank"]
    assert any("2nd" in x and "Giuseppe Cambini" in x for x in f["flags"]), f["flags"]


@case("no readable count, no article, and a shared surname are each flagged")
def other_flags(_):
    rows = [["Joseph Haydn", 1732, 1809, 68, 9000, 0, 0, "male"]]
    f = roster.facts("Somebody Haydn", entry("Somebody Haydn", quartets=None), {}, {}, None, rows)
    text = " ".join(f["flags"])
    assert "no Wikipedia article" in text, text
    assert "table only" in text, text
    assert "Joseph Haydn" in text, text


@case("the entry is quoted without its citations")
def entry_text(_):
    wiki = "*[[A B]] (1800–1870): 4 quartets.<ref>{{cite web|url=x}}</ref> More.\n*[[C]]"
    assert roster.entry_line(wiki, "A B") == "*[[A B]] (1800–1870): 4 quartets. More.", \
        roster.entry_line(wiki, "A B")


# ------------------------------------------------------------------ build_rows
def build_with(decisions):
    with tempfile.TemporaryDirectory() as tmp:
        paths = {k: os.path.join(tmp, k + ".json") for k in ("list", "people", "views", "inclusion")}
        files = {"list": {"entries": [entry("Kept"), entry("Held")]},
                 "people": {"Kept": {"canonical": "Kept", "qid": "Q2", "birth": 1800, "death": 1870},
                            "Held": {"canonical": "Held", "qid": "Q3", "birth": 1800, "death": 1870}},
                 "views": {"months": ["2026-01"], "series": {}},
                 "inclusion": decisions}
        for k, v in files.items():
            json.dump(v, open(paths[k], "w"))
        saved = build_data.LIST, build_data.PEOPLE, build_data.VIEWS, getattr(build_data, "ROSTER", None)
        build_data.LIST, build_data.PEOPLE, build_data.VIEWS = paths["list"], paths["people"], paths["views"]
        build_data.ROSTER = paths["inclusion"]
        try:
            return [r[0] for r in build_data.build_rows()[0]]
        finally:
            build_data.LIST, build_data.PEOPLE, build_data.VIEWS, build_data.ROSTER = saved


@case("build_rows ships a yes and leaves out a no")
def build_respects_no(_):
    got = build_with({"Kept": True, "Held": False})
    assert got == ["Kept"], got


@case("build_rows refuses an entry nobody has decided on, rather than shipping it")
def build_refuses_undecided(_):
    try:
        got = build_with({"Kept": True})
    except build_data.BuildError as e:
        assert "Held" in str(e), e
        return
    raise AssertionError("built %r with Held undecided" % got)


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
        except Exception as e:                         # noqa: BLE001 - a missing function is a FAIL
            print("  FAIL - %s\n       raised: %s: %s" % (name, type(e).__name__, e))
            failed += 1
    print("\n%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
