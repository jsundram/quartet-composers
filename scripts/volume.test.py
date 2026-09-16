#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Prove volume.py classifies before it counts, and reports what it cannot read.

    python3 scripts/volume.test.py

NO NETWORK, NO REPO: every case is a string or a temp tree, so this runs anywhere.

WHY THIS FILE EXISTS. The counting is arithmetic and nobody gets it wrong. The CLASSIFYING is four
judgements, and an ad-hoc measurement re-decides all of them every time it is written — which is
how this repo came to report `scripts/` at 83% prose when it was 35%. Those four are what the cases
below pin: vendored against ours, test against source, what is excluded outright, and comment
against docstring.

The fifth is the one with teeth. A file whose code cannot be told from its prose must be REPORTED,
never skipped, because a bucket that silently omits what it could not read is a ratio that gets
better by failing — and it gets better precisely on the files something is wrong with.
"""
import importlib.util
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("volume", os.path.join(HERE, "volume.py"))
vol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vol)

CASES, FAILED = [], []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def tree(files):
    """A throwaway git repo holding `files`, so measure() sees it through git ls-files."""
    d = tempfile.mkdtemp()
    for path, body in files.items():
        full = os.path.join(d, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, "w").write(body)
    q = dict(cwd=d, capture_output=True)
    subprocess.run(["git", "init", "-q"], **q)
    subprocess.run(["git", "add", "-A"], **q)
    return d


STAMPED = "// pwa-starter: app.js @ 1a2b3c4\nconst x = 1;\n// a comment\n"


# ---- the four judgements ----------------------------------------------------------------------

@case("a stamped file is vendored, wherever it sits")
def vendored_by_stamp(_):
    # By the STAMP and not by a path list: a hardcoded list is a second copy of a fact the file
    # already carries, and it goes stale the moment a vendored file is added or renamed.
    assert vol.bucket("app.js", STAMPED) == "vendored"
    assert vol.bucket("scripts/deep/nested.py", "# pwa-starter: x.py @ abc1234\n") == "vendored"
    assert vol.bucket("app.js", "const x = 1;\n") == "source", "unstamped is ours"


@case("a suite is test, and the runner it launches is source")
def test_vs_source(_):
    # ui-test.sh derives its own ports and refuses one it did not take, which is logic; ablate.py
    # already settled that it is SOURCE, and this must not answer differently.
    assert vol.bucket("scripts/validate.test.py", "x = 1\n") == "test"
    assert vol.bucket("scripts/ui.test.mjs", "let x;\n") == "test"
    assert vol.bucket("scripts/ui-test.sh", "echo hi\n") == "source"
    assert vol.bucket("scripts/validate.py", "x = 1\n") == "source"


@case("data, mocks and assets are not prose anyone writes")
def excluded(_):
    for p in ("data/pageviews.json", "mocks/gen.py", "assets/og.svg", "composers.json"):
        assert vol.bucket(p, "x") is None, p


@case("a python docstring and a python comment are counted apart")
def docstring_vs_comment(_):
    src = '"""Module.\n\nTwo lines.\n"""\n# a comment\nx = 1\n'
    assert vol.split("a.py", src) == (1, 1, 4), vol.split("a.py", src)


# ---- and it never improves a ratio by failing --------------------------------------------------

@case("a file whose code cannot be told from its prose is REPORTED, not skipped")
def unreadable_is_reported(_):
    # codehash answers None for JS that does not parse. Counting it as pure code would flatter the
    # ratio; skipping it silently would too, and neither says anything went wrong.
    assert vol.split("a.js", "function ( {\n") is None
    assert vol.split("a.py", "def f(:\n") is None
    d = tree({"broken.js": "function ( {\n", "ok.py": "x = 1\n"})
    buckets, unread = vol.measure(d)
    assert unread == ["broken.js"], unread
    assert buckets["source"]["code"] == 1, buckets


# ---- the arithmetic, and the exit code ---------------------------------------------------------

@case("the ratio is prose over the whole file, not over code")
def ratio_math(_):
    # prose/(prose+code), so it is bounded at 1 and reads as "how much of this file is prose".
    assert vol.ratio({"code": 80, "comment": 15, "docstring": 5}) == 0.2
    assert vol.ratio({"code": 0, "comment": 0, "docstring": 0}) == 0.0, "an empty bucket is not 1"


@case("--check goes nonzero only when a bucket with a ceiling is over it")
def check_exit(_):
    lean = "x = 1\n" * 90 + "# c\n" * 10
    d = tree({"scripts/a.py": lean})
    buckets, _ = vol.measure(d)
    assert vol.ratio(buckets["source"]) <= vol.CEILING["source"], vol.ratio(buckets["source"])
    fat = tree({"scripts/a.py": "x = 1\n" * 10 + "# c\n" * 90})
    b2, _ = vol.measure(fat)
    assert vol.ratio(b2["source"]) > vol.CEILING["source"]


@case("a vendored file has no ceiling, however much prose it carries")
def vendored_has_no_ceiling(_):
    # Its prose is upstream's and editing it breaks the sha check-downstream.py syncs on, so a
    # ceiling there would be a standing failure nobody here is allowed to fix.
    assert "vendored" not in vol.CEILING
    d = tree({"app.js": "// pwa-starter: app.js @ 1a2b3c4\n" + "// prose\n" * 90 + "let x;\n"})
    buckets, _ = vol.measure(d)
    # Asserted before it is indexed: without the stamp rule that file lands in `source`, and a
    # KeyError here would report as a crash rather than as the classification being wrong —
    # ablate.py calls that INCONCLUSIVE, which proves nothing either way.
    assert "vendored" in buckets, "a stamped file was not classified vendored: %s" % list(buckets)
    assert vol.ratio(buckets["vendored"]) > 0.9
    over = [n for n in buckets if n in vol.CEILING and vol.ratio(buckets[n]) > vol.CEILING[n]]
    assert over == [], over


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
