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

WHAT YOU INHERIT IS REPORTED; WHAT YOU WRITE IS CHECKED. Every bucket's standing ratio is printed
without a verdict, because it is history rather than this commit's doing, and every bucket's DIFF
answers to the one ceiling. That is also why no bucket is exempt: grandfathering is free once the
check is marginal, so a file nobody has touched never fires however much prose it carries.

WHAT IT BOUNDS. A ratio only means something where the numerator and the denominator move
together, so this bounds prose against the code it explains and says nothing about the length of
CLAUDE.md: measured over this repo's history the two are uncorrelated, the app source holding flat
while CLAUDE.md grew by a third. A doc-to-code ratio would license the briefing to grow on any
commit that adds code. CLAUDE.md's ceiling is attention, and it is stated there.

The deltas are per BUCKET, so a rename across one reports as that file's own ratio — known, and
cheaper than per-file identity across a commit.

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
# ONE CEILING, AND EVERY BUCKET'S DIFF ANSWERS TO IT. What you inherit is history and is reported
# as it stands; what you write is yours. Exempting a bucket was the mistake: `vendored` was let off
# on the reasoning that its prose is upstream's and not ours to cut — but that is only true of a
# file nobody here has touched, and the stamp cannot say which those are (see STAMP). app.js says
# "the render/data half is this app's own" and styles.css says "app layout is this repo's own", so
# the largest module in the app sat in a bucket with no ceiling at all. Since --check judges the
# CHANGE, grandfathering is free: an untouched file never fires however much prose it carries, and
# editing one means this diff obeys the same 20% as any other.
CEILING = 0.20

# A file carrying the upstream stamp DESCENDS from pwa-starter — which is not the same as being
# upstream's, and reading it as ownership is what exempted app.js. What it is for is the sync
# check-downstream.py does on the sha; the bucket is a reporting label, nothing more.
# It must OPEN a comment line, over the whole file. A byte window is too narrow for sw.js and a
# wider one exempts this tool's own suite, which QUOTES a stamp in a fixture; the marker tells them
# apart, because a real stamp opens its line and a quoted one sits inside a string. `/*` is in the
# markers because styles.css carries the same stamp in CSS syntax, and dropping it filed one
# convention under two answers.
STAMP = re.compile(r"^\s*(?://|#|/\*)\s*pwa-starter: [\w.-]+ @ [0-9a-f]{7}", re.M)

# None of these is prose anyone writes: data/ and the shipped json are the project, mocks/ is a
# record of a decision nothing follows, assets/ is generated.
SKIP = ("data/", "mocks/", "assets/")
# d3.v7.min.js is a library we did not write and cannot read: filed as `source` it was a quarter of
# a megabyte of somebody else's code counted as ours.
SKIP_SUFFIX = (".min.js", ".min.css")
CODE = (".py", ".js", ".mjs", ".css", ".html", ".sh", ".yml", ".yaml")
# A git hook is a shell script with no extension, so the extension test alone dropped every one of
# them — including .githooks/pre-commit, which this very tool is wired into.
CONFIG = (".github/", ".githooks/")


def selects(path):
    """Is this file in the ratios at all? Answerable from the PATH, so it runs before any read.

    Both readers ask it first. measure() used to read every tracked blob and let bucket() throw
    the answer away — megabytes of shipped json, and under --check a `git show` apiece — while at()
    carried its own copy of the test and had already drifted off SKIP_SUFFIX.
    """
    if path.startswith(SKIP) or path.endswith(SKIP_SUFFIX):
        return False
    return path.endswith(CODE) or path.startswith(CONFIG)


def bucket(path, src):
    """Which bucket this file is reported under, or None to leave it out of the ratios entirely."""
    if not selects(path):
        return None
    # ROLE BEFORE ORIGIN. sw.test.mjs carries the stamp and is a suite; filed as `vendored` it left
    # the test bucket short and put a suite in with the app shell. Now that no bucket is exempt,
    # origin only chooses between the two remaining kinds.
    # ui-test.sh is SOURCE to the gates (it derives its own ports and refuses one it did not take),
    # so it is source here too — ablate.py already settled that argument and this must not reopen it.
    if ".test." in path:
        return "test"
    if path.startswith(CONFIG) or path.endswith((".yml", ".yaml")):
        return "config"
    return "vendored" if STAMP.search(src) else "source"


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


def nonblank(text):
    return sum(1 for line in text.split("\n") if line.strip())


def text_split(src, marks, block=("/*", "*/")):
    """(code, comment, 0) for a language codehash does not read at all — shell, yaml, html."""
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
            # `<div> <!-- why` opens a block the next lines belong to. Live for HTML only now
            # that JS and CSS are counted off codehash's strip.
            if block[0] in s and block[1] not in s.split(block[0], 1)[1]:
                inside = True
    return code, com, 0


def split(path, src):
    """(code, comment, docstring), or None where the file cannot be told apart."""
    if path.endswith(".py"):
        return py_split(src)
    if path.endswith((".js", ".mjs", ".css")):
        # COUNTED OFF codehash's STRIPPED TEXT, which is what "prose is source minus code" means
        # and what this file claimed to be doing while a line reader did the counting. That reader
        # had no idea what a string was, so one `const SEP = "/* not a comment";` opened a block
        # comment running to EOF and collapsed chart.js's whole body into it. codehash's scanner
        # knows strings, template literals and regex literals, and re-parses to prove it — which is
        # also why HOW it verified is part of the answer: without node nothing is re-parsed, `code`
        # comes back non-None for a file nothing checked, and cannot-tell degrades to a false pass.
        # The lines do not align, a whole-line comment taking its newline with it, so they are
        # counted rather than zipped; JS has no docstrings to separate out.
        code, _, how = codehash.code_of(path, src)
        if code is None or how.startswith("UNVERIFIED"):
            return None
        return nonblank(code), nonblank(src) - nonblank(code), 0
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


def by_bucket(unread):
    """{bucket: {path}} — compared per FILE, because two files swapping readability inside one
    bucket cancel out over bucket names and the delta is then taken over mismatched sets."""
    out = {}
    for b, path in unread:
        out.setdefault(b, set()).add(path)
    return out


def in_merge(root=ROOT):
    """Is a merge in progress? Its HEAD is the first parent, so a delta against it is the branch."""
    got = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=root, capture_output=True, text=True)
    return not got.returncode and os.path.exists(
        os.path.join(root, got.stdout.strip(), "MERGE_HEAD"))


def sh_show(root, spec):
    """`git show <spec>` as text, or None where it cannot be read."""
    got = subprocess.run(["git", "show", spec], cwd=root, capture_output=True,
                         text=True, errors="ignore")
    return None if got.returncode else got.stdout


def at(ref, root=ROOT):
    """measure() against a git ref, or None where the ref does not resolve (a first commit)."""
    # ASKED SEPARATELY: a ref that does not resolve is a repo one commit old, and a ref that
    # resolves and then fails to list is broken. `or {}` in main() reads None as a base holding
    # nothing, which would report the whole repo as this one commit's work.
    if subprocess.run(["git", "rev-parse", "--verify", "-q", ref + "^{commit}"],
                      cwd=root, capture_output=True).returncode:
        return None
    ls = subprocess.run(["git", "ls-tree", "-r", "-z", "--name-only", ref],
                        cwd=root, capture_output=True, text=True)
    if ls.returncode:
        raise RuntimeError("git ls-tree %s failed in %s: %s" % (ref, root, ls.stderr.strip()))
    out, unread = {}, []
    for path in ls.stdout.split("\0"):
        if not path or not selects(path):
            continue
        src = sh_show(root, "%s:%s" % (ref, path))
        if src is None:
            continue
        b = bucket(path, src)
        if b is None:
            continue
        got = split(path, src)
        if got is None:
            unread.append((b, path))
            continue
        acc = out.setdefault(b, {"code": 0, "comment": 0, "docstring": 0})
        acc["code"] += got[0]
        acc["comment"] += got[1]
        acc["docstring"] += got[2]
    return out, unread


def measure(root=ROOT, staged=False):
    """({bucket: {code, comment, docstring}}, [paths it could not read]).

    `staged` reads the INDEX rather than disk, which is what --check wants: the hook judges what
    is about to be committed, and under `git add -p` that is not what is on disk. The bare table
    reads the working tree, where the question is what you are looking at.
    """
    out, unread = {}, []
    read = (lambda path, full: sh_show(root, ":" + path)) if staged else \
        (lambda path, full: open(full, errors="ignore").read())
    listing = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True)
    if listing.returncode:
        # Empty buckets are a clean --check, so a failed listing must raise rather than read as
        # a repo with no prose in it.
        raise RuntimeError("git ls-files failed in %s: %s" % (root, listing.stderr.strip()))
    for path in listing.stdout.split("\0"):
        if not path:
            continue
        if not selects(path):
            continue
        full = os.path.join(root, path)
        if not staged and not os.path.isfile(full):
            continue
        try:
            src = read(path, full)
        except OSError:
            continue
        if src is None:          # staged as a deletion, or unreadable as text
            continue
        b = bucket(path, src)
        if b is None:
            continue
        got = split(path, src)
        if got is None:
            unread.append((b, path))
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
    """What this change ADDED, or None where there is no ratio to take.

    SIGNED, and tested on the NET: a bucket is every file at once, so refusing a negative code
    delta bought silence for a whole commit in exchange for one removed import. What has no ratio
    is a change that did not GROW the bucket.
    """
    before = before or {"code": 0, "comment": 0, "docstring": 0}
    d = {k: after[k] - before[k] for k in after}
    if d["comment"] + d["docstring"] < FLOOR or sum(d.values()) <= 0:
        return None
    return d


def ratio(acc):
    prose = acc["comment"] + acc["docstring"]
    total = prose + acc["code"]
    return prose / total if total else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if this change is over a ceiling")
    ap.add_argument("--json", action="store_true", help="the numbers, for a script")
    # Not for the hook, which always means this repo. It is what lets the suite drive the REAL
    # entry point over a throwaway tree: measure() and at() both took a root already, and main()
    # hardcoding ROOT left every decision it makes — which bucket is exempt, what sets the exit
    # code — reachable only by reading it.
    ap.add_argument("--root", default=ROOT, help=argparse.SUPPRESS)
    a = ap.parse_args()

    buckets, unread = measure(a.root, staged=a.check)
    # --check JUDGES THE CHANGE, NOT THE TOTAL. Every bucket is well over today, so a
    # check against the total would be red on every commit — and unanswerable besides: nothing a
    # reader can do to the file in front of them clears a ratio the whole repo owns. The commit's
    # own ratio against the same ceiling is answerable, converges from wherever history sits, and
    # says nothing to a change whose comments are proportionate to its code.
    # `or {}`: at() answers None where there is no HEAD to read, which is a repo one commit old
    # and not a repo that held nothing.
    # A FILE THAT CHANGED READABILITY HAS NO DELTA. at() used to drop what it could not classify
    # while measure() reported it, so the two sides held different file sets — and a one-character
    # syntax fix to a JS file that did not parse at HEAD arrived as its whole length of new prose.
    was, was_unread = (at("HEAD", a.root) or ({}, [])) if a.check else ({}, [])
    if in_merge(a.root):
        # HEAD during a merge is the FIRST PARENT, so the whole incoming branch is charged to the
        # merge commit. sw-lint.py --fix declines in this state for the same reason.
        was, moot = {}, set(buckets)
    else:
        moot = {b for b in set(buckets) | set(was)
                if by_bucket(unread).get(b) != by_bucket(was_unread).get(b)}
    over, rows, lines = [], [], []
    say = lines.append if a.json else print
    say("  %-10s %7s %8s %8s %8s" % ("", "code", "comment", "docstr", "prose"))
    for name in sorted(buckets):
        acc = buckets[name]
        # The total's flag is CONTEXT, not a verdict: it is where the bucket stands, which is
        # history and not this commit's doing. Only the change's flag drives the exit code.
        flag = "  <-- over %.0f%%" % (CEILING * 100) if ratio(acc) > CEILING else ""
        if a.check and name not in moot:
            d = delta(was.get(name), acc)
            # Capped: prose up while code comes down is a ratio over 1, which reads as a bug.
            if d and ratio(d) > CEILING:
                flag += "%s this change is %.0f%% prose, over %.0f%%" % (
                    ";" if flag else "  <--", min(1.0, ratio(d)) * 100, CEILING * 100)
                over.append(name)
                rows.append(dict(acc, bucket=name, change=d))
        say("  %-10s %7d %8d %8d %6.1f%%%s"
            % (name, acc["code"], acc["comment"], acc["docstring"], ratio(acc) * 100, flag))
    for _b, path in unread:
        say("  could not tell code from prose: %s" % path)
    # NOTHING BUT JSON on stdout under --json, or what the docstring calls "for a script" does not
    # parse. The table is kept and handed back under a key, so --json --check loses nothing.
    if a.json:
        print(json.dumps({"buckets": buckets, "ceiling": CEILING, "unread": [p for _b, p in unread],
                          "over": rows, "table": lines}, indent=2))
        return 1 if over else 0
    if over:
        print("\n  This change adds prose faster than %s will hold." % ", ".join(over))
        print("  Cut it, or move it where it keeps better — a rule belongs here, an incident")
        print("  belongs in the commit. Raising a ceiling is an argument to make, not a fix.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
