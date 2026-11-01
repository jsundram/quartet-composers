#!/usr/bin/env python3
# pwa-starter: none — this script is this repo's own
# /// script
# requires-python = ">=3.9"
# ///
"""Prove scripts/fetch_wikidata.py's request helper survives a dropped connection, offline.

    python3 scripts/fetch_wikidata.test.py

NO NETWORK: urlopen and sleep are stubbed. The monthly refresh runs this stage every time now, so
one truncated response must cost a retry, not the month's data.
"""
import http.client
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import fetch_wikidata as fw                             # noqa: E402

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


class Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def serve(*answers):
    """urlopen that gives each answer in turn: an exception is raised, bytes are the body."""
    calls = []

    def urlopen(req, timeout=None):
        calls.append(req)
        a = answers[len(calls) - 1]
        if isinstance(a, Exception):
            raise a
        return Answer(a)
    return urlopen, calls


def with_stubs(urlopen, fn):
    saved = fw.urllib.request.urlopen, fw.time.sleep
    fw.urllib.request.urlopen, fw.time.sleep = urlopen, lambda s: None
    try:
        return fn()
    finally:
        fw.urllib.request.urlopen, fw.time.sleep = saved


@case("a short read is retried, and the retry's answer is what comes back")
def short_read(_):
    urlopen, calls = serve(http.client.IncompleteRead(b"x"), b'{"ok": 1}')
    got = with_stubs(urlopen, lambda: fw.api("https://example.org", {}))
    assert got == {"ok": 1} and len(calls) == 2, (got, len(calls))


@case("JSON cut off part-way is retried, not handed on as an error")
def truncated_json(_):
    urlopen, calls = serve(b'{"entities": {"Q1"', b'{"ok": 2}')
    got = with_stubs(urlopen, lambda: fw.api("https://example.org", {}))
    assert got == {"ok": 2} and len(calls) == 2, (got, len(calls))


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
