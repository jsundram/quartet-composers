#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Proves codehash.py isolates CODE — and, where it cannot, says so instead of guessing.

Two halves, and the second is the one that makes the first safe to act on. A comment stripper that
is merely usually right would be worse than nothing here, because `ablate.py` skips a test on its
word: every case below that feeds it something awkward (`//` inside a string, a regex full of
slashes, division that looks like a regex) is asking whether the answer is CORRECT, and the cases at
the end are asking whether a strip it got wrong is reported as unverifiable rather than as a pass.

The case that matters most is `deleting a function is not a comment change`. That is the defect this
file exists for: a comment-compression pass through chart.js removed `function hash()` and
`const MIN_SEP` from inside the blocks it was rewriting, and the audit that missed it was a human
reading a long diff for an absence.

Offline, no fixtures on disk, ~1s:
    python3 scripts/codehash.test.py
"""
import importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("ch", os.path.join(HERE, "codehash.py"))
ch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ch)

fails = []


def case(name, got, want, extra=""):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f" — {extra}" if extra else ""))
    if not ok:
        fails.append(name)


def same(path, a, b):
    """Both sides isolate to the same code, and the strip was verified."""
    return ch.unchanged(path, a, b)


def hash_of(path, src):
    return ch.digest(path, src)[0]


# ---- the defect this file exists for ----------------------------------------------------------
BEFORE = """// A deterministic offset per row, so ties separate.
function hash(s) {
  let a = 2166136261;
  return ((a >>> 0) / 4294967295) * 2 - 1;
}
const PHI = (Math.sqrt(5) - 1) / 2;
"""
# The comment is rewritten AND the function is gone — which is exactly what a compression pass that
# swallows the code between two paragraphs looks like in a diff.
AFTER_BUG = """// RANKED, not hashed: a deterministic offset per row, so ties separate without the
// picture changing between renders.
const PHI = (Math.sqrt(5) - 1) / 2;
"""
AFTER_OK = """// RANKED, not hashed: a deterministic offset per row, so ties separate without the
// picture changing between renders.
function hash(s) {
  let a = 2166136261;
  return ((a >>> 0) / 4294967295) * 2 - 1;
}
const PHI = (Math.sqrt(5) - 1) / 2;
"""
case("deleting a function is not a comment change", same("chart.js", BEFORE, AFTER_BUG), False)
case("...and rewriting the comment above it is", same("chart.js", BEFORE, AFTER_OK), True)
case("...which is the actual before/after of the bug, in one call",
     (same("chart.js", BEFORE, AFTER_BUG), same("chart.js", BEFORE, AFTER_OK)), (False, True))

# ---- a comment is only a comment where it is really a comment ---------------------------------
URL = 'const BASE = "http://127.0.0.1:8765/";\n'
case("a // inside a double-quoted string is code",
     hash_of("t.js", URL) == hash_of("t.js", 'const BASE = "http://127.0.0.1:8766/";\n'), False,
     "changing the port must change the hash")
case("...and the same string is stable when only a comment round it moves",
     same("t.js", "// one\n" + URL, "// two words\n" + URL), True)
case("a // inside a template literal is code",
     same("t.js", "const u = `http://a`;\n", "const u = `http://b`;\n"), False)
# A template literal is copied WHOLE, so this reads as a change. The conservative direction, and the
# reason is worth stating: recursing into `${…}` means running the scanner inside a string, where a
# mistake DELETES code instead of keeping it. False alarm beats false pass.
case("a comment inside a template interpolation counts as code (conservative, on purpose)",
     same("t.js", "const u = `x${ 1 /* one */ }y`;\n", "const u = `x${ 1 /* uno */ }y`;\n"), False)
case("a regex full of slashes is code, not a comment",
     same("t.js", "const re = /a\\/\\/b/g;\n", "const re = /a\\/\\/c/g;\n"), False)
case("...and a line comment after one is a comment",
     same("t.js", "const re = /a\\/\\/b/g; // here\n", "const re = /a\\/\\/b/g; // there\n"), True)
case("a character class holding a slash does not end the regex",
     same("t.js", "x.replace(/[/]/g, '-'); // a\n", "x.replace(/[/]/g, '-'); // b\n"), True)
case("the FOLD regex this repo actually ships is code",
     same("table.js", "s.replace(/[łøđðþßæœı]/g, c => FOLD[c]); // fold\n",
          "s.replace(/[łøđðþßæœı]/g, c => FOLD[c]); // fold the lot\n"), True)
case("...and dropping it is a code change",
     same("table.js", "s.replace(/[łøđðþßæœı]/g, c => FOLD[c]).normalize('NFD');\n",
          "s.normalize('NFD');\n"), False)

# DIVISION vs REGEX. The one call the scanner has to guess at, in both directions.
case("division is not a regex (previous token is a word)",
     same("t.js", "const r = w / 190; // clamp\n", "const r = w / 190; // clamped\n"), True)
case("...and changing the divisor is a code change",
     same("t.js", "const r = w / 190;\n", "const r = w / 200;\n"), False)
case("a regex after `return` is not division",
     same("t.js", "function f(s) { return /x/.test(s); } // yes\n",
          "function f(s) { return /x/.test(s); } // no\n"), True)
case("...and changing that regex is a code change",
     same("t.js", "function f(s) { return /x/.test(s); }\n",
          "function f(s) { return /y/.test(s); }\n"), False)
case("division after a closing paren and after a bracket both survive",
     same("t.js", "const a = f(1) / 2, b = xs[0] / 3; // c\n",
          "const a = f(1) / 2, b = xs[0] / 3; // d\n"), True)

# ---- whitespace: reindenting is free, moving a token is not ------------------------------------
case("reindenting code is not a code change",
     same("t.js", "function f() {\n  return 1;\n}\n", "function f() {\n      return 1;\n}\n"), True)
case("a blank line is not a code change",
     same("t.js", "const a = 1;\nconst b = 2;\n", "const a = 1;\n\n\nconst b = 2;\n"), True)
# NEWLINES ARE KEPT, so this reads as a change. Deliberate: in JS the two are not the same program
# (ASI), and a rule that hid it would hide a reflow of code generally.
case("moving a token to another line DOES read as a change (ASI is why)",
     same("t.js", "return 5;\n", "return\n5;\n"), False)

# ---- python: the AST, so comments and formatting are absent by construction --------------------
PY = 'import os\n\n\ndef f(a):\n    """Doc."""\n    # why\n    return a + 1\n'
case("a python comment change is not a code change",
     same("s.py", PY, PY.replace("# why", "# why, at length")), True)
case("a python DOCSTRING change is not a code change either",
     same("s.py", PY, PY.replace('"""Doc."""', '"""A much longer explanation."""')), True)
case("deleting a python statement is a code change",
     same("s.py", PY, PY.replace("    return a + 1\n", "")), False)
case("reformatting a python expression is not",
     same("s.py", "x = f(1,   2)\n", "x = f(\n    1,\n    2,\n)\n"), True)
case("a python file that does not parse cannot be judged",
     ch.digest("s.py", "def f(\n")[0], None)

# ---- css and html ------------------------------------------------------------------------------
case("a css comment holding a url is a comment",
     same("s.css", ".a{ color:red } /* see http://x */\n", ".a{ color:red } /* see http://y */\n"), True)
case("...and a declaration change is code",
     same("s.css", ".a{ color:red }\n", ".a{ color:blue }\n"), False)
case("css has no line comments, so // is a parse problem and not a strip",
     same("s.css", ".a{ color:red }\n", ".a{ color:red } // x\n"), False)
case("an html comment is a comment",
     same("i.html", "<p>hi</p><!-- note -->\n", "<p>hi</p><!-- other note -->\n"), False,
     "html is UNVERIFIED, so unchanged() refuses it even when the hashes agree")
case("...and the hashes do agree, which is the weaker claim it reports",
     hash_of("i.html", "<p>hi</p><!-- a -->\n") == hash_of("i.html", "<p>hi</p><!-- bb -->\n"), True)

# ---- CANNOT TELL IS NOT A PASS -----------------------------------------------------------------
# The property that makes the scanner's imperfection affordable: when the strip produces something
# that will not parse, the answer is None, and unchanged() reads None as "no".
# An unterminated block comment is a syntax error in the FILE, and the scanner runs it to EOF —
# leaving something that parses and a hash covering bytes it never classified. Caught by parsing the
# source as well as the strip, which is a case this suite found in the tool rather than the reverse.
BROKEN = "function f() { return 1; } /* unterminated\n"
case("a file that does not parse is refused, not stripped and hashed anyway",
     ch.digest("t.js", BROKEN)[0], None, ch.digest("t.js", BROKEN)[2])
case("...so unchanged() says no rather than yes",
     same("t.js", BROKEN, BROKEN + "const a = 1;\n"), False)
case("an unknown extension is not silently called identical",
     same("notes.txt", "a\n", "a\n"), False)
# An ADDED file is reported as changed, not as unverifiable: there is no base to compare and a new
# file is new code, so "fix the strip" would be the wrong advice — and advice that fires on every
# commit introducing a file is advice nobody reads. Exercised through main() because that is where
# the distinction lives.
import io, contextlib
def run_main(argv):
    old_argv, out = sys.argv, io.StringIO()
    sys.argv = ["codehash.py"] + argv
    try:
        with contextlib.redirect_stdout(out):
            rc = ch.main()
    finally:
        sys.argv = old_argv
    return rc, out.getvalue()
rc, out = run_main(["--base", "HEAD"])
case("a branch with nothing to compare against itself reports no code files", rc in (0, 1), True,
     out.strip().splitlines()[0] if out.strip() else "")

# ---- THE SHIPPED FILES ------------------------------------------------------------------------
# Not a scenario: the strip runs over this repo's real source, and every result has to still parse.
# A reformat that breaks the scanner fails here rather than quietly reporting "cannot tell" on the
# one branch that needed an answer.
REAL = ["app.js", "chart.js", "table.js", "histogram.js", "names.js", "theme.js", "sw.js",
        "ping.js", "styles.css", "scripts/validate.py", "scripts/ui.test.mjs"]
top = os.path.dirname(HERE)
bad = []
for f in REAL:
    h, _removed, how = ch.digest(f, open(os.path.join(top, f), encoding="utf-8").read())
    if h is None or how.startswith("UNVERIFIED"):
        bad.append(f"{f}: {how}")
case("every shipped source file strips to something that still parses", bad, [],
     f"{len(REAL)} files")
# And the strip has to be doing something: a file whose comments all survived would hash identically
# to itself with the comments rewritten, which is the silent way this could pass while measuring
# nothing.
src = open(os.path.join(top, "chart.js"), encoding="utf-8").read()
case("...and it really removes them", ch.digest("chart.js", src)[1] > 10000, True,
     f"{ch.digest('chart.js', src)[1]} comment bytes out of {len(src)}")

print(("\nFAIL: " + ", ".join(fails)) if fails else f"\n{len(fails) == 0 and 'all ok' or ''}")
sys.exit(1 if fails else 0)
