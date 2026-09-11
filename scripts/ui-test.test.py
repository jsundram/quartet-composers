#!/usr/bin/env python3
# pwa-starter: none — this script is this repo's own
# /// script
# requires-python = ">=3.9"
# ///
"""Prove that two checkouts of this repo do not take each other's ui-test run down (#49).

    python3 scripts/ui-test.test.py

NO BROWSER AND NO SERVER: every case runs `scripts/ui-test.sh --ports`, which answers out of the
checkout's own path and exits before anything is started. So it runs anywhere in about a second.

WHY IT EXISTS. The runner clears its two ports with a `pkill -f` that matches every process on the
machine, and the ports were FIXED, so a second checkout starting up killed the first one's browser
and server mid-run. The fix is a default derived from the checkout's path, and its failure mode is
the shape this repo keeps meeting: fixing the ports again — or writing the port into the kill
pattern as a literal — would be invisible in a single run and in CI, where nothing runs twice at
once. It only shows up on the machine with two worktrees open, as a suite that dies in the one
that did nothing wrong.

A hash into 200 slots HAS collisions by construction, so the distinctness case below asserts what
is true rather than what would read better: many checkouts land on many pairs, not on one. The
residual is why both variables stay overridable and why the runner prints the pair it derived.
"""
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(HERE, "ui-test.sh")

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def checkout(root, name):
    """A directory shaped like a checkout as far as the runner is concerned, and no further.

    `ui-test.sh` cd's to its own parent's parent and derives the pair from there, so a scripts/
    holding a copy of it is the whole fixture — which is also the proof that --ports answers
    before it needs the app, the suite, node or a browser.
    """
    d = os.path.join(root, name)
    os.makedirs(os.path.join(d, "scripts"))
    shutil.copy2(RUNNER, os.path.join(d, "scripts", "ui-test.sh"))
    return d


def run(d, env=None, via=None, timeout=20):
    # TIMED, because the failure this asks about includes "the runner did not answer": a build
    # that no longer knows --ports takes it for a normal run and opens a browser.
    e = {k: v for k, v in os.environ.items() if k not in ("PORT", "CDP")}
    e.update(env or {})
    return subprocess.run([via or os.path.join(d, "scripts", "ui-test.sh"), "--ports"],
                          capture_output=True, text=True, env=e, timeout=timeout)


def ports(d, env=None, via=None):
    r = run(d, env, via)
    assert r.returncode == 0, "--ports exited %d: %s%s" % (r.returncode, r.stdout, r.stderr)
    m = re.fullmatch(r"PORT=(\d+) CDP=(\d+)\n", r.stdout)
    assert m, "--ports printed %r" % r.stdout
    return int(m.group(1)), int(m.group(2))


@case("a checkout derives the same pair on every run, so the clear still reaps its own leftovers")
def stable(t):
    # The kill is not dead weight to be traded away for distinctness: a browser left over from an
    # INTERRUPTED run still holds the port, and node would otherwise connect to it and test the
    # previous edit's JS out of its service-worker cache. That only works if this run lands on the
    # same pair as the one that died, which is why the pair is derived and not allocated.
    d = checkout(t, "w")
    assert ports(d) == ports(d) == ports(d)


@case("many checkouts land on many server ports AND on many devtools ports")
def distinct(t):
    # BOTH, separately. Asserting over the pair passes as soon as EITHER half varies, so a tree
    # that had gone back to `CDP=${CDP:-9333}` with PORT still derived scored 24 distinct pairs
    # and 1 debug port — which is #49 exactly, every checkout killing every other checkout's
    # browser, through a green suite.
    pairs = [ports(checkout(t, "w%d" % i)) for i in range(24)]
    for what, got in (("server", {p for p, _ in pairs}), ("devtools", {c for _, c in pairs})):
        # 24 checkouts over 200 slots: ~23 distinct is the expectation and 12 is far below any run
        # this can have, while a fixed default scores exactly 1. A floor rather than "all 24
        # differ" because a hash into 200 slots collides sometimes — the residual the runner
        # prints its pair for.
        assert len(got) >= 12, "24 checkouts share %d %s port(s)" % (len(got), what)


@case("the server band and the devtools band cannot overlap")
def bands(t):
    # One run's server on another run's debug port would be the same cross-kill wearing a
    # different number — and worse, node would find an HTTP server where it expects CDP.
    for i in range(24):
        p, c = ports(checkout(t, "w%d" % i))
        assert 8765 <= p <= 8964, p
        assert 9333 <= c <= 9532, c


@case("the same checkout reached through a symlink is the same checkout")
def symlinked(t):
    # `pwd -P`, not `$PWD`: /work -> ~/src/repo is how one of these gets invoked two ways, and two
    # spellings of one checkout hashing apart would put the second run beside its own leftover
    # rather than on top of it.
    d = checkout(t, "w")
    link = os.path.join(t, "link")
    os.symlink(d, link)
    assert ports(d, via=os.path.join(link, "scripts", "ui-test.sh")) == ports(d)


@case("PORT and CDP still pin, together and each on its own")
def pinned(t):
    # The answer to a collision, so it has to reach past the derivation rather than offset it.
    d = checkout(t, "w")
    p, c = ports(d)
    assert ports(d, {"PORT": "8700", "CDP": "9300"}) == (8700, 9300)
    assert ports(d, {"PORT": "8700"}) == (8700, c)
    assert ports(d, {"CDP": "9300"}) == (p, 9300)


@case("--ports answers before anything is started")
def early(t):
    # The fixture has no server, no node and no browser, so an answer at all proves the exit
    # precedes them — and it has to, or asking which ports a run would use would start one.
    r = run(checkout(t, "w"))
    assert r.stderr == "", "--ports wrote to stderr: %r" % r.stderr
    assert len(r.stdout.splitlines()) == 1, "--ports printed %r" % r.stdout


# A process that is NOT this suite's, holding one of the two ports — a stranger, since the bands
# are 200 wide and cover ports people use, or a sibling run that derived the same slot. Neither
# `pkill` pattern can match it.
#
# THE REPLY IS THE PARAMETER, because each guard was first written against the one shape that
# happened to be in the fixture and waved the other one through: a 200 on the server port
# satisfies any HTTP probe while our own python has not reached its bind yet, and a 404 on the
# debug port — chromedriver's answer, on a default port inside the derived band — is what `curl
# -sf` reports exactly as it reports an empty port.
SQUAT = ("import http.server as h,sys;"
         "n=int(sys.argv[2]);"
         "c=type('C',(h.BaseHTTPRequestHandler,),"
         "{'do_GET':lambda s:(s.send_response(n),s.end_headers(),s.wfile.write(b'{}')),"
         "'log_message':lambda *a:None});"
         "h.HTTPServer(('127.0.0.1',int(sys.argv[1])),c).serve_forever()")


def squat(port, reply=None):
    """Hold `port`, answering `reply` (200/404) or — with None — accepting and never replying."""
    if reply is None:
        s = socket.socket()
        s.bind(("127.0.0.1", port))
        s.listen(1)
        return s
    p = subprocess.Popen([sys.executable, "-c", SQUAT, str(port), str(reply)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            return p
        except OSError:
            time.sleep(0.05)
    raise AssertionError("the squatter never came up on %d" % port)


def held(port, reply, run_it):
    """Hold `port` in the given shape for the duration of one full run, and give back its result."""
    s = squat(port, reply)
    try:
        return run_it()
    finally:
        if isinstance(s, socket.socket):
            s.close()
        else:
            s.terminate()
            s.wait(timeout=10)


def full_run(d, out):
    """The whole runner, with a browser it will never reach: both guards stop before the launch."""
    e = {k: v for k, v in os.environ.items() if k not in ("PORT", "CDP", "REQUIRE_BROWSER", "KEEP")}
    e.update({"CHROME": "/bin/echo", "OUT": out})
    return subprocess.run([os.path.join(d, "scripts", "ui-test.sh")],
                          capture_output=True, text=True, env=e, timeout=120)


def stopped(t, which, reply, says):
    """One full run against a squatter on one of the two ports. It must stop, and say which."""
    d = checkout(t, "w")
    port, cdp = ports(d)
    p = port if which == "server" else cdp
    r = held(p, reply, lambda: full_run(d, os.path.join(t, "out")))
    assert r.returncode == 1, "exited %d, not 1:\n%s%s" % (r.returncode, r.stdout, r.stderr)
    assert says % p in r.stdout, r.stdout
    # The reason has to reach $OUT as well: in CI that directory IS the artifact, and a run which
    # stops before it opens a browser writes nothing else into it.
    note = os.path.join(t, "out", "ui-test.log")
    assert os.path.exists(note) and (says % p) in open(note, encoding="utf-8").read(), note


@case("a stranger ANSWERING on the server port stops the run, not just a silent one")
def foreign_server_200(t):
    # The shape the first version of this guard let through, and the likelier of the two: whatever
    # is on that port is probably an HTTP server (8888 is Jupyter's). "Does something answer" is
    # satisfied on iteration 1, while our own python has not reached its bind yet — so the
    # `kill -0` beside it still saw a live pid, and the run went on to test a stranger's page.
    stopped(t, "server", 200, "the server never took %d")


@case("a silent squatter on the server port stops it too")
def foreign_server_silent(t):
    # Accepts and never replies, which is the other reason every probe is bounded: an unbounded
    # curl waits on this one for as long as it likes, and the runner stops before it starts.
    stopped(t, "server", None, "the server never took %d")


@case("a stranger 404ing on the debug port stops the run, instead of driving a foreign browser")
def foreign_cdp_404(t):
    # chromedriver's shape, on a default port (9515) inside the derived band. It 404s on
    # /json/version, which `curl -sf` reports exactly as it reports an empty port — so the guard
    # asks what is HELD instead. The pkill frees only a Chrome carrying this debug port.
    stopped(t, "cdp", 404, "%d is still held")


@case("a browser-shaped stranger on the debug port stops it too")
def foreign_cdp_200(t):
    # The other half: a live sibling's Chrome, or anything else answering 200 there. Driving it
    # would test a browser this run did not start, on a profile it did not clear.
    stopped(t, "cdp", 200, "%d is still held")


@case("the clear still matches BY the derived ports, not by a literal")
def kill_patterns(_):
    # The half of the fix the cases above cannot see. Distinct defaults protect nothing if the
    # patterns go back to naming a number: `pkill -f "remote-debugging-port=9333"` from one
    # checkout kills every other checkout's browser exactly as before, while --ports goes on
    # reporting a pair that is no longer the one being cleared.
    src = open(RUNNER, encoding="utf-8").read()
    for pat in ('pkill -f "remote-debugging-port=$CDP"', 'pkill -f "http.server $PORT"'):
        assert pat in src, "the clear no longer reads %s" % pat


def preflight():
    """--ports has to answer at all, or every case below is that one failure, slowly.

    A runner that does not know the flag takes it for a normal run and opens a browser — once per
    checkout the cases build, and the distinctness ones build two dozen each. One named line
    beats a browser per checkout.
    """
    with tempfile.TemporaryDirectory() as t:
        d = checkout(t, "w")
        try:
            r = run(d)
        except subprocess.TimeoutExpired:
            return "no answer in 20s — the runner is treating --ports as a normal run"
        if r.returncode != 0 or not re.fullmatch(r"PORT=\d+ CDP=\d+\n", r.stdout):
            return "exit %d, printed %r" % (r.returncode, r.stdout[:120])
    return ""


def main():
    why = preflight()
    if why:
        print("  FAIL - the runner answers --ports at all\n       %s" % why)
        print("\n0 passed, 1 failed")
        return 1
    passed = failed = 0
    for name, fn in CASES:
        with tempfile.TemporaryDirectory() as t:
            try:
                fn(t)
                print("  ok   - %s" % name)
                passed += 1
            # Exception, not AssertionError: squat() raises OSError when this machine already has
            # something on the derived port, and full_run() raises on a timeout. Either one used
            # to end the run mid-suite with a traceback and no summary — the shape of failure this
            # repo keeps fixing one file at a time.
            except Exception as e:
                print("  FAIL - %s\n       %s: %s" % (name, type(e).__name__, e))
                failed += 1
    print("\n%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
