#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""How much of this repo is prose, and is any bucket over its ceiling?

    python3 scripts/volume.py            # the table
    python3 scripts/volume.py --check    # nonzero if a bucket is over — what the hook runs
    python3 scripts/volume.py --json     # the same numbers, for a script

WARN-ONLY IN THE HOOK. Going over is a prompt to cut something, not a reason to refuse a commit,
and a ratio crosses its line on the commit that adds a function as readily as on the one that adds
a paragraph. CI does not run it at all: a branch that lands a large feature with proportionate
comments would be blocked for being large.

WHY IT EXISTS. The rule is that a number the repo recomputes is read off the thing that holds it,
and until this file there was nothing holding these. So every measurement was written fresh, and
they disagreed: one pass through this repo reported `scripts/` at 83% prose because it took
codehash's Python answer as line-oriented, and `py_code()` returns a single-line AST dump. The real
figure was 35%. Nothing caught it except the number looking absurd.

The disagreement is not in the counting, it is in the CLASSIFYING, and there are four judgements
that an ad-hoc script re-decides every time: vendored against ours, test against source, docstring
against comment, and whether data and design records count at all. They are answered once here.

WHAT IT MEASURES, AND WHAT IT DOES NOT. A ratio only means something where the numerator and the
denominator move together, so this bounds prose against the code it explains and says nothing about
the length of CLAUDE.md. Measured over this repo's history the two are uncorrelated: the app source
held flat while CLAUDE.md grew by a third. A doc-to-code ratio would license the briefing to grow on
any commit that adds code, when what actually grows it is review rounds appending incidents. CLAUDE.md's ceiling is attention — it is read in full before a
session's first change — so it is stated there as a readability test and not as a number here.

THE PROSE COMES FROM codehash, NOT FROM A SECOND SCANNER, for the reason record-lint.py does it:
a file's prose is its source minus its code, and the one place that question is settled is the file
verified by re-parsing. A file codehash cannot classify is REPORTED rather than counted, because a
bucket that quietly omits what it could not read is a ratio that improves by failing.
"""
import argparse
import ast
import io
import json
import os
import re
import subprocess
import sys
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import codehash                                                    # noqa: E402

# THE CEILINGS, and the only numbers in this file. Prose earns its place here — every invariant was
# bought with an incident and the rule that came out of it is worth the lines — so these are set
# above what a codebase with no such history would want, and still well under where this repo sat
# when they were written. A bucket over its ceiling is a prompt to cut, not a verdict.
CEILING = {"source": 0.20, "test": 0.20}

# A file carrying the upstream stamp is pwa-starter's, and its prose is not ours to cut: editing it
# breaks the sync check-downstream.py does on the sha. Counted and shown, never held to a ceiling.
STAMP = re.compile(r"pwa-starter: [\w.-]+ @ [0-9a-f]{7}")

# Measured, not read. data/ and the shipped json are the point of the project; mocks/ is a record of
# a decision that nothing follows (see CLAUDE.md's Design artifacts); assets/ is generated. None of
# them is prose anyone writes, so none belongs in a prose ratio.
SKIP = ("data/", "mocks/", "assets/")
CODE = (".py", ".js", ".mjs", ".css", ".html", ".sh", ".yml", ".yaml")


def bucket(path, src):
    """Which ceiling this file answers to, or None to leave it out of the ratios entirely."""
    if path.startswith(SKIP) or not path.endswith(CODE):
        return None
    if STAMP.search(src[:2000]):
        return "vendored"
    if path.startswith((".github/", ".githooks/")) or path.endswith((".yml", ".yaml")):
        return "config"
    # ui-test.sh is SOURCE to the gates (it derives its own ports and refuses one it did not take),
    # so it is source here too — ablate.py already settled that argument and this must not reopen it.
    if ".test." in path:
        return "test"
    return "source"


def py_split(src):
    """(code, comment, docstring) line counts. The AST answers both prose kinds exactly."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    doc = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) \
                    and isinstance(getattr(body[0].value, "value", None), str):
                doc.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
    com = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                com.add(tok.start[0])
    except (tokenize.TokenError, IndentationError):
        return None
    code = sum(1 for i, l in enumerate(src.split("\n"), 1)
               if l.strip() and i not in doc and i not in com)
    return code, len(com), len(doc)


def text_split(src, marks, block=("/*", "*/")):
    """(code, comment, 0) for a language codehash strips but does not count per line."""
    code = com = 0
    inside = False
    for line in src.split("\n"):
        s = line.strip()
        if not s:
            continue
        if inside:
            com += 1
            inside = block[1] not in s
        elif s.startswith(block[0]):
            com += 1
            inside = block[1] not in s
        elif any(s.startswith(m) for m in marks):
            com += 1
        else:
            code += 1
    return code, com, 0


def split(path, src):
    """(code, comment, docstring), or None where the file cannot be told apart."""
    if path.endswith(".py"):
        return py_split(src)
    if path.endswith((".js", ".mjs", ".css")):
        # codehash's scanner is the authority on WHETHER this parses; it re-parses both sides and
        # answers None when it cannot tell. Asking it first means a file with an unterminated block
        # comment is reported rather than counted under a line reader that would not notice.
        code, _, _ = codehash.code_of(path, src)
        if code is None:
            return None
        return text_split(src, ("//", "*"))
    if path.endswith((".sh", ".yml", ".yaml")):
        return text_split(src, ("#",), ("\x00", "\x00"))
    if path.endswith(".html"):
        return text_split(src, ("<!--",), ("<!--", "-->"))
    return None


def measure(root=ROOT):
    """({bucket: {code, comment, docstring}}, [paths it could not read])."""
    out, unread = {}, []
    listing = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True)
    for path in listing.stdout.split():
        full = os.path.join(root, path)
        if not os.path.isfile(full):
            continue
        try:
            src = open(full, errors="ignore").read()
        except OSError:
            continue
        b = bucket(path, src)
        if b is None:
            continue
        got = split(path, src)
        if got is None:
            unread.append(path)
            continue
        acc = out.setdefault(b, {"code": 0, "comment": 0, "docstring": 0})
        acc["code"] += got[0]
        acc["comment"] += got[1]
        acc["docstring"] += got[2]
    return out, unread


def ratio(acc):
    prose = acc["comment"] + acc["docstring"]
    total = prose + acc["code"]
    return prose / total if total else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if a bucket is over its ceiling")
    ap.add_argument("--json", action="store_true", help="the numbers, for a script")
    a = ap.parse_args()

    buckets, unread = measure()
    if a.json:
        print(json.dumps({"buckets": buckets, "ceiling": CEILING, "unread": unread}, indent=2))
        return 0

    over = []
    print("  %-10s %7s %8s %8s %8s" % ("", "code", "comment", "docstr", "prose"))
    for name in sorted(buckets):
        acc = buckets[name]
        r = ratio(acc)
        cap = CEILING.get(name)
        flag = ""
        if cap is not None and r > cap:
            flag = "  <-- over %.0f%%" % (cap * 100)
            over.append((name, r, cap))
        print("  %-10s %7d %8d %8d %7.0f%%%s"
              % (name, acc["code"], acc["comment"], acc["docstring"], r * 100, flag))
    for path in unread:
        print("  could not tell code from prose: %s" % path)
    if a.check and over:
        print("\n  Over the ceiling. Cut prose, or move it where it keeps better — CLAUDE.md's")
        print("  `Where a thing goes` says which. Raising a ceiling here is an argument to make,")
        print("  not a fix to apply.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
