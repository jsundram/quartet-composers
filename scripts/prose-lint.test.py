#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Proves prose-lint.py counts what table.js folds, and reads every number word it may meet.

Small on purpose: most of prose-lint is a table of patterns whose correctness is visible in the
file, and the linter fails loudly the moment one stops matching. What is NOT visible there is
`fold_count`, because it duplicates a rule that lives in another language in another file
(`table.js` folds AFTER `s.toLowerCase()`), and because its failure mode is a number that looks
entirely plausible: the wrong count would be written into invariant 13 as a correction, by the
one file whose job is stopping exactly that. It is also latent — no roster name carries an
uppercase folded character today — so nothing in the repo could go red on it.

Offline, no fixtures on disk:
    python3 scripts/prose-lint.test.py
"""
import importlib.util, os, sys

spec = importlib.util.spec_from_file_location(
    "pl", os.path.join(os.path.dirname(os.path.abspath(__file__)), "prose-lint.py"))
pl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pl)

# READ from table.js via the module under test, not typed out here. A hand-copied list is the
# drift sw.test.mjs avoids by reading BOOT out of sw.js, and here it would drift silently in the
# worst direction: a test asserting the folding rule against characters the app no longer folds.
KEYS = pl.fold_keys()
fails = []


def case(name, got, want, extra=""):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f" — {extra}" if extra else ""))
    if not ok:
        fails.append(name)


case("a lowercase folded character counts",
     pl.fold_count(["Witold Lutosławski"], KEYS), 1)
# The one that goes red without the fix: `Ø` is not `ø`, and table.js lowercases before folding.
case("an UPPERCASE folded character counts too",
     pl.fold_count(["Øystein Sevåg"], KEYS), 1)
case("...and it is the same name either way",
     pl.fold_count(["Øystein"], KEYS), pl.fold_count(["øystein"], KEYS))
case("a name NFD can decompose does not count",
     pl.fold_count(["Antonín Dvořák", "Béla Bartók"], KEYS), 0)
case("a plain ASCII name does not count",
     pl.fold_count(["Joseph Haydn"], KEYS), 0)
case("one name carrying two folded characters is still one name",
     pl.fold_count(["Łukasz Nørgård"], KEYS), 1)
case("the live FOLD map is what is being tested, not a copy of it",
     "ł" in KEYS and len(KEYS) >= 6, True, f"{len(KEYS)} keys read from table.js")

# WORDS is the other thing here a reader cannot check by eye, for the same reason: its failure is a
# claim the linter declines to read rather than one it gets wrong. A literal map carries the numbers
# somebody happened to write down, so the first claim to pass twenty reported "not a number this can
# check" about a sentence that was perfectly clear — which is a lint telling you to reword correct
# prose, the one way to get it switched off. Built now, so the gap cannot come back.
case("every number word the docs write is readable",
     [pl.num(w) for w in ("three", "ten", "twelve", "eighteen", "twenty-two", "thirty-two")],
     [3, 10, 12, 18, 22, 32])
case("...including the tens the docs have not reached yet",
     [pl.num(w) for w in ("forty-two", "fifty", "ninety-nine")], [42, 50, 99])
case("a digit is still a number, and a non-number is still None",
     [pl.num("884"), pl.num("several")], [884, None])

print(("\nFAIL: " + ", ".join(fails)) if fails else "\nall ok")
sys.exit(1 if fails else 0)
