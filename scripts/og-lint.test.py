#!/usr/bin/env python3
# pwa-starter: none — this script is this repo's own
# /// script
# requires-python = ">=3.9"
# ///
"""Prove og-lint.py --fix moves a stated count with its own measure, and only then. Offline.

    python3 scripts/og-lint.test.py
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("og_lint", os.path.join(HERE, "og-lint.py"))
og = importlib.util.module_from_spec(spec)
spec.loader.exec_module(og)

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def rows(counted, uncounted):
    return [["c%d" % i, 1800, 1850, 4] for i in range(counted)] + \
           [["u%d" % i, 1800, 1850, None] for i in range(uncounted)]


@case("a newcomer with a count moves both the roster and the plotted number")
def both_move(_):
    got = og.moves(rows(5, 2), rows(6, 2))
    assert got == {7: 8, 5: 6}, got


@case("a newcomer with no count moves the roster and leaves the plotted number")
def roster_only(_):
    got = og.moves(rows(5, 2), rows(5, 3))
    assert got == {7: 8}, got


@case("two measures that agreed and then parted are ambiguous, so nothing is guessed")
def ambiguous(_):
    assert og.moves(rows(5, 0), rows(5, 1)) == {}, og.moves(rows(5, 0), rows(5, 1))


@case("each phrasing of the count is rewritten, and an unrelated number is left alone")
def rewrite(_):
    text = ('"790 string quartet composers, plotted" · content="790 quartet composers: '
            'their" · 885 composers · 790 quartets')
    got = og.rewrite(text, {790: 791})
    assert got == ('"791 string quartet composers, plotted" · content="791 quartet composers: '
                   'their" · 885 composers · 790 quartets'), got


def main():
    passed = failed = 0
    for name, fn in CASES:
        try:
            fn(None)
            print("  ok   - %s" % name)
            passed += 1
        except AssertionError as e:
            print("  FAIL - %s\n       %s" % (name, e))
            failed += 1
        except Exception as e:                         # noqa: BLE001 - a raise is a FAIL, see imslp.test.py
            print("  FAIL - %s\n       raised: %s: %s" % (name, type(e).__name__, e))
            failed += 1
    print("\n%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
