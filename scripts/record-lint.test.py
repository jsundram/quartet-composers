#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Prove record-lint asks about a NEW number and stays quiet about a moved one.

    python3 scripts/record-lint.test.py

NO NETWORK, NO REPO: every case is a pair of strings through check(), so this runs anywhere.

WHY THIS FILE EXISTS. The lint is one regex away from being prose-lint.py again, and prose-lint was
deleted for a failure a reader cannot see by eye: it could not tell a REFLOWED paragraph from a
stale fact, so wrapping a line at 100 columns demanded an edit to a claim nobody had touched. The
property that makes this one different is not in its output — a quiet run looks the same either
way — it is that the comparison is a multiset over the whole file. reflow_is_silent is therefore
the case this suite exists for; the rest keep the noise floor honest enough that the nag gets read.

The other half is the one every check here owes: a lint that flags nothing is not a lint. Each
`flags` case names a number the repo recomputes and would have shipped wrong, and four of them are
real lines this pass found — Beethoven's 23 pages, the 406 derived categories, "37 requests" (38),
and a docstring, which is where 44% of this repo's Python prose lives and where a `#`-only reader
would have seen none of it.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("record_lint", os.path.join(HERE, "record-lint.py"))
rl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rl)

CASES = []
FAILED = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def flags(path, old, new, want):
    """The numbers check() reports for old -> new."""
    found, note = rl.check(path, old, new)
    assert note is None, "unreadable: %s" % note
    got = sorted(n for _p, _l, n, _t in found)
    assert got == sorted(want), "wanted %s, got %s" % (sorted(want), got)


# ---- it asks about a number that is new -------------------------------------------------------

@case("a count written into a JS comment is flagged")
def js_comment(_):
    flags("a.js", "// nothing here\n", "// 406 of the 462 categories are derived\n", ["406", "462"])


@case("a count written into a python DOCSTRING is flagged")
def py_docstring(_):
    # 44% of this repo's python prose is docstrings, and a reader that only knew `#` would pass
    # build_data.py's imslp_cat, validate.py's per-check docstrings and every module header.
    old = 'def f():\n    """Does a thing."""\n    return 1\n'
    new = 'def f():\n    """Does a thing. It holds for 406 of the 462."""\n    return 1\n'
    flags("a.py", old, new, ["406", "462"])


@case("a count written into a python # comment is flagged")
def py_comment(_):
    flags("a.py", "x = 1\n", "# re-reading must not cost 37 requests\nx = 1\n", ["37"])


@case("a count edited to a different wrong count is flagged")
def edited(_):
    # The repair for a stale number is deleting it. Changing 406 to 407 is the OTHER repair, and it
    # is the one that keeps the claim alive to go stale again.
    flags("a.js", "// it holds for 406 of them\n", "// it holds for 407 of them\n", ["407"])


# ---- and stays quiet about one that only moved ------------------------------------------------

@case("REFLOWING a paragraph that quotes a number says nothing")
def reflow_is_silent(_):
    # prose-lint.py's grave. The claim is untouched; only the line wrap changed, and every number
    # in the file is exactly where it was as far as a multiset is concerned.
    old = "// it holds for 406 of the 462 composers IMSLP has; the other 56 ship\n// verbatim\n"
    new = "// it holds for 406 of the 462 composers IMSLP\n// has; the other 56 ship verbatim\n"
    flags("a.js", old, new, [])


@case("moving a commented number to another FILE position says nothing")
def moved_is_silent(_):
    old = "// the 462 are derived\nfunction f() {}\n"
    new = "function f() {}\n// the 462 are derived\n"
    flags("a.js", old, new, [])


@case("deleting a number says nothing — that is the repair, not a finding")
def deletion_is_silent(_):
    flags("a.js", "// it holds for 406 of them\n", "// it holds for most of them\n", [])


# ---- what a number may be attached to and still be a record -----------------------------------

@case("an issue reference, an invariant and a year are not counts")
def records(_):
    new = "// #42 and invariant 15, measured in 2015 and again in 2026-08\n"
    flags("a.js", "//\n", new, [])


@case("a measured offset, a ratio and a percentage are records")
def measurements(_):
    # "the title's box centre is 4.47px above its baseline" is the result of an experiment, and
    # invariant 15's "the median correction was 1.02x" is the evidence for a policy. Neither can
    # go stale: nothing recomputes them.
    new = "// 4.47px above the baseline, a 1.02x correction, 12% off typical\n"
    flags("a.js", "//\n", new, [])


@case("a QID, a property id and a catalogue number are somebody else's identifiers")
def identifiers(_):
    flags("a.py", "# x\n", "# Q255 states P839, on the Op.18 No.1 page\n", [])


@case("0 and 1 in prose name a value, not a tally")
def values(_):
    flags("a.js", "//\n", "// `0` means asked, and 1 changed line per composer\n", [])


# ---- and it never claims more than it can see -------------------------------------------------

@case("a number added to the CODE is not a prose finding")
def code_is_not_prose(_):
    # The finding is source-minus-code. Without that subtraction every new constant, array length
    # and pixel value in a diff would be reported as prose, which is a nag nobody would read twice.
    flags("a.js", "", "const N = 462;\nconst M = [1, 2, 3, 406];\n", [])


@case("...but a comment QUOTING a code literal still is")
def quoted_literal(_):
    # The subtraction is per-number, not per-file: one 462 in the code and one in the comment
    # leaves one for prose. Matching whole-file would let a constant launder the claim beside it.
    flags("a.js", "const N = 462;\n", "const N = 462;   // the 462 placed composers\n", ["462"])


@case("a file whose code cannot be told from its prose is REPORTED, not passed")
def unreadable(_):
    # codehash's contract one level up: cannot-tell is a third answer. A python file that does not
    # parse has no AST, so there is no way to know which numbers were prose — and silence there
    # would read exactly like a clean run.
    found, note = rl.check("a.py", "", "def f(:\n  # 406 of them\n")
    assert found == [], "should not report findings it cannot stand behind: %r" % (found,)
    assert note and "cannot tell" in note, "should say it could not look, got %r" % (note,)


def main():
    for name, fn in CASES:
        try:
            fn(None)
            print("  ok   %s" % name)
        except AssertionError as e:
            FAILED.append(name)
            print("  FAIL %s\n       %s" % (name, e))
    print("\n%d passed, %d failed" % (len(CASES) - len(FAILED), len(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
