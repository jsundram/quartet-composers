#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Proves sw-lint.py's --base check catches the incident it was written for, and nothing else.

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
print("all sw-lint --base cases pass")
