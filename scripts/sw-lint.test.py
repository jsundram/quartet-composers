#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Proves sw-lint.py's --base check catches the incident it was written for, and that --fix
bumps V exactly when check 1 would have nagged about it.

The other five checks read one commit and can be judged by eye. This one reads TWO, and the whole
reason it exists is that the failure it catches looks correct from either side alone: #28 and #30
both bumped quartets-v32 -> v33 from the same base, byte-identically, so each PR was right about
its own parent and the second still merged with a net V delta of zero (#32). A test that builds
only one branch could never show that, so every case here builds a real throwaway repo with real
branches and runs the real script over it.

Offline, no fixtures on disk, ~1s:
    python3 scripts/sw-lint.test.py
"""
import importlib.util, os, subprocess, sys, tempfile

LINT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sw-lint.py")
SW = 'const V = "%s";\nconst SHELL = ["./", "./index.html", "./styles.css", "./app.js"];\n'

fails = []


def git(repo, *a):
    r = subprocess.run(("git",) + a, cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(a)}: {r.stderr.strip()}")
    return r.stdout


def write(repo, name, text):
    with open(os.path.join(repo, name), "w") as f:
        f.write(text)


def commit(repo, msg):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)


def new_repo(tmp, v="quartets-v32"):
    """A base commit on main: sw.js at `v`, plus the two shell files the cases edit."""
    repo = tempfile.mkdtemp(dir=tmp)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@t"); git(repo, "config", "user.name", "t")
    write(repo, "sw.js", SW % v)
    write(repo, "styles.css", "body{}\n")
    write(repo, "README.md", "hi\n")
    commit(repo, "base")
    return repo


def run(repo, ref="main"):
    r = subprocess.run([sys.executable, LINT, "--base", ref], cwd=repo,
                       capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def whole_repo(tmp, v="quartets-v32"):
    """new_repo() plus the rest of the SHELL list on disk.

    The --base cases do not care whether a SHELL entry exists — that is check 2, which reads one
    commit — but the --fix cases assert on the EXIT CODE, and a missing entry makes it 1 for a
    reason that has nothing to do with the bump. So these start from a repo with nothing else to
    report."""
    repo = new_repo(tmp, v)
    write(repo, "index.html", "<p>hi\n")
    write(repo, "app.js", 'const VER_PREFIX = "quartets-v";\n')
    commit(repo, "the rest of the shell")
    return repo


def run_fix(repo, *args):
    r = subprocess.run([sys.executable, LINT, "--fix", *args], cwd=repo,
                       capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def staged_v(repo):
    """V as the INDEX holds it — what the commit about to be made would carry."""
    import re as _re
    m = _re.search(r'const V\s*=\s*"([^"]*)"', git(repo, "show", ":sw.js"))
    return m.group(1) if m else None


def case(name, got, want, extra=""):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f" — {extra}" if extra else ""))
    if not ok:
        fails.append(name)


with tempfile.TemporaryDirectory() as tmp:
    # --- THE INCIDENT ---------------------------------------------------------------------------
    # Both branches bump v32 -> v33 off the same base. The first merges; the second is then correct
    # against its own merge base and catastrophic against the branch it is about to join. This is
    # the case that decides merge-base-vs-tip for the V half of the check, so it runs first.
    repo = new_repo(tmp)
    git(repo, "checkout", "-q", "-b", "pr28")
    write(repo, "sw.js", SW % "quartets-v33"); write(repo, "styles.css", "body{a}\n")
    commit(repo, "28")
    git(repo, "checkout", "-q", "main")
    git(repo, "checkout", "-q", "-b", "pr30", "HEAD")
    write(repo, "sw.js", SW % "quartets-v33"); write(repo, "app.js", "//b\n")
    commit(repo, "30")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", "merge 28", "pr28")   # #28 lands first
    git(repo, "checkout", "-q", "pr30")
    code, out = run(repo)
    case("two branches that bumped to the SAME generation: the second one fails",
         code, 1, out.splitlines()[-1].strip() if out else "no output")
    case("...and it names the shell file that would have gone stale",
         "app.js" in out and "quartets-v33" in out, True, out.splitlines()[-1].strip())
    # The merge really is silent — this is why nothing upstream of CI catches it.
    mt = subprocess.run(["git", "merge-tree", "--write-tree", "main", "pr30"],
                        cwd=repo, capture_output=True, text=True)
    case("...and git itself resolves that merge without a conflict", mt.returncode, 0)
    # Bumping past what main now holds is the fix, and it is the ONLY thing that changed.
    write(repo, "sw.js", SW % "quartets-v34")
    commit(repo, "bump to 34")
    code, out = run(repo)
    case("bumping past the base's generation clears it", (code, out), (0, ""), out)

    # --- THE ORDINARY CASES ---------------------------------------------------------------------
    repo = new_repo(tmp)
    git(repo, "checkout", "-q", "-b", "b")
    write(repo, "styles.css", "body{c}\n")
    commit(repo, "shell edit, no bump")
    code, out = run(repo)
    case("a shell change with no bump at all fails", code, 1, out.splitlines()[-1].strip() if out else "")
    case("...and says which file", "styles.css" in out, True)

    repo = new_repo(tmp)
    git(repo, "checkout", "-q", "-b", "b")
    write(repo, "README.md", "changed\n")
    commit(repo, "non-shell edit")
    case("a change to a file outside SHELL needs no bump", run(repo), (0, ""))

    repo = new_repo(tmp)
    git(repo, "checkout", "-q", "-b", "b")
    write(repo, "styles.css", "body{d}\n"); write(repo, "sw.js", SW % "quartets-v33")
    commit(repo, "shell edit + bump")
    case("a shell change with a bump passes", run(repo), (0, ""))

    # One generation per PUSH, not per PR: a branch that bumps twice is fine, and so is one that
    # jumps several. The rule is only that V ends up past the base's.
    write(repo, "styles.css", "body{e}\n"); write(repo, "sw.js", SW % "quartets-v37")
    commit(repo, "second bump on the same branch")
    case("a branch that bumps more than once is not punished for it", run(repo), (0, ""))

    # The tail ORDERS generations, so a lower one merges as the stale cache. Distinct message from
    # the equal case: "you did bump, just not far enough".
    repo = new_repo(tmp, "quartets-v40")
    git(repo, "checkout", "-q", "-b", "b")
    write(repo, "styles.css", "body{f}\n"); write(repo, "sw.js", SW % "quartets-v33")
    commit(repo, "backwards")
    code, out = run(repo)
    case("a V that goes backwards fails", code, 1)
    case("...and says what to bump past", "Bump past 40" in out, True, out.splitlines()[-1].strip())

    # A renamed stem is a deliberate reset (sw-lint's own rule 4: rename freely, keep the digits),
    # so the tails are not comparable and V simply differing is the whole answer.
    repo = new_repo(tmp, "quartets-v40")
    git(repo, "checkout", "-q", "-b", "b")
    write(repo, "styles.css", "body{g}\n"); write(repo, "sw.js", SW % "rebrand-v1")
    commit(repo, "rename the stem")
    case("a renamed stem is not read as going backwards", run(repo), (0, ""))

    # --- WHY THE TOUCHED SET COMES FROM THE MERGE BASE -------------------------------------------
    # main moves on with a shell change of its own. Diffed against main's TIP, that edit comes back
    # as a file this branch "touched" (in reverse), and a branch that changed nothing but README
    # would be told to bump. Diffed from the merge base, it is invisible, which is the same
    # property that makes this survive a rebase.
    repo = new_repo(tmp)
    git(repo, "checkout", "-q", "-b", "b")
    write(repo, "README.md", "branch\n")
    commit(repo, "docs only")
    git(repo, "checkout", "-q", "main")
    write(repo, "styles.css", "body{h}\n"); write(repo, "sw.js", SW % "quartets-v33")
    commit(repo, "someone else's shell change, properly bumped")
    git(repo, "checkout", "-q", "b")
    case("a base that moved ahead is not charged to this branch", run(repo), (0, ""))

    # --- REPORTED, NOT SKIPPED -------------------------------------------------------------------
    # An unrelated ref has no merge base, which is what a too-shallow CI checkout looks like. The
    # check must SAY it could not run; passing silently is the failure mode the whole issue is about.
    repo = new_repo(tmp)
    git(repo, "checkout", "-q", "--orphan", "island")
    write(repo, "sw.js", SW % "quartets-v32")
    commit(repo, "unrelated history")
    code, out = run(repo, "main")
    case("no shared history is reported, not passed over", code, 1, out.splitlines()[-1].strip() if out else "")
    case("...and names the fix", "fetch-depth" in out, True)

    code, out = subprocess.run([sys.executable, LINT, "--base"], cwd=repo,
                               capture_output=True, text=True).returncode, ""
    case("--base with no ref is an error, not a silent pass", code, 1)

    # --- --fix: THE BUMP IS DERIVED, NOT TYPED ---------------------------------------------------
    # Check 1 knows which files are SHELL, which of them are staged, and what V was. Everything it
    # needs in order to DO the bump, which is why the hook no longer asks for one. These cases are
    # about the staged result, not the message: what matters is that the commit about to be made
    # carries a new V and the author did not have to know that.
    repo = whole_repo(tmp)
    write(repo, "styles.css", "body{x}\n")
    git(repo, "add", "-A")
    code, out = run_fix(repo)
    case("--fix bumps the tail when a staged SHELL file would otherwise ship unseen",
         (code, staged_v(repo)), (0, "quartets-v33"), out.splitlines()[-1].strip() if out else "")
    case("...and re-stages sw.js, so the bump lands in the same commit",
         "sw.js" in git(repo, "diff", "--cached", "--name-only").split(), True)
    case("...and says so rather than bumping silently", "bumped" in out, True)
    case("...and the worktree matches the index afterwards",
         git(repo, "diff", "--name-only", "--", "sw.js").strip(), "")
    # Idempotent: V has now moved, so check 1 no longer fires and there is nothing to do.
    code2, _ = run_fix(repo)
    case("...and a second run does not bump again", (code2, staged_v(repo)), (0, "quartets-v33"))

    # Nothing staged that is precached: the tail must not move for a README commit.
    repo = whole_repo(tmp)
    write(repo, "README.md", "changed\n")
    git(repo, "add", "-A")
    code, out = run_fix(repo)
    case("--fix leaves V alone when no staged file is precached",
         (code, staged_v(repo), out), (0, "quartets-v32", ""))

    # Already bumped by hand: --fix has nothing to add, and must not stack a second generation.
    repo = whole_repo(tmp)
    write(repo, "styles.css", "body{y}\n"); write(repo, "sw.js", SW % "quartets-v40")
    git(repo, "add", "-A")
    code, _ = run_fix(repo)
    case("--fix does not bump a V that already moved", (code, staged_v(repo)), (0, "quartets-v40"))

    # DECLINES with unstaged sw.js edits, because `git add sw.js` would sweep work into this commit
    # that the author deliberately left out. The nag is the right answer there.
    repo = whole_repo(tmp)
    write(repo, "styles.css", "body{z}\n")
    git(repo, "add", "-A")
    write(repo, "sw.js", SW % "quartets-v32" + "// half-finished edit\n")
    code, out = run_fix(repo)
    case("--fix declines when sw.js has unstaged edits, and nags instead",
         (code, staged_v(repo), "bump V in sw.js" in out), (1, "quartets-v32", True))

    # DECLINES mid-merge: the resolution is the human's, and check 6 is what catches #32 in CI.
    repo = whole_repo(tmp)
    git(repo, "checkout", "-q", "-b", "other")
    write(repo, "styles.css", "body{one}\n"); commit(repo, "one")
    git(repo, "checkout", "-q", "main")
    write(repo, "styles.css", "body{two}\n"); commit(repo, "two")
    subprocess.run(("git", "merge", "other"), cwd=repo, capture_output=True, text=True)
    case("(the merge really did conflict, so MERGE_HEAD is there)",
         os.path.exists(os.path.join(repo, ".git", "MERGE_HEAD")), True)
    write(repo, "styles.css", "body{resolved}\n")
    git(repo, "add", "-A")
    code, out = run_fix(repo)
    case("--fix declines during a merge, and nags instead",
         (code, staged_v(repo), "bump V in sw.js" in out), (1, "quartets-v32", True))

    # A V with no tail is check 4's problem; --fix must not invent one.
    repo = whole_repo(tmp, v="quartets")
    write(repo, "styles.css", "body{w}\n")
    git(repo, "add", "-A")
    code, out = run_fix(repo)
    case("--fix declines a V with no numeric tail",
         (code, staged_v(repo), "numeric tail" in out), (1, "quartets", True))

    # --- --bump: THE ONE IMPLEMENTATION -----------------------------------------------------------
    # refresh.py calls this instead of carrying its own regex. No git in it: the monthly top-up
    # stages nothing, and the workflow commits afterwards.
    repo = whole_repo(tmp)
    r = subprocess.run([sys.executable, LINT, "--bump"], cwd=repo, capture_output=True, text=True)
    case("--bump increments the tail and prints the new V",
         (r.returncode, r.stdout.strip()), (0, "quartets-v33"))
    case("...in the worktree, staging nothing",
         git(repo, "diff", "--cached", "--name-only").strip(), "")
    r = subprocess.run([sys.executable, LINT, "--bump"], cwd=whole_repo(tmp, v="quartets"),
                       capture_output=True, text=True)
    case("--bump reports a V it cannot move rather than writing one", r.returncode, 1)

    # --- THE SHIPPED SCRIPT AGREES WITH THE SHIPPED sw.js ----------------------------------------
    # Not a scenario: the parser reads THIS repo's real SHELL block, so a reformat that breaks
    # shell_entries() fails here rather than by quietly matching nothing in CI.
    top = os.path.dirname(os.path.dirname(LINT))
    src = open(os.path.join(top, "sw.js")).read()
    spec = importlib.util.spec_from_file_location("swlint", LINT)   # the filename has a dash
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    case("the SHELL parser still reads the real sw.js", "./app.js" in mod.shell_entries(src), True,
         f"{len(mod.shell_entries(src))} entries")
    case("...and the real V still has a numeric tail", mod.tail_of(mod.ver(src)) is not None, True,
         mod.ver(src))

print()
if fails:
    print(f"{len(fails)} FAILED: " + ", ".join(fails))
    sys.exit(1)
print("all sw-lint --base and --fix cases pass")
