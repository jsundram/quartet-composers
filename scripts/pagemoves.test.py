#!/usr/bin/env python3
# pwa-starter: none — this script is this repo's own
# /// script
# requires-python = ">=3.9"
# ///
"""Prove scripts/pagemoves.py's four judgements, offline.

    python3 scripts/pagemoves.test.py

NO NETWORK: `step`, `tenures`, `confirm` and `stitch` are pure, and `find_moves`'s walk is tested
with its two requests stubbed. So the whole file runs in CI beside the other three suites.

WHY IT EXISTS SEPARATELY from fetch_views.test.py, which covers the same feature end to end: every
defect this module has had is one the pipeline CANNOT show you. A dropped middle hop double-counts
one month; a mis-ordered guard throws away a complete chain; a reverted move looks exactly like a
permanent one in the log. None of them crashes, none of them changes a number by an order of
magnitude, and the shipped data happens to miss all three — which is why they survived review-by-
reading and needed a case each. Every case below is a fact about the rule, stated in ten lines,
that goes red if the rule is undone.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pagemoves as pm                                 # noqa: E402

CASES = []
MONTHS = ["%04d-%02d" % (y, m) for y in range(2015, 2027) for m in range(1, 13)]


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


# ------------------------------------------------------------------ tenures
@case("a dropped middle hop leaves ONE tenure, not two the boundary month is counted in twice")
def merge_adjacent(_):
    # confirm() judges hops independently, so an alternating chain A -> B -> A can lose its middle
    # one and name A twice in a row. Without the merge, stitch() finds A holding the boundary month
    # in both spans and sums it with itself: a plausible month, no crash, and nothing shipped today
    # exercises it (Gerhard, Takemitsu and López all alternate cleanly). Which is the whole point.
    kept = [("2020-04", "A"), ("2021-02", "A")]
    assert pm.tenures("B", kept) == [("A", None, "2021-02"), ("B", "2021-02", None)], pm.tenures("B", kept)
    got = pm.stitch(MONTHS, {"A": [100] * len(MONTHS), "B": [7] * len(MONTHS)}, "B", kept)
    i = MONTHS.index("2020-04")
    assert got[i] == 100, "the boundary month reads %r; A drew 100 there" % got[i]


@case("a hop that crosses no boundary is collapsed out of the chain, not just out of the spans")
def collapse_the_record(_):
    # The record has to agree with the series about how many moves there were. validate.py derives
    # the months that must be null from tenures(), and fetch_views.py collapses before writing
    # `moves`, so a chain naming a boundary the article never crossed cannot make the gate fail a
    # correctly stitched series — which it did, on the exact shape the merge above exists for.
    assert pm.collapse("B", [("2020-04", "A"), ("2021-02", "A")]) == [("2021-02", "A")]
    assert pm.collapse("A", [("2020-04", "A")]) == []
    assert pm.collapse("C", [("2020-04", "A"), ("2021-02", "B")]) == \
        [("2020-04", "A"), ("2021-02", "B")]


@case("a chain whose last surviving source IS the canonical does not open a second span for it")
def merge_final(_):
    # Same merge, at the other end: the article left its own name and came back, and the hop that
    # took it away was the one confirm() rejected.
    assert pm.tenures("A", [("2020-04", "A")]) == [("A", None, None)], pm.tenures("A", [("2020-04", "A")])


# ------------------------------------------------------------------ stitch
@case("the month of a move is null, never either title's count and never their sum")
def move_month_null(_):
    # Summing added the redirect share every other month excludes: on the real data Takemitsu's
    # 2020-10 came out 53% over its neighbours, in a series the sparkline prints exactly on hover.
    by = {"Old": [900] * len(MONTHS), "New": [40] * len(MONTHS)}
    got = pm.stitch(MONTHS, by, "New", [("2020-04", "Old")])
    i = MONTHS.index("2020-04")
    assert got[i - 1] == 900 and got[i + 1] == 40, (got[i - 1], got[i + 1])
    assert got[i] is None, "the month of the move reads %r" % got[i]


# ------------------------------------------------------------------ step
@case("a spike is not a step: an obituary must not send the pipeline to the move log")
def spike_is_not_a_step(_):
    vals = [200] * 60
    vals[30] = 40000                                   # one month, then back to normal
    ratio, _i = pm.step(vals)
    assert ratio < pm.SUSPECT_STEP, "a single spike scored %.1fx" % ratio
    vals = [200] * 30 + [4000] * 30                    # a level that shifts and stays
    ratio, _i = pm.step(vals)
    assert ratio >= pm.SUSPECT_STEP, "a sustained shift scored only %.1fx" % ratio


# ------------------------------------------------------------------ confirm
@case("a move the traffic did not follow is rejected; the one it did follow is kept")
def confirm_needs_a_handover(_):
    n = len(MONTHS)
    i = MONTHS.index("2020-04")
    real = {"Old": [900] * i + [900] + [30] * (n - i - 1),
            "New": [30] * i + [40] + [900] * (n - i - 1)}
    assert pm.confirm(MONTHS, real, "New", [("2020-04", "Old")]) == [("2020-04", "Old")]
    # The same log entry, with the readers staying where they were: a move reverted an hour later
    # leaves exactly this trace, and following it put Roberto Gerhard at a title he never held.
    revert = {"Old": [30] * n, "New": [900] * n}
    assert pm.confirm(MONTHS, revert, "New", [("2020-04", "Old")]) == []


# ------------------------------------------------------------------ find_moves
def stub(monkey_edges, redirects=("R1",)):
    """Point find_moves at a fixed log instead of the network."""
    pm.redirects = lambda t: list(redirects)
    pm._move_log = lambda t: [e for e in monkey_edges if e[1] == t]
    pm.PAUSE = 0


@case("a chain that walks out of the window is complete, not truncated")
def walk_leaves_the_window(_):
    # `inbound` is filtered by the ceiling and not by the axis start, so the exhaustion check has
    # to come AFTER the floor check. Before that swap, a full in-window chain plus any older
    # logged move was thrown away entirely and reported as truncated — which it was not.
    months = ["2020-%02d" % m for m in range(1, 13)] + ["2021-%02d" % m for m in range(1, 13)]
    edges = [("2019-06-01T00:00:00Z", "T%d" % pm.MAX_HOPS, "T%d" % (pm.MAX_HOPS - 1))]
    for k in range(pm.MAX_HOPS):
        edges.append(("2020-%02d-01T00:00:00Z" % (k + 2), "T%d" % (pm.MAX_HOPS - 1 - k),
                      "T%d" % (pm.MAX_HOPS - 2 - k) if k < pm.MAX_HOPS - 1 else "CANON"))
    stub(edges, redirects=["T%d" % k for k in range(pm.MAX_HOPS + 1)])
    got = pm.find_moves("CANON", months)
    assert got is not None, "a complete %d-hop chain was reported as truncated" % pm.MAX_HOPS
    assert len(got) == pm.MAX_HOPS, "walked %d hops, expected %d: %r" % (len(got), pm.MAX_HOPS, got)


@case("a chain longer than the cap returns None rather than a partial one that looks finished")
def walk_exhausts(_):
    months = ["2020-%02d" % m for m in range(1, 13)] + ["2021-%02d" % m for m in range(1, 13)]
    n = pm.MAX_HOPS + 1
    edges = [("2020-%02d-01T00:00:00Z" % (k + 1), "T%d" % (n - k), "T%d" % (n - k - 1))
             for k in range(n)]
    edges.append(("2021-01-01T00:00:00Z", "T0", "CANON"))
    stub(edges, redirects=["T%d" % k for k in range(n + 1)])
    said = []
    got = pm.find_moves("CANON", months, log=said.append)
    assert got is None, (
        "a truncated chain was returned as though it were finished: %r. tenures() would hand every "
        "month before its oldest hop to that hop's source, on no evidence." % (got,))
    assert any("truncated" in m for m in said), "the truncation was silent: %r" % said


@case("a log that cannot be read returns None, which is not the same answer as 'no move'")
def walk_cannot_read(_):
    def boom(_t):
        raise OSError("simulated 429 after four retries")
    pm.redirects = boom
    assert pm.find_moves("CANON", MONTHS, log=lambda *_: None) is None
    pm.redirects = lambda t: ["R1"]
    pm._move_log = boom
    assert pm.find_moves("CANON", MONTHS, log=lambda *_: None) is None


def main():
    real = (pm.redirects, pm._move_log, pm.PAUSE)
    passed = failed = 0
    for name, fn in CASES:
        pm.redirects, pm._move_log, pm.PAUSE = real
        try:
            fn(None)
            print("  ok   - %s" % name)
            passed += 1
        except AssertionError as e:
            print("  FAIL - %s\n       %s" % (name, e))
            failed += 1
    pm.redirects, pm._move_log, pm.PAUSE = real
    print("\n%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
