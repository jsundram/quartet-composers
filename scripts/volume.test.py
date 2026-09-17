#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Prove volume.py classifies before it counts, and reports what it cannot read.

    python3 scripts/volume.test.py

NO NETWORK, NO REPO: every case is a string or a temp tree, so this runs anywhere.

WHY THIS FILE EXISTS. The counting is arithmetic and nobody gets it wrong. The CLASSIFYING is four
judgements an ad-hoc measurement re-decides every time it is written, which is how this repo came
to report `scripts/` at 83% prose when it was 35%. Those four are what the cases pin: vendored
against ours, test against source, what is excluded outright, comment against docstring.

The fifth has the teeth. A file whose code cannot be told from its prose must be REPORTED, never
skipped, because a bucket that omits what it could not read is a ratio that gets better by failing
— and it gets better precisely on the files something is wrong with.

"""
import importlib.util
import json
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


def tree(files, commit=False):
    """A throwaway git repo holding `files`, so measure() sees it through git ls-files."""
    d = tempfile.mkdtemp()
    q = dict(cwd=d, capture_output=True)
    subprocess.run(["git", "init", "-q"], **q)
    write(d, files)
    if commit:
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "base"], **q)
    return d


def write(d, files):
    """Add files to an existing tree. Staged, because measure() reads git ls-files."""
    for path, body in files.items():
        full = os.path.join(d, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, "w").write(body)
    subprocess.run(["git", "add", "-A"], cwd=d, capture_output=True)


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
    # The blank line INSIDE the docstring is blank, like every other blank line the count skips.
    # Charging it to prose made a spaced-out module header read as denser than a packed one saying
    # the same thing, which is the opposite of what this measures.
    assert vol.split("a.py", src) == (1, 1, 3), vol.split("a.py", src)


@case("a trailing comment is a line of CODE that also explains itself")
def trailing_comment(_):
    # Counting it as prose deleted the code line outright, and the two languages then disagreed
    # about the identical construct — Python's answer being the one that flattered the ratio.
    assert vol.split("a.py", "x = 1  # note\n") == (1, 0, 0), vol.split("a.py", "x = 1  # note\n")
    assert vol.split("a.js", "let x; // note\n") == (1, 0, 0), vol.split("a.js", "let x; // note\n")


@case("a block comment OPENED after code on the same line swallows the lines under it")
def block_after_code(_):
    # HTML, because that is the only thing text_split still reads: JS and CSS are counted off
    # codehash's strip now, so a case written against a.js proved nothing about this branch.
    src = "<div> <!-- why\n   because\n   of this -->\n<p>\n"
    assert vol.split("a.html", src) == (2, 2, 0), vol.split("a.html", src)


@case("a stamp must OPEN a comment line, not merely appear in the file")
def stamp_must_open_a_comment(_):
    # This suite QUOTES the stamp, so a substring test exempted the one file whose job is
    # enforcing the ceiling.
    quoted = 'STAMPED = "// pwa-starter: app.js @ 1a2b3c4"\nx = 1\n'
    assert vol.bucket("scripts/volume.test.py", quoted) == "test", vol.bucket("x.py", quoted)
    # And it is read over the WHOLE file rather than a byte window: sw.js carries a long header
    # above its stamp, and it is the largest vendored file here.
    deep = "// header\n" * 400 + "// pwa-starter: sw.js @ 1a2b3c4\nlet x;\n"
    assert vol.bucket("sw.js", deep) == "vendored"


@case("a hook says what it is on its FIRST LINE, having no extension to say it with")
def shebang(_):
    # .githooks/pre-commit has no extension and this tool is wired into it, so the extension
    # dispatch reported the one file it most obviously has to read.
    # The shebang line counts with the comments, as it does in every .sh file here — one line per
    # shell script, and singling it out would be a rule the extension dispatch does not have.
    assert vol.split(".githooks/pre-commit", "#!/bin/sh\n# why\ntrue\n") == (1, 2, 0)
    assert vol.split("hook", '#!/usr/bin/env python3\n"""Doc."""\nx = 1\n') == (1, 1, 1)
    assert vol.split("whatever", "just text\n") is None, "still None with nothing to go on"


# ---- and it never improves a ratio by failing --------------------------------------------------

@case("a file whose code cannot be told from its prose is REPORTED, not skipped")
def unreadable_is_reported(_):
    # codehash answers None for JS that does not parse. Counting it as pure code would flatter the
    # ratio; skipping it silently would too, and neither says anything went wrong.
    assert vol.split("a.js", "function ( {\n") is None
    assert vol.split("a.py", "def f(:\n") is None
    d = tree({"broken.js": "function ( {\n", "ok.py": "x = 1\n"})
    files, unread = vol.measure(d)
    buckets = vol.totals(files)
    assert unread == [("source", "broken.js")], unread
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
    buckets = vol.totals(vol.measure(d)[0])
    assert vol.ratio(buckets["source"]) <= vol.CEILING, vol.ratio(buckets["source"])
    fat = tree({"scripts/a.py": "x = 1\n" * 10 + "# c\n" * 90})
    b2 = vol.totals(vol.measure(fat)[0])
    assert vol.ratio(b2["source"]) > vol.CEILING


@case("--check judges what the CHANGE added, not what history holds")
def check_is_marginal(_):
    # A check against the TOTAL is red on every commit while the repo sits over its ceiling, and
    # unanswerable: nothing a reader can do here clears a ratio the whole repo owns.
    d = tree({"scripts/a.py": "x = 1\n" * 10 + "# c\n" * 90}, commit=True)
    was = vol.totals(vol.at("HEAD", d)[0])
    assert vol.ratio(was["source"]) > vol.CEILING, "the history is fat on purpose"
    write(d, {"scripts/b.py": "y = 1\n" * 100 + "# c\n" * 25})
    now = vol.totals(vol.measure(d)[0])
    assert vol.ratio(now["source"]) > vol.CEILING, "and still is"
    lean = vol.delta(was["source"], now["source"])
    assert lean and vol.ratio(lean) <= vol.CEILING, vol.ratio(lean)
    write(d, {"scripts/b.py": "y = 1\n" * 5 + "# c\n" * 100})
    now = vol.totals(vol.measure(d)[0])
    fat = vol.delta(was["source"], now["source"])
    assert fat and vol.ratio(fat) > vol.CEILING, vol.ratio(fat)


@case("a change that REMOVED code is not a change that added prose")
def delta_is_signed(_):
    # Flooring each key at zero read "deleted a module, added a comment block" as 100% prose, on a
    # commit that shrank the repo and lowered the ratio being complained about.
    acc = {"code": 300, "comment": 10, "docstring": 0}
    assert vol.delta(acc, {"code": 100, "comment": 10 + vol.FLOOR, "docstring": 0}) is None
    # ...and a change that adds prose over NO new code is still the case this exists to catch.
    d = vol.delta(acc, {"code": 300, "comment": 10 + vol.FLOOR, "docstring": 0})
    assert d and vol.ratio(d) == 1.0, d


@case("`*` opens a CSS rule, not a CSS comment")
def css_marks(_):
    # styles.css opens two rules with the universal selector today. `//` is not a CSS comment at
    # all, and a JSDoc continuation line is already owned by the block flag.
    assert vol.split("a.css", "*{ box-sizing:border-box }\n") == (1, 0, 0)
    assert vol.split("a.css", "/* why */\n*, *::before{ margin:0 }\n") == (1, 1, 0)
    assert vol.split("a.js", "/**\n * why\n */\nlet x;\n") == (1, 3, 0), "the block flag owns it"


@case("--json prints JSON and nothing else")
def json_is_parseable(_):
    # The docstring calls it "for a script". The table was printed first, so it did not parse.
    d = tree({"scripts/a.py": "x = 1\n" * 30 + "# c\n" * 20}, commit=True)
    out = subprocess.run([sys.executable, os.path.join(HERE, "volume.py"), "--json", "--check",
                          "--root", d], capture_output=True, text=True)
    got = json.loads(out.stdout)
    assert sorted(got) == ["buckets", "ceiling", "over", "table", "unread"], sorted(got)
    assert got["table"], "the table is handed back, not thrown away"


@case("a change too small to have a ratio is not given one")
def delta_floor(_):
    # Below the floor the marginal ratio is arithmetic on a handful of lines.
    acc = {"code": 100, "comment": 10, "docstring": 0}
    assert vol.delta(acc, {"code": 101, "comment": 13, "docstring": 0}) is None
    assert vol.delta(acc, {"code": 100, "comment": 10 + vol.FLOOR, "docstring": 0}) is not None
    assert vol.delta(acc, {"code": 200, "comment": 0, "docstring": 0}) is None, "deleting is silent"


@case("the NET decides, so one deleted line does not buy a commit silence")
def delta_is_net(_):
    # A bucket is every file at once. Refusing any negative code delta meant removing one import
    # anywhere silenced the whole commit — a bigger hole than the flooring it replaced.
    acc = {"code": 300, "comment": 10, "docstring": 0}
    d = vol.delta(acc, {"code": 299, "comment": 10 + vol.FLOOR + 10, "docstring": 0})
    assert d and vol.ratio(d) > vol.CEILING, d
    # ...but a change that did not GROW the bucket has no growth for prose to be a fraction of.
    assert vol.delta(acc, {"code": 100, "comment": 10 + vol.FLOOR, "docstring": 0}) is None


@case("a ref that cannot be LISTED is not a ref that does not exist")
def at_distinguishes_failure(_):
    # `or {}` in main() reads None as a base holding nothing, which reports the whole repo as this
    # one commit's work. A repo with no HEAD is that; a broken git call is not.
    d = tree({"scripts/a.py": "x = 1\n"})
    assert vol.at("HEAD", d) is None, "nothing committed yet, so there is no base"
    d = tree({"scripts/a.py": "x = 1\n"}, commit=True)
    real = subprocess.run

    def ls_tree_fails(argv, **kw):
        if "ls-tree" in argv:
            return subprocess.CompletedProcess(argv, 128, "", "fatal: not a tree object")
        return real(argv, **kw)

    vol.subprocess.run = ls_tree_fails
    try:
        vol.at("HEAD", d)
    except RuntimeError:
        return
    finally:
        vol.subprocess.run = real
    assert False, "a ref that resolves and then fails to list is not an empty tree"


@case("JS nothing re-parsed is REPORTED, not counted")
def unverified_is_unreadable(_):
    # codehash's imperfection is affordable because a misclassification leaves something that does
    # not parse. Without node on PATH nothing re-parses, so `code` comes back non-None for a file
    # nothing checked and cannot-tell degrades to a false pass.
    real = vol.codehash.code_of

    def unverified(path, src):
        code, n, _how = real(path, src)
        return code, n, "UNVERIFIED (no node)"

    vol.codehash.code_of = unverified
    try:
        assert vol.split("a.js", "let x; // c\n") is None
    finally:
        vol.codehash.code_of = real
    assert vol.split("a.js", "let x; // c\n") == (1, 0, 0), "and verified JS still counts"


@case("a listing that FAILED is not a repo with no prose in it")
def listing_failure_raises(_):
    # Empty buckets are a clean run, so swallowing the return code turns "not a git repo" into a
    # pass and the hook goes quiet everywhere it is misconfigured.
    try:
        vol.measure(tempfile.mkdtemp())
    except RuntimeError:
        return
    assert False, "measure() passed on a directory git cannot list"


@case("at() does not READ a blob it is going to throw away")
def at_filters_before_reading(_):
    # `git show` on a PNG decoded as text raises outright, and every shipped json would be a
    # subprocess and a megabyte through a pipe, for an answer bucket() discards.
    d = tree({"scripts/a.py": "x = 1\n", "mocks/shot.png": "PNG\n",
              "d3.v7.min.js": "var d3=1;\n", "composers.json": "[]\n"}, commit=True)
    real, read = subprocess.run, []

    def spy(argv, **kw):
        if argv[:2] == ["git", "show"]:
            read.append(argv[2])
        return real(argv, **kw)

    vol.subprocess.run = spy
    try:
        got = vol.totals(vol.at("HEAD", d)[0])
    finally:
        vol.subprocess.run = real
    assert read == ["HEAD:scripts/a.py"], read
    assert got["source"]["code"] == 1, got
    assert vol.at("nosuchref", d) is None, "a ref that cannot be read is not an empty repo"


@case("a vendored file's STANDING prose is grandfathered; its diff is not")
def vendored_is_grandfathered(_):
    # The stamp marks DESCENT from pwa-starter, not ownership: app.js says "the render/data half is
    # this app's own". Read as ownership it exempted the largest module in the app from any
    # ceiling. Since --check judges the change, no exemption is needed — an untouched file never
    # fires however much prose it carries, and a diff to one obeys what every other diff does.
    fat = "// pwa-starter: app.js @ 1a2b3c4\n" + "// prose\n" * 90 + "let x;\n"
    d = tree({"app.js": fat}, commit=True)
    was = vol.totals(vol.at("HEAD", d)[0])
    # Asserted before it is indexed: without the stamp rule that file lands in `source`, and a
    # KeyError here would report as a crash rather than as the classification being wrong —
    # ablate.py calls that INCONCLUSIVE, which proves nothing either way.
    assert "vendored" in was, "a stamped file was not classified vendored: %s" % list(was)
    assert vol.ratio(was["vendored"]) > 0.9, "and it is far over the ceiling standing still"
    buckets = vol.totals(vol.measure(d)[0])
    assert vol.delta(was["vendored"], buckets["vendored"]) is None, "untouched, so it says nothing"
    write(d, {"app.js": fat + "// prose\n" * vol.FLOOR})
    now = vol.totals(vol.measure(d)[0])
    edited = vol.delta(was["vendored"], now["vendored"])
    assert edited and vol.ratio(edited) > vol.CEILING, edited


@case("--check exempts NO bucket, vendored included")
def check_exempts_nothing(_):
    # Through the real entry point, because which buckets main() puts on the exit code is a
    # decision no assertion against delta() can reach.
    fat = "// pwa-starter: app.js @ 1a2b3c4\nlet x;\n"
    d = tree({"app.js": fat}, commit=True)
    write(d, {"app.js": fat + "// prose\n" * (vol.FLOOR + 5)})
    out = subprocess.run([sys.executable, os.path.join(HERE, "volume.py"), "--check",
                          "--root", d], capture_output=True, text=True)
    assert out.returncode == 1, out.stdout
    row = next(l for l in out.stdout.splitlines() if l.strip().startswith("vendored"))
    assert "this change is" in row, row


@case("measure() does not READ a blob it is going to throw away")
def measure_filters_before_reading(_):
    # It read every tracked blob and let bucket() discard the answer — megabytes of it, and
    # under --check (the hook path) that is a `git show` apiece on every commit.
    d = tree({"scripts/a.py": "x = 1\n", "composers.json": "[]\n",
              "d3.v7.min.js": "var d3=1;\n"}, commit=True)
    real, read = vol.sh_show, []
    vol.sh_show = lambda root, spec: read.append(spec) or real(root, spec)
    try:
        vol.measure(d, staged=True)
    finally:
        vol.sh_show = real
    assert read == [":scripts/a.py"], read


@case("--check judges what is STAGED, not what is on disk")
def check_reads_the_index(_):
    # The hook is judging what is about to be committed. Under `git add -p` that is not what is on
    # disk, and record-lint.py reads the index for the same reason.
    d = tree({"scripts/a.py": "x = 1\n" * 40}, commit=True)
    open(os.path.join(d, "scripts/a.py"), "a").write("# c\n" * 40)   # written, NOT staged
    run = lambda *a: subprocess.run([sys.executable, os.path.join(HERE, "volume.py"), "--root", d]
                                    + list(a), capture_output=True, text=True)
    assert run("--check").returncode == 0, "unstaged prose is not this commit's"
    assert "50.0%" in run().stdout, "...but the bare table does show the working tree"
    subprocess.run(["git", "add", "-A"], cwd=d, capture_output=True)
    assert run("--check").returncode == 1, "and staging it makes it this commit's"


@case("a STRING holding `/*` does not turn the rest of the file into prose")
def strings_are_not_comments(_):
    # The counting was a line reader that had no idea what a string was, while the docstring said
    # the prose came from codehash. One such line in chart.js swallowed the whole file.
    trap = 'const SEP = "/* not a comment";\nlet a = 1;\nlet b = 2;\n// real\n'
    assert vol.split("a.js", trap) == (3, 1, 0), vol.split("a.js", trap)
    css = '.x{ content:"/*" }\n.y{ margin:0 }\n/* real */\n'
    assert vol.split("a.css", css) == (2, 1, 0), vol.split("a.css", css)


@case("a minified library is not our code, and a suite is not the app shell")
def role_before_origin(_):
    # d3.v7.min.js is a quarter of a megabyte we did not write; filed as `source` it was counted
    # as ours. sw.test.mjs carries the stamp AND is a suite — filed as `vendored` it left the test
    # bucket short and put a suite in with the app shell.
    assert vol.bucket("d3.v7.min.js", "var d3=...") is None
    assert vol.bucket("scripts/sw.test.mjs", "// pwa-starter: sw.test.mjs @ 1a2b3c4\n") == "test"
    assert vol.bucket("sw.js", "// pwa-starter: sw.js @ 1a2b3c4\n") == "vendored"


@case("a file that changed READABILITY has no delta")
def readability_moot(_):
    # at() dropped what it could not classify while measure() reported it, so the two sides held
    # different file sets — and a one-character syntax fix to a JS file that did not parse at HEAD
    # arrived as its whole length of new prose.
    broken = "function ( {\n" + "// prose\n" * 60
    d = tree({"a.js": broken}, commit=True)
    was, was_unread = vol.at("HEAD", d)
    assert [p for _b, p in was_unread] == ["a.js"], was_unread
    write(d, {"a.js": broken.replace("function ( {", "function f() {}")})
    out = subprocess.run([sys.executable, os.path.join(HERE, "volume.py"), "--check",
                          "--root", d], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout


@case("readability is compared per FILE, not per bucket")
def moot_is_per_file(_):
    # Two files swapping readability inside one bucket cancel over bucket NAMES, and the delta is
    # then taken over mismatched sets — which is the whole defect, arriving in a pair.
    prose = "// prose\n" * (vol.FLOOR * 3)
    d = tree({"a.js": "function ( {\n" + prose, "b.js": "let x;\n"}, commit=True)
    # a.js starts parsing and brings its prose into the bucket with it; b.js stops, and takes the
    # only code line out. Over bucket NAMES the two cancel and the delta reads as pure prose.
    write(d, {"a.js": "let a;\n" + prose, "b.js": "function ( {\n"})
    out = subprocess.run([sys.executable, os.path.join(HERE, "volume.py"), "--check",
                          "--root", d], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout


@case("one unreadable FILE does not mute the bucket holding it")
def moot_is_the_file_not_the_bucket(_):
    # Muting the bucket meant a commit that fixed a non-parsing module could carry any amount of
    # prose into it in silence — which is the one direction this check exists to stop.
    d = tree({"a.js": "function ( {\n", "big.js": "let x;\n"}, commit=True)
    write(d, {"a.js": "let a;\n", "big.js": "let x;\n" + "// prose\n" * (vol.FLOOR * 3)})
    out = subprocess.run([sys.executable, os.path.join(HERE, "volume.py"), "--check",
                          "--root", d], capture_output=True, text=True)
    assert out.returncode == 1, out.stdout


@case("a line that CLOSES one block and opens another is still inside one")
def html_close_then_open(_):
    # Asking whether the line contains a closer at all read `<!-- a -->x<!-- b` as closed, and the
    # second comment's body was counted as code. Only the LAST opener can still be open.
    src = "<div>\n<!-- a -->x<!-- b\nmore\n-->\n<p>\n"
    assert vol.split("a.html", src) == (2, 3, 0), vol.split("a.html", src)
    shut = "<!-- a --> <!-- b -->\n<p>\n"
    assert vol.split("a.html", shut) == (1, 1, 0), vol.split("a.html", shut)


@case("a def that carries its own docstring is a line of CODE")
def one_line_docstring(_):
    # `def f(): """doc"""` puts both on one line, and the AST's docstring range starts there.
    assert vol.split("a.py", 'def f(): """doc"""\nx = 1\n') == (2, 0, 0)
    assert vol.split("a.py", 'def f():\n    """doc"""\n    return 1\n') == (2, 0, 1), "normal"


@case("a MERGE is not a commit that wrote the branch it merges")
def merge_is_not_authorship(_):
    # HEAD during a merge is the FIRST PARENT, so the whole incoming branch is charged to the
    # merge commit. sw-lint.py --fix declines in this state for the same reason.
    d = tree({"scripts/a.py": "x = 1\n" * 40}, commit=True)
    q = dict(cwd=d, capture_output=True)
    subprocess.run(["git", "checkout", "-q", "-b", "side"], **q)
    write(d, {"scripts/b.py": "# prose\n" * 80})
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "docs"], **q)
    subprocess.run(["git", "checkout", "-q", "-"], **q)
    write(d, {"scripts/c.py": "y = 1\n" * 40})
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "code"], **q)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "merge", "--no-commit", "--no-ff", "side"], **q)
    assert vol.in_merge(d), "the fixture did not actually leave a merge in progress"
    out = subprocess.run([sys.executable, os.path.join(HERE, "volume.py"), "--check",
                          "--root", d], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout


@case("the CSS stamp is the same stamp")
def stamp_in_css(_):
    # styles.css carries it as `/* pwa-starter: styles.css @ ...`, and a markers list of ("//", "#")
    # filed one convention under two answers — styles.css source, app.js vendored.
    assert vol.bucket("styles.css", "/* pwa-starter: styles.css @ 1a2b3c4\n*{ margin:0 }\n") \
        == "vendored"


def main():
    for name, fn in CASES:
        try:
            fn(None)
            print("  ok   %s" % name)
        except Exception as e:
            # Not AssertionError alone: an ablated tree is this branch's cases over the base's
            # code, where a crash reports as INCONCLUSIVE and proves nothing. ablate.py is looking
            # for a named FAIL.
            FAILED.append(name)
            print("  FAIL %s\n       %s: %s" % (name, type(e).__name__, e))
    print("\n%d passed, %d failed" % (len(CASES) - len(FAILED), len(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
