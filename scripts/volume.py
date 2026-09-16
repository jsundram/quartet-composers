#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""How much of this repo is prose, and is this change adding more of it?

    python3 scripts/volume.py            # the table
    python3 scripts/volume.py --check    # nonzero if this CHANGE is over — what the hook runs
    python3 scripts/volume.py --json     # the same numbers, for a script

WARN-ONLY IN THE HOOK. The classifying is exact but the judgement is not — a run of commented-out
debugging reads the same as an essay — so going over is a prompt to cut something, never a refusal.
CI does not run it, for the reason record-lint.py is not there either.

WHY IT EXISTS. The rule is that a number the repo recomputes is read off the thing that holds it,
and until this file there was nothing holding these. So every measurement was written fresh and
they disagreed: one pass reported `scripts/` at 83% prose because it took codehash's Python answer
as line-oriented, and `py_code()` returns a single-line AST dump. The real figure was 35%. Nothing
caught it except the number looking absurd.

The disagreement is never in the counting. It is in four judgements an ad-hoc script re-decides
every time: vendored against ours, test against source, docstring against comment, and whether data
and design records count at all. They are answered once here and pinned by volume.test.py.

WHAT IT BOUNDS. A ratio only means something where the numerator and the denominator move
together, so this bounds prose against the code it explains and says nothing about the length of
CLAUDE.md: measured over this repo's history the two are uncorrelated, the app source holding flat
while CLAUDE.md grew by a third. A doc-to-code ratio would license the briefing to grow on any
commit that adds code. CLAUDE.md's ceiling is attention, and it is stated there.

THE PROSE COMES FROM codehash, NOT A SECOND SCANNER, for the reason record-lint.py does it: a
file's prose is its source minus its code, and the one place that question is settled is the file
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

# THE CEILINGS. Set above what a codebase with no such history would want — every invariant here
# was bought with an incident and the rule that came out of it is worth the lines — and well under
# where this repo sat when they were written.
CEILING = {"source": 0.20, "test": 0.20}

# A file carrying the upstream stamp is pwa-starter's, and its prose is not ours to cut: editing it
# breaks the sync check-downstream.py does on the sha. Counted and shown, never held to a ceiling.
# It must OPEN a comment line, over the whole file. A byte window is too narrow for sw.js and a
# wider one exempts this tool's own suite, which QUOTES a stamp in a fixture; the marker tells them
# apart, because a real stamp opens its line and a quoted one sits inside a string.
STAMP = re.compile(r"^\s*(?://|#)\s*pwa-starter: [\w.-]+ @ [0-9a-f]{7}", re.M)

# None of these is prose anyone writes: data/ and the shipped json are the project, mocks/ is a
# record of a decision nothing follows, assets/ is generated.
SKIP = ("data/", "mocks/", "assets/")
CODE = (".py", ".js", ".mjs", ".css", ".html", ".sh", ".yml", ".yaml")
# A git hook is a shell script with no extension, so the extension test alone dropped every one of
# them — including .githooks/pre-commit, which this very tool is wired into.
CONFIG = (".github/", ".githooks/")


def bucket(path, src):
    """Which ceiling this file answers to, or None to leave it out of the ratios entirely."""
    if path.startswith(SKIP):
        return None
    if not path.endswith(CODE) and not path.startswith(CONFIG):
        return None
    if STAMP.search(src):
        return "vendored"
    if path.startswith(CONFIG) or path.endswith((".yml", ".yaml")):
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
            # ONLY A WHOLE-LINE COMMENT. `x = 1  # note` is a line of code that also explains
            # itself; charging it to prose deletes the code line, and disagrees with text_split
            # about the identical construct in JS.
            if tok.type == tokenize.COMMENT and not src.split("\n")[tok.start[0] - 1][:tok.start[1]].strip():
                com.add(tok.start[0])
    except (tokenize.TokenError, IndentationError):
        return None
    lines = src.split("\n")
    # A blank line inside a docstring is blank, like every other. Otherwise a spaced-out module
    # header reads as denser prose than a packed one saying the same thing.
    doc = {i for i in doc if lines[i - 1].strip()}
    code = sum(1 for i, l in enumerate(lines, 1)
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
            # `let x; /* why` opens a block the next lines belong to, and styles.css is one wrap
            # away from it in about ten places.
            if block[0] in s and block[1] not in s.split(block[0], 1)[1]:
                inside = True
    return code, com, 0


def split(path, src):
    """(code, comment, docstring), or None where the file cannot be told apart."""
    if path.endswith(".py"):
        return py_split(src)
    if path.endswith((".js", ".mjs", ".css")):
        # codehash is the authority on WHETHER this parses — it re-parses both sides. Asking it
        # first means an unterminated block comment is reported rather than counted by a line
        # reader that would not notice.
        code, _, _ = codehash.code_of(path, src)
        if code is None:
            return None
        return text_split(src, ("//", "*"))
    if path.endswith((".sh", ".yml", ".yaml")):
        return text_split(src, ("#",), ("\x00", "\x00"))
    if path.endswith(".html"):
        return text_split(src, ("<!--",), ("<!--", "-->"))
    # A git hook has no extension for the dispatch above to read, and says what it is on its first
    # line instead. That is a fact in the file, not a guess from its path.
    shebang = src.split("\n", 1)[0]
    if shebang.startswith("#!"):
        if "python" in shebang:
            return py_split(src)
        if any(sh in shebang for sh in ("sh", "zsh")):
            return text_split(src, ("#",), ("\x00", "\x00"))
    return None


def at(ref, root=ROOT):
    """measure() against a git ref, or None where the ref cannot be read (a first commit)."""
    ls = subprocess.run(["git", "ls-tree", "-r", "-z", "--name-only", ref],
                        cwd=root, capture_output=True, text=True)
    if ls.returncode:
        return None
    out = {}
    for path in ls.stdout.split("\0"):
        # Filtered BEFORE the blob is read: a tree holds the PNGs and the shipped json too, and
        # that is a subprocess and a pipe apiece for an answer bucket() discards.
        if not path or path.startswith(SKIP) \
                or (not path.endswith(CODE) and not path.startswith(CONFIG)):
            continue
        blob = subprocess.run(["git", "show", "%s:%s" % (ref, path)],
                              cwd=root, capture_output=True, text=True, errors="ignore")
        if blob.returncode:
            continue
        b = bucket(path, blob.stdout)
        if b is None:
            continue
        got = split(path, blob.stdout)
        if got is None:
            continue
        acc = out.setdefault(b, {"code": 0, "comment": 0, "docstring": 0})
        acc["code"] += got[0]
        acc["comment"] += got[1]
        acc["docstring"] += got[2]
    return out


def measure(root=ROOT):
    """({bucket: {code, comment, docstring}}, [paths it could not read])."""
    out, unread = {}, []
    listing = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True)
    if listing.returncode:
        # Empty buckets are a clean --check, so a failed listing must raise rather than read as
        # a repo with no prose in it.
        raise RuntimeError("git ls-files failed in %s: %s" % (root, listing.stderr.strip()))
    for path in listing.stdout.split("\0"):
        if not path:
            continue
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


# Below this the marginal ratio is arithmetic on a handful of lines: two comment lines over one of
# code is 67% prose and means nothing by it, and a one-line fix to a comment is 100%.
FLOOR = 20


def delta(before, after):
    """What this change ADDED, or None where it added too little prose to have a ratio."""
    before = before or {"code": 0, "comment": 0, "docstring": 0}
    d = {k: max(0, after[k] - before[k]) for k in after}
    return d if d["comment"] + d["docstring"] >= FLOOR else None


def ratio(acc):
    prose = acc["comment"] + acc["docstring"]
    total = prose + acc["code"]
    return prose / total if total else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if this change is over a ceiling")
    ap.add_argument("--json", action="store_true", help="the numbers, for a script")
    a = ap.parse_args()

    buckets, unread = measure()
    # --check JUDGES THE CHANGE, NOT THE TOTAL. Both ceilinged buckets are well over today, so a
    # check against the total would be red on every commit — and unanswerable besides: nothing a
    # reader can do to the file in front of them clears a ratio the whole repo owns. The commit's
    # own ratio against the same ceiling is answerable, converges from wherever history sits, and
    # says nothing to a change whose comments are proportionate to its code.
    # `or {}`: at() answers None where there is no HEAD to read, which is a repo one commit old
    # and not a repo that held nothing.
    was = (at("HEAD") or {}) if a.check else {}
    over, rows = [], []
    print("  %-10s %7s %8s %8s %8s" % ("", "code", "comment", "docstr", "prose"))
    for name in sorted(buckets):
        acc = buckets[name]
        cap = CEILING.get(name)
        flag = "  <-- over %.0f%%" % (cap * 100) if cap is not None and ratio(acc) > cap else ""
        if a.check and cap is not None:
            d = delta(was.get(name), acc)
            if d and ratio(d) > cap:
                # Appended: the total being over is the standing state, the change being over is
                # what the reader can act on.
                flag += "%s this change is %.0f%% prose, over %.0f%%" % (
                    ";" if flag else "  <--", ratio(d) * 100, cap * 100)
                over.append(name)
                rows.append(dict(acc, bucket=name, change=d))
        print("  %-10s %7d %8d %8d %6.1f%%%s"
              % (name, acc["code"], acc["comment"], acc["docstring"], ratio(acc) * 100, flag))
    for path in unread:
        print("  could not tell code from prose: %s" % path)
    if a.json:
        print(json.dumps({"buckets": buckets, "ceiling": CEILING, "unread": unread,
                          "over": rows}, indent=2))
    if over:
        print("\n  This change adds prose faster than %s will hold." % ", ".join(over))
        print("  Cut it, or move it where it keeps better — a rule belongs here, an incident")
        print("  belongs in the commit. Raising a ceiling is an argument to make, not a fix.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
