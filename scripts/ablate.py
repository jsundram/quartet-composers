#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Prove that a branch's TESTS actually catch what its SOURCE changed.

A green suite is not evidence that a fix is right; it is only evidence that nothing already
covered went red. Every long review on this repo has been the same shape — a fix shipped on a
green suite, review found it wrong, the NEXT commit added the test that would have caught it.
PR #23 ran six rounds that way, and four of them fixed a defect in the previous round's fix:
"the fourth mutation-green fix on this PR", in that branch's own words. The test that proves a
fix always arrived one round late.

So this asks the question the reviewer asks by hand — most recently by deleting
`pointer-events="none"` from histogram.js's grips group and watching the grip-drag check go red
(#42). Revert the branch's SOURCE hunks to the base, keep its TEST hunks, and run the suite. If
the branch's tests still pass without the branch's code, they do not prove it.

Three things about the shape, each of which is the difference between a gate and a nuisance:

  A NEW NAMED `FAIL`, not a nonzero exit. An ablated tree is a chimera — this branch's tests over
  the base's code — and it can fail to run at ALL: a test that calls a function the branch
  introduced dies on import, exits nonzero, and proves nothing whatsoever about the fix. Every
  suite here prints `ok  ` / `FAIL <name>` lines, so requiring a failure that NAMES a check the
  clean run passed separates "the test proves the fix" from "the ablated tree exploded". The
  explosion is reported as INCONCLUSIVE and fails too, because a gate that cannot tell those
  apart is worse than none: it would go green on a suite that never ran.

  ONLY THE SUITES THAT COVER WHAT CHANGED. A branch touching chart.js will never redden
  validate.test.py, and demanding it would train everyone to reach for the escape hatch. COVERS
  below maps source to suite; a source file no suite covers is reported and does not fail, which
  is honest rather than silent — see the note there.

  ONE ESCAPE HATCH, SHARED WITH fix-lint.py. A `No-test:` trailer on any commit in the range
  skips both gates and prints the stated reason. A pure refactor and a comment fix are real, and
  the point is not to forbid them — it is to make an untested source change a sentence somebody
  wrote on purpose and a reviewer can read, rather than a silence.

The working tree is rewritten in place and restored in a `finally`, so it REFUSES to run on a
dirty tree: restoring means `git checkout HEAD -- <file>`, which would take uncommitted work with
it. A file the branch ADDED is not ablated at all — see plan(), where the reason is that the
question is empty rather than unanswered.

    python3 scripts/ablate.py --base origin/main
    python3 scripts/ablate.py --base origin/main --list      # what it would run, tree untouched
    python3 scripts/ablate.py --base origin/main --with-ui   # include the browser suite (slow)
    python3 scripts/ablate.py --base origin/main --cmd "python3 scripts/validate.test.py"
"""
import os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Source -> the suite that can testify about it. A branch is only asked to redden the suites that
# cover the files it touched.
#
# `ui.test.mjs` needs a real headless Chrome, which is why it is marked and not merely absent: a
# UI branch REPORTS that its ablation is owed rather than passing quietly, and `--with-ui` runs it
# here, on the same machinery, wherever there is a browser. CI is now one of those places — the
# gates job passes `--with-ui`, so the mark is about a machine without a browser rather than about
# CI, which is what it used to say and what kept UI branches unproven by anything automatic. The
# entries with no suite at all (build_data.py, scrape_list.py, make-og-svg.py) are named too, for
# the same reason — an uncovered file should read as a known gap, not as a clean run.
COVERS = [
    (("scripts/validate.py",),        ["python3 scripts/validate.test.py"]),
    (("scripts/pagemoves.py",),       ["python3 scripts/pagemoves.test.py"]),
    (("scripts/fetch_views.py",),     ["python3 scripts/fetch_views.test.py"]),
    (("scripts/sw-lint.py",),         ["python3 scripts/sw-lint.test.py"]),
    (("sw.js",),                      ["node scripts/sw.test.mjs"]),
    (("app.js", "chart.js", "table.js", "histogram.js", "names.js", "theme.js",
      "styles.css", "index.html"),    ["BROWSER:scripts/ui-test.sh"]),
    # The gates cover themselves. Without this the next change to this very file would never be
    # ablated against the suite written for it, which is the failure the whole PR is about.
    (("scripts/ablate.py", "scripts/fix-lint.py"),
                                      ["python3 scripts/fix-lint.test.py"]),
]

# Load-bearing source that genuinely has no suite. plan() no longer READS this — anything unmapped
# defaults to reported — so it would be pure decoration, and a decorative list once kept a name in
# it through the very commit that gave that file a suite. It is an ASSERTION now, checked by
# unsuited() below: a name here that has a test file beside it, or that COVERS already maps, is a
# stale claim that this file has nothing to prove, which is exactly the silence the gate is for.
UNCOVERED = ("scripts/build_data.py", "scripts/scrape_list.py", "scripts/fetch_wikidata.py",
             "scripts/make-og-svg.py", "scripts/og-lint.py", "scripts/refresh.py",
             "manifest.json", "ping.js")

# WHAT COUNTS AS SOURCE lives here and nowhere else, because fix-lint.py asks the same question
# and two copies of a classification drift into disagreeing — the lesson #23 round 3 spent a
# commit on, one file over ("make the gate and the stitch share one rule"). fix-lint.py imports
# these two; this module is named without a hyphen so that it can.
#
# Data files (composers.json, readership.json, data/) are generated by the pipeline and gated by
# validate.py instead: a top-up changes them by design and has no test to write. Docs, mocks/,
# .github/ and .githooks/ are not source. The audits are human-graded by construction
# (invariant 11), so a test for one would be a test of the thing a human is there to judge.
SOURCE = re.compile(
    r"^(app|chart|table|histogram|names|theme|sw|ping)\.js$"
    r"|^(styles\.css|index\.html|manifest\.json)$"
    r"|^scripts/(validate|pagemoves|fetch_views|fetch_wikidata|build_data|scrape_list"
    r"|make-og-svg|og-lint|sw-lint|refresh|ablate|fix-lint)\.py$")
TESTS = re.compile(r"^scripts/.*(\.test\.(py|mjs)|ui-test\.sh)$")
# Both halves of the line matter: `FAIL` at the head, and the name with any trailing detail cut.
# The detail carries measured numbers that differ between two runs of the same suite, so a set
# difference over whole lines would report noise as signal.
FAILED = re.compile(r"^\s*FAIL\s*[-–]?\s+(.*?)\s*(?:—|$)")
# Evidence that a suite actually executed: every one here prints `ok`/`FAIL` lines per check.
RAN = re.compile(r"^\s*(ok|FAIL)\b", re.M)


def flat_tail(out, n=90):
    """The last non-empty line, for saying WHY a suite produced nothing."""
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines[-1][:n] if lines else ""


def unsuited():
    """Names in UNCOVERED that are no longer uncovered. Empty is the invariant."""
    mapped = {f for pats, _ in COVERS for f in pats}
    bad = []
    for f in UNCOVERED:
        if f in mapped:
            bad.append(f"{f} is in UNCOVERED and in COVERS")
        elif f.endswith(".py") and os.path.exists(os.path.join(ROOT, f[:-3] + ".test.py")):
            bad.append(f"{f} is in UNCOVERED but {f[:-3]}.test.py exists — map it in COVERS")
    return bad


def sh(*a, **kw):
    return subprocess.run(a, capture_output=True, text=True, cwd=ROOT, **kw)


def fails(out):
    return {m.group(1).strip() for m in (FAILED.match(l) for l in out.splitlines()) if m}


def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=ROOT)
    return r.returncode, r.stdout + r.stderr


def changed(base):
    mb = sh("git", "merge-base", base, "HEAD")
    if mb.returncode != 0:
        return None, (f'no merge base between HEAD and "{base}" — with a shallow checkout there '
                      f"is nothing to compare against; fetch-depth 0 in CI")
    mb = mb.stdout.strip()
    # -M05% because the DEFAULT threshold is the bug: a rename git scores below 50% arrives as
    # D + A instead, and those two entries ablate the OLD path while the new one keeps the fix —
    # a suite that then passes, reported as "your tests prove nothing". Finding the rename is what
    # lets it be ablated properly below.
    d = sh("git", "diff", "--name-status", "-M05%", mb, "HEAD")
    if d.returncode != 0:
        return None, f"could not diff {mb[:8]}..HEAD"
    out = []
    for line in d.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            # For R/C the format is `R050<TAB>old<TAB>new`, so the LAST field is the path that
            # exists at HEAD and the middle one is the path that exists at base. Taking only the
            # last silently produced `git checkout <base> -- <new path>`, which cannot resolve.
            out.append((parts[0][0], parts[-1], parts[1] if len(parts) >= 3 else parts[-1]))
    return (mb, out), None


def excused(base_mb):
    """A `No-test:` trailer anywhere in the range, and the reason it gives."""
    log = sh("git", "log", "--format=%B", f"{base_mb}..HEAD")
    for line in log.stdout.splitlines():
        m = re.match(r"^\s*No-test:\s*(.+?)\s*$", line, re.I)
        if m:
            return m.group(1)
    return None


def only_a_version_bump(base_mb):
    """True when sw.js differs from base ONLY in V.

    Invariant 1 makes a V bump the mandatory companion of any SHELL edit, so nearly every branch
    here touches sw.js without having anything to assert about the fetch handler. Asking such a
    branch to redden sw.test.mjs would fire the gate on almost every PR, which is how a gate gets
    switched off. The bump is already gated — by sw-lint.py, in two places — so it is exempted
    here rather than made somebody's problem twice.
    """
    head, base = sh("git", "show", "HEAD:sw.js"), sh("git", "show", f"{base_mb}:sw.js")
    if head.returncode != 0 or base.returncode != 0:
        return False
    norm = lambda t: re.sub(r'const V\s*=\s*"[^"]*"', 'const V = "X"', t)
    return norm(head.stdout) == norm(base.stdout)


def plan(files, base_mb=None):
    """Which suites this branch's source changes are answerable by, and what nothing covers."""
    # A file the branch ADDED has no version at base, so there is nothing to revert it TO — the
    # ablated tree simply lacks the module, every suite that imports it dies on import, and the
    # verdict is INCONCLUSIVE forever. That would fire on every genuinely new module, which is
    # neither a defect nor something a `No-test:` trailer describes (there IS a test). Ablation
    # asks whether a test catches a CHANGE, and for a wholly new file the question is empty: a
    # test that references it cannot pass without it. So added files are dropped here, and a
    # branch that adds only new files is reported as having nothing to ablate rather than failing.
    # A RENAME is NOT the same question: the base content exists, it just lives at the old path.
    # `git checkout <base> -- <new path>` cannot find it and used to fail silently, so nothing was
    # reverted and a passing suite was reported as proving nothing. Carrying the old path lets the
    # file actually be ablated — `git show <base>:<old>` written to the new path — instead of
    # exempted, so a rename that also carries a fix is held to the same standard as any edit.
    src = [f for st, f, _o in files if SOURCE.match(f) and st != "A"]
    renamed_from = {f: o for st, f, o in files if st in ("R", "C") and SOURCE.match(f)}
    added = [(st, f) for st, f, _o in files if SOURCE.match(f) and st == "A"]
    if "sw.js" in src and base_mb and only_a_version_bump(base_mb):
        src = [f for f in src if f != "sw.js"]
    suites, uncovered = [], []
    for f in src:
        hit = next((cmds for pats, cmds in COVERS if f in pats), None)
        if hit:
            for c in hit:
                if c not in suites:
                    suites.append(c)
        else:
            # Default to UNCOVERED rather than requiring membership. Four SOURCE files were in
            # neither table and so passed in total silence, which is the opposite of what the
            # docstring promises. UNCOVERED is documentation now; this branch is the guarantee.
            uncovered.append(f)
    return src, suites, uncovered, added, renamed_from


def at(ref, path):
    """Does `path` exist at `ref`?"""
    return sh("git", "cat-file", "-e", f"{ref}:{path}").returncode == 0


def restore(source_files):
    """Put every ablated file back the way HEAD has it. Returns the paths it could NOT restore.

    ONE PER FILE, and the return code is checked. It used to be a single
    `git checkout HEAD -- <every file>`, and git validates the whole pathspec list before it
    touches anything: one path absent at HEAD — which is exactly what a branch that DELETES a
    source file produces — aborted the entire command, so NOTHING was restored. The tree was then
    left holding base content, staged, and a commit at that moment would have silently shipped the
    un-fixed file. A file absent at HEAD is removed rather than checked out, because "as HEAD has
    it" for a deleted file means gone.
    """
    failed = []
    for f in source_files:
        if at("HEAD", f):
            if sh("git", "checkout", "HEAD", "--", f).returncode != 0:
                failed.append(f)
        elif os.path.exists(os.path.join(ROOT, f)):
            if sh("git", "rm", "-f", "-q", "--", f).returncode != 0:
                failed.append(f)
    return failed


def ablate(base_mb, source_files, suites, renamed=None):
    """Revert source to base, keep tests, run each suite, restore. Returns per-suite verdicts."""
    renamed = renamed or {}
    try:
        for f in source_files:
            old = renamed.get(f)
            if old:
                # The base version of a renamed file is at its OLD path, so there is nothing to
                # `checkout` onto the new one — write the blob instead. restore() puts it back
                # from HEAD like any other file.
                blob = sh("git", "show", f"{base_mb}:{old}")
                if blob.returncode == 0:
                    with open(os.path.join(ROOT, f), "w") as fh:
                        fh.write(blob.stdout)
            elif at(base_mb, f):
                sh("git", "checkout", base_mb, "--", f)
        verdicts = []
        for cmd in suites:
            code, out = run(cmd)
            verdicts.append((cmd, code, fails(out), out))
        return verdicts
    finally:
        broken = restore(source_files)
        if broken:
            # Loud, and not swallowed by whatever verdict was being computed: the tree is the
            # user's, and leaving it mangled is worse than any finding this script can report.
            print("\n  ablate: COULD NOT RESTORE " + ", ".join(broken)
                  + "\n   - your working tree still holds base content for those files."
                  + "\n   - recover with: git checkout HEAD -- " + " ".join(broken), flush=True)


def main():
    if "--base" not in sys.argv:
        print("usage: python3 scripts/ablate.py --base REF [--list]")
        return 2
    i = sys.argv.index("--base")
    if i + 1 >= len(sys.argv):
        print("  ablate: --base needs a ref to compare against")
        return 2
    base, listing = sys.argv[i + 1], "--list" in sys.argv
    with_ui = "--with-ui" in sys.argv
    # An explicit suite overrides COVERS. It is how fix-lint.test.py drives this against a
    # throwaway repo, and how a human ablates against one suite without waiting for the rest.
    cmd = None
    if "--cmd" in sys.argv:
        j = sys.argv.index("--cmd")
        if j + 1 >= len(sys.argv):
            print("  ablate: --cmd needs a command to run")
            return 2
        cmd = sys.argv[j + 1]

    stale = unsuited()
    if stale:
        print("  ablate: UNCOVERED is out of date, so a covered file would be reported as "
              "having no suite:")
        for b in stale:
            print(f"   - {b}")
        return 2

    got, err = changed(base)
    if err:
        print(f"  ablate:\n   - {err}")
        return 2
    base_mb, files = got
    src, suites, uncovered, added_src, renamed = plan(files, base_mb)

    if not src:
        if added_src:
            print("  ablate: every source file this branch changed is NEW, so there is no "
                  "before-state to ablate against:")
            for _st, f in added_src:
                print(f"     {f}  (added)")
            return 0
        print("  ablate: no source changes on this branch — nothing to prove")
        return 0

    why = excused(base_mb)
    if why:
        print(f"  ablate: skipped by a No-test: trailer — {why}")
        return 0

    browser = [s.split(":", 1)[1] for s in suites if s.startswith("BROWSER:")]
    runnable = [s for s in suites if not s.startswith("BROWSER:")]
    if with_ui:
        runnable += browser
        browser = []
    if cmd:
        runnable, browser, uncovered = [cmd], [], []

    if listing:
        print(f"  ablate: {len(src)} source file(s) changed against {base_mb[:8]}")
        for s in src:
            print(f"     {s}")
        for s in runnable:
            print(f"   - would run: {s}")
        for s in browser:
            print(f"   - owed locally (needs a browser): --with-ui runs {s}")
        for f in uncovered:
            print(f"   - no suite covers {f}")
        return 0

    if not runnable:
        # Honest rather than silent: a UI branch has a real ablation owed, just not one CI can run.
        print("  ablate: no CI-runnable suite covers this branch's source.")
        for s in browser:
            print(f"   - run locally with a browser: python3 scripts/ablate.py --base {base} --with-ui")
        for f in uncovered:
            print(f"   - no suite covers {f}")
        return 0

    # TRACKED changes only. `git checkout <ref> -- <path>` can never touch an untracked file, so
    # counting them refused a local run over a stray scratch note while the stated reason — that
    # restoring would take uncommitted work with it — was only ever about tracked files.
    dirty = sh("git", "status", "--porcelain", "--untracked-files=no").stdout.strip()
    if dirty:
        print("  ablate: the working tree is dirty, and this rewrites source files in place.")
        print("   - commit or stash first; restoring would otherwise take your changes with it")
        return 2

    # A suite that produced no ok/FAIL lines at all did not RUN — `ui-test.sh` prints
    # "no Chromium found — skipping (this is not a failure)" and exits 0, so on a machine with no
    # browser the baseline and the ablated run are identical empty passes, and the verdict fell
    # through to "its tests still PASS" — telling an author without a browser that their test
    # proves nothing, from the very command README tells them to run.
    #
    # THE EXIT CODE IS HALF OF THAT TEST. Silence with code 0 is a deliberate skip; silence with a
    # NONZERO code is a suite that crashed — an import error, a missing dependency, a syntax
    # error — and treating it as "not runnable here" let a broken suite pass the gate, which is a
    # louder version of the hole this whole script exists to close. The ablated side already
    # separates the two; the baseline was throwing `code` away.
    before, skipped = {}, []
    for cmd in list(runnable):
        code, out = run(cmd)
        if not RAN.search(out):
            if code != 0:
                print(f"  ablate: {cmd} is BROKEN before ablating — it exited {code} without "
                      f"printing a single ok or FAIL line, so it never ran")
                if flat_tail(out):
                    print(f"     {flat_tail(out, 200)}")
                return 2
            skipped.append((cmd, flat_tail(out)))
            runnable.remove(cmd)
            continue
        before[cmd] = fails(out)
        if before[cmd]:
            print(f"  ablate: {cmd} is ALREADY red before ablating — fix that first")
            for n in sorted(before[cmd]):
                print(f"     FAIL {n}")
            return 2

    for cmd, why in skipped:
        print(f"   - not runnable here, so it can prove nothing: {cmd}"
              + (f"  ({why})" if why else ""))
    if not runnable:
        print("  ablate: no suite that covers this branch could actually run.")
        return 0

    # ONE suite going red is proof. A branch that touches histogram.js and validate.py is proven
    # by whichever suite covers the part that changed behaviour; demanding that EVERY covered
    # suite redden would ask for a test of the thing that did not change.
    proved, problems = False, []
    for cmd, code, after, out in ablate(base_mb, src, runnable, renamed):
        new = after - before[cmd]
        if new:
            proved = True
            print(f"  ok   - {cmd} reddens without this branch's source")
            for n in sorted(new):
                print(f"          FAIL {n}")
        elif not after and code != 0:
            problems.append((cmd, "INCONCLUSIVE — it exited %d without printing a single FAIL "
                                  "line, so the suite did not run" % code, out))
        else:
            problems.append((cmd, "its tests still PASS without this branch's source, so they do "
                                  "not prove it", ""))

    if proved:
        # Reported, not silenced: the branch is proven, but a covered suite that stayed green is
        # worth seeing — it is often the sign of a second change nobody wrote a test for.
        for cmd, msg, _out in problems:
            print(f"   - (also ran) {cmd}: {msg.split('—')[0].strip()}")
        problems = []

    if not problems:
        for s in browser:
            print(f"   - still owed locally: python3 scripts/ablate.py --base {base} --with-ui  ({s})")
        return 0

    print("\n  ablate:")
    if added_src:
        # A file ADDED cannot be ablated, so a verdict of "your tests prove nothing" may be about
        # a change this script never reverted. The sharp case is a rename git scored at 0%: it
        # arrives as D + A at ANY -M threshold, indistinguishable from an unrelated delete plus
        # add, so the old path is ablated while the new one keeps the fix and the suite passes.
        # Naming the un-ablatable files turns a confidently wrong verdict into an accurate one.
        print("   NOTE: these files are new at their path and were NOT ablated, so the verdict "
              "below\n   may be about a change that was never reverted "
              "(a wholly-rewritten rename arrives this way):")
        for _st, f in added_src:
            print(f"     {f}")
    for cmd, msg, out in problems:
        print(f"   - {cmd}: {msg}")
        if out:
            for line in out.strip().splitlines()[-6:]:
                print(f"       {line}")
    print("\n   Add a test that goes red without the fix, or say why there isn't one with a")
    print("   `No-test: <reason>` trailer on a commit. See scripts/ablate.py's header.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
