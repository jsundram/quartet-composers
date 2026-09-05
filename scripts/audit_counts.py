#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Sample parsed quartet counts next to the sentence they came from, for a human to grade.

    python3 scripts/audit_counts.py               # 30 random entries, fixed seed
    python3 scripts/audit_counts.py -n 60         # more
    python3 scripts/audit_counts.py --seed 7      # a different sample
    python3 scripts/audit_counts.py --rule "dated works"   # only entries a given rule produced
    python3 scripts/audit_counts.py --null        # only entries with no count

WHY THIS EXISTS. The tempting way to grade scrape_list.py is "how often does it agree with the 2014
scrape", and that number is worse than useless: the page has been rewritten over twelve years, so
disagreement is usually the parser being RIGHT about a sentence that changed. Optimising toward the
old numbers optimises toward being out of date.

The only honest measure is accuracy against the page as it is now, which needs eyes. Thirty entries
takes a couple of minutes to grade and gives a real error rate per rule. The last audit scored 25
exactly right, 4 correctly null, 1 arguable — and it is what surfaced the two rules ("dated works",
the works-for-string-quartet pattern) that lifted coverage from 709 entries to 791.

Grade an entry as: right / wrong number / should have a number but got null / correctly null.
The middle category is the one that matters — a wrong number ships as a confident dot.
"""
import argparse
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scrape_list as S  # noqa: E402

CACHE = os.path.join(os.path.dirname(HERE), "data", "list.wiki")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-n", type=int, default=30, help="sample size (default 30)")
    ap.add_argument("--seed", type=int, default=20260905, help="sample seed (fixed, so reruns match)")
    ap.add_argument("--rule", help="only entries produced by this rule, e.g. 'singular'")
    ap.add_argument("--null", action="store_true", help="only entries with no parsed count")
    args = ap.parse_args()

    if not os.path.exists(CACHE):
        print("no data/list.wiki - run scripts/scrape_list.py first", file=sys.stderr)
        return 1
    wikitext = open(CACHE, encoding="utf-8").read()
    rows, _, _, _ = S.parse(wikitext)

    source = {}
    for line in wikitext.split("\n"):
        m = S.LINK.match(line)
        if m:
            source[m.group(1).strip()] = S.clean(line)

    pool = rows
    if args.null:
        pool = [r for r in rows if r["quartets"] is None]
    elif args.rule:
        pool = [r for r in rows if r["how"] == args.rule]
    if not pool:
        print("nothing matches that filter")
        return 0

    random.seed(args.seed)
    sample = random.sample(pool, min(args.n, len(pool)))
    for r in sample:
        s = source.get(r["title"], "")
        desc = s.split("):", 1)[1].strip() if "):" in s else s
        print("%-4s [%-22s] %s" % (r["quartets"] if r["quartets"] is not None else "--",
                                   r["how"] or "no rule", r["title"]))
        print("       %s" % desc[:165].replace("\n", " "))
    print("\n%d of %d entries shown. Grade each against the sentence above it." % (len(sample), len(pool)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
