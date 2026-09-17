#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Prove setup.sh enables the hook, is safe to re-run, and never takes over somebody else's answer.

    python3 scripts/setup.test.py

NO NETWORK: every case is a throwaway git repo in a temp dir, the same harness sw-lint.test.py uses.

WHY IT EXISTS. What the script prevents is a SILENCE — a clone whose pre-commit lints never run —
so the script failing is that same silence one level up, and CI can testify neither way because CI
never runs the hook. The two cases that matter are the ones nobody would think to try: re-running
must be a no-op, since the session hook runs it EVERY session, and a core.hooksPath already
pointing elsewhere must survive.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SETUP = os.path.join(HERE, "setup.sh")
CASES, FAILED = [], []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def git(repo, *a):
    r = subprocess.run(("git",) + a, cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(a)}: {r.stderr.strip()}")
    return r.stdout.strip()


def new_repo(tmp):
    """A checkout with setup.sh where setup.sh expects to be: it cds relative to its own path."""
    repo = tempfile.mkdtemp(dir=tmp)
    git(repo, "init", "-q", "-b", "main")
    os.mkdir(os.path.join(repo, "scripts"))
    with open(SETUP) as f:
        body = f.read()
    dst = os.path.join(repo, "scripts", "setup.sh")
    with open(dst, "w") as f:
        f.write(body)
    os.chmod(dst, 0o755)
    return repo


def run(repo, *args):
    r = subprocess.run(["bash", os.path.join(repo, "scripts", "setup.sh"), *args],
                       cwd=repo, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def hooks_path(repo):
    r = subprocess.run(("git", "config", "--local", "--get", "core.hooksPath"),
                       cwd=repo, capture_output=True, text=True)
    return r.stdout.strip()


@case("a fresh clone comes out with the hook enabled")
def enables(tmp):
    repo = new_repo(tmp)
    assert hooks_path(repo) == "", "the premise: a clone starts with it unset"
    code, out = run(repo)
    assert code == 0, out
    assert hooks_path(repo) == ".githooks", hooks_path(repo)


@case("running it again changes nothing and still succeeds")
def idempotent(tmp):
    # The second run is the common one, not the rare one: the session hook runs this every time.
    repo = new_repo(tmp)
    run(repo)
    code, out = run(repo)
    assert code == 0, out
    assert hooks_path(repo) == ".githooks", hooks_path(repo)
    assert "enabled" in out, out


@case("a core.hooksPath somebody else set is left exactly as it was")
def never_clobbers(tmp):
    # Taking over a deliberate arrangement is worse than the problem this fixes, so it reports and
    # stops — and the EXIT CODE has to say so, since nothing reads stderr.
    repo = new_repo(tmp)
    git(repo, "config", "--local", "core.hooksPath", "my-hooks")
    code, out = run(repo)
    assert hooks_path(repo) == "my-hooks", "it overwrote a deliberate setting: " + hooks_path(repo)
    assert code != 0, "a clone whose lints will not run must not report success"
    assert "my-hooks" in out, out


@case("--check reports without enabling, in both directions")
def check_is_read_only(tmp):
    # If --check ever enabled anything, the one mode that promises to touch nothing would be the
    # one that changed the clone.
    repo = new_repo(tmp)
    code, out = run(repo, "--check")
    assert code == 1, out
    assert hooks_path(repo) == "", "--check enabled it: " + hooks_path(repo)
    run(repo)
    code, out = run(repo, "--check")
    assert code == 0, out


@case("an argument it does not know writes nothing, rather than falling through to the write")
def unknown_arg(tmp):
    # Testing `$1` for equality with --check makes every OTHER argument a plain run, so `-check`,
    # a typo, or a future --dry-run took the write path — the one invocation whose whole promise
    # is "change nothing" changing the clone, silently and with exit 0.
    for arg in ("--dry-run", "-check", "--checkk", "check"):
        repo = new_repo(tmp)
        code, out = run(repo, arg)
        assert hooks_path(repo) == "", f"{arg} enabled the hook: " + hooks_path(repo)
        assert code == 2, f"{arg} -> exit {code}: {out}"
        assert arg in out, out


@case("outside a git checkout it fails rather than reporting success")
def not_a_repo(tmp):
    # `git config --local` outside a repo errors and `|| true` swallows it, so without the rev-parse
    # guard this falls through to the write and dies under `set -e` saying nothing useful.
    loose = tempfile.mkdtemp(dir=tmp)
    os.mkdir(os.path.join(loose, "scripts"))
    with open(SETUP) as f:
        body = f.read()
    dst = os.path.join(loose, "scripts", "setup.sh")
    with open(dst, "w") as f:
        f.write(body)
    r = subprocess.run(["bash", dst], cwd=loose, capture_output=True, text=True)
    assert r.returncode != 0, "it reported success outside a checkout"
    assert "not a git checkout" in (r.stdout + r.stderr), (r.stdout + r.stderr)


@case("the session-start hook runs THIS script, and the README says to as well")
def wired_up(_):
    # Two entry points, one per audience. Either quietly renamed leaves a setup step nothing
    # performs — and both still "work", so only a check notices.
    root = os.path.dirname(HERE)
    hook = os.path.join(root, ".claude", "hooks", "session-start.sh")
    assert os.path.exists(hook), "no .claude/hooks/session-start.sh"
    assert "scripts/setup.sh" in open(hook).read(), "the session hook does not run setup.sh"
    readme = open(os.path.join(root, "README.md")).read()
    assert "scripts/setup.sh" in readme, "the README does not tell a human to run it"


def main():
    with tempfile.TemporaryDirectory() as tmp:
        for name, fn in CASES:
            try:
                fn(tmp)
                print("  ok   %s" % name)
            except Exception as e:
                FAILED.append(name)
                print("  FAIL %s\n       %s: %s" % (name, type(e).__name__, e))
    print("\n%d passed, %d failed" % (len(CASES) - len(FAILED), len(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
