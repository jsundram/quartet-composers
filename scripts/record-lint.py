#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Did this commit write a number into a comment or a docstring?

    python3 scripts/record-lint.py            # the staged diff (what the hook runs)
    python3 scripts/record-lint.py --tree     # every tracked source file, for an audit
    python3 scripts/record-lint.py FILE...    # named files, against HEAD

HOOK-ONLY AND WARN-ONLY, AND IT MUST STAY THAT WAY. The question it asks — "is that number a
RECORD?" — is not one a program can answer, so a nonzero exit here is a prompt to a human and never
a verdict. Wiring it into CI would block a pull request on a judgement call, which is the trade
.githooks/pre-commit already refuses for everything it runs.

WHY IT EXISTS. CLAUDE.md's rule is that a number in prose is a RECORD or it is absent: a
measurement that happened cannot go stale, and anything the repo recomputes can. That rule was
written down, and forty-nine comments and doc lines went stale under it anyway — thirty of them in
one feature. Nothing asked. Both branch gates import codehash.unchanged() and stop asking a
comments-only hunk for a test, correctly, because a comment cannot be tested; the side effect is
that prose is the one surface here with no check on it at all.

IT IS NOT prose-lint.py, WHICH WAS DELETED, and the difference is the whole design. That one stored
the VALUE of each claim and re-checked it, so it could not tell a reflowed paragraph from a stale
fact and twice forced an edit over a line wrap. This stores nothing and re-checks nothing. It asks
only whether a number is NEW to the file's prose, by comparing the staged text against HEAD's, so
re-wrapping a paragraph — which moves every number and changes none — says nothing at all.

THE COMMENTS COME FROM codehash, NOT FROM A SECOND SCANNER. A file's prose is its source minus its
code, so code_of() answers this too: for Python the AST with docstrings dropped, for JS and CSS the
scanner that is verified by re-parsing. A second scanner here would be a second opinion about what
a comment is, and the one place that question is already settled is the file that has to be right
about it. It also inherits codehash's failure mode: a file it cannot classify is reported as such
rather than passed, because "no numbers found" and "could not look" are different answers.

DOCSTRINGS ARE THE POINT, not an extension of it. They are 44% of this repo's Python prose and hold
the module headers that explain the pipeline, so a check that read `#` lines only would have missed
the invariant-4 header, validate.py's per-check docstrings and build_data.py's imslp_cat — all of
which shipped wrong numbers. py_code() drops them, so they are covered by construction.
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import codehash                                                    # noqa: E402

SOURCE = (".py", ".js", ".mjs", ".css", ".md")

# A MARKDOWN FILE IS ALL PROSE, so there is no code to subtract — except a fenced block, which is
# code somebody pasted. The docs are where this rule was broken worst: prose-lint.py existed to
# pin seventeen numbers in CLAUDE.md and README.md, and scanning only source would leave exactly
# the files that motivated it unwatched.
FENCE = re.compile(r"^```.*?^```", re.M | re.S)

# A bare count, which is the thing that goes stale. Anything glued to a letter, a %, a # or a . is
# left to EXEMPT below rather than matched loosely here.
# THE DIGIT RUN IS UNBOUNDED on purpose. Written `\d{1,3}(?:,\d{3})*` — thousands with separators
# — it matched "4,926" and not "4926", so every unpunctuated four-figure count in this repo was
# invisible to it: "1770 composer pages", "4215". A year is four figures too and is handled where
# every other safe form is, in EXEMPT, which runs first.
NUMBER = re.compile(r"(?<![\w.#$%-])\d+(?:,\d{3})*(?:\.\d+)?(?![\w%])")

# What a number can be attached to and still be safe. Every entry is a form that either cannot go
# stale or is not a claim about the data: an issue or invariant this repo will always have numbered
# that way, a date, a measured offset, a version, an identifier somebody else assigns, a catalogue
# reference, a ratio. A measured offset IS a record — "the title's box centre is 4.47px above its
# baseline" is the result of an experiment — which is why px survives and a bare 4.47 would not.
EXEMPT = re.compile(
    r"#\d+"                       # issue reference
    r"|\b(?:invariant|section|round|PR|issue)\s+\d+"
    r"|\b(?:WCAG|PEP|RFC|ISO|HTTP)\s?[\d.]+"   # a standard somebody else numbers
    r"|\b(?:19|20)\d\d\b"         # a year, and 2015-07 style months
    r"|\d+(?:\.\d+)?\s?(?:px|em|rem|ch|vh|vw|ms|s|KB|MB|GB|B)\b"
    r"|\bv\d+"                    # quartets-v74
    r"|\b[PQ]\d+\b"               # Wikidata property and item ids
    r"|\b(?:Op|No|K|BWV|Hob|D|G|Wq)\.\s?\d+"
    r"|\d+(?:\.\d+)?x\b"          # a ratio, which is how a measurement is stated here
    r"|\d+(?:\.\d+)?%"            # a percentage, likewise
    r"|(?m:^\s{0,3}\d+\.\s)"    # a markdown ordered-list marker: invariant 16 numbers itself
    r"|https?://\S+"
    r"|#[0-9a-fA-F]{3,8}\b",      # a colour
    re.I)


# SPELLED counts, from eleven up. "the shipped twelve chains", "Twelve articles in this roster
# moved" and "in thirteen cases that need no browser" all went stale this pass and all are
# invisible to a digit scanner. The floor is where it is because below it the word is ordinary
# English: "one" appears 286 times in these three docs and "three" 87, against 42 for every word
# from eleven up combined, so a lower floor reports the prose rather than the claims in it.
WORDS = re.compile(
    r"\b(?:eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
    r"|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](?:one|two|three|four|five"
    r"|six|seven|eight|nine))?"
    r"|hundred|thousand)\b", re.I)


# 0 and 1 in prose name a VALUE, not a count — "`0` both for a composer IMSLP holds with no
# quartets", "one changed line per composer". Neither can go stale the way a tally does, and
# including them buries the real findings under every mention of either.
VALUES = {"0", "1"}


def selects(path):
    """Is this a file the lint looks at? The one place that question is answered, so a case can
    ask it: handling markdown and never SELECTING a markdown file are the same silence."""
    return path.endswith(SOURCE)


def numbers(text):
    """The multiset of bare counts in text, exempt forms removed first."""
    out = {}
    clean = EXEMPT.sub(" ", text)
    for n in NUMBER.findall(clean):
        if n not in VALUES:
            out[n] = out.get(n, 0) + 1
    for w in WORDS.findall(clean):
        k = w.lower()
        out[k] = out.get(k, 0) + 1
    return out


# PEP 723's inline metadata is a comment block to Python and a manifest to everything else, and
# every script here opens with one. Left in, its pinned interpreter version is a finding on the
# first commit of every new file — and a nag that fires where nothing was ever claimed teaches the
# reader to skip the whole report.
META = re.compile(r"^# /// script$.*?^# ///$", re.M | re.S)


def prose_numbers(path, src):
    """({number: count} for the file's PROSE, why-not). Code numbers are subtracted, not matched."""
    src = META.sub("", src)
    if path.endswith(".md"):
        code = "\n".join(FENCE.findall(src))
    else:
        code, _, how = codehash.code_of(path, src)
        if code is None:
            return None, how
    whole, in_code = numbers(src), numbers(code)
    return {n: c - in_code.get(n, 0) for n, c in whole.items() if c > in_code.get(n, 0)}, None


# A line that opens with one of these is prose beyond argument. It is only used to ORDER the
# report — the finding itself came from the multiset — because a bare 0 appears in prose and in
# `slice(0, -1)` alike, and pointing a reader at the code line wastes the one glance a nag gets.
PROSE_LINE = re.compile(r"^\s*(#|//|/\*|\*|\"\"\"|\'\'\')")


def lines_with(src, num):
    """The lines quoting `num` once its exempt forms are blanked, prose-looking ones first.

    The multiset above has deliberately forgotten which line a number came from — that is what
    makes a reflow silent — so this finds it again, and is best-effort by construction.
    """
    pat = (re.compile(r"\b" + re.escape(num) + r"\b", re.I) if num.isalpha()
           else re.compile(r"(?<![\w.#$%-])" + re.escape(num) + r"(?![\w%])"))
    hits = [(i, l.strip()) for i, l in enumerate(src.split("\n"), 1)
            if pat.search(EXEMPT.sub(" ", l))]
    return sorted(hits, key=lambda h: not PROSE_LINE.match(h[1]))


def head_src(path):
    r = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=ROOT, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def staged():
    r = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                       cwd=ROOT, capture_output=True, text=True)
    return [p for p in r.stdout.split() if selects(p)]


def staged_src(path):
    r = subprocess.run(["git", "show", f":{path}"], cwd=ROOT, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def check(path, old_src, new_src):
    """(findings, note) — the numbers this change ADDS to `path`'s prose."""
    new, why = prose_numbers(path, new_src)
    if new is None:
        return [], f"{path}: cannot tell prose from code — {why}"
    old, _ = prose_numbers(path, old_src) if old_src else ({}, None)
    old = old or {}
    found = []
    for n, c in sorted(new.items(), key=lambda kv: -len(kv[0])):
        if c > old.get(n, 0):
            # A finding the locator cannot place is still a finding. Appending only inside the
            # loop over lines_with() dropped it instead, so any disagreement between the two
            # places that blank exempt forms deleted a real report rather than mis-pointing it.
            where = lines_with(new_src, n) or [(0, "")]
            found.append((path,) + where[0][:1] + (n, where[0][1]))
    return found, None


def report(found, notes):
    for note in notes:
        print(f"  record-lint: {note}")
    if not found:
        return 0
    print("  record-lint: a number reached prose. Is it a RECORD — a measurement that happened —")
    print("               or something the repo recomputes? See CLAUDE.md's rule.")
    for path, ln, num, text in found:
        print(f"   * {path}:{ln}  [{num}]  {text[:88]}")
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="*", help="files to check against HEAD (default: the index)")
    ap.add_argument("--tree", action="store_true", help="every tracked source file, from nothing")
    a = ap.parse_args()

    found, notes = [], []
    if a.tree:
        r = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
        for p in [x for x in r.stdout.split() if selects(x)]:
            f, note = check(p, "", open(os.path.join(ROOT, p), errors="ignore").read())
            found += f
            if note:
                notes.append(note)
    else:
        for p in a.files or staged():
            new = open(os.path.join(ROOT, p), errors="ignore").read() if a.files else staged_src(p)
            f, note = check(p, head_src(p), new)
            found += f
            if note:
                notes.append(note)
    return report(found, notes)


if __name__ == "__main__":
    sys.exit(main())
