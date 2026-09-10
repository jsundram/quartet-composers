#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Every number in the docs that the repo can COMPUTE, checked against the live value.

CLAUDE.md's own rule is that prose the app can falsify is built or cut. It has been applied to
what the page prints and never to what the docs say, and the docs have drifted three times that
this catches on the day it was written:

  - README.md stated a UI-suite size that was two rewrites out of date. That exact drift was
    spotted during #23, deferred to a follow-up in fd7be6f, and never done — which is the whole
    argument for a gate over a convention.
  - CLAUDE.md invariant 13 said 58 names carry a character NFD cannot decompose. Eight do.
    113 carry any non-ASCII character, so no reading of the sentence lands on 58.

A stale number in a document that exists to stop a cold session re-deriving a decision is worse
than no number: it is confidently wrong, and it is read exactly when nobody has the context to
doubt it.

WHAT IS PINNED AND WHAT DELIBERATELY IS NOT. Only claims with ONE mechanical reading. og-lint.py
already learned the other half of this — "884 quartet composers" and "790 quartet composers" are
both grammatical and no regex can tell which a sentence means — so composer counts are checked
PERMISSIVELY here (a stated count must be one the data supports) and the curated-list sizes,
which name their own constant, are checked exactly. Inventing an error out of a phrasing nobody
anticipated is how a lint gets disabled.

The Testing section's entry count used to be in that unpinnable class — "Eleven entries" over ten
bullets was RIGHT, because sw-lint.test.py shares a bullet with sw-lint.py, and no mechanical
reading could confirm it. The sentence now says "one per bullet", which costs three words and
turns an unverifiable claim into a counted one. That is the cheaper half of the built-or-cut rule
and worth reaching for first: a claim can often be made checkable by being made precise.

A CLAIM THAT STOPS MATCHING IS A FAILURE, not a pass. This is round 5 of #23's lesson, one file
over: a negative case that can go vacuous proves nothing, and a pinned sentence that gets
reworded would silently retire its own check. So every claim must be FOUND and then be right.
Rewording is fine — update the pattern in the same commit, which is the point at which somebody
is looking at the number anyway.

The UI suite's own count is NOT here: some of its checks run in loops, so the literal `check(`
count is not the number it reports and no offline count is exact. `scripts/ui.test.mjs` asserts it
instead, at runtime where the real total is known — the same pin-it-where-the-file-settles-it rule
og-lint.py uses for manifest.json. (Quoting the two numbers here went stale within this very
branch, which is the Conventions rule about mechanical facts in comments, self-demonstrating.)

    python3 scripts/prose-lint.py
"""
import json, os, re, subprocess, sys, unicodedata as ud

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
         "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
         "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
         "twenty": 20, "twenty-one": 21, "twenty-two": 22, "twenty-five": 25}


def read(p):
    return open(os.path.join(ROOT, p), encoding="utf-8").read()


def num(s):
    s = s.strip().lower()
    return WORDS.get(s, int(s) if s.isdigit() else None)


def js_list(src, name):
    """Length of a `const NAME = [ "a", "b" ]` string array in a .js file."""
    m = re.search(r"const %s\s*=\s*\[(.*?)\]" % name, src, re.S)
    return len(re.findall(r'"[^"]*"', m.group(1))) if m else None


def cases(path):
    """len(CASES) by IMPORTING the suite, not by counting decorators.

    Counting them statically is the very mistake this file exists to catch: ui.test.mjs registers
    some of its checks in loops, so its literal call count is not what it reports. A subprocess
    keeps the import's side effects out of here.
    """
    code = ("import importlib.util,sys;"
            "spec=importlib.util.spec_from_file_location('m',%r);"
            "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
            "print(len(m.CASES))" % os.path.join(ROOT, path))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)
    return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else None


def fold_keys():
    """The FOLD map's keys, READ out of table.js rather than copied.

    sw.test.mjs reads BOOT out of sw.js for this reason: a second copy drifts, and here the drift
    would be silent in the worst direction — a test asserting the folding rule against a set of
    characters the app no longer folds.
    """
    m = re.search(r"FOLD\s*=\s*\{(.*?)\}", read("table.js"), re.S)
    return re.findall(r'"([^"])"\s*:', m.group(1)) if m else []


def fold_count(names, keys):
    """How many names carry a character NFD cannot decompose — what FOLD exists for.

    Lowercased first, because table.js folds AFTER `s.toLowerCase()` and the FOLD keys are all
    lowercase. Matching the raw name missed an "Øystein", which would have reported a live 8 where
    nine names need FOLD and then "corrected" invariant 13 to a wrong number — the exact defect
    this file exists to prevent, in the file that prevents it, and unable to go red.
    """
    return sum(1 for n in names if any(c in keys for c in n.lower()))


def live():
    chart = read("chart.js")
    rows = json.loads(read("composers.json"))["rows"]
    keys = fold_keys()
    moves = json.loads(read("data/pageviews.json")).get("moves", {})
    return {
        "CANON": js_list(chart, "CANON"),
        "OUTLIERS": js_list(chart, "OUTLIERS"),
        "WOMEN_CANON": js_list(chart, "WOMEN_CANON"),
        "curated": (js_list(chart, "CANON") or 0) + (js_list(chart, "OUTLIERS") or 0),
        "all_curated": sum(js_list(chart, n) or 0
                           for n in ("CANON", "OUTLIERS", "WOMEN_CANON")),
        "fold_names": fold_count([r[0] for r in rows], keys),
        "moved": sum(1 for v in moves.values() if v),
        "testing_bullets": len(re.findall(
            r"^- ", read("CLAUDE.md").split("## Testing", 1)[1].split("\n## ", 1)[0], re.M)),
        "fetch_views_cases": cases("scripts/fetch_views.test.py"),
        "pagemoves_cases": cases("scripts/pagemoves.test.py"),
        "validate_cases": cases("scripts/validate.test.py"),
        # No loops in that file, so the literal call count IS the case count. fix-lint.test.py is
        # NOT counted this way even though its literal count happens to be exact today: its cases
        # are inline rather than registered, so nothing stops the next one going inside a loop and
        # making this silently wrong. It asserts its own size at runtime instead, like
        # ui.test.mjs — the count that cannot drift rather than the one that happens to agree.
        "sw_lint_cases": len(re.findall(r"^\s*case\(", read("scripts/sw-lint.test.py"), re.M)),
        "prose_lint_cases": len(re.findall(r"^case\(", read("scripts/prose-lint.test.py"), re.M)),
        "roster": len(rows),
        "plotted": sum(1 for r in rows if r[3] is not None),
    }


# (file, key into live(), regex with ONE capture group holding the number, what it claims)
CLAIMS = [
    ("CLAUDE.md", "CANON", r"`CANON` \(the REPERTOIRE — (\S+) composers", "CANON's size"),
    ("CLAUDE.md", "OUTLIERS", r"`OUTLIERS` \((\w+)\)", "OUTLIERS' size"),
    ("CLAUDE.md", "WOMEN_CANON", r"`WOMEN_CANON` \((\w+),", "WOMEN_CANON's size"),
    ("CLAUDE.md", "all_curated", r"are ([\w-]+) canonical Wikipedia titles", "the three lists"),
    ("CLAUDE.md", "sw_lint_cases", r"covers that sixth check alone, in ([\w-]+) cases",
     "sw-lint.test.py's cases"),
    ("CLAUDE.md", "testing_bullets", r"([\w-]+) entries, one per bullet below",
     "the Testing section's entries"),
    ("CLAUDE.md", "moved", r"the shipped ([\w-]+) chains", "recorded page-move chains"),
    ("CLAUDE.md", "moved", r"([\w-]+) articles in this roster moved", "recorded page-move chains"),
    # Anchored to invariant 13's own sentence rather than to the bare phrase: the Conventions
    # section QUOTES the stale version of this claim as an example of the defect, and a pattern
    # loose enough to match a quotation reports the documentation of a bug as the bug.
    ("CLAUDE.md", "fold_names", r"Lutosławski\"\.\s+(\d+)\s+names carry such\s+characters",
     "names needing FOLD"),
    ("README.md", "prose_lint_cases", r"prose-lint\.test\.py.*?\((\d+) cases\)",
     "prose-lint.test.py's cases"),
    ("README.md", "validate_cases", r"validate\.test\.py.*?\((\d+) \+ a clean pass\)",
     "validate.test.py's cases"),
    ("README.md", "fetch_views_cases", r"fetch_views\.test\.py.*?\((\d+) cases\)",
     "fetch_views.test.py's cases"),
    ("README.md", "pagemoves_cases", r"pagemoves\.test\.py.*?\((\d+) cases\)",
     "pagemoves.test.py's cases"),
]

# Composer counts anywhere in the docs must be one the data currently supports. Permissive on
# purpose — see the header: the sentence cannot be disambiguated, the number can be bounded.
#
# The negative lookahead is load-bearing: without it "487 KB against composers.json's 46" reads
# as a claim that there are 487 composers, because `.` ends a word and the two intervening words
# are inside the allowance. og-lint.py's copy of this pattern runs over files that never mention
# the filename, which is why it has not been bitten by the same thing.
COUNTS = (("README.md", "CLAUDE.md"), r"\b(\d{3,5})(?:\s+\w+){0,2}\s+composers\b(?!\.\w)")
# A line about the 2014 scrape is stating a HISTORICAL total, which invariant 12 makes a
# first-class idea here: those numbers came from a different measurement system and are archived
# for provenance. README's comparison table exists to print 477 beside 884.
HISTORICAL = re.compile(r"\b2014\b")


def main():
    L = live()
    bad = []

    missing = [k for k, v in L.items() if v is None]
    if missing:
        bad.append("could not compute a live value for: " + ", ".join(sorted(missing)))

    for f, key, pat, what in CLAIMS:
        want = L.get(key)
        if want is None:
            continue
        hits = re.findall(pat, read(f), re.S)
        if not hits:
            # Not a pass. A pinned sentence that stops matching retires its own check silently,
            # which is the failure mode #23 round 5 spent a commit on.
            bad.append(f"{f}: the claim about {what} no longer matches its pattern "
                       f"— reword the pattern in scripts/prose-lint.py, or it proves nothing")
            continue
        for h in hits:
            got = num(h)
            if got is None:
                bad.append(f"{f}: {what} reads {h!r}, which is not a number this can check")
            elif got != want:
                bad.append(f"{f}: {what} says {h} — it is {want}")

    # Invariant 13 spells the folded characters out. A stale LIST is the same defect as a stale
    # count and reads more authoritatively, being a quotation of the code.
    keys = set(fold_keys())
    m = re.search(r"\*\*Search folds `([^`]+)` before NFD\*\*", read("CLAUDE.md"))
    if not m:
        bad.append("CLAUDE.md: invariant 13's folded-character list no longer matches its pattern")
    else:
        stated = set(m.group(1).split())
        if stated != keys:
            miss = " ".join(sorted(keys - stated)) or "none"
            extra = " ".join(sorted(stated - keys)) or "none"
            bad.append(f"CLAUDE.md: invariant 13 lists the folded characters as "
                       f"{' '.join(sorted(stated))}; FOLD has {' '.join(sorted(keys))} "
                       f"(missing: {miss}; not in FOLD: {extra})")

    files, pat = COUNTS
    allowed = {L["roster"]: "the roster", L["plotted"]: "the composers the chart can plot"}
    for f in files:
        for line in read(f).splitlines():
            if HISTORICAL.search(line):
                continue
            for stated in sorted(set(re.findall(pat, line))):
                if int(stated) not in allowed:
                    bad.append(f"{f}: states {stated} composers; live totals are "
                               + " and ".join(f"{n} ({w})" for n, w in allowed.items()))

    if bad:
        print("  prose-lint:")
        for b in bad:
            print(f"   - {b}")
        print("\n   A number in the docs that the repo can compute is a check, not a sentence.")
        return 1
    print(f"  prose-lint: {len(CLAIMS)} pinned claims and every stated composer count agree "
          f"with the data")
    return 0


if __name__ == "__main__":
    sys.exit(main())
