#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Prove data/pageviews.json can only ever say things that are true.

    python3 scripts/fetch_views.test.py

NO NETWORK: `fetch` is stubbed and the cache is a temp file, so this runs anywhere and in CI.

WHY THIS FILE EXISTS. The cache stores each series as a flat array aligned to one `months` axis,
which has exactly two values available — a count, and `null` for "asked, and there was nothing".
There is no third value for "never asked", so the file can only stay honest if every series really
was asked over the whole axis. Two bugs in a row came from writing a null that no request had ever
justified, and both were invisible afterwards: the array is the right length, every number in it is
plausible, and the only symptom is that `todo` silently stops asking.

  1. The writer flattened onto the union axis, so a title fetched over a NARROWER window had its
     un-asked months written as nulls. `--months 24` on a composer added since the last run buried
     nine years of their history permanently.
  2. A title that did not ANSWER — a 404, or five exhausted retries — skipped the store but got
     flattened anyway, so it was null-padded for the new month, looked complete forever, and the
     "rerun to pick them up" advice was false. It also silenced the 404 report, which exists to
     name a bad canonical title in people.json on every run until someone fixes it.

Each case below is one of those, stated as the property it violates.
"""
import io
import json
import os
import sys
import tempfile
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))

CASES = []


def case(name, cache=None):
    """Register a case. `cache` overrides the two-month fixture for the ones that need a history."""
    def deco(fn):
        CASES.append((name, fn, cache))
        return fn
    return deco


def load(tmp, cache):
    """A fresh copy of the module, pointed at a temp cache, with the network and the clock stubbed.

    Reloaded per case because main() is written against module-level paths — which is fine for a
    script and would be over-engineering to change for a test."""
    spec = importlib.util.spec_from_file_location("fv", os.path.join(HERE, "fetch_views.py"))
    fv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fv)
    fv.OUT = os.path.join(tmp, "pageviews.json")
    fv.PEOPLE = os.path.join(tmp, "people.json")
    fv.PAUSE = 0
    with open(fv.PEOPLE, "w", encoding="utf-8") as f:
        json.dump({t: {"canonical": t} for t in ("A", "B")}, f)
    if cache is not None:
        with open(fv.OUT, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    return fv


# The window every case runs in: the two cached months plus the one a run adds. Stated explicitly
# rather than left to the default, which is the whole decade back to FLOOR.
WINDOW = ["--months", "3", "--end", "2026-08"]


def run(fv, argv, quiet=True):
    """Run main() and return (exit code, the cache it wrote, what it printed)."""
    argv_, out_, err_ = sys.argv, sys.stdout, sys.stderr
    sys.argv = ["fetch_views.py"] + argv
    buf = io.StringIO()
    if quiet:
        sys.stdout = sys.stderr = buf     # stderr too: a refusal is expected output here, not noise
    try:
        rc = fv.main()
    finally:
        sys.argv, sys.stdout, sys.stderr = argv_, out_, err_
    with open(fv.OUT, encoding="utf-8") as f:
        return rc, json.load(f), buf.getvalue()


# The axis a case starts from, and the one month a run adds to it.
CACHED = {"months": ["2026-06", "2026-07"], "series": {"A": [99, 99], "B": [20, 21]}}
ANSWER = {"2026-06": 99, "2026-07": 99, "2026-08": 99}


@case("a title whose refetch fails is not written with a null for the month it never answered")
def transport_failure(fv):
    def stub(title, months):
        if title == "B":
            raise OSError("simulated 429 after five retries")
        return {m: ANSWER[m] for m in months}
    fv.fetch = stub
    _, out, _log = run(fv, WINDOW)
    assert "B" not in out["series"], (
        "B failed to answer but was written anyway: %r. A null here is indistinguishable from "
        "'asked, nothing there', so the next run skips it forever." % (out["series"].get("B"),))
    assert out["series"]["A"] == [99, 99, 99], "the other title's fetch was discarded: %r" % (
        out["series"]["A"],)


@case("and the rerun the failure message promises actually refetches it")
def rerun_picks_it_up(fv):
    def flaky(title, months):
        if title == "B" and not flaky.healed:
            flaky.healed = True
            raise OSError("simulated 429")
        return {m: ANSWER[m] for m in months}
    flaky.healed = False
    fv.fetch = flaky
    run(fv, WINDOW)
    _, out, _log = run(fv, WINDOW)
    assert out["series"].get("B") == [99, 99, 99], (
        "the rerun did not pick B up: %r. 'rerun to pick them up' has to be true." % (
            out["series"].get("B"),))


@case("the failure report says WHY, not just which title")
def failure_report_names_the_reason(fv):
    # The run has just deleted those series, so "rerun to pick them up" is the recovery path and
    # the reason decides when to rerun: an hour for a 429, sooner for a timeout. Checked here
    # because it is report text — nothing else in the pipeline reads it, so it can rot in silence.
    def stub(title, months):
        if title == "B":
            raise OSError("simulated 429: Too Many Requests")
        return {m: ANSWER[m] for m in months}
    fv.fetch = stub
    _rc, _out, log = run(fv, WINDOW)
    assert "429" in log, "the failure report dropped the reason:\n%s" % log


@case("a 404 keeps being reported, rather than exactly once")
def four_oh_four_keeps_reporting(fv):
    fv.fetch = lambda title, months: None if title == "B" else {m: ANSWER[m] for m in months}
    said = []
    for _ in range(2):
        _rc, _out, log = run(fv, WINDOW)
        said.append("B" in log)
    assert said == [True, True], (
        "the bad-canonical report fired %r across two runs; it must name the title every run "
        "until somebody fixes people.json" % (said,))


@case("a narrower --months still fetches a new title over the WHOLE axis")
def narrow_window_new_title(fv):
    asked = {}

    def stub(title, months):
        asked[title] = list(months)
        return {m: ANSWER.get(m, 1) for m in months}
    fv.fetch = stub
    _, out, _log = run(fv, ["--months", "1", "--end", "2026-08"])
    assert asked.get("B", [])[0] == "2026-06", (
        "B was asked only for %r. Fetching a narrower window than the axis writes the rest as "
        "nulls, which read back as complete forever." % (asked.get("B"),))
    assert all(v is not None for v in out["series"]["B"]), out["series"]["B"]


@case("every written series covers the axis exactly")
def arrays_are_aligned(fv):
    fv.fetch = lambda title, months: {m: ANSWER.get(m, 1) for m in months}
    _, out, _log = run(fv, WINDOW)
    n = len(out["months"])
    bad = {k: len(v) for k, v in out["series"].items() if len(v) != n}
    assert not bad, "ragged series against a %d-month axis: %r" % (n, bad)


@case("a month in progress is refused rather than cached as a whole month")
def partial_month_refused(fv):
    # The API does not withhold the current month: asked on the 6th it returns six days aggregated
    # exactly like a finished month. Nothing downstream can tell the difference, so the clock is
    # the only guard.
    fv.fetch = lambda title, months: {m: ANSWER.get(m, 1) for m in months}
    nxt = fv.months_back(1)[0]
    y, m = int(nxt[:4]), int(nxt[5:7])
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    rc, _out, _log = run(fv, ["--months", "3", "--end", "%04d-%02d" % (y, m)])
    assert rc == 2, "an incomplete month was accepted (rc=%r)" % rc


# ------------------------------------------------------------------ page moves
# A sixteen-month axis, because the detector measures a level shift over windows and cannot see one
# in the two months the cases above run in. "A" is an article that moved from "Old A" in the twelfth
# month; its own series is redirect traffic before that and real traffic after, which is exactly
# the shape Fanny Hensel's had. "B" never moves and is here to be left alone.
MOVED = {
    "months": ["2025-%02d" % m for m in range(5, 13)] + ["2026-%02d" % m for m in range(1, 9)],
    "series": {"A": [3] * 11 + [400] + [900, 950, 880, 910],
               "B": [20] * 16},
}
OLD_A = [800] * 11 + [500] + [60, 55, 58, 52]
LONG = ["--months", "16", "--end", "2026-08"]


def moving(fv, chain, extra=None):
    """Stub the network: `chain` is what the move log says, `extra` the old titles' own counts."""
    tables = dict({"Old A": OLD_A}, **(extra or {}))

    def stub(title, months):
        vals = tables.get(title)
        if vals is not None:
            return dict(zip(MOVED["months"], vals))
        return {m: MOVED["series"].get(title, [1] * 16)[i]
                for i, m in enumerate(MOVED["months"]) if m in months}
    fv.fetch = stub
    asked = []
    real = fv.pagemoves.find_moves

    def log_stub(canonical, months, log=None):
        asked.append(canonical)
        if canonical != "A":
            return []
        return None if chain is None else list(chain)  # None = the log could not be read
    fv.pagemoves.find_moves = log_stub
    return asked, lambda: setattr(fv.pagemoves, "find_moves", real)


@case("a moved article is stitched back into one series", MOVED)
def move_stitched(fv):
    _asked, restore = moving(fv, [("2026-04", "Old A")])
    try:
        _rc, out, _log = run(fv, LONG + ["--force"])
    finally:
        restore()
    got = out["series"]["A"]
    assert got[:11] == [800] * 11, (
        "the months before the move were left under the new title (%r). That is the whole defect: "
        "the API answers per title, so those months measure a redirect nobody followed." % got[:11])
    # The move happened on a day, so its month was read under both names and belongs to neither.
    # Summing them adds the redirect share every other month excludes, which on the real data
    # invented a peak 53% over its neighbours in a series the sparkline prints exactly.
    assert got[11] is None, "the month of the move is %r, not null" % got[11]
    assert got[12:] == [900, 950, 880, 910], "the months after the move were altered: %r" % got[12:]
    assert out["moves"]["A"] == [["2026-04", "Old A"]], out["moves"].get("A")
    assert out["series"]["B"] == [20] * 16, "an article that never moved was rewritten"


@case("a recorded move is re-applied every time the canonical series is refetched", MOVED)
def move_reapplied(fv):
    # A refetch overwrites the stitched series with the API's per-title answer, so the repair is
    # not a migration that happens once. If it were, the next monthly top-up would silently undo
    # every stitch in the file and nothing downstream could tell.
    asked, restore = moving(fv, [("2026-04", "Old A")])
    try:
        run(fv, LONG + ["--force"])
        first = list(asked)
        _rc, out, _log = run(fv, LONG + ["--force"])
    finally:
        restore()
    assert out["series"]["A"][:11] == [800] * 11, (
        "the second run undid the stitch: %r" % out["series"]["A"][:11])
    assert out["series"]["A"][11] is None, (
        "the second run rewrote the month of the move (%r). Every repair reads the PRE-STITCH "
        "counts, so running it twice has to land on the same series"
        % out["series"]["A"][11])
    assert asked == first, (
        "the move log was asked again for %r — a recorded move is re-applied from the record, "
        "which is what keeps a monthly run from re-investigating the whole roster"
        % (asked[len(first):],))


@case("a logged move the traffic does not support is recorded and NOT stitched", MOVED)
def move_not_confirmed(fv):
    # The log states events, not tenures: a move reverted twenty minutes later leaves the same two
    # entries a permanent one does. "Other A" here is logged as the source and never had the
    # readers, which is Roberto Gerhard's case — stitching it would have handed him a decade of an
    # empty redirect's traffic and made his series worse than leaving it alone.
    _asked, restore = moving(fv, [("2026-04", "Other A")], extra={"Other A": [4] * 16})
    try:
        _rc, out, _log = run(fv, LONG + ["--force"])
    finally:
        restore()
    assert out["series"]["A"] == MOVED["series"]["A"], (
        "an unconfirmed move was stitched anyway: %r" % out["series"]["A"])
    assert out["moves"]["A"] == [], (
        "the empty record is what tells validate.py somebody looked, and what stops the next run "
        "asking again; got %r" % (out["moves"].get("A"),))


@case("a source title that does not answer leaves the series AND the record alone", MOVED)
def move_source_unavailable(fv):
    # The failure the main fetch loop's `except` exists to prevent, one function over: fetch()
    # re-raises a 429 once its retries are spent, and this runs after all 884 titles are in hand
    # and before anything is written, so an unguarded raise here discards the whole top-up.
    #
    # And the recovery must not be to write `[]`. That sentence means "the log was asked and there
    # is no move here", which retires the question — the series would revert to the pre-move
    # numbers with the record agreeing that nothing is wrong.
    _asked, restore = moving(fv, [("2026-04", "Old A")])
    try:
        run(fv, LONG + ["--force"])                    # establish the record
        good = fv.fetch

        def flaky(title, months):
            if title == "Old A":
                raise OSError("simulated 429 after five retries")
            return good(title, months)
        fv.fetch = flaky
        rc, out, log = run(fv, LONG + ["--force"])
    finally:
        restore()
    assert rc == 0 and out["series"]["B"] == [20] * 16, (
        "one unavailable source title discarded the run (rc=%r)" % rc)
    assert out["moves"]["A"] == [["2026-04", "Old A"]], (
        "the recorded move was downgraded to %r — an empty list says the log found nothing, and "
        "the next run would never look again" % (out["moves"].get("A"),))
    assert "Old A" in log, "nothing said which source was missing:\n%s" % log


# A record from before the collapse rule: two entries naming one title in a row, which is what a
# rejected middle hop leaves behind. It names a boundary the article never crossed.
LEGACY = dict(MOVED, moves={"A": [["2025-09", "Old A"], ["2026-04", "Old A"]]})


@case("the RECORD names only boundaries the article actually crossed", LEGACY)
def record_is_collapsed(fv):
    # Written down uncollapsed, the file claims a move it did not act on and `stitched across`
    # names a hop that never happened — and before the gate learned to derive its months from
    # pagemoves.holes(), it also failed the build over the count stitch() correctly writes there.
    # A run that touches the title has to rewrite the record as what it actually did.
    _asked, restore = moving(fv, [("2026-04", "Old A")])
    try:
        _rc, out, log = run(fv, LONG + ["--force"])
    finally:
        restore()
    got = out["moves"]["A"]
    assert got == [["2026-04", "Old A"]], (
        "the record still names %d boundaries; the article crossed one: %r" % (len(got), got))
    said = [ln for ln in log.splitlines() if "stitched across" in ln]
    assert said and "2025-09" not in said[0], (
        "the summary named a hop that did not happen: %r" % (said,))
    assert out["series"]["A"][:11] == [800] * 11, (
        "the series was not stitched: %r" % out["series"]["A"][:11])


@case("a chain already on record is not re-confirmed, so it cannot silently empty", MOVED)
def move_record_is_trusted(fv):
    # confirm() is how a chain EARNS its place in the record; re-deriving it on every run gives it
    # a way back out. Anything that moves the numbers under a recorded hop — a redirect retargeted,
    # a CONFIRM_ threshold nudged — would empty the record, unstitch the series, and leave
    # validate.py looking at a title whose record agrees nothing is wrong. Here "Old A" stops
    # looking like a handover entirely; the recorded chain has to survive it.
    _asked, restore = moving(fv, [("2026-04", "Old A")])
    try:
        run(fv, LONG + ["--force"])                    # establish the record
        good = fv.fetch
        fv.fetch = lambda t, months: ({m: 4 for m in months} if t == "Old A"
                                      else good(t, months))
        _rc, out, _log = run(fv, LONG + ["--force"])
    finally:
        restore()
    assert out["moves"]["A"] == [["2026-04", "Old A"]], (
        "a recorded chain was re-judged and dropped: %r" % (out["moves"].get("A"),))
    assert out["series"]["A"][:11] == [4] * 11, (
        "the recorded move was not re-applied: %r" % out["series"]["A"][:11])


@case("a move log that cannot be READ is not recorded as 'no move'", MOVED)
def move_log_unreadable(fv):
    _asked, restore = moving(fv, None)                 # find_moves returns None: the log failed
    try:
        _rc, out, log = run(fv, LONG + ["--force"])
    finally:
        restore()
    assert "A" not in out["moves"], (
        "a failed lookup was recorded as an answer (%r). Next run has to ask again."
        % (out["moves"].get("A"),))
    # The report is the only place this failure is visible, so the WRONG sentence is the whole
    # defect: "really had" sends the operator away satisfied about a question still open.
    assert "really had" not in log, (
        "a lookup that failed was reported as a settled reading:\n%s" % log)


@case("a source that answers 200 with no data is not an answer either", MOVED)
def move_source_empty(fv):
    # fetch() returns {} for a payload with no `items`, not None, so a guard that tests `is None`
    # has a hole one branch wide — and this is the bad side of it. For a chain already on record
    # (trusted, not re-confirmed) an all-null source makes stitch() lay nulls over the whole
    # pre-move stretch while `moves` still says stitched, and step() cannot see it because the
    # before-window is then empty. Nothing downstream would ever report it.
    _asked, restore = moving(fv, [("2026-04", "Old A")])
    try:
        run(fv, LONG + ["--force"])                    # establish the record
        good = fv.fetch
        fv.fetch = lambda t, months: ({} if t == "Old A" else good(t, months))
        _rc, out, _log = run(fv, LONG + ["--force"])
    finally:
        restore()
    assert out["moves"]["A"] == [["2026-04", "Old A"]], (
        "the record was rewritten from an empty answer: %r" % (out["moves"].get("A"),))
    assert out["series"]["A"][:11] == MOVED["series"]["A"][:11], (
        "nulls from an empty payload were stitched over the pre-move months: %r"
        % out["series"]["A"][:11])


def main():
    passed = failed = 0
    for name, fn, cache in CASES:
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            try:
                fn(load(tmp, json.loads(json.dumps(cache or CACHED))))
                print("  ok   - %s" % name)
                passed += 1
            except AssertionError as e:
                print("  FAIL - %s\n       %s" % (name, e))
                failed += 1
    print("\n%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
