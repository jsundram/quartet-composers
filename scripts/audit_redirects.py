#!/usr/bin/env python3
# pwa-starter: none — this script is this repo's own
# /// script
# requires-python = ">=3.9"
# ///
"""Price every redirect into every composer's article, and report what summing them would change.

    python3 scripts/audit_redirects.py               # all 884; ~2,900 requests, about ten minutes
    python3 scripts/audit_redirects.py --limit 50    # the 50 most-read, a couple of minutes
    python3 scripts/audit_redirects.py --months 12   # the window to price over

NOT AUTOMATED, and not a gate: like audit_counts.py it prints a measurement for a human, because
the question is a POLICY question.

THE QUESTION. Views are counted per title, so a reader who typed "Toru Takemitsu" is counted under
that string and not under "Tōru Takemitsu", where the article lives. Every alias holds a slice of
the readership, and summing them is defensible.

THE ANSWER, measured: don't (#107). 436 of 884 composers read higher with redirects added in and
the median correction is 1.024x — invisible on an axis spanning four orders of magnitude; only 49
exceed 10% and every one of CANON rounds to 1.0x. What the sum buys is noise; what it costs is a
stated measure traded for one that depends on how many aliases an article happened to accumulate,
which is an artefact of edit history rather than of readership.

WHAT IT DID TURN UP is the defect now fixed elsewhere: the one composer corrected by more than 2x
was not a split at all. Fanny Hensel's article was MOVED, so her old title was where the whole
article used to be rather than an alias holding a slice. scripts/pagemoves.py handles that, and the
`moved` column names the ones already repaired, so a large correction reads as explained or new.


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
