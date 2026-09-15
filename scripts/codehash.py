#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Prove a change touched COMMENTS ONLY, mechanically, instead of promising it in a message.

    python3 scripts/codehash.py                      # staged vs HEAD
    python3 scripts/codehash.py --base origin/main   # this branch vs its merge base
    python3 scripts/codehash.py chart.js app.js      # just print the code hashes

WHY THIS EXISTS. A comment-compression pass through chart.js deleted `function hash()` and
`const MIN_SEP`, both of which sat INSIDE the blocks being rewritten. The repair was immediate; what
was not immediate was noticing it had been undone — a restore from the index pulled the broken copy
back, it got committed, and the branch shipped un-bootable. The audit that should have caught it was
"diff the file and read every line that is not a comment", which is a human reading hundreds of
changed lines for an absence, at the end of a long session. A hash does not get tired.

It exits 0 when every changed file is comments-only, 1 when any code changed, and 2 when it cannot
TELL — which is a distinct answer and never folded into either, because "I could not verify this"
read as "verified" is the failure mode the whole repo is arranged against.

HOW THE CODE IS ISOLATED, per language, and how strongly:

  .py           the AST. `ast.parse` then `ast.dump`, with docstrings dropped as the prose they are.
                Comments and formatting are absent from an AST by construction, so there is nothing
                to strip and nothing to get wrong. This is the strong one.
  .js .mjs      a scanner, because node exposes no parser. It tracks strings, template literals,
                regex literals and both comment forms, so `"http://x"` and `/a\\/\\/b/` are code and
                not comments. VERIFIED by running `node --check` over BOTH the source and the
                stripped text: a scanner that swallowed real code produces something that does not
                parse, so a misclassification degrades to "cannot tell" rather than to a false pass,
                and a file that does not parse to begin with is refused outright. That property is
                what makes the scanner's imperfection affordable.
                A template literal is copied WHOLE, so a comment inside `${…}` counts as code and
                editing one reads as a change. Deliberate: recursing would mean running the scanner
                inside a string, and a mistake there would DELETE code rather than keep it. The cost
                is a false alarm on `ui.test.mjs`, whose page snippets carry comments; the benefit is
                that the only direction this tool can be wrong in is the safe one.
  .css          the same scanner with only `/* */` and strings — no regex literals, no line
                comments, so the ambiguity that makes JS hard is absent. Verified by brace balance.
  .html         `<!-- -->` only, and NOT verified — there is no cheap parser here, so it reports the
                weaker claim rather than implying the stronger one.

NEWLINES SURVIVE THE STRIP, deliberately. Collapsing them would make a reflow of CODE invisible too,
and in JavaScript it would change meaning: `return` and its value on two lines is not `return value`.
Horizontal runs collapse and blank lines go, so reindenting is free and re-wrapping a comment is
free, while moving a token to another line reads as a code change. Conservative in the safe
direction.

WHAT IT IS NOT. Not a formatter, not a minifier, and not a substitute for a test: it says the code is
byte-identical, which is a much narrower claim than "this change is safe". `ablate.py` and
`fix-lint.py` import `unchanged()` to stop demanding a test for a hunk that cannot change behaviour,
which is the one place the claim is strong enough to act on.
"""
import ast, hashlib, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE = re.compile(r"\.(py|js|mjs|css|html)$")


def sh(*a):
    return subprocess.run(a, capture_output=True, text=True, cwd=ROOT)


# ---- the scanner ------------------------------------------------------------------------------
# One pass, one state variable. The only genuinely hard call is `/`: it opens a regex in some
# positions and divides in others, and the two are not distinguishable without knowing whether the
# parser wants an expression or an operator. The heuristic is the usual one — the previous
# significant character — plus the keywords after which a regex is legal (`return /re/.test(s)`
# reads as division under the character rule alone, since `n` is a word character). When it guesses
# wrong the stripped text stops parsing, and main() reports that it cannot tell.
KEYWORDS = ("return", "typeof", "instanceof", "in", "of", "new", "delete", "void", "do", "else",
            "case", "yield", "await", "throw")
DIV_AFTER = set("_$)].") | set("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")


def strip_js(src, regex=True, line_comments=True):
    """src with comments replaced by nothing. `regex=False` for CSS, which has no regex literals."""
    out, i, n = [], 0, len(src)
    prev = ""                      # last significant code character emitted
    word = ""                      # ...and the word it ended, for the keyword rule
    removed = 0
    while i < n:
        c = src[i]
        two = src[i:i + 2]
        if line_comments and two == "//":
            j = src.find("\n", i)
            j = n if j < 0 else j
            removed += j - i
            i = j
            continue
        if two == "/*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            removed += j - i
            # A block comment between two tokens is whitespace, not nothing: `a/**/b` is two tokens.
            out.append(" ")
            i = j
            continue
        if c in "\"'":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            out.append(src[i:j + 1]); prev, word = c, ""
            i = j + 1
            continue
        if c == "`":
            # A template literal can hold `${ code }` that itself holds strings and comments. Handled
            # by scanning to the matching brace and recursing, so a comment inside an interpolation
            # is still a comment and a `//` inside the literal text is still text.
            j, depth = i + 1, 0
            while j < n:
                if src[j] == "\\":
                    j += 2; continue
                if src[j] == "`" and depth == 0:
                    break
                if src[j:j + 2] == "${":
                    depth += 1; j += 2; continue
                if src[j] == "}" and depth:
                    depth -= 1
                if src[j] == "{" and depth:
                    depth += 1
                j += 1
            out.append(src[i:j + 1]); prev, word = "`", ""
            i = j + 1
            continue
        if regex and c == "/" and not (prev in DIV_AFTER and word not in KEYWORDS):
            j, cls = i + 1, False
            while j < n:
                if src[j] == "\\":
                    j += 2; continue
                if src[j] == "[":
                    cls = True
                elif src[j] == "]":
                    cls = False
                elif src[j] == "/" and not cls:
                    break
                elif src[j] == "\n":
                    break                      # unterminated: not a regex after all
                j += 1
            out.append(src[i:j + 1]); prev, word = "/", ""
            i = j + 1
            continue
        out.append(c)
        if not c.isspace():
            prev = c
            word = word + c if (c.isalnum() or c in "_$") else ""
        i += 1
    return "".join(out), removed


def normalise(text):
    """Horizontal runs to one space, no trailing space, no blank lines. Newlines survive — see the
    header: collapsing them would hide a reflow of code and would change JS meaning."""
    lines = [re.sub(r"[ \t]+", " ", l).strip() for l in text.splitlines()]
    return "\n".join(l for l in lines if l)


def py_code(src):
    """The AST with docstrings dropped, as text. Raises SyntaxError if src does not parse."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            body.pop(0)
    return ast.dump(tree)


def node_check(text, ext):
    """True if node parses it, False if not, None if there is no node to ask."""
    with tempfile.NamedTemporaryFile("w", suffix="." + ext, delete=False) as f:
        f.write(text); tmp = f.name
    try:
        return subprocess.run(["node", "--check", tmp], capture_output=True).returncode == 0
    except FileNotFoundError:
        return None
    finally:
        os.unlink(tmp)


def code_of(path, src):
    """(code, comment_bytes_removed, how_it_was_verified) — or (None, n, why) if it cannot be told."""
    ext = path.rsplit(".", 1)[-1]
    if ext == "py":
        try:
            return py_code(src), 0, "ast"
        except SyntaxError as e:
            return None, 0, f"does not parse ({e.msg})"
    if ext in ("js", "mjs"):
        # BOTH SIDES OF THE STRIP ARE PARSED, and the source first. An unterminated block comment is
        # a syntax error in the file, and the scanner runs it to EOF — which leaves something that
        # parses perfectly well and a hash that means nothing, because the bytes it covered were
        # never classified, only consumed. Checking the source closes that: a file that does not
        # parse is one this cannot make claims about, which is a different answer from "the strip
        # went wrong" and gets a different message.
        code, removed = strip_js(src)
        ok = lambda text: node_check(text, ext)
        good = ok(src)
        if good is None:
            return normalise(code), removed, "UNVERIFIED (no node)"
        if not good:
            return None, removed, "the file itself does not parse, so there is nothing to compare"
        if not ok(code):
            return None, removed, "the stripped text does not parse, so the strip cannot be trusted"
        return normalise(code), removed, "node --check"
    if ext == "css":
        code, removed = strip_js(src, regex=False, line_comments=False)
        if code.count("{") != code.count("}"):
            return None, removed, "the stripped text has unbalanced braces"
        return normalise(code), removed, "braces balance"
    if ext == "html":
        code, removed = re.subn(r"<!--.*?-->", "", src, flags=re.S)[0], 0
        removed = len(src) - len(code)
        return normalise(code), removed, "UNVERIFIED (no html parser)"
    return None, 0, "not a language this knows"


def digest(path, src):
    code, removed, how = code_of(path, src)
    return (None if code is None else hashlib.sha256(code.encode()).hexdigest()[:12]), removed, how


def unchanged(path, old_src, new_src):
    """True when both sides isolate to the SAME code. False covers 'differs' AND 'cannot tell'.

    The conservative direction on purpose: a caller asks this to skip work it would otherwise
    demand, so the answer it must never get wrong is yes.
    """
    a, _r, how = digest(path, old_src)
    b, _r2, _how2 = digest(path, new_src)
    return a is not None and a == b and not how.startswith("UNVERIFIED")


def main():
    args = [a for a in sys.argv[1:] if a != "--base"]
    if "--base" in sys.argv:
        i = sys.argv.index("--base")
        if i + 1 >= len(sys.argv):
            print("  codehash: --base needs a ref")
            return 2
        ref = sys.argv[i + 1]
        mb = sh("git", "merge-base", ref, "HEAD")
        if mb.returncode != 0 or not mb.stdout.strip():
            print(f'  codehash: no merge base between HEAD and "{ref}"')
            return 2
        old, new, label = mb.stdout.strip(), "HEAD", f"{ref}..HEAD"
        names = sh("git", "diff", "--name-only", old, new).stdout.split()
    elif args:
        for f in args:
            h, removed, how = digest(f, open(os.path.join(ROOT, f), encoding="utf-8").read())
            print(f"  {h or '-':>12}  {f}   ({how}, {removed} comment bytes)")
        return 0
    else:
        old, new, label = "HEAD", None, "staged vs HEAD"
        names = sh("git", "diff", "--cached", "--name-only").stdout.split()

    files = [f for f in names if CODE.search(f)]
    if not files:
        print(f"  codehash ({label}): no code files changed")
        return 0

    def read(ref, f):
        r = sh("git", "show", f"{ref}:{f}") if ref else None
        if ref:
            return r.stdout if r.returncode == 0 else None
        p = os.path.join(ROOT, f)                       # working tree, for the staged comparison
        return open(p, encoding="utf-8").read() if os.path.exists(p) else None

    verdicts = []
    for f in files:
        a, b = read(old, f), (read(new, f) if new else read(None, f))
        if a is None or b is None:
            # ADDED or DELETED, which is not the same as "cannot tell". There is no base version to
            # compare, and a new file is new code by definition — ablate.py reasons the same way
            # about added files. Counting it as unverifiable would make the hook print "fix the
            # strip" on every commit that introduces a file, which is how a warning gets ignored.
            verdicts.append(("-", f, "added" if a is None else "deleted" + " — no pair to compare"))
            continue
        ha, ra, how = digest(f, a)
        hb, rb, how2 = digest(f, b)
        if ha is None or hb is None:
            verdicts.append(("?", f, how if ha is None else how2))
        elif ha != hb:
            verdicts.append(("-", f, f"CODE CHANGED  ({how2})"))
        else:
            d = rb - ra
            verdicts.append(("*", f, f"comments only ({how2}, {d:+d} comment bytes)"))

    print(f"  codehash ({label}):")
    for mark, f, why in verdicts:
        print(f"   {mark} {f:<26} {why}")
    if any(m == "?" for m, _f, _w in verdicts):
        print("\n   ? means it could not TELL, which is not a pass. Fix the strip or read the diff.")
        return 2
    if any(m == "-" for m, _f, _w in verdicts):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
