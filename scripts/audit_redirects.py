#!/usr/bin/env python3
# pwa-starter: none — this script is this repo's own
# /// script
# requires-python = ">=3.9"
# ///
"""Price every redirect into every composer's article, and report what summing them would change.

    python3 scripts/audit_redirects.py               # all 884; ~2,900 requests, about ten minutes
    python3 scripts/audit_redirects.py --limit 50    # the 50 most-read, a couple of minutes
    python3 scripts/audit_redirects.py --months 12   # the window to price over (default: the
                                                     # twelve the shipped median uses)

NOT AUTOMATED, and not a gate. Like scripts/audit_counts.py, this prints a measurement for a human
to read: the question it answers is a POLICY question, and the answer is currently no.

THE QUESTION. Page views are counted per title, so a reader who typed "Toru Takemitsu" is counted
under that string and not under "Tōru Takemitsu", where the article lives. Every alias an article
has accumulated therefore holds a slice of its readership, and summing them is defensible.

THE ANSWER, measured: don't. 436 of 884 composers read higher with their redirects added in, and
the median correction is 1.024x — invisible on an axis spanning five orders of magnitude. Only 49
exceed 10%, and nothing in the curated sets moves at all: Mozart goes 186,772 -> 191,780, Beethoven
122,811 -> 123,318, and every one of the ten in CANON rounds to 1.0x. What the sum would buy is
noise, and what it would cost is a stated measure — "monthly English Wikipedia page views for this
article" — traded for one that depends on how many aliases the article happened to accumulate,
which is an artefact of Wikipedia's edit history rather than of readership. That is the same trade
TODO.md refuses under "Deliberately not doing" for per-language views, for the same reason.

WHAT THIS AUDIT DID TURN UP is the defect that is now fixed elsewhere: one composer corrected by
more than 2x, and she was not a split at all. Fanny Hensel's article was MOVED — it sat at "Fanny
Mendelssohn" until March 2026 — so her old title was not an alias holding a slice, it was where the
whole article used to be. Redirect traffic is a rounding error; a page move is an order of
magnitude. scripts/pagemoves.py handles that case, and this script's `moved` column names the ones
it has already repaired, so a large correction here can be read as "explained" or "new".
"""
import argparse
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fetch_views                                     # noqa: E402 - the pageviews fetch and PAUSE
import pagemoves                                       # noqa: E402 - the redirect enumeration

ROOT = os.path.dirname(HERE)
VIEWS = os.path.join(ROOT, "data", "pageviews.json")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, help="audit only the N most-read composers")
    ap.add_argument("--months", type=int, default=12, help="window to price over (default 12)")
    ap.add_argument("--top", type=int, default=15, help="how many corrections to print")
    args = ap.parse_args()

    with open(VIEWS, encoding="utf-8") as f:
        pv = json.load(f)
    axis, series, moved = pv["months"], pv["series"], pv.get("moves") or {}
    window = axis[-args.months:]

    def median_of(vals):
        got = [v for v in vals if v is not None]
        return statistics.median(got) if got else 0

    ranked = sorted(series, key=lambda t: -median_of(series[t][-args.months:]))
    titles = ranked[:args.limit] if args.limit else ranked
    print("%d composers, %s .. %s" % (len(titles), window[0], window[-1]))

    rows, calls = [], 0
    for i, t in enumerate(titles, 1):
        shipped = median_of(series[t][-args.months:])
        try:
            reds = pagemoves.redirects(t)
        except Exception as e:                         # noqa: BLE001 - one dud title, not the run
            print("  %-34s redirect list failed (%s)" % (t, e))
            continue
        calls += 1
        totals, best = [0] * len(window), (0, None)
        for r in reds:
            try:
                got = fetch_views.fetch(r, window) or {}
            except Exception:                          # noqa: BLE001 - same
                continue
            calls += 1
            time.sleep(fetch_views.PAUSE)
            for j, m in enumerate(window):
                totals[j] += got.get(m) or 0
            hit = median_of([got.get(m) for m in window])
            if hit > best[0]:
                best = (hit, r)
        summed = median_of([(series[t][-args.months:][j] or 0) + totals[j]
                            for j in range(len(window))])
        rows.append((summed / shipped if shipped else 0, t, shipped, summed, len(reds), best[1]))
        print("  %d/%d" % (i, len(titles)), end="\r", flush=True)
    print()

    corrected = [r for r in rows if r[0] > 1.0]
    print("\n%d of %d read higher with redirects summed; %d requests" %
          (len(corrected), len(rows), calls))
    if corrected:
        print("median correction across those: %.3fx" % statistics.median(r[0] for r in corrected))
    for lo, hi in ((2.0, None), (1.5, 2.0), (1.2, 1.5), (1.05, 1.2)):
        n = [r for r in rows if r[0] >= lo and (hi is None or r[0] < hi)]
        print("  %-12s %3d  (%d of them a page move already repaired)"
              % (("> %gx" % lo) if hi is None else "%g - %gx" % (lo, hi),
                 len(n), sum(1 for r in n if moved.get(r[1]))))

    print("\nlargest corrections:")
    print("  %-30s %9s %9s %6s  %s" % ("composer", "shipped", "+redirs", "x", "biggest redirect"))
    for ratio, t, shipped, summed, n, top in sorted(rows, reverse=True)[:args.top]:
        print("  %-30s %9d %9d %5.2fx  %s%s"
              % (t[:30], shipped, summed, ratio, top or "-",
                 "   <- page move, already repaired" if moved.get(t) else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
