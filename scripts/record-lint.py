#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Did this commit write a number into a comment or a docstring?

    python3 scripts/record-lint.py            # the staged diff (what the hook runs)
    python3 scripts/record-lint.py --base REF # what this BRANCH adds (what CI reports)
    python3 scripts/record-lint.py --tree     # every tracked source file, for an audit
    python3 scripts/record-lint.py FILE...    # named files, against HEAD

WARN-ONLY WHEREVER IT RUNS, AND IT MUST STAY THAT WAY. The question it asks — "is that number a
RECORD?" — is not one a program can answer, so a nonzero exit is a prompt to a human and never a
verdict. It runs in two places for two audiences and gates in neither: the pre-commit hook, where
it is cheapest to act on, and CI under --base, which writes it to the run summary with `|| true`.
Giving it teeth in CI would block a pull request on a judgement call, and a lint that did exactly
that was built and reverted (#67, #74).

WHY IT EXISTS. CLAUDE.md's rule is that a number in prose is a RECORD or it is absent: a measurement
that happened cannot go stale, and anything the repo recomputes can. That rule was written down and
comments and doc lines went stale under it anyway, because nothing asked — both branch gates import
codehash.unchanged() and stop asking a comments-only hunk for a test, correctly, since a comment
cannot be tested, and the side effect is that prose is the one surface here with no check on it.

WHAT IT ASKS, AND THE ORDER. Not "record or not" — that is a binary, and it sends a reader straight
to a vaguer rewrite, which keeps the clause that was only ever hosting the count. The repo's own
rule puts deletion first, so the report names three branches in order and the first is to take the
number out and read what is left.

IT IS NOT prose-lint.py, WHICH WAS DELETED, and the difference is the whole design. That one stored
the VALUE of each claim and re-checked it, so it could not tell a reflowed paragraph from a stale
fact. This stores nothing and re-checks nothing: it asks only whether a number is NEW to the file's
prose, by comparing the staged text against HEAD's, so re-wrapping a paragraph — which moves every
number and changes none — says nothing at all.

THE COMMENTS COME FROM codehash, NOT FROM A SECOND SCANNER. A file's prose is its source minus its
code, so code_of() answers this too. A second scanner would be a second opinion about what a comment
is, and the one place that question is settled is the file that has to be right about it. It also
inherits codehash's failure mode: a file it cannot classify is reported rather than passed, because
"no numbers found" and "could not look" are different answers.

DOCSTRINGS ARE THE POINT, not an extension of it. They are most of this repo's Python prose and hold
the module headers that explain the pipeline, so a check reading `#` lines only would have missed
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
# — it matched a count written "4,926" and not the same count written "4926", so every
# unpunctuated four-figure figure in this repo was invisible to it. A year is four figures too and
# is handled where every other safe form is, in EXEMPT, which runs first.
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
# English rather than a tally — the docs here say "one" and "three" constantly and mean neither as
# a count — so a lower floor would report the prose instead of the claims in it.
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
    """({value: count}, {value: [spellings as written]}) for the bare counts in text.

    KEYED BY VALUE, because the two sides being subtracted do not share a spelling: codehash's
    Python answer is an ast.dump, which prints `0.20` as `0.2`. Keyed by spelling the subtraction
    had to GUESS which prose occurrence a code literal cancelled, and the guess was file order —
    so the same file reported a different number, on a different line, depending on which of two
    lines came first. By value there is nothing to guess. The spellings ride along because a
    finding has to point at what was WRITTEN.
    """
    out, seen = {}, {}
    clean = EXEMPT.sub(" ", text)
    for n in NUMBER.findall(clean):
        if n in VALUES:
            continue
        k = canon(n)
        out[k] = out.get(k, 0) + 1
        seen.setdefault(k, []).append(n)
    for w in WORDS.findall(clean):
        k = w.lower()
        out[k] = out.get(k, 0) + 1
        seen.setdefault(k, []).append(w)
    return out, seen


# PEP 723's inline metadata is a comment block to Python and a manifest to everything else, and
# every script here opens with one. Left in, its pinned interpreter version is a finding on the
# first commit of every new file — and a nag that fires where nothing was ever claimed teaches the
# reader to skip the whole report.
META = re.compile(r"^# /// script$.*?^# ///$", re.M | re.S)


def canon(n):
    """A number's identity for CANCELLING is its value: `0.20` and `0.2` are the same number.

    TEXTUAL, not `float()`. Parsing merged numbers that are not the same one at all: `09` in a
    date became `9`, and `0,400` became `400` — so a new count in prose could be cancelled by an
    untouched line elsewhere in the file, and the finding pointed there instead. Only the two
    spellings that really are one number are collapsed: comma grouping, and the trailing zeros of
    a decimal, which is the pair ast.dump produces.
    """
    if not n[0].isdigit():
        return n                                   # a spelled count, which has no other form
    whole, _, frac = n.replace(",", "").partition(".")
    frac = frac.rstrip("0")
    return whole + ("." + frac if frac else "")


def prose_numbers(path, src):
    """({value: count} for the file's PROSE, its spellings, the code text, why-not)."""
    src = META.sub("", src)
    if path.endswith(".md"):
        code = "\n".join(FENCE.findall(src))
    else:
        code, _, how = codehash.code_of(path, src)
        if code is None:
            return None, None, None, how
    (whole, forms), (in_code, _) = numbers(src), numbers(code)
    return ({k: c - in_code.get(k, 0) for k, c in whole.items() if c > in_code.get(k, 0)},
            forms, code, None)


# A line that opens with one of these is prose beyond argument. It is only used to ORDER the
# report — the finding itself came from the multiset — because a bare 0 appears in prose and in
# `slice(0, -1)` alike, and pointing a reader at the code line wastes the one glance a nag gets.
PROSE_LINE = re.compile(r"^\s*(#|//|/\*|\*|\"\"\"|\'\'\')")


def lines_with(src, spellings, code=""):
    """The lines quoting ANY spelling of one number, prose-looking ones first, then in file order.

    The multiset above has deliberately forgotten which line a number came from — that is what
    makes a reflow silent — so this finds it again, and is best-effort by construction. It takes
    every spelling because the key is a value now: `0.20` and `0.2` are one finding, and the line
    worth pointing at is whichever of them a comment wrote.
    """
    # THE CODE TEXT IS THE BETTER ORACLE, where there is one. PROSE_LINE only knows markers, so
    # in markdown — where prose carries none and a fenced line carries none either — the tie fell
    # to file order and a finding landed INSIDE the fence prose_numbers() had just treated as
    # code. A marker is not much better than file order anyway: `/* why */ const N = 462;` opens
    # with one and is a line of code.
    # So the test is not whether the line LOOKS like prose, nor whether it appears verbatim in the
    # code — both miss, the second on any line the strip reflowed or only partly removed. Delete
    # every code line from it and ask whether this number SURVIVED. A line whose copy is inside
    # code loses it; a comment keeps it; and a short code line quoted inside a comment cannot
    # demote it, because removing `}` does not remove the number. For Python the code is an
    # ast.dump matching no source line, so nothing there changes and the marker rule still
    # decides.
    # LONGEST FIRST, because deleting them is destructive: a bare `}` earlier in the file ate the
    # brace a whole CSS rule needed to match, and the rule then survived as prose. Length order
    # cannot be defeated that way — nothing shorter is removed until everything containing it is.
    flat = lambda l: re.sub(r"[ \t]+", " ", l).strip()
    code_lines = sorted({flat(l) for l in code.split("\n") if l.strip()}, key=len, reverse=True)

    def in_code(line, pat):
        bare = flat(line)
        for cl in code_lines:
            bare = bare.replace(cl, " ")
        return not pat.search(bare)

    hits = []
    for num in dict.fromkeys(spellings):
        pat = (re.compile(r"\b" + re.escape(num) + r"\b", re.I) if num.isalpha()
               else re.compile(r"(?<![\w.#$%-])" + re.escape(num) + r"(?![\w%])"))
        hits += [(i, l.strip(), num, in_code(l, pat)) for i, l in enumerate(src.split("\n"), 1)
                 if pat.search(EXEMPT.sub(" ", l))]
    hits = sorted(hits, key=lambda h: (h[3], not PROSE_LINE.match(h[1]), h[0]))
    return [h[:3] for h in hits]


# EVERY GIT READER TAKES ITS ROOT, for the reason volume.py's --root exists one file over: with
# ROOT hardcoded from this script's own path, a suite driving the real entry point over a throwaway
# tree silently reads THIS repo instead. Not hypothetical — record-lint.test.py's --base case was
# written that way first and passed on a number it found in its own source.
def at(ref, path, root=ROOT):
    """`path` as `ref` holds it, or "" where it is absent. `ref=""` reads the INDEX.

    One reader for every side, because a file the other side lacks is not an error here — it has no
    prose to subtract — and two copies of that rule is two places to forget it."""
    r = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=root, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def staged(root=ROOT):
    r = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                       cwd=root, capture_output=True, text=True)
    return [p for p in r.stdout.split() if selects(p)]


def branch(base, root=ROOT):
    """(merge-base, files the branch changed) for a --base run, or (None, why not).

    THE MERGE BASE, not the ref's tip — the diff a rebase, a squash and a stacked branch all leave
    alone, which is what sw-lint.py --base and ablate.py read from. Against the tip, every commit
    somebody else landed on main since this branch started is charged to it."""
    mb = subprocess.run(["git", "merge-base", base, "HEAD"], cwd=root,
                        capture_output=True, text=True)
    if mb.returncode != 0 or not mb.stdout.strip():
        return None, f'no merge base between HEAD and "{base}"'
    mb = mb.stdout.strip()
    # ASKED, not assumed: a diff that fails prints nothing, and an empty file list here is a clean
    # run — the silence this whole lint exists to break, arriving from inside it.
    r = subprocess.run(["git", "diff", "--name-only", "--diff-filter=ACM", mb, "HEAD"],
                       cwd=root, capture_output=True, text=True)
    if r.returncode != 0:
        return None, f'git diff {mb[:8]}..HEAD failed: {r.stderr.strip()}'
    return mb, [p for p in r.stdout.split() if selects(p)]


def check(path, old_src, new_src):
    """(findings, note) — the numbers this change ADDS to `path`'s prose."""
    new, forms, code, why = prose_numbers(path, new_src)
    if new is None:
        return [], f"{path}: cannot tell prose from code — {why}"
    old = prose_numbers(path, old_src)[0] if old_src else {}
    old = old or {}
    found = []
    for n, c in sorted(new.items(), key=lambda kv: -len(kv[0])):
        if c > old.get(n, 0):
            # A finding the locator cannot place is still a finding. Appending only inside the
            # loop over lines_with() dropped it instead, so any disagreement between the two
            # places that blank exempt forms deleted a real report rather than mis-pointing it.
            where = lines_with(new_src, forms.get(n, [n]), code) or [(0, "", n)]
            found.append((path, where[0][0], where[0][2], where[0][1]))
    return found, None


def report(found, notes):
    for note in notes:
        print(f"  record-lint: {note}")
    if not found:
        return 0
    print("  record-lint: a number reached prose. Three branches, and CUT IS THE FIRST TO TRY:")
    print("    1. delete it — take the number out and read what is left. A clause that now says")
    print("       nothing was hosting the number, not making a point, and a vaguer rewrite of it")
    print("       (\"hundreds of them\", \"a couple of dozen\") keeps the filler and loses the fact.")
    print("    2. keep it — a RECORD is a measurement that happened and cannot go stale.")
    print("    3. reword it — last resort, when the sentence needs the shape but not the figure.")
    for path, ln, num, text in found:
        print(f"   * {path}:{ln}  [{num}]  {text[:88]}")
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="*", help="files to check against HEAD (default: the index)")
    ap.add_argument("--tree", action="store_true", help="every tracked source file, from nothing")
    # A BRANCH's numbers, for CI, where the index is empty and the default mode therefore examines
    # nothing — which reads exactly like a clean run. Still exits 1 on a finding; whether to ACT on
    # that is the workflow's call, and checks.yml makes it a report rather than a gate (#67, #74).
    ap.add_argument("--base", metavar="REF", help="what this BRANCH adds, against REF's merge base")
    ap.add_argument("--root", default=ROOT, help=argparse.SUPPRESS)
    a = ap.parse_args()

    found, notes = [], []
    if a.base:
        mb, files = branch(a.base, a.root)
        if mb is None:
            print(f"  record-lint: {files}")
            return 2
        for p in files:
            f, note = check(p, at(mb, p, a.root), at("HEAD", p, a.root))
            found += f
            if note:
                notes.append(note)
    elif a.tree:
        r = subprocess.run(["git", "ls-files"], cwd=a.root, capture_output=True, text=True)
        for p in [x for x in r.stdout.split() if selects(x)]:
            f, note = check(p, "", open(os.path.join(a.root, p), errors="ignore").read())
            found += f
            if note:
                notes.append(note)
    else:
        for p in a.files or staged(a.root):
            new = open(os.path.join(a.root, p), errors="ignore").read() if a.files \
                else at("", p, a.root)
            f, note = check(p, at("HEAD", p, a.root), new)
            found += f
            if note:
                notes.append(note)
    return report(found, notes)


if __name__ == "__main__":
    sys.exit(main())
