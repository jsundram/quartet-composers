#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Prove record-lint asks about a NEW number and stays quiet about a moved one.

    python3 scripts/record-lint.test.py

NO NETWORK, NO REPO: every case is a pair of strings through check(), so this runs anywhere.

WHY THIS FILE EXISTS. The lint is one regex away from being prose-lint.py again, and prose-lint was
deleted for a failure a reader cannot see by eye: it could not tell a REFLOWED paragraph from a
stale fact, so wrapping a line at 100 columns demanded an edit to a claim nobody had touched. What
makes this one different is not in its output — a quiet run looks the same either way — but that
the comparison is a multiset over the whole file. `reflow_is_silent` is the case this suite exists
for; the rest keep the noise floor honest enough that the nag gets read.

The other half is what every check here owes: a lint that flags nothing is not a lint. Each `flags`
case names a number the repo recomputes and would have shipped wrong, and four of them are real
lines this pass found.

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


@case("a count written into a MARKDOWN doc is flagged")
def markdown(_):
    # The docs are what prose-lint.py existed for: seventeen numbers in CLAUDE.md and README.md.
    # Scanning source only would leave the files that motivated the whole rule unwatched.
    flags("CLAUDE.md", "The roster is large.\n", "The roster holds 884 rows.\n", ["884"])


@case("the docs are among the files it LOOKS at")
def selects_docs(_):
    # check() handling markdown and staged() never offering it a markdown file are the same
    # silence, and the second is a one-word edit that looks like tidying.
    picked = [p for p in ("CLAUDE.md", "README.md", "app.js", "scripts/validate.py",
                          "composers.json", "index.html", ".github/workflows/checks.yml")
              if rl.selects(p)]
    assert picked == ["CLAUDE.md", "README.md", "app.js", "scripts/validate.py"], picked


@case("a fenced code block in markdown is code, not prose")
def markdown_fence(_):
    # Otherwise every pasted snippet reports its own literals, and the docs here are full of them.
    new = "Run it:\n\n```\nconst N = 462;\n```\n"
    flags("CLAUDE.md", "Run it:\n", new, [])


@case("a SPELLED count from eleven up is flagged")
def spelled(_):
    # "the shipped twelve chains", "Twelve articles in this roster moved" and "in thirteen cases
    # that need no browser" all went stale this pass, and a digit scanner sees none of them.
    flags("CLAUDE.md", "It ships chains.\n", "It ships twelve chains.\n", ["twelve"])


@case("a spelled number BELOW eleven is ordinary English, not a count")
def spelled_floor(_):
    # Below the floor the word is ordinary English rather than a tally, and these docs use "one"
    # and "three" constantly meaning neither as a count. A lower floor reports the prose.
    flags("CLAUDE.md", "x\n", "There are three states and two halves, one each.\n", [])


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


@case("a float written with a trailing zero is still the CODE's number")
def trailing_zero_float(_):
    # codehash's python answer is an ast.dump, which prints a float's VALUE and not its source
    # text: `0.20` comes back `0.2`, the two never cancelled, and the lint reported the constant
    # on the commit that added it. Cancelling by value fixes `1,000` against `1000` too.
    flags("a.py", "", "CEILING = {'source': 0.20, 'test': 0.20}\n", [])
    flags("a.py", "", "N = 1000\n", [])
    # ...and it is still REPORTED by the spelling that was written, which is what a reader has to
    # find in the file.
    flags("a.py", "x = 1\n", "x = 1\n# a 0.20 ratio nobody measured\n", ["0.20"])


@case("...and which spelling cancels does not depend on which comes FIRST")
def cancel_is_order_free(_):
    # Keyed by spelling, the subtraction had to guess which prose occurrence a code literal
    # cancelled, and the guess was FILE ORDER: the same file reported a different number, on a
    # different line, depending on which of two lines came first — and in one order it pointed at
    # the CODE line with the real finding dropped. Both pairs are here because the integer pair is
    # settled before a value comparison is ever reached, so on its own it proves nothing.
    for a, b in ((" # the roster holds 1,000 composers\n", "N = 1000\n"),
                 (" # the 0.200 ratio nobody measured\n", "X = 0.20\n")):
        one, _ = rl.check("a.py", "", a.strip() + "\n" + b)
        two, _ = rl.check("a.py", "", b + a.strip() + "\n")
        # ONE finding, the prose spelling, pointing at the comment — in either order. Asserting
        # only that the two orders AGREE is not enough: they already agreed before the fix, both
        # reporting the code's number as well, so the case could not go red for what it names.
        for got in (one, two):
            assert len(got) == 1, "the code's own number is not prose: %r" % (got,)
            assert got[0][3].startswith("#"), "and it points at the PROSE line: %r" % (got[0],)
        assert [n for _p, _l, n, _t in one] == [n for _p, _l, n, _t in two], (a, one, two)


@case("two numbers that are not the same number are not one")
def canon_is_textual(_):
    # canon() parsed with float(), which merged numbers that are not one number at all: `09` in a
    # date with `9`, and `0,400` with `400`. A count added to prose was then cancelled by an
    # untouched line elsewhere in the file, and the finding pointed AT that line instead.
    assert rl.canon("09") != rl.canon("9"), "a date fragment is not a count"
    assert rl.canon("0,400") != rl.canon("400")
    # ...while the two spellings that really are one number still collapse, which is the pair
    # ast.dump produces and the whole reason canon() exists.
    assert rl.canon("0.20") == rl.canon("0.2") == "0.2"
    assert rl.canon("1,000") == rl.canon("1000")
    assert rl.canon("100.0") == rl.canon("100")
    # End to end, which is how it was found: the number the change ADDED is the one reported.
    old = "# a run from 2026-09-07 to 09\nx = 1\n"
    found, _ = rl.check("a.py", old, old + "# real moves run 9 times faster\n")
    assert [(l, n) for _p, l, n, _t in found] == [(3, "9")], found


@case("a finding points at PROSE, not at the code line that shares its number")
def located_in_prose(_):
    # PROSE_LINE only knows comment markers. In markdown neither a prose line nor a fenced line
    # carries one, so the tie fell to file order and the finding landed INSIDE the fence that
    # prose_numbers() had itself treated as code. The code text is the better oracle where there
    # is one: a line that appears verbatim in it is ranked last.
    md = "Notes.\n\n```\nconst N = 1000;\n```\n\nThe roster holds 1,000 composers.\n"
    found, _ = rl.check("D.md", "", md)
    assert [(l, n) for _p, l, n, _t in found] == [(7, "1,000")], found
    # ...and the same in a language where the marker rule COULD have answered, since ranking the
    # code line last is what makes the two agree rather than the marker happening to be there.
    found, _ = rl.check("a.js", "", "const N = 462;\n// the 462 placed composers\n")
    assert [(l, n) for _p, l, n, _t in found] == [(2, "462")], found
    # A line that OPENS with a marker and carries code is not prose, and comparing it verbatim
    # against the code cannot say so — the strip took the comment off it.
    found, _ = rl.check("a.js", "", "/* why */ const N = 462;\n// the 462 placed composers\n")
    assert [(l, n) for _p, l, n, _t in found] == [(2, "462")], found
    # Nor can a verbatim comparison survive the strip reflowing a line's alignment.
    md = "Notes.\n\n```\nconst  N =   1000;\n```\n\nThe roster holds 1,000 composers.\n"
    found, _ = rl.check("D.md", "", md)
    assert [(l, n) for _p, l, n, _t in found] == [(7, "1,000")], found
    # The strip also REFLOWS: this repo's source is column-aligned and codehash collapses runs of
    # spaces, so a verbatim comparison misses the code line it was looking at. Nothing else
    # rescues this one — the comment's continuation line carries no marker either.
    found, _ = rl.check("a.js", "", "const T = { a:   462 };\n/* the placed\n   composers: 462 of them */\n")
    assert [(l, n) for _p, l, n, _t in found] == [(3, "462")], found
    # Deleting code lines is DESTRUCTIVE, so their order decides. A bare `}` earlier in the file
    # ate the brace the whole rule below needed to match, and the rule survived as prose — which
    # is what styles.css did to the real run: the finding landed on a CSS rule, not on the comment
    # explaining it. Longest first cannot be defeated that way.
    found, _ = rl.check("a.js", "", "function f() {\n}\nconst T = { a: 462 };\n"
                                    "/* the placed\n   composers: 462 of them */\n")
    assert [(l, n) for _p, l, n, _t in found] == [(5, "462")], found
    # And the other direction: a SHORT code line quoted inside a comment must not demote it,
    # which is why the test is whether the NUMBER survived rather than whether the line matched.
    found, _ = rl.check("a.js", "", "function f() {\n}\n// closing 462 of them }\n")
    assert [(l, n) for _p, l, n, _t in found] == [(3, "462")], found


@case("a number the CODE spells differently is still the code's")
def code_spelling_is_not_prose(_):
    # ast.dump prints a float's value, so the code's `0.20` arrives as `0.2`. Cancelling that
    # against the PROSE `0.2` left the code literal's own spelling unbudgeted, and the finding
    # landed on `CEILING = 0.20` — a line of code — while the comment went unreported.
    found, _ = rl.check("a.py", "", "# Set to 0.2 because of the cap\nCEILING = 0.20\n")
    assert [(l, n) for _p, l, n, _t in found] == [(1, "0.2")], found


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
        except Exception as e:
            # Not AssertionError alone: under ablation this suite runs against the BASE's module,
            # where a helper it names may not exist at all. A crash there aborted every case after
            # it, so the gate saw fewer FAILs than the branch actually earns — and a suite that
            # dies partway reports as INCONCLUSIVE, which proves nothing.
            FAILED.append(name)
            print("  FAIL %s\n       %s: %s" % (name, type(e).__name__, e))
    print("\n%d passed, %d failed" % (len(CASES) - len(FAILED), len(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
