#!/usr/bin/env python3
# pwa-starter: sw-lint.py @ d2fad01  (+ the --base branch check)
# /// script
# requires-python = ">=3.9"
# ///
"""Commit-time checks for sw.js's precache contract.

sw.js precaches the app SHELL. Five mistakes are cheap to catch here and expensive at runtime:

1. A staged SHELL file with an unchanged V. An edit to a precached file only reaches installed
   clients when V changes — forget the bump and the fix ships to the repo but never to anyone's
   home-screen copy. The single most common PWA deploy bug.
2. A SHELL entry that doesn't exist on disk. It can never be fetched, so it permanently wedges
   the old-generation collect: both cache generations pile up on every device, with the stale one
   still answering via the whole-store fallback. (#7)
3. A cross-origin SHELL entry. The fetch handler passes other origins straight through, so the
   entry would be cached but never served — vendor the file locally instead.
4. A V without a numeric tail. The tail orders generations for sw.js's collect and app.js's
   checkVer() ranking; a non-numeric V makes collection silently stop, no error, no symptom,
   until caches pile up. Rename the stem freely — keep the digits.
5. app.js's VER_PREFIX not matching V's stem. checkVer() ranks installed caches by that prefix,
   so a renamed stem on one side only makes the version tag go blank (no cache matches) or read
   a sibling app's caches — silently, since nothing throws. The stems must agree. (#7)

Check 1 reads the INDEX, so it only ever bites in the pre-commit hook, and it is blind to what a
branch does as a whole. Two PRs off one base can each bump v32 -> v33 byte-identically; a
three-way merge resolves that silently, and the second one lands its shell changes with a net V
delta of zero (#32). Hence the sixth check, which needs a second commit to compare against and so
takes it as an argument:

6. `--base REF`: a branch that changes shell files without carrying V past the one REF is
   already on. What the branch CHANGED is read from the merge base (the diff a rebase, a squash
   and a stacked branch all leave alone); which V it must CLEAR is read from REF's tip, which is
   what it is about to merge into — against the merge base instead, the motivating case passes,
   since both PRs did differ from their own v32 base. It replaces the other five rather than
   joining them, being a different question asked with different information, and it is where CI
   earns its keep: CI has both sides of the merge and the hook has neither.

The pre-commit hook runs the first five warn-only; run them in CI with a real exit code, and the
sixth on pull requests with the base sha. By hand:
    python3 scripts/sw-lint.py
    python3 scripts/sw-lint.py --base origin/main
"""
import os, re, subprocess, sys


def sh(*a):
    return subprocess.run(a, capture_output=True, text=True)


def ver(src):
    # Anchored to the DECLARATION — the same expression app.js's checkVer() uses (keep them in
    # agreement). sw.js's comments cite version names as examples, so a first-match-anywhere
    # scan would read a comment.
    m = re.search(r'const V\s*=\s*"([^"]*)"', src)
    return m.group(1) if m else None


def shell_entries(src):
    m = re.search(r"const SHELL\s*=\s*\[(.*?)\]", src, re.S)
    if not m:
        return []
    # Alternation, not a strip pass: deleting //-comments first would also eat the "//" inside a
    # cross-origin URL plus every entry after it on that line — failing open on exactly what the
    # cross-origin check exists to catch. Scanning left to right, a comment consumes any strings
    # it contains, so a commented-out entry ('// "./old-page.html",') is correctly ignored.
    return [s for s in re.findall(r'//[^\n]*|"([^"]+)"', m.group(1)) if s]


def tail_of(v):
    m = re.search(r"(\d+)$", v or "")
    return int(m.group(1)) if m else None


# Check 6. The hook cannot ask this: it sees one commit against its parent, so a branch that bumps
# v32 -> v33 from a base that has since become v33 looks correct at every step and still merges to
# a net delta of zero. CI has both sides.
#
# Two references, deliberately, because the two halves are different questions:
#   - WHAT THIS BRANCH CHANGED is measured from the MERGE BASE, so a base that moved ahead does not
#     show up as files this branch touched. That is also the diff a rebase, a squash and a stacked
#     branch all leave unchanged.
#   - WHICH V IT HAS TO CLEAR is REF's TIP, because the tip is what it is about to merge into.
#     Against the merge base instead, the motivating case passes: both PRs bumped v32 -> v33 off a
#     v32 base, so each one differs from its own merge base and the second still lands a net zero.
#
# Everything here is REPORTED rather than skipped, including "I could not read the base". Silence
# is what opened the hole in the first place — a check that passes when it could not run is a check
# that reports an answer it does not have.
def base_check(ref):
    mb = sh("git", "merge-base", ref, "HEAD")
    if mb.returncode != 0 or not mb.stdout.strip():
        return [f'no merge base between HEAD and "{ref}" — with a shallow checkout there is '
                "nothing to compare V against, so this check cannot run. Fetch enough history "
                "(actions/checkout with fetch-depth: 0) rather than letting it pass silently."]
    mb = mb.stdout.strip()

    head, base = sh("git", "show", "HEAD:sw.js"), sh("git", "show", f"{ref}:sw.js")
    if head.returncode != 0 or base.returncode != 0:
        return []                                 # sw.js added on this branch: no prior V to hold
    v, old = ver(head.stdout), ver(base.stdout)
    if v is None or old is None:
        return []                                 # no declaration to read; checks 1-5 own that

    # The UNION of both SHELL lists, because dropping an entry is itself a shell change: clients
    # that already cached it keep serving it out of the old generation until V moves.
    shell = {e.lstrip("./") for src in (head.stdout, base.stdout)
             for e in shell_entries(src) if "://" not in e and e.strip("./")}
    diff = sh("git", "diff", "--name-only", mb, "HEAD")
    touched = sorted(set(diff.stdout.split()) & shell)
    if not touched:
        return []

    files = ", ".join(touched)
    if v == old:
        return [f'V is "{v}" on both this branch and {ref}, but the branch changes precached '
                f"shell files ({files}) — merging it leaves every installed client on the cached "
                "version. Bump V in sw.js."]
    # Any bump clears it (one generation per push is fine); the tail must only ever go UP, because
    # both sw.js's collect and app.js's checkVer() rank generations by it and would read a lower
    # number as the older cache. A renamed stem is a deliberate reset, so the tails are not
    # comparable and V simply differing is the whole answer.
    stem, old_stem = re.sub(r"\d+$", "", v), re.sub(r"\d+$", "", old)
    if stem == old_stem:
        t, ot = tail_of(v), tail_of(old)
        if t is not None and ot is not None and t < ot:
            return [f'V is "{v}" but {ref} is already on "{old}", and the branch changes precached '
                    f"shell files ({files}) — the numeric tail orders cache generations, so this "
                    f"one would be collected as the stale one. Bump past {ot}."]
    return []


def main():
    if "--base" in sys.argv:
        i = sys.argv.index("--base")
        if i + 1 >= len(sys.argv):
            print("  sw.js:\n   - --base needs a ref to compare against")
            return 1
        problems = base_check(sys.argv[i + 1])
        if not problems:
            return 0
        print("  sw.js:")
        for p in problems:
            print(f"   - {p}")
        return 1

    idx = sh("git", "show", ":sw.js")            # staged sw.js
    if idx.returncode != 0:
        return 0                                  # no sw.js in the index / not a repo
    src = idx.stdout
    v = ver(src)
    entries = shell_entries(src)
    problems = []

    if v is not None and not re.search(r"\d+$", v):
        problems.append(f'V is "{v}", which has no numeric tail. The tail orders cache '
                        "generations (sw.js's collect, app.js's ranking) — rename the stem "
                        "freely, but keep the digits.")

    # Downstream copies don't always vendor app.js (some graft only the version-tag region, some
    # skip it), so a missing file or a missing declaration is silence, not a problem.
    app = sh("git", "show", ":app.js")
    if v is not None and app.returncode == 0:
        m = re.search(r'const VER_PREFIX\s*=\s*"([^"]*)"', app.stdout)
        stem = re.sub(r"\d+$", "", v)
        if m and m.group(1) != stem:
            problems.append(f'app.js\'s VER_PREFIX is "{m.group(1)}" but sw.js\'s V stem is '
                            f'"{stem}" — checkVer() ranks caches by that prefix, so the version '
                            "tag silently stops tracking this app. Keep the two in agreement.")

    top = sh("git", "rev-parse", "--show-toplevel").stdout.strip()
    for entry in entries:
        if "://" in entry:
            problems.append(f'SHELL entry "{entry}" is cross-origin — the fetch handler passes '
                            "other origins straight through, so it caches but never serves. "
                            "Vendor the file locally.")
            continue
        p = entry.lstrip("./")
        if not p:
            continue                              # "./" — the scope root, served as index.html
        if p.endswith("/"):
            p += "index.html"                     # a directory entry serves its index.html
        if top and not os.path.exists(os.path.join(top, p)):
            problems.append(f'SHELL entry "{entry}" doesn\'t exist ({p}) — an unfetchable entry '
                            "wedges the old-generation collect on every device. Fix the path, or "
                            "generate the file (icons: scripts/make-icons.sh).")

    shell = {e.lstrip("./") for e in entries if "://" not in e and e.strip("./")}
    staged = set(sh("git", "diff", "--cached", "--name-only").stdout.split())
    touched = sorted((staged & shell) - {"sw.js"})
    if touched:
        head = sh("git", "show", "HEAD:sw.js")
        old = ver(head.stdout) if head.returncode == 0 else None
        if old is not None and v == old:          # not the first commit, and V unchanged
            problems.append(f'V is still "{v}" but this commit changes precached shell files '
                            f'({", ".join(touched)}) — bump V in sw.js or installed clients '
                            "keep the cached version.")

    if not problems:
        return 0
    print("  sw.js:")
    for p in problems:
        print(f"   - {p}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
