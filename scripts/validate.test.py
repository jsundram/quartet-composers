#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Prove scripts/validate.py actually catches the bugs it claims to.

    python3 scripts/validate.test.py

A validator that only ever passes is decoration, and there is no way to tell the two apart by
reading it. So each case here REPRODUCES a defect this repo really shipped — into a throwaway copy
of the data — and asserts that validate.py fails with the expected reason. If someone weakens a
check, a test goes red instead of the gate going quietly green.

The first six are named for the incident they come from. The rest never shipped — they are the
failure modes this schema invites next, mostly because it is positional.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VALIDATE = os.path.join(HERE, "validate.py")

CASES = []


def case(name, expect, strict=False):
    """Register a mutation. `expect` is a substring the failure message must contain.

    `strict` runs the gate with --strict, which is how a WARNING is asserted: a warn() leaves the
    exit code 0, so without it the case reads as "validate PASSED a corrupted dataset".

    An `expect` beginning with "!" inverts it: that substring must NOT appear. Every case here was
    a positive one — break the data, expect an error — which is the right shape for a check that
    CATCHES something and the wrong shape for one that was deliberately LOOSENED. The gate learned
    not to fail a correctly stitched series whose chain names a boundary the article never crossed;
    with only positive cases, re-tightening it back to the false positive left the suite green.

    The inverted form names the STRING rather than demanding a clean exit, because a case that
    asserts the whole dataset passes is hostage to every check added later: close an unrelated gap
    and it goes red pointing at an ERROR that has nothing to do with what it is about.

    AND IT MUST FORBID A STRING SOME POSITIVE CASE REQUIRES, or it is an assertion about nothing:
    absence proves the check stayed quiet only if the words could have appeared at all, and a
    reword of the message quietly retires it. Pairing them is what makes it non-vacuous by
    construction — the message cannot be reworded without reddening the positive case first.
    """
    def deco(fn):
        CASES.append((name, expect, fn, strict))
        return fn
    return deco


# ---------------------------------------------------------------- the incidents
@case("Bartok: views keyed by a redirect, not the canonical article", "NON-canonical")
def bartok(d):
    pv = d["pageviews"]
    victim = next(iter(pv["series"]))
    pv["series"]["Bela Bartok"] = pv["series"].pop(victim)


@case("John Adams: a wrong-article join, 30x the readership", "page views")
def john_adams(d):
    # Drift is the only thing that can see this: 144,948 views is not implausible on its own, it is
    # implausible next to what the same row said last build.
    d["composers"]["rows"][0][4] *= 30
    d["composers"]["rows"][0][6] *= 30


@case("de la Tombelle: a list title that resolves to no article at all", "do not resolve",
      strict=True)
def redlink(d):
    # Shipped for the life of the dataset. Every other check here passes on it: the row is the
    # right shape and the number is plausible.
    t = next(iter(d["people"]))
    d["people"][t]["canonical"] = None


@case("Tania Leon: a death year that cannot be true", "future")
def tania(d):
    t = next(iter(d["people"]))
    d["people"][t]["wd_death"] = 2999


@case("living flag broken: everyone reads as dead", "plausible 15-60% band")
def living_flag(d):
    for r in d["composers"]["rows"]:
        if r[2] is None:
            r[2] = r[1] + 60


@case("a resurrection: someone who had a death year now reads as living", "reads as LIVING")
def resurrection(d):
    for r in d["composers"]["rows"]:
        if r[2] is not None:
            r[2] = None
            break


@case("names sourced from raw scrape text again", "not resolved Wikipedia titles")
def raw_names(d):
    d["composers"]["rows"][0][0] = "Lutosawski"


# ---------------------------------------------------------------- the schema traps
@case("fields reordered under positional readers", "index these POSITIONALLY")
def reorder(d):
    f = d["composers"]["fields"]
    f[3], f[4] = f[4], f[3]


@case("median outside its own min-max range", "outside its own range")
def bad_median(d):
    r = d["composers"]["rows"][0]
    r[4] = r[6] + 1000


@case("a quartet count no one wrote", "implausible quartet count")
def silly_count(d):
    d["composers"]["rows"][0][3] = 5000


@case("duplicate names make a shared link ambiguous", "duplicate name")
def dupes(d):
    rows = d["composers"]["rows"]
    rows[1][0] = rows[0][0]


@case("P21 value shipped unlabelled, as a raw QID", "raw QID")
def unlabelled_gender(d):
    # What an item outside fetch_wikidata.py's GENDERS map looks like downstream. It is a REAL
    # value, deliberately not nulled — so the gate is the only thing between it and a UI printing
    # "Q48270" at somebody.
    d["composers"]["rows"][0][7] = "Q48270"


@case("the P21 read broke and the whole column is null", "floor 95%")
def gender_column_lost(d):
    for r in d["composers"]["rows"]:
        r[7] = None


@case("a real P21 label the UI has no pill for", "cannot filter")
def unfilterable_gender(d):
    # Not a corruption: "non-binary" is a value fetch_wikidata.py labels correctly and validate.py
    # would otherwise wave through. The bug is that the app has two pills, so the row lands in
    # neither filter and the footnote — which counts only the composers with NO claim — says so
    # about nobody. The gate is what makes the two vocabularies drift loudly.
    row = next(r for r in d["composers"]["rows"] if r[7] == "female")
    row[7] = "non-binary"
    # The CACHE has to agree, or this reproduces the previous case instead of this one.
    for p_ in d["people"].values():
        if p_.get("canonical", "").startswith(row[0]):
            p_["gender"] = "non-binary"


# ---------------------------------------------------------------- two files, one measurement
@case("the sparkline and the number beside it were built from different fetches", "different data")
def history_drift(d):
    # What rebuilding composers.json without rebuilding readership.json looks like: both files are
    # internally consistent, the panel prints one readership and draws another, and no code path
    # anywhere can notice. The only thing that can is recomputing one from the other.
    name = d["composers"]["rows"][0][0]
    d["history"]["series"][name] = [None if v is None else v * 3
                                    for v in d["history"]["series"][name]]


@case("a month cached in one file and not the other", "different fetches")
def history_short(d):
    d["history"]["months"] = d["history"]["months"][:-1]
    for k in d["history"]["series"]:
        d["history"]["series"][k] = d["history"]["series"][k][:-1]


@case("a cached series that fell out of step with its own month axis", "not aligned")
def ragged_cache(d):
    # data/pageviews.json stores each series as a FLAT ARRAY aligned to `months`, which is a
    # quarter of the bytes of the old {month: count} form and diffs one line per composer. The
    # price is that alignment is now load-bearing: an array one short shifts every month by one
    # and the numbers that come out are entirely plausible.
    pv = d["pageviews"]
    victim = next(iter(pv["series"]))
    pv["series"][victim] = pv["series"][victim][:-1]


@case("a month the API had not published cached as though nobody read anything",
      "newest cached month")
def unsettled_month(d):
    # The pageviews API does not withhold a month in progress — it returns the days so far — so
    # fetch_views.py guards this on the CLOCK. This is the net for a cache that got one anyway:
    # left in, it is the newest month on the axis, so every median is computed over eleven values
    # and composers.json's window ends there, which tells refresh.py it is done for the month.
    for k, v in d["pageviews"]["series"].items():
        v[-1] = None


@case("a rename that only landed in one file", "name nobody in composers.json")
def history_rename(d):
    ser = d["history"]["series"]
    victim = d["composers"]["rows"][0][0]
    ser["Fanny Mendelssohn"] = ser.pop(victim)


# ---------------------------------------------------------------- a page move
def _step_it(pv, title, upto=-12):
    """Give one cached series the shape of an article that was renamed mid-window."""
    vals = pv["series"][title]
    for i in range(len(vals) + upto):
        vals[i] = 2                       # what the new title drew while it was still a redirect


@case("a renamed article nobody has put to the move log", "asked the move log")
def unstitched_move(d):
    # Fanny Hensel's defect, reproduced. The series is the right length, aligned to the right axis
    # and full of numbers the API really returned; what it is not is continuous. Nothing else in
    # this file can see that, because every check either reads the last twelve months or compares
    # two files that were both built from the same wrong series.
    pv = d["pageviews"]
    title = max(pv["series"], key=lambda t: pv["series"][t][-1] or 0)
    pv["moves"].pop(title, None)
    _step_it(pv, title)


@case("a recorded page move whose stitch was lost in a rebuild", "stitch was lost")
def lost_stitch(d):
    # The other way it reaches a build: the repair was found, recorded, and then dropped — which
    # is what rebuilding data/pageviews.json without re-applying it looks like. Silent, because
    # every number that comes back is one the API really answered for the title as it stands now.
    pv = d["pageviews"]
    title = max((t for t, c in pv["moves"].items() if c),
                key=lambda t: pv["series"][t][-1] or 0)
    _step_it(pv, title)


@case("a stitch dropped on a composer too quietly read for the shape check", "still carries a count")
def lost_stitch_below_the_floor(d):
    # The shape check has a floor of 100 readers a month, which most of this roster's tail is
    # under: Lois V. Vierk's post-move median is 44, so a lost stitch on her scores (0.0, None)
    # and passes. fetch_views.py's recovery from a source that does not answer is to leave the
    # series unrepaired and let the gate say so, which makes this the case that has to hold.
    # The null at the month of the move is exact and needs no threshold.
    pv = d["pageviews"]
    title, chain = min(((t, c) for t, c in pv["moves"].items() if c),
                       key=lambda tc: max(v or 0 for v in pv["series"][tc[0]][-12:]))
    i = pv["months"].index(chain[-1][0])
    for j in range(i + 1):
        pv["series"][title][j] = 3                     # written as fetched: redirect-scale, no null


@case("a chain whose surviving hops leave two tenures under one title is NOT a lost stitch",
      "!still carries a count")
def adjacent_tenures_are_not_a_lost_stitch(d):
    # The mirror image of the case above, and the only shape that can tell the gate's rule from
    # the one it replaced. confirm() judges hops independently, so an alternating chain can lose
    # its middle one and name a boundary the article never crossed — stitch() writes a real count
    # there, correctly. Asserting a null at every month the RECORD names would fail this, with a
    # message saying the series was written as fetched and advice to rerun a deterministic script
    # that reproduces it: a build with no way back to green.
    sys.path.insert(0, HERE)
    import pagemoves
    pv = d["pageviews"]
    months = pv["months"]
    # The longest recorded chain, with its MIDDLE hop dropped — that is what leaves two entries
    # naming one title in a row. Taken deliberately rather than from whichever chain sorts first:
    # dropping the last hop of a two-hop chain collapses to nothing at all, which the gate is
    # equally right about and which does not exercise this shape.
    # next() rather than max() for the message, not for the legibility: run_case() is what turns a
    # fixture that has aged out into one FAIL line, and it has to, because the asserts below have
    # the same shape and no selection can guard those.
    title = next((t for t, c in sorted(pv["moves"].items()) if len(c) >= 3), None)
    assert title, "no recorded chain has three hops any more; this case needs a new fixture"
    chain = [tuple(e) for e in pv["moves"][title]]
    del chain[1]
    assert chain[0][1] == chain[1][1], "the chain picked does not leave two tenures under one title"
    pv["moves"][title] = [list(c) for c in chain]
    # Counts, not the shipped nulls: the point is that the month the record names but the article
    # never crossed carries a real number, and the gate must not object to it.
    by = {src: [100] * len(months) for _m, src in chain}
    by[title] = [7] * len(months)
    pv["series"][title] = pagemoves.stitch(months, by, title, chain)
    assert pv["series"][title][months.index(chain[0][0])] == 100, "the boundary month is not a count"


@case("a ragged series crashes the gate instead of reporting what it already found", "not aligned")
def ragged_crashes_check_moves(d):
    # step() returns an index into the series, so a series LONGER than the axis made months[i]
    # raise — and a traceback out of check_moves loses every error already collected, including
    # the ragged-series one from check_sources that explains it. The expected message is that
    # one: it has to survive.
    pv = d["pageviews"]
    title = max(pv["series"], key=lambda t: pv["series"][t][-1] or 0)
    # The step has to land PAST the end of the axis for months[i] to raise, so the padding carries
    # it there: a flat stretch and then a jump, both beyond len(months).
    pv["series"][title] = pv["series"][title] + [2] * 20 + [50000] * 20


@case("a move chain that hands one composer another's history", "another composer's canonical")
def borrowed_history(d):
    pv = d["pageviews"]
    title = next(t for t, c in pv["moves"].items() if c)
    other = next(t for t in pv["series"] if t != title)
    pv["moves"][title] = [[pv["months"][40], other]]


@case("a gender the cache never stated", "does not state")
def invented_gender(d):
    for r in d["composers"]["rows"]:
        if r[7] == "female":
            r[7] = "male"
            break


def run_case(name, expect, mutate, strict=False):
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "data"))
        for rel in ["composers.json", "readership.json",
                    "data/people.json", "data/pageviews.json", "data/list.json"]:
            shutil.copy(os.path.join(ROOT, rel), os.path.join(tmp, rel))
        base = os.path.join(tmp, "baseline.json")
        shutil.copy(os.path.join(ROOT, "composers.json"), base)

        d = {
            "composers": json.load(open(os.path.join(tmp, "composers.json"), encoding="utf-8")),
            "people": json.load(open(os.path.join(tmp, "data/people.json"), encoding="utf-8")),
            "pageviews": json.load(open(os.path.join(tmp, "data/pageviews.json"), encoding="utf-8")),
            "history": json.load(open(os.path.join(tmp, "readership.json"), encoding="utf-8")),
        }
        try:
            mutate(d)
        except Exception as e:                         # noqa: BLE001 - a fixture that aged out
            # A case whose FIXTURE no longer exists is a failed case, not a dead suite. Neither
            # this function nor main() wrapped the mutation, so any raise in one — a selection
            # that found nothing, an assert guarding a shape — took the summary line and every
            # case after it down with the traceback. Hardening the selections could not fix that;
            # only this can, and it covers the ones already written the same way.
            # "or its own checks": the same wrapper catches a post-condition assert inside the
            # mutation, where the change WAS applied and it is the claim about it that failed.
            return False, "the mutation or its own checks raised: %s: %s" % (type(e).__name__, e)
        json.dump(d["composers"], open(os.path.join(tmp, "composers.json"), "w", encoding="utf-8"))
        json.dump(d["people"], open(os.path.join(tmp, "data/people.json"), "w", encoding="utf-8"))
        json.dump(d["pageviews"], open(os.path.join(tmp, "data/pageviews.json"), "w", encoding="utf-8"))
        json.dump(d["history"], open(os.path.join(tmp, "readership.json"), "w", encoding="utf-8"))

        out = subprocess.run([sys.executable, VALIDATE, "--root", tmp, "--baseline", base]
                             + (["--strict"] if strict else []),
                             capture_output=True, text=True)
        blob = out.stdout + out.stderr
        if expect.startswith("!"):
            if "Traceback" in blob:
                return False, "validate crashed, so the absence proves nothing: %s" % blob[-300:]
            if expect[1:] in blob:
                return False, "validate REJECTED a dataset it must accept: %s" % (
                    "; ".join(l.strip() for l in blob.splitlines() if expect[1:] in l)[:300])
            return True, ""
        if out.returncode == 0:
            return False, "validate PASSED a corrupted dataset"
        if expect not in blob:
            return False, "failed for the wrong reason (wanted %r), got: %s" % (
                expect, blob.strip().splitlines()[-2] if blob.strip() else "(no output)")
        return True, ""


def main():
    # THE PAIRING RULE, CHECKED RATHER THAN STATED. An inverted case proves the gate stayed quiet
    # only if the words it forbids could have appeared, so it has to forbid something a positive
    # case requires — otherwise a reword of the message retires it in silence, which is exactly
    # how the first version of the one below stopped asserting anything. The rule was documented
    # and held by inspection, and a rule that holds by inspection is the shape of half the defects
    # this file exists to catch.
    # Exact membership, not containment: a forbidden string is paired only by a positive case that
    # requires that string, so the pairing is unambiguous rather than "some other expect happens to
    # contain these words". The cost is that MAKING A POSITIVE EXPECT MORE SPECIFIC orphans its
    # partner — widen "still carries a count" to "still carries a count at the boundary" and this
    # fires. That is the safe direction (a loud refusal to run, fixed the same day, rather than a
    # silent pass), but it is a trap worth knowing about: change both halves together.
    pins = {e for _n, e, _f, _s in CASES if not e.startswith("!")}
    orphans = [(n, e[1:]) for n, e, _f, _s in CASES if e.startswith("!") and e[1:] not in pins]
    if orphans:
        for n, e in orphans:
            print("  FAIL - %s\n       nothing positive requires %r, so its absence proves nothing"
                  % (n, e), file=sys.stderr)
        return 1

    # The gate must also pass the REAL data, or every case above is vacuously green.
    out = subprocess.run([sys.executable, VALIDATE], capture_output=True, text=True)
    ok = out.returncode == 0
    print("  %s - clean dataset passes" % ("ok  " if ok else "FAIL"))
    passed, failed = (1, 0) if ok else (0, 1)
    if not ok:
        print("       %s" % (out.stdout + out.stderr).strip()[:300])

    for name, expect, fn, strict in CASES:
        good, why = run_case(name, expect, fn, strict)
        print("  %s - %s" % ("ok  " if good else "FAIL", name))
        if not good:
            print("       %s" % why)
        passed += good
        failed += not good

    print("\n%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
