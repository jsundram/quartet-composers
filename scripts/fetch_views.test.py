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


def case(name):
    def deco(fn):
        CASES.append((name, fn))
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


def main():
    passed = failed = 0
    for name, fn in CASES:
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            try:
                fn(load(tmp, dict(CACHED)))
                print("  ok   - %s" % name)
                passed += 1
            except AssertionError as e:
                print("  FAIL - %s\n       %s" % (name, e))
                failed += 1
    print("\n%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
