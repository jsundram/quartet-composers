#!/usr/bin/env python3
# pwa-starter: none — this script is this repo's own
# /// script
# requires-python = ">=3.9"
# ///
"""Prove scripts/list_discrepancies.py flags what it should and never repeats itself, offline.

    python3 scripts/list_discrepancies.test.py

The silent failure is a monthly agent spending quota on the same composers, so the record gets the
most checks. The article sentences are real ones that produced false alarms.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import list_discrepancies as ld                         # noqa: E402

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def values(text, name="Ann Lee"):
    stated, numbered = ld.evidence(name, text)
    return [v for v, _, _ in stated], [v for v, _, _ in numbered]


@case("a stated count and a later numbered quartet are both read")
def reads_both():
    assert values("She wrote six string quartets.\n* String Quartet No. 7 (2025)") == ([6], [7])


@case("a part of the output is not a count")
def part_of():
    assert values("He then finished the first six string quartets.")[0] == []


@case("one published set is not a count")
def one_set():
    assert values("He published three string quartets, Op. 1.")[0] == []


@case("somebody else's quartets are not the subject's")
def somebody_else():
    assert values("She admired the sixteen string quartets of Beethoven.")[0] == []


@case("a piano quartet's number is not read as a string quartet's")
def piano_quartet():
    assert values("* Piano Quartet No. 4 in G minor (1867)")[1] == []


@case("flags name the disagreement and a match raises none")
def flags():
    assert ld.flags_for(5, 0, [(6, "", "")], []) == ["article states more"]
    assert ld.flags_for(5, 0, [(3, "", "")], []) == ["article states fewer"]
    assert ld.flags_for(5, 0, [], [(7, "", "")]) == ["article numbers higher"]
    assert ld.flags_for(None, 0, [(4, "", "")], []) == ["no count on list"]
    assert ld.flags_for(5, 0, [(5, "", "")], [(5, "", "")]) == []


@case("IMSLP needs two extra works to flag")
def imslp_margin():
    assert ld.flags_for(5, 6, [], []) == []
    assert ld.flags_for(5, 7, [], []) == ["IMSLP has more"]


@case("a marker round-trips through an issue body")
def round_trip():
    batch = [{"composer": "Dvořák", "entry_hash": "abc"}, {"composer": "Ann Lee", "entry_hash": "d"}]
    body = "Some drafts.\n\n" + ld.marker(batch) + "\n"
    assert ld.seen_in([{"body": body}]) == {"Dvořák": "abc", "Ann Lee": "d"}


@case("issues with no body or no marker are harmless")
def no_marker():
    assert ld.seen_in([{"body": None}, {"body": "nothing here"}, {}]) == {}


@case("the newest issue's hash wins")
def newest_wins():
    old = {"number": 1, "body": ld.marker([{"composer": "A", "entry_hash": "old"}])}
    new = {"number": 2, "body": ld.marker([{"composer": "A", "entry_hash": "new"}])}
    assert ld.seen_in([new, old]) == {"A": "new"}


def real_flagged(seen):
    from_page = "Eva Ruth Spalding composed six string quartets, the first in the early 1920s."
    batch, _ = ld.next_batch(ld.scan({"Eva Ruth Spalding": from_page}), seen, 500)
    return [b for b in batch if b["composer"] == "Eva Ruth Spalding"]


@case("a flagged composer is offered, with links that open")
def offered():
    b = real_flagged({})[0]
    assert b["flags"] == ["article states more"] and b["list_count"] == 5
    assert b["article_url"].endswith("/Eva_Ruth_Spalding")
    assert "action=edit&section=" in b["list_edit_url"]
    assert "#:~:text=six%20string%20quartets" in b["article_says"][0]["url"]


@case("a researched composer is skipped, even if nobody acted")
def researched_is_done():
    b = real_flagged({})[0]
    assert real_flagged({b["composer"]: b["entry_hash"]}) == []


@case("a change to the entry brings a composer back")
def changed_entry_returns():
    assert len(real_flagged({"Eva Ruth Spalding": "a-different-hash"})) == 1


@case("the entry text keeps its citations, because a draft replaces the whole line")
def keeps_citations():
    wiki = "==A==\n*[[X]] (born 1950): Two string quartets.<ref name=a/>\n"
    assert ld.entries(wiki)["X"] == ("*[[X]] (born 1950): Two string quartets.<ref name=a/>", "X", 1)


@case("the limit caps a batch, article flags first")
def limit():
    articles = {"Eva Ruth Spalding": "She composed six string quartets."}
    batch, waiting = ld.next_batch(ld.scan(articles), {}, 1)
    assert [b["composer"] for b in batch] == ["Eva Ruth Spalding"] and waiting > 0


@case("the same number stated twice is quoted once")
def dedupes():
    b = ld.scan({"Eva Ruth Spalding": "She wrote six string quartets. In all, six string quartets."})
    b = [x for x in b if x["composer"] == "Eva Ruth Spalding"][0]
    assert [a["value"] for a in b["article_says"]] == [6]


@case("picking a batch reads the flags and touches no network")
def no_network():
    def refuse(titles):
        raise AssertionError("fetched the network")
    fetch, flags, argv = ld.fetch_articles, ld.FLAGS, sys.argv
    stdout, ld.fetch_articles = sys.stdout, refuse
    with tempfile.TemporaryDirectory() as d:
        ld.FLAGS = os.path.join(d, "flags.json")
        out = os.path.join(d, "queue.json")
        with open(ld.FLAGS, "w", encoding="utf-8") as f:
            json.dump([{"composer": "A", "entry_hash": "x", "flags": ["article states more"],
                        "birth": 1900}], f)
        sys.argv = ["list_discrepancies.py", "--limit", "5", "--out", out]
        sys.stdout = open(os.devnull, "w")
        try:
            assert ld.main() == 0
        finally:
            sys.stdout.close()
            sys.stdout, ld.fetch_articles, ld.FLAGS, sys.argv = stdout, fetch, flags, argv
        with open(out, encoding="utf-8") as f:
            assert [c["composer"] for c in json.load(f)["composers"]] == ["A"]


def main():
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            print("  ok   %s" % name)
        except Exception as e:     # over older code a missing name must fail, not crash
            failed += 1
            print("  FAIL %s: %s" % (name, e))
    print("%d of %d passed" % (len(CASES) - failed, len(CASES)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
