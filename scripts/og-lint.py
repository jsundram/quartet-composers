#!/usr/bin/env python3
# pwa-starter: og-lint.py @ d2fad01  (+ the meta-length and stated-count checks below)
# /// script
# requires-python = ">=3.9"
# ///
"""Catch an OG share card too big for link scrapers to render.

The og:image is the difference between a rich link preview and a grey box. When someone pastes the
URL, iMessage/WhatsApp/Slack fetch that image — and quietly SKIP one over ~300 KB. So a card that
rasterized fine but never got compressed previews as *nothing*, and you only find out when a friend
texts back a blank box. `make-og.sh` compresses + gates at generation time; this guards the commit,
catching a hand-exported or externally-produced PNG that never went through the script.

So: if this commit stages an oversized OG image, warn.

MAX_BYTES keeps a margin under WhatsApp's ~300 KB scrape cutoff (keep in sync with make-og.sh).

It also checks the TEXT of the preview, because the same failure mode applies: a description that
is too long is silently truncated mid-sentence by the scraper, and a title that is too short
wastes the search result. These bands came from opengraph.xyz's report on the deployed page, and
they live here rather than in a browser tab so they are checked offline, on every commit, before
the thing ships — an external validator can only tell you after you have already deployed it.

The two descriptions are deliberately DIFFERENT lengths and must not be re-unified: a SERP snippet
has 120-160 characters to fill, and a link preview truncates near 125 on a phone. One string
cannot do both jobs.

Last: any "NNN composers" the page or the manifest states is checked against composers.json — both
of the counts that are live there, the roster and the smaller set the chart can plot. Either
changes when the pipeline runs, and a hardcoded count in a share preview is exactly the kind of
number nobody thinks to re-read.

The pre-commit hook runs it warn-only; run it in CI with a real exit code. By hand:
    python3 scripts/og-lint.py
"""
import importlib.util, json, os, pathlib, re, subprocess, sys

MAX_BYTES = 250_000   # keep in sync with scripts/make-og.sh

ROOT = pathlib.Path(__file__).resolve().parent.parent
HERE = pathlib.Path(__file__).resolve().parent

# (attribute value, pattern, low, high). low is a floor, not a target: under it the field is
# wasting space a scraper has already allocated.
META = [
    ("<title>",             r"<title>(.*?)</title>",                            50, 65),
    ("description",         r'name="description" content="(.*?)"',             120, 160),
    ("og:title",            r'property="og:title" content="(.*?)"',             15, 60),
    ("og:description",      r'property="og:description" content="(.*?)"',       60, 125),
    ("twitter:description", r'name="twitter:description" content="(.*?)"',      60, 125),
    ("og:image:alt",        r'property="og:image:alt" content="(.*?)"',         50, 420),
]


def sh(*a):
    return subprocess.run(a, capture_output=True, text=True)


def is_card(path):
    name = path.rsplit("/", 1)[-1]
    return name == "og.png" or (name.startswith("og-") and name.endswith(".png"))


def blob_size(path):                              # staged bytes, without reading the binary in
    r = sh("git", "cat-file", "-s", f":{path}")
    return int(r.stdout) if r.returncode == 0 and r.stdout.strip().isdigit() else None


def check_meta():
    """Length bands for the fields a scraper and a search result actually render."""
    html = (ROOT / "index.html").read_text()
    bad = []
    for name, pat, lo, hi in META:
        m = re.search(pat, html)
        if not m:
            bad.append(f"           {name}: MISSING")
            continue
        n = len(m.group(1))
        if not (lo <= n <= hi):
            how = "too short" if n < lo else "too long"
            bad.append(f"           {name}: {n} characters, {how} (want {lo}-{hi})")
    if bad:
        print("  Link-preview / search text is outside the band a scraper renders:")
        print("\n".join(bad))
    return 1 if bad else 0


def check_counts():
    """A stated composer count must match the data, or the preview ships a number that went stale.

    TWO counts are live and both get hardcoded into prose: the ROSTER (884 rows) and what the chart
    can PLACE (790 — chart.js's `plottable`, i.e. a stated quartet count). They differ by the 94
    rows the table carries and the plot cannot, which is a distinction this page is careful about
    everywhere else. A lint that knew only the roster left the other number free to go stale, and
    the two move independently: a rerun can add a composer with no stated count, which changes 884
    and not 790.

    Within index.html it does NOT try to work out which one a sentence means. "884 quartet
    composers" and "790 quartet composers" are both grammatical and only one is true, and no regex
    can tell them apart — a discriminator built on the word "quartet" would fail on the roster
    sentence that already calls them quartet composers. So the rule there is that a stated count
    must be one the data currently supports, which catches the failure this exists to catch (a
    total moves and a hardcoded string does not follow) without inventing an error out of a
    phrasing nobody anticipated.

    manifest.json is pinned, because the SENTENCE cannot be told apart but the FILE can: it holds
    exactly one description of the app, so what it may state is a settled question rather than a
    guess. It is pinned to the PLOTTED count — the manifest describes what the app draws, and the
    884-row roster is the table's number, stated in full on the provenance line where the
    difference is explained. Leaving it as permissive as index.html would let the two numbers swap
    places and pass clean, which is half of what the old check enforced and worth keeping.

    If the manifest is ever reworded to describe the roster instead, this pin moves with it — that
    is the point of pinning per FILE rather than per number.
    """
    rows = json.loads((ROOT / "composers.json").read_text())["rows"]
    live = {len(rows): "the roster",
            sum(1 for r in rows if r[3] is not None): "the composers the chart can plot"}
    # "884 composers", "790 quartet composers", "790 string quartet composers" — a qualifier or
    # two, because that is how these sentences actually read.
    pat = r"\b(\d{3,5})(?:\s+\w+){0,2}\s+composers\b"
    bad = []
    plotted = sum(1 for r in rows if r[3] is not None)
    for f, allowed in (("index.html", live),
                       ("manifest.json", {plotted: "the composers the chart can plot"})):
        for stated in set(re.findall(pat, (ROOT / f).read_text())):
            if int(stated) not in allowed:
                want = ", ".join(f"{n} ({what})" for n, what in sorted(allowed.items()))
                bad.append(f"           {f}: says {stated} composers; it may state {want}")
    if bad:
        print("  A stated composer count is not one this file may state:")
        print("\n".join(bad))
    return 1 if bad else 0


def check_card_axis():
    """The share card's readership axis must contain every tick it draws.

    make-og-svg.py duplicates chart.js's scales on purpose (invariant 14), and the drift is silent
    in the worst possible way: its logscale() CLAMPS, so a tick below the floor is not dropped, it
    is drawn hard on the bottom edge with the wrong number beside it. When the y floor moved up to
    the first occupied decade (issue 38) the card went on printing a "1" against an axis starting
    at 8.5 — a label naming a value the picture no longer contains, on the one image that gets
    scraped into every link preview and is never looked at again.

    Compared against `vy_domain()` itself rather than a copy of the rule, so this checks the card ON
    DISK against the script that should have drawn it: a stale assets/og.svg fails here too, which
    is the other way the two go out of step. The y ticks are the `text-anchor="end"` ones — the x
    axis anchors middle — so nothing here has to know the plot's geometry.
    """
    spec = importlib.util.spec_from_file_location("og", os.path.join(HERE, "make-og-svg.py"))
    og = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(og)
    with open(os.path.join(ROOT, "composers.json"), encoding="utf-8") as f:
        rows = json.load(f)["rows"]
    lo, hi = og.vy_domain(rows)
    with open(os.path.join(ROOT, "assets", "og.svg"), encoding="utf-8") as f:
        card = f.read()
    drawn = []
    for lab in re.findall(r'text-anchor="end">([\d.]+k?)</text>', card):
        drawn.append(float(lab[:-1]) * 1000 if lab.endswith("k") else float(lab))
    if not drawn:
        print("  og.svg has no readership axis labels — has the card's markup changed?")
        return 1
    stray = [v for v in drawn if not lo <= v <= hi]
    if stray:
        print("  assets/og.svg draws readership ticks its own axis does not contain: %s"
              % ", ".join("%g" % v for v in stray))
        print("  The axis runs %g..%g. logscale() clamps, so these are painted on the bottom edge "
              "with the wrong number beside them." % (lo, hi))
        print("  Rerun: python3 scripts/make-og-svg.py")
        return 1
    # ...and it must be ANCHORED: a floor with no label near it leaves an unexplained empty band
    # under the lowest gridline, which is the same wasted space issue 38 was about.
    if min(drawn) > lo * 100:
        print("  assets/og.svg labels nothing in its bottom decade: axis starts at %g, lowest "
              "tick is %g. Rerun: python3 scripts/make-og-svg.py" % (lo, min(drawn)))
        return 1
    return 0


def main():
    rc = check_meta() | check_counts() | check_card_axis()
    staged = sh("git", "diff", "--cached", "--name-only").stdout.split()
    over = []
    for f in staged:
        if not is_card(f):
            continue
        n = blob_size(f)
        if n is not None and n > MAX_BYTES:
            over.append((f, n))
    if not over:
        return rc
    print("  OG share card exceeds the scraper size budget (some previews will show a grey box):")
    for f, n in over:
        print(f"           {f}  {n:,} bytes  (> {MAX_BYTES:,})")
    print("  Recompress: rerun scripts/make-og.sh (pngquant), simplify og.svg, or shrink the palette.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
