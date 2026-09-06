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

Last: any "NNN composers" the page or the manifest states is checked against composers.json. The
roster changes when the pipeline runs, and a hardcoded count in a share preview is exactly the
kind of number nobody thinks to re-read.

The pre-commit hook runs it warn-only; run it in CI with a real exit code. By hand:
    python3 scripts/og-lint.py
"""
import json, pathlib, re, subprocess, sys

MAX_BYTES = 250_000   # keep in sync with scripts/make-og.sh

ROOT = pathlib.Path(__file__).resolve().parent.parent

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
    """A stated roster size must match the data, or the preview ships a number that went stale."""
    rows = json.loads((ROOT / "composers.json").read_text())["rows"]
    bad = []
    for f in ("index.html", "manifest.json"):
        for stated in set(re.findall(r"\b(\d{3,5}) composers\b", (ROOT / f).read_text())):
            if int(stated) != len(rows):
                bad.append(f"           {f}: says {stated} composers, composers.json has {len(rows)}")
    if bad:
        print("  A stated composer count no longer matches the data:")
        print("\n".join(bad))
    return 1 if bad else 0


def main():
    rc = check_meta() | check_counts()
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
