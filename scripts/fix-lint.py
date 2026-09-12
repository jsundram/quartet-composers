#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""A branch that changes source must change a test — or say in a trailer why it doesn't.

This is the cheap half of the pair. `ablate.py` proves a test actually catches the change; this
only notices that no test was touched at all, which is the failure that costs the most rounds
because it is invisible: the suite is green, so nothing on screen says the fix is unproven.

It is a BRANCH question and so needs a second ref, for the same reason sw-lint.py's sixth check
does — what the branch changed is read from the merge base, which is the diff a rebase, a squash
and a stacked branch all leave alone. The pre-commit hook can never answer it: a branch's first
commit legitimately has no test yet.

The escape hatch is a `No-test: <reason>` trailer on the commit that changed source, shared with
ablate.py so there is one sentence to write and one place to look. It is deliberately a trailer
and not a path allowlist: a comment fix, a pure rename and a data regeneration are all real, and
each is a judgement about THIS change that belongs in the log where a reviewer reads it. An
allowlist would make that judgement once, in advance, for changes nobody had seen yet.

    python3 scripts/fix-lint.py --base origin/main
"""
import os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# What counts as source and what counts as a test are defined ONCE, in ablate.py, and
# imported — the two gates ask the same question and a second copy would drift. No bytecode, for
# the reason ablate.py gives: a gate that litters the tree it is judging cannot claim to restore it.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import ablate
SOURCE, TESTS = ablate.SOURCE, ablate.TESTS


def sh(*a):
    return subprocess.run(a, capture_output=True, text=True, cwd=ROOT)


def main():
    if "--base" not in sys.argv:
        print("usage: python3 scripts/fix-lint.py --base REF")
        return 2
    i = sys.argv.index("--base")
    if i + 1 >= len(sys.argv):
        print("  fix-lint: --base needs a ref to compare against")
        return 2
    base = sys.argv[i + 1]

    mb = sh("git", "merge-base", base, "HEAD")
    if mb.returncode != 0:
        print(f'  fix-lint:\n   - no merge base between HEAD and "{base}" — with a shallow '
              f"checkout there is nothing to compare against; fetch-depth 0 in CI")
        return 2
    mb = mb.stdout.strip()

    d = sh("git", "diff", "--name-only", mb, "HEAD")
    if d.returncode != 0:
        print(f"  fix-lint:\n   - could not diff {mb[:8]}..HEAD")
        return 2
    files = [f for f in d.stdout.splitlines() if f]

    src = [f for f in files if SOURCE.match(f)]
    tests = [f for f in files if TESTS.match(f)]
    # The SAME exemption ablate.py applies, imported rather than restated, or the two gates give
    # opposite verdicts on one branch. The monthly refresh branch that refresh.yml pushes changes
    # composers.json, readership.json and data/, bumps V in sw.js, touches no test and carries no
    # trailer — so src was ["sw.js"] and this failed it while ablate.py exempted it. Latent only
    # because a GITHUB_TOKEN PR does not trigger checks.yml; any human-opened regeneration hits it.
    if "sw.js" in src and ablate.only_a_version_bump(mb):
        src = [f for f in src if f != "sw.js"]
    # And the same for a file whose CODE is unchanged, for the same reason in a second shape: if
    # ablate.py exempts a comments-only hunk and this does not, one branch gets opposite verdicts
    # from the pair and the trailer becomes the only way through — which is how `No-test:` stops
    # being a sentence somebody meant and becomes a thing you type to get past the gate.
    src = [f for f in src if not ablate.only_comments(mb, f)]
    if not src or tests:
        return 0

    # ablate.excused(), imported rather than restated — the third exemption shared with the other
    # gate, and the one that had drifted into two copies of the same regex. It is scoped to commits
    # that changed SOURCE, so a docs-only commit's trailer no longer excuses somebody else's code.
    why = ablate.excused(mb)
    if why:
        print(f"  fix-lint: no test on this branch, excused — {why}")
        return 0

    print("  fix-lint:")
    print(f"   - this branch changes source and no test, against {mb[:8]}:")
    for f in src:
        print(f"       {f}")
    print("\n   A fix ships with the test that goes red without it — not with the next review.")
    print("   If this one genuinely has no test to write (a comment, a rename, a regeneration),")
    print("   say so in the log:  git commit --amend -m \"$(git log -1 --format=%B)")
    print("")
    print("   No-test: <why there is nothing to assert>\"")
    return 1


if __name__ == "__main__":
    sys.exit(main())
