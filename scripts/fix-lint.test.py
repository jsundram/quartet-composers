#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Proves the two branch gates — fix-lint.py and ablate.py — do what they claim.

Both read TWO commits, so neither can be judged from a single staged diff, and both are the kind
of check whose failure is a SILENCE: a branch that should have been stopped merges green. That is
the same shape sw-lint.test.py exists for, so this borrows its harness — every case builds a real
throwaway repo with real branches and runs the real script over it.

The ablation cases matter most, because the interesting half of that script is what it does NOT
count as proof. A suite that goes red because the ablated tree could not run at all exits nonzero
while proving nothing, and a gate that accepted it would go green on a suite that never executed.
So there is a case for each of the three verdicts — reddens, still passes, could not run — and
one for a suite that was already red before ablating, which would otherwise let a pre-existing
failure masquerade as proof.

Offline, no browser, ~3s:
    python3 scripts/fix-lint.test.py
"""
import os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FIXLINT, ABLATE = os.path.join(HERE, "fix-lint.py"), os.path.join(HERE, "ablate.py")
fails = []

# A tiny stand-in for one of the real suites: it prints the `ok  ` / `FAIL <name>` lines every
# suite here prints, and asserts one thing about app.js. The scripts are pointed at it with an
# explicit command, so nothing depends on the real COVERS map.
SUITE = '''import re, sys
src = open("app.js").read()
ok = bool(re.search(r"FIXED", src))
print(("  ok   - " if ok else "  FAIL - ") + "app.js carries the fix")
sys.exit(0 if ok else 1)
'''
# The same suite, but it dies before printing anything when app.js lacks something the branch
# introduced — the chimera case: this branch's tests over the base's code, nonzero exit, no FAIL
# line, nothing whatsoever proven about the fix.
EXPLODES = '''import sys
src = open("app.js").read()
if "FIXED" not in src:
    raise SystemExit("exploded before it could report anything")
print("  ok   - app.js carries the fix")
'''


def git(repo, *a):
    r = subprocess.run(("git",) + a, cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(a)}: {r.stderr.strip()}")
    return r.stdout


def write(repo, name, text):
    p = os.path.join(repo, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(text)


def commit(repo, msg):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)


def new_repo(tmp):
    """A base commit on main: an unfixed app.js and a suite that does not yet assert the fix."""
    repo = tempfile.mkdtemp(dir=tmp)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@t"); git(repo, "config", "user.name", "t")
    # The gates resolve their own directory, so the scripts under test must live in the throwaway
    # repo too — they are read as scripts/, exactly where they sit in the real one.
    for f in ("fix-lint.py", "ablate.py"):
        write(repo, f"scripts/{f}", open(os.path.join(HERE, f)).read())
    write(repo, "app.js", "// nothing yet\n")
    write(repo, "README.md", "hi\n")
    commit(repo, "base")
    return repo


def run(repo, script, *args):
    r = subprocess.run([sys.executable, script, "--base", "main"] + list(args),
                       cwd=repo, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


printed = []


def case(name, got, want, extra=""):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f" — {extra}" if extra else ""))
    printed.append(name)
    if not ok:
        fails.append(name)


with tempfile.TemporaryDirectory() as tmp:
    # --- fix-lint: SOURCE WITHOUT A TEST ---------------------------------------------------------
    repo = new_repo(tmp)
    git(repo, "checkout", "-q", "-b", "b1")
    write(repo, "app.js", "// FIXED\n")
    commit(repo, "fix it")
    code, out = run(repo, os.path.join(repo, "scripts/fix-lint.py"))
    case("a branch that changes source and no test fails", code, 1, out.splitlines()[-1][:60])
    case("...and it names the file", "app.js" in out, True)

    # --- fix-lint: THE TRAILER --------------------------------------------------------------------
    git(repo, "commit", "-q", "--amend", "-m", "fix it\n\nNo-test: a comment, nothing to assert")
    code, out = run(repo, os.path.join(repo, "scripts/fix-lint.py"))
    case("a No-test: trailer excuses it", (code, "excused" in out), (0, True))
    case("...and the stated reason is printed", "nothing to assert" in out, True)

    # --- fix-lint: A TEST WAS TOUCHED ------------------------------------------------------------
    repo = new_repo(tmp)
    git(repo, "checkout", "-q", "-b", "b2")
    write(repo, "app.js", "// FIXED\n")
    write(repo, "scripts/thing.test.py", SUITE)
    commit(repo, "fix it, with a test")
    code, _ = run(repo, os.path.join(repo, "scripts/fix-lint.py"))
    case("a branch that touches a test passes", code, 0)

    # A docs-only branch is not a source change, and must not be asked for a test.
    repo = new_repo(tmp)
    git(repo, "checkout", "-q", "-b", "b3")
    write(repo, "README.md", "hi there\n")
    commit(repo, "docs")
    code, _ = run(repo, os.path.join(repo, "scripts/fix-lint.py"))
    case("a docs-only branch is not asked for a test", code, 0)

    # --- ablate: THE TEST REDDENS WITHOUT THE FIX (the good case) ---------------------------------
    repo = new_repo(tmp)
    write(repo, "suite.py", SUITE)
    commit(repo, "add a suite runner")
    git(repo, "checkout", "-q", "-b", "b4")
    write(repo, "app.js", "// FIXED\n")
    write(repo, "scripts/thing.test.py", "x\n")   # so fix-lint is satisfied; ablate uses the cmd
    commit(repo, "fix it, with a test")
    ab = os.path.join(repo, "scripts/ablate.py")
    code, out = run(repo, ab, "--cmd", f"{sys.executable} suite.py")
    case("a test that reddens without the fix passes the gate", code, 0, out.splitlines()[0][:60])
    case("...and it names the check that went red", "carries the fix" in out, True)

    # --- ablate: THE TEST STILL PASSES (mutation-green — the #23 failure) -------------------------
    repo = new_repo(tmp)
    write(repo, "suite.py", '''print("  ok   - something unrelated")''')
    commit(repo, "add a suite runner")
    git(repo, "checkout", "-q", "-b", "b5")
    write(repo, "app.js", "// FIXED\n")
    write(repo, "scripts/thing.test.py", "x\n")
    commit(repo, "fix it, with a test that proves nothing")
    code, out = run(repo, os.path.join(repo, "scripts/ablate.py"),
                    "--cmd", f"{sys.executable} suite.py")
    case("a test that still passes without the fix FAILS the gate", code, 1)
    case("...and says so in those words", "still PASS" in out, True)

    # --- ablate: THE ABLATED TREE COULD NOT RUN (nonzero, but nothing proven) ---------------------
    repo = new_repo(tmp)
    write(repo, "suite.py", EXPLODES)
    commit(repo, "add a suite runner")
    git(repo, "checkout", "-q", "-b", "b6")
    write(repo, "app.js", "// FIXED\n")
    write(repo, "scripts/thing.test.py", "x\n")
    commit(repo, "fix it")
    code, out = run(repo, os.path.join(repo, "scripts/ablate.py"),
                    "--cmd", f"{sys.executable} suite.py")
    case("a nonzero exit with no FAIL line is INCONCLUSIVE, not proof", code, 1)
    case("...and it says the suite did not run", "did not run" in out, True)

    # --- ablate: ALREADY RED BEFORE ABLATING ------------------------------------------------------
    # Without this, a suite failing for an unrelated reason supplies the FAIL line the gate is
    # looking for, and an unproven fix rides in on somebody else's breakage.
    repo = new_repo(tmp)
    write(repo, "suite.py", '''print("  FAIL - something already broken")\nimport sys; sys.exit(1)''')
    commit(repo, "add a broken suite")
    git(repo, "checkout", "-q", "-b", "b7")
    write(repo, "app.js", "// FIXED\n")
    write(repo, "scripts/thing.test.py", "x\n")
    commit(repo, "fix it")
    code, out = run(repo, os.path.join(repo, "scripts/ablate.py"),
                    "--cmd", f"{sys.executable} suite.py")
    case("a suite that is already red is refused, not counted as proof", code, 2)
    case("...and says which check was already failing", "already broken" in out, True)

    # --- ablate: THE TREE IS RESTORED -------------------------------------------------------------
    # It rewrites source in place. A gate that leaves the tree mangled after a failing run would
    # be worse than the defect it catches.
    case("the working tree is clean afterwards",
         git(repo, "status", "--porcelain").strip(), "")
    case("...and app.js still carries the branch's fix",
         "FIXED" in open(os.path.join(repo, "app.js")).read(), True)

    # --- ablate: A DIRTY TREE IS REFUSED ----------------------------------------------------------
    write(repo, "app.js", "// FIXED, plus uncommitted work\n")
    code, out = run(repo, os.path.join(repo, "scripts/ablate.py"),
                    "--cmd", f"{sys.executable} suite.py")
    case("a dirty tree is refused before anything is touched", code, 2)
    case("...and the uncommitted work is still there",
         "uncommitted" in open(os.path.join(repo, "app.js")).read(), True)

    # --- ablate: THE TRAILER SKIPS IT TOO ---------------------------------------------------------
    git(repo, "checkout", "-q", "--", "app.js")
    git(repo, "commit", "-q", "--amend", "-m", "fix it\n\nNo-test: a rename, nothing to assert")
    code, out = run(repo, os.path.join(repo, "scripts/ablate.py"),
                    "--cmd", f"{sys.executable} suite.py")
    case("one trailer excuses BOTH gates", (code, "No-test" in out), (0, True))

    # --- ablate: ONE SUITE REDDENING IS PROOF -----------------------------------------------------
    # A branch that touches two covered areas is proven by the suite covering the part that
    # changed behaviour. Requiring every covered suite to redden would ask for a test of the
    # thing that did not change, which is how a gate teaches people to reach for the escape hatch.
    repo = new_repo(tmp)
    write(repo, "suite.py", SUITE)
    write(repo, "unrelated.py", 'print("  ok   - something unrelated")')
    commit(repo, "two suites")
    git(repo, "checkout", "-q", "-b", "b8")
    write(repo, "app.js", "// FIXED\n")
    write(repo, "scripts/thing.test.py", "x\n")
    commit(repo, "fix it")
    ab = os.path.join(repo, "scripts/ablate.py")
    code, out = run(repo, ab, "--cmd", f"{sys.executable} suite.py")
    case("the covering suite alone proves the branch", code, 0)
    code, out = run(repo, ab, "--cmd", f"{sys.executable} unrelated.py")
    case("...but a suite that covers nothing proves nothing on its own", code, 1)

    # --- ablate: A BARE V BUMP IS NOT A SOURCE CHANGE TO PROVE ------------------------------------
    # Invariant 1 makes bumping V the mandatory companion of any SHELL edit, so nearly every
    # branch touches sw.js with nothing to assert about the fetch handler. Without this the gate
    # fires on almost every PR, and a gate that does that gets switched off.
    repo = new_repo(tmp)
    write(repo, "sw.js", 'const V = "quartets-v32";\nconst SHELL = ["./"];\n')
    write(repo, "suite.py", 'print("  ok   - unrelated to V")')
    commit(repo, "add sw.js")
    git(repo, "checkout", "-q", "-b", "b9")
    write(repo, "sw.js", 'const V = "quartets-v33";\nconst SHELL = ["./"];\n')
    write(repo, "scripts/thing.test.py", "x\n")
    commit(repo, "bump V")
    code, out = run(repo, os.path.join(repo, "scripts/ablate.py"),
                    "--cmd", f"{sys.executable} suite.py")
    case("a branch whose only sw.js change is V is not asked to prove it", code, 0,
         out.splitlines()[0][:60] if out else "")
    # ...and the exemption is exactly that narrow: touch anything else in sw.js and it applies.
    write(repo, "sw.js", 'const V = "quartets-v33";\nconst SHELL = ["./", "./app.js"];\n')
    commit(repo, "and change SHELL too")
    code, out = run(repo, os.path.join(repo, "scripts/ablate.py"),
                    "--cmd", f"{sys.executable} suite.py")
    case("...but a real sw.js change still has to be proven", code, 1)

    # --- ablate: A BRANCH THAT ONLY ADDS NEW SOURCE ----------------------------------------------
    # A new module has no version at base to revert to, so the ablated tree just lacks it and
    # every suite dies on import — INCONCLUSIVE forever, on every genuinely new file. The question
    # is empty rather than unanswered: a test that references a new module cannot pass without it.
    repo = new_repo(tmp)
    write(repo, "suite.py", 'print("  ok   - fine")')
    commit(repo, "a suite")
    git(repo, "checkout", "-q", "-b", "b10")
    write(repo, "chart.js", "// brand new module\n")
    write(repo, "scripts/thing.test.py", "x\n")
    commit(repo, "add a new module, with a test")
    code, out = run(repo, os.path.join(repo, "scripts/ablate.py"),
                    "--cmd", f"{sys.executable} suite.py")
    case("a branch that only ADDS source has nothing to ablate", code, 0)
    case("...and says the file is new rather than claiming it was proven",
         "is NEW" in out and "(added)" in out, True)

    # --- ablate: A BRANCH THAT DELETES A SOURCE FILE (the High finding on #43) --------------------
    # Restoring was one `git checkout HEAD -- <every file>`, and git validates the whole pathspec
    # list before touching anything: the deleted file is absent at HEAD, so the command aborted and
    # NOTHING was restored -- the tree left holding base content, STAGED, where a commit would have
    # silently shipped the un-fixed file. This is the case the old "tree is clean afterwards" check
    # could not see, because it only ever built a modify-only branch.
    repo = new_repo(tmp)
    write(repo, "histogram.js", "// doomed\n")
    write(repo, "suite.py", SUITE)
    commit(repo, "a suite and a file to delete")
    git(repo, "checkout", "-q", "-b", "b11")
    git(repo, "rm", "-q", "histogram.js")
    write(repo, "app.js", "// FIXED\n")
    write(repo, "scripts/thing.test.py", "x\n")
    commit(repo, "delete one source file and fix another")
    code, out = run(repo, os.path.join(repo, "scripts/ablate.py"),
                    "--cmd", f"{sys.executable} suite.py")
    case("a branch that DELETES a source file still proves itself", code, 0)
    case("...and the tree is restored, not left holding base content",
         git(repo, "status", "--porcelain").strip(), "")
    case("...and app.js keeps the branch's fix",
         "FIXED" in open(os.path.join(repo, "app.js")).read(), True)
    case("...and the deleted file stays deleted",
         os.path.exists(os.path.join(repo, "histogram.js")), False)

    # --- ablate: A SUITE THAT DID NOT RUN IS NOT A SUITE THAT PASSED ------------------------------
    # ui-test.sh prints "no Chromium found -- skipping (this is not a failure)" and exits 0, so on
    # a machine with no browser the baseline and the ablated run were identical empty passes and
    # the verdict fell through to "its tests still PASS" -- telling an author without a browser
    # that their test proves nothing, from the command README tells them to run.
    repo = new_repo(tmp)
    write(repo, "suite.py", 'print("suite: skipping, nothing to run here")')
    commit(repo, "a suite that skips")
    git(repo, "checkout", "-q", "-b", "b13")
    write(repo, "app.js", "// FIXED\n")
    write(repo, "scripts/thing.test.py", "x\n")
    commit(repo, "fix it")
    code, out = run(repo, os.path.join(repo, "scripts/ablate.py"),
                    "--cmd", f"{sys.executable} suite.py")
    case("a suite that produced no ok/FAIL lines is not counted as a pass", code, 0)
    case("...and says it could prove nothing", "prove nothing" in out, True)

    # --- ablate: A SOURCE FILE NO SUITE COVERS IS NAMED ------------------------------------------
    # Four SOURCE files were in neither COVERS nor UNCOVERED and so passed in total silence, with
    # "no CI-runnable suite covers this branch's source." printed over an empty list.
    repo = new_repo(tmp)
    git(repo, "checkout", "-q", "-b", "b14")
    write(repo, "manifest.json", '{"name":"x"}\n')
    write(repo, "scripts/thing.test.py", "x\n")
    commit(repo, "touch a source file nothing covers")
    code, out = run(repo, os.path.join(repo, "scripts/ablate.py"))
    case("a source file no suite covers is NAMED, not passed in silence",
         (code, "manifest.json" in out), (0, True))

    # --- fix-lint: THE V EXEMPTION IS SHARED -----------------------------------------------------
    # refresh.yml's monthly branch changes the data files, bumps V, touches no test and carries no
    # trailer. fix-lint failed it while ablate.py exempted the identical branch.
    repo = new_repo(tmp)
    write(repo, "sw.js", 'const V = "quartets-v32";\nconst SHELL = ["./"];\n')
    write(repo, "composers.json", '{"rows":[]}\n')
    commit(repo, "add sw.js and data")
    git(repo, "checkout", "-q", "-b", "b15")
    write(repo, "sw.js", 'const V = "quartets-v33";\nconst SHELL = ["./"];\n')
    write(repo, "composers.json", '{"rows":[1]}\n')
    commit(repo, "monthly top-up")
    code, out = run(repo, os.path.join(repo, "scripts/fix-lint.py"))
    case("fix-lint applies the same V exemption ablate.py does", code, 0, out[:70])

    # --- ablate: A BROKEN SUITE IS NOT A SKIPPED ONE ---------------------------------------------
    # Both produce a baseline with no ok/FAIL lines. Classifying on that alone let a suite that
    # CRASHES -- import error, missing dep, syntax error -- read as "not runnable here" and pass
    # the gate, which is a louder version of the hole this script exists to close. The exit code
    # is the other half of the test: 0 is a deliberate skip, nonzero is a suite that never ran.
    repo = new_repo(tmp)
    write(repo, "suite.py", 'import sys\nsys.stderr.write("Traceback: boom\\n")\nsys.exit(1)')
    commit(repo, "a suite that crashes")
    git(repo, "checkout", "-q", "-b", "b16")
    write(repo, "app.js", "// FIXED\n")
    write(repo, "scripts/thing.test.py", "x\n")
    commit(repo, "fix it")
    code, out = run(repo, os.path.join(repo, "scripts/ablate.py"),
                    "--cmd", f"{sys.executable} suite.py")
    case("a suite that CRASHES is refused, not read as a skip", code, 2)
    case("...and says it never ran", "never ran" in out, True)

    # --- ablate: A RENAME IS ABLATED, NOT EXEMPTED ------------------------------------------------
    # The base content of a renamed file lives at its OLD path, so it can be ablated properly
    # rather than waved through. This is the case that used to report a passing suite as proof of
    # nothing; now it has to actually prove the fix.
    repo = new_repo(tmp)
    body = "".join(f"// line {i}\n" for i in range(40))
    write(repo, "table.js", body)
    write(repo, "suite.py", 'import sys\nsrc=open("chart.js").read() if __import__("os").path.exists("chart.js") else ""\n'
                            'ok="FIXED" in src\nprint(("  ok   - " if ok else "  FAIL - ")+"chart.js carries the fix")\n'
                            'sys.exit(0 if ok else 1)')
    commit(repo, "a suite and a file to rename")
    git(repo, "checkout", "-q", "-b", "b17")
    git(repo, "mv", "table.js", "chart.js")
    write(repo, "chart.js", body.replace("// line 7\n", "// line 7 FIXED\n"))
    write(repo, "scripts/thing.test.py", "x\n")
    commit(repo, "rename and fix")
    code, out = run(repo, os.path.join(repo, "scripts/ablate.py"),
                    "--cmd", f"{sys.executable} suite.py")
    case("a renamed file is ABLATED, so its fix must be proven", code, 0, out.splitlines()[0][:58])
    case("...and the tree survives it",
         git(repo, "status", "--porcelain").strip(), "")
    case("...and the renamed file keeps its fix",
         "FIXED" in open(os.path.join(repo, "chart.js")).read(), True)

    # A rename git scores BELOW the default 50% used to arrive as D+A, which ablated the old path
    # while the new one kept the fix -- a suite that then passed, reported as proving nothing.
    repo = new_repo(tmp)
    write(repo, "table.js", "// almost nothing in common\n")
    write(repo, "suite.py", 'import sys,os\nsrc=open("chart.js").read() if os.path.exists("chart.js") else ""\n'
                            'ok="FIXED" in src\nprint(("  ok   - " if ok else "  FAIL - ")+"chart.js carries the fix")\n'
                            'sys.exit(0 if ok else 1)')
    commit(repo, "a suite and a small file")
    git(repo, "checkout", "-q", "-b", "b18")
    git(repo, "mv", "table.js", "chart.js")
    write(repo, "chart.js", "// FIXED, and wholly rewritten\n")
    write(repo, "scripts/thing.test.py", "x\n")
    commit(repo, "rename with a rewrite")
    code, out = run(repo, os.path.join(repo, "scripts/ablate.py"),
                    "--cmd", f"{sys.executable} suite.py")
    # git reports this as D + A at ANY -M threshold — it genuinely cannot tell a 0%-similar
    # rename from an unrelated delete plus add. So the branch is NOT waved through; what it must
    # not do is claim the tests prove nothing without saying the new file was never ablated.
    case("a wholly-rewritten rename does not get a confidently wrong verdict",
         "NOT ablated" in out, True, out.splitlines()[-1][:58] if out else "")
    case("...and it names the file it could not ablate", "chart.js" in out, True)

    # --- ablate: UNCOVERED IS AN ASSERTION, NOT DECORATION ----------------------------------------
    # plan() defaults anything unmapped to reported, so UNCOVERED is read by nothing -- which is
    # how prose-lint.py sat in it through the very commit that gave it a suite.
    import importlib.util as _il
    _spec = _il.spec_from_file_location("abl", os.path.join(HERE, "ablate.py"))
    _abl = _il.module_from_spec(_spec); _spec.loader.exec_module(_abl)
    case("no name in UNCOVERED has a suite or a COVERS entry", _abl.unsuited(), [])

    # --- THIS SUITE'S OWN SIZE, PRINTED ----------------------------------------------------------
    # It used to be asserted against a count typed into the docs, which made every added case a
    # three-file edit — and a count only this run can produce is exactly the kind nobody should be
    # re-typing. So the number is REPORTED here and stated nowhere: a reader who wants it runs the
    # suite. (Counted at runtime rather than by grepping for `case(`, because these cases are inline
    # and a static count reads low.)
    print(f"\n{len(printed) + 1} cases")

print(("\nFAIL: " + ", ".join(fails)) if fails else "\nall ok")
sys.exit(1 if fails else 0)
