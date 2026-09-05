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


def case(name, expect):
    """Register a mutation. `expect` is a substring the failure message must contain."""
    def deco(fn):
        CASES.append((name, expect, fn))
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


def run_case(name, expect, mutate):
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "data"))
        for rel in ["composers.json", "data/people.json", "data/pageviews.json", "data/list.json"]:
            shutil.copy(os.path.join(ROOT, rel), os.path.join(tmp, rel))
        base = os.path.join(tmp, "baseline.json")
        shutil.copy(os.path.join(ROOT, "composers.json"), base)

        d = {
            "composers": json.load(open(os.path.join(tmp, "composers.json"), encoding="utf-8")),
            "people": json.load(open(os.path.join(tmp, "data/people.json"), encoding="utf-8")),
            "pageviews": json.load(open(os.path.join(tmp, "data/pageviews.json"), encoding="utf-8")),
        }
        mutate(d)
        json.dump(d["composers"], open(os.path.join(tmp, "composers.json"), "w", encoding="utf-8"))
        json.dump(d["people"], open(os.path.join(tmp, "data/people.json"), "w", encoding="utf-8"))
        json.dump(d["pageviews"], open(os.path.join(tmp, "data/pageviews.json"), "w", encoding="utf-8"))

        out = subprocess.run([sys.executable, VALIDATE, "--root", tmp, "--baseline", base],
                             capture_output=True, text=True)
        blob = out.stdout + out.stderr
        if out.returncode == 0:
            return False, "validate PASSED a corrupted dataset"
        if expect not in blob:
            return False, "failed for the wrong reason (wanted %r), got: %s" % (
                expect, blob.strip().splitlines()[-2] if blob.strip() else "(no output)")
        return True, ""


def main():
    # The gate must also pass the REAL data, or every case above is vacuously green.
    out = subprocess.run([sys.executable, VALIDATE], capture_output=True, text=True)
    ok = out.returncode == 0
    print("  %s - clean dataset passes" % ("ok  " if ok else "FAIL"))
    passed, failed = (1, 0) if ok else (0, 1)
    if not ok:
        print("       %s" % (out.stdout + out.stderr).strip()[:300])

    for name, expect, fn in CASES:
        good, why = run_case(name, expect, fn)
        print("  %s - %s" % ("ok  " if good else "FAIL", name))
        if not good:
            print("       %s" % why)
        passed += good
        failed += not good

    print("\n%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
