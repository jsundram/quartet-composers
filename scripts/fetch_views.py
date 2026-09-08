#!/usr/bin/env python3
# pwa-starter: none — this script is this repo's own
# /// script
# requires-python = ">=3.9"
# ///
"""Cache a monthly page-view SERIES per composer -> data/pageviews.json.

    python3 scripts/fetch_views.py                # every month the API has, topped up
    python3 scripts/fetch_views.py --months 24    # narrow the window to the last 24
    python3 scripts/fetch_views.py --force        # refetch even months already cached
    python3 scripts/fetch_views.py --dry-run      # fetch and report, write nothing

WHY A SERIES AND NOT A NUMBER. Dot size is the most visually dominant channel on the chart and
page views are the noisiest input to it. Measured against a 12-month window, a single month is off
the median by 12% typically and 29% at worst, and August is a seasonal trough that every sampled
composer fell below. Philip Glass has a month at 2.13x his median. Sizing dots from one month
means a chunk of the picture is weather.

The fix costs nothing: `monthly` granularity returns EVERY month in the requested range from ONE
request, so twelve months of data is the same ~880 calls that one month was. build_data.py takes
the MEDIAN, which ignores a death-or-anniversary spike instead of baking it in permanently.

WHY THE WHOLE HISTORY AND NOT TWELVE MONTHS. The window defaults to everything the API has —
2015-07 to the last complete month, 134 months as of this writing — for the same one-request
reason: the range is free, so the only cost is the file on disk. What it buys is the readership
SPARKLINE in the app's detail panel, which is the one thing twelve months cannot show. Saariaho
runs at ~2,000 a month for eight years and hits 42,195 in June 2023, the month she died; Haydn
has slid from 32,000 to 20,000 across the decade. A twelve-month window sees the first as a flat
line and the second as noise.

It does NOT move the headline number: build_data.py still takes the median of the last TWELVE
cached months, because "how much read is this composer" is a question about now. The rest of the
series is history, and history is a different question.

Storing the raw series rather than the computed statistic means the statistic can be changed
without touching the network and a refresh only fetches months it does not already have.

ON DISK: `months` is the axis and each series is a FLAT ARRAY aligned to it, null where the API
had no datum. The obvious alternative — a {month: count} object per composer — repeats the month
key 884 times per month and cost 1.9 MB against 0.5 MB for the same numbers, which then has to be
rewritten whole on every monthly top-up. The dict form is still READ, once, so an older cache
migrates itself the first time this runs.

A null is "asked, and the API had nothing" — an article that did not exist yet — or, at the month
an article was MOVED, "asked, and the answer belongs to neither of its titles" (see the page-move
section below). It is not the same
as a MISSING month, which is "never asked", and recording it is what keeps a top-up cheap: without
it an article created in 2019 is forever missing its 2015 months, so it looks incomplete and is
refetched in full on every single run (62 of 884 titles). Same distinction the app makes
everywhere else; see invariant 10 in CLAUDE.md.

WHICH MEANS EVERY TITLE IS FETCHED OVER THE WHOLE AXIS, not over `--months`. A flat array cannot
say "never asked" — there is no third value between a count and a null — so the only way the two
states stay distinct on disk is for the file to hold exactly one asked window, the axis itself.
Fetching a title over a narrower window and writing it onto the wider axis would record its
un-asked months as nulls, and it would then read as complete FOREVER: `--months 24` on a composer
added since the last run buried nine years of their history permanently. The range is free (one
request either way), so `--months` narrows what counts as STALE and never what gets asked for.

TITLES MUST BE CANONICAL. Views are counted per title and a redirect is its own title with its own
tiny count: asking for "Bela Bartok" returns 41 instead of Béla Bartók's 14,330, with a 200 and no
error. Canonical titles come from data/people.json (scripts/fetch_wikidata.py). Run that first.

AND THE CANONICAL TITLE IS ONLY CANONICAL TODAY. An article that was MOVED inside the window was
counted under its old name for every month before the move, so asking the right title still
undercounts — Fanny Hensel's article sat at "Fanny Mendelssohn" until March 2026 and her shipped
median of 500 was eleven times too small. scripts/pagemoves.py holds that rule and the reasoning;
this file applies it, after the fetch, to the series it just wrote. Two passes, for two different
failure modes: a move already recorded in `moves` is re-applied UNCONDITIONALLY to any title this
run refetched (the refetch has just overwritten the stitched series with the raw per-title counts,
so the repair has to happen again every time), and a title whose series still shows the SHAPE of a
move is put to the move log to find new ones. Re-deriving rather than trusting is what keeps the
two in step; the detector is a suspect generator and the log is the arbiter.

`moves` records the answer either way, including "looked, found nothing" as an empty list. That
empty list is load-bearing twice: it is what stops a no-op run from asking the same eight noisy
articles again, and it is how validate.py tells genuine growth from a move nobody has checked.

WHAT THIS DOES NOT DO: re-scrape the composer list (scripts/scrape_list.py) or re-read birth and
death dates (scripts/fetch_wikidata.py).

AFTERWARDS: composers.json is precached in sw.js. Bump V or the new numbers reach the repo and
nobody's phone. scripts/sw-lint.py will remind you.
"""
import argparse
import calendar
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pagemoves                                       # noqa: E402 - needs HERE on the path first

ROOT = os.path.dirname(HERE)
PEOPLE = os.path.join(ROOT, "data", "people.json")
OUT = os.path.join(ROOT, "data", "pageviews.json")

API = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
       "en.wikipedia/all-access/user/{title}/monthly/{start}/{end}")
UA = "quartet-composers/1.0 (https://github.com/jsundram/quartet-composers)"

# Tuned against the real limiter, not the published headline rate: 0.06s/req drew a 429 about 300
# titles in. 0.15s (~7/s) runs the full list clean, and the whole job is ~2 minutes either way.
PAUSE = 0.15
TRIES = 5
BACKOFF = [2, 5, 15, 40]

# The API has no per-article data before this. Anything earlier came from a different measurement
# system (the pre-2015 dumps / stats.grok.se) and is NOT comparable to what this fetches — which
# is why the 2014 numbers are archived rather than plotted alongside these.
FLOOR = "2015-07"


def months_back(n, end=None):
    """The n complete months ending with `end` (default: the last complete month), as YYYY-MM.

    n=None means every month the API has: back to FLOOR."""
    if end is None:
        first_of_now = dt.date.today().replace(day=1)
        end = first_of_now - dt.timedelta(days=1)
    else:
        y, m = int(end[:4]), int(end[5:7])
        end = dt.date(y, m, calendar.monthrange(y, m)[1])
    if n is None:
        n = (end.year - int(FLOOR[:4])) * 12 + (end.month - int(FLOOR[5:7])) + 1
    out = []
    y, m = end.year, end.month
    for _ in range(n):
        out.append("%04d-%02d" % (y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return sorted(v for v in out if v >= FLOOR)


def stamps(months):
    """REST start/end covering the whole span. `monthly` needs a range that SPANS full months —
    passing the same first-of-month for both ends returns 400 'no full months between dates'."""
    sy, sm = int(months[0][:4]), int(months[0][5:7])
    ey, em = int(months[-1][:4]), int(months[-1][5:7])
    return ("%04d%02d0100" % (sy, sm),
            "%04d%02d%02d00" % (ey, em, calendar.monthrange(ey, em)[1]))


def fetch(title, months):
    """{'YYYY-MM': views} for one article. None means the article has no data at all (404)."""
    start, end = stamps(months)
    url = API.format(title=urllib.parse.quote(title.replace(" ", "_"), safe=""),
                     start=start, end=end)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(TRIES):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                items = json.load(r).get("items") or []
            return {"%s-%s" % (i["timestamp"][:4], i["timestamp"][4:6]): i["views"] for i in items}
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (429, 500, 502, 503) and attempt < TRIES - 1:
                wait = BACKOFF[min(attempt, len(BACKOFF) - 1)]
                try:                                  # honor Retry-After; it knows better
                    wait = max(wait, int(e.headers.get("Retry-After", 0)))
                except (TypeError, ValueError):
                    pass
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < TRIES - 1:
                time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
                continue
            raise
    return None


def repair_moves(series, axis, recorded, refetched, report):
    """Put every series back under the title the article actually occupied. Returns the new record.

    Two passes, because a known move and an unknown one fail differently (see the header). The
    first re-applies what `data/pageviews.json` already records, for every title this run refetched
    — the refetch overwrote the stitched series with the API's per-title answer, so the repair is
    not a migration that happens once, it is part of writing the file. The second asks the move log
    about anything that still LOOKS moved, and records the answer either way.

    A suspect is investigated when its series was refetched (so the shape is new information) or
    when nothing has ever been recorded for it (so nobody has looked). Both conditions are false on
    a run that fetched nothing, which is what keeps `fetch_views.py` a true no-op at the network
    when it has nothing to do.
    """
    moves = {t: [tuple(m) for m in v] for t, v in (recorded or {}).items()}
    by_title, handled = {}, set()
    # The PRE-STITCH counts, snapshotted before anything below rewrites `series`. Stitching reads
    # the canonical title's own numbers, and a stitched series contains the source's months already
    # — so repairing from `series` twice would add the transition month to itself. A title is only
    # ever repaired from this snapshot, which makes the operation idempotent whatever order the two
    # passes run in. (`raw` really is raw for every title either pass touches: one that was not
    # refetched is only repaired when nothing has ever been recorded for it, which means nothing
    # has ever stitched it.)
    raw = {t: list(v) for t, v in series.items()}

    def series_for(title):
        """The title's counts over the axis, or None if it did not answer. Fetched once per run.

        GUARDED FOR THE SAME REASON THE MAIN FETCH LOOP IS. fetch() re-raises a 429 or a timeout
        once its retries are spent, and repair_moves() runs AFTER all 884 titles are in hand and
        BEFORE the file is written — so an unguarded raise on one of these dozen-odd old-title
        requests would leave main() with nothing written and discard the entire top-up. That is
        precisely the failure the `except` in the main loop exists to prevent, and this is the same
        network.

        A 404 counts as not answering too: for a SOURCE title it means the redirect the article
        used to live at is gone, so its months cannot be recovered — which is a thing to report and
        retry, not a series of nulls to stitch in as though they were readings. So does an EMPTY
        payload, which fetch() returns as `{}` rather than None: a 200 carrying no `items` is the
        same absence wearing a different type, and taking it for an answer is worse here than
        anywhere else — for a new suspect the all-null source makes confirm() reject the hop and
        write the `[]` that retires the question, and for a chain already on record (trusted, not
        re-confirmed) stitch() would lay nulls over the whole pre-move stretch while `moves` still
        says stitched, which step() cannot see because the before-window is then empty.
        """
        if title not in by_title:
            if title in raw and title not in refetched:
                by_title[title] = raw[title]           # nothing refetched it; the cache is it
            else:
                try:
                    got = fetch(title, axis)
                except Exception as e:                 # noqa: BLE001 - any transport failure
                    report("      %r did not answer (%s)" % (title, e))
                    return None
                time.sleep(PAUSE)
                if not got:
                    report("      %r returned no data at all" % title)
                    return None
                by_title[title] = [got.get(m) for m in axis]
        return by_title[title]

    def repair(title, chain, recorded_already=False):
        """Stitch `chain` into `title`'s series and record it. Returns what happened, in a word.

        THREE OUTCOMES, NOT TWO, because two of them are not the same news. "stitched" and
        "no-move" are answers — the log named a chain, or it named nothing — while "unresolved"
        means the question is still open and nothing was written. Collapsing the last into a
        boolean printed the operator "a 105x step in readership this article really had" after a
        429 on Fanny's redirect list, which is the opposite of what happened and the opposite of
        what to do about it.

        NOTHING IS RECORDED UNLESS THE WHOLE ANSWER IS IN HAND. `chain is None` means the move log
        could not be read; a source that does not answer means the numbers to stitch are missing.
        Either way this leaves both the series and the record exactly as they were and reports why,
        because the alternative is worse than doing nothing: writing `[]` would say "the log was
        asked and there is no move here", which is the sentence that retires the question for good.

        For a title whose chain is already ON RECORD the confirmation is not repeated. The record
        was written only after confirm() accepted it, and re-deriving it every run opened a path
        where a rejected hop silently emptied a good record and reverted the series — a 404 on one
        redirect, or a nudged CONFIRM_ threshold, and Fanny reads 500 again with `moves` saying
        nobody found anything and validate.py agreeing. A chain therefore only ever goes from
        non-empty to empty by a human editing the file.
        """
        handled.add(title)
        if chain is None:
            report("   %-32s the move log could not be read; leaving it as it was" % title)
            return "unresolved"
        by_title[title] = raw[title]                   # the canonical's own counts, pre-stitch
        for _, src in chain:
            if series_for(src) is None:
                report("   %-32s cannot be repaired this run; %r is missing. The series is "
                       "written as fetched and the gate will say so." % (title, src))
                return "unresolved"
        if not recorded_already:
            chain = pagemoves.confirm(axis, by_title, title, chain, log=report)
        # A rejected hop can leave the chain naming a boundary the article never crossed — two
        # entries under one title, or a last entry naming the canonical. Recording that would have
        # the file claim a move it did not act on; before the gate learned to derive its months
        # from pagemoves.holes(), it also asserted a null at every month the record NAMED, which
        # stitch() rightly does not write there. Collapsed, the record and the series agree.
        # Applied on the recorded path too, so a record written before this rule is repaired the
        # next time the title is touched.
        chain = pagemoves.collapse(title, chain)
        # EXCEPT that it must not empty one. `[]` is not a shorter record, it is the sentence "the
        # log was asked and there is no move here" — and on this path the log was not opened at
        # all, so writing it would retire a question nobody put. Hand it back to the suspects loop,
        # which asks properly; `handled` is what would otherwise stop it looking. That handoff is
        # conditional, though: the loop only takes titles whose series still STEPS, so a garbage
        # record on a quiet article is deferred every run and never resolved here. Harmless —
        # tenures() collapses it, so the series and the gate still agree — and validate.py's shape
        # check is what names it if it ever matters.
        if recorded_already and not chain:
            report("   %-32s the record names no boundary the article crossed; leaving it for "
                   "the move log to answer" % title)
            handled.discard(title)
            return "unresolved"
        moves[title] = chain
        if not chain:
            return "no-move"
        series[title] = pagemoves.stitch(axis, by_title, title, chain)
        report("   %-32s stitched across %s" % (
            title, ", ".join("%s <- %s" % (m, src) for m, src in chain)))
        return "stitched"

    known = [t for t in sorted(moves) if t in series and moves[t] and t in refetched]
    if known:
        report("re-applying %d recorded page move(s):" % len(known))
    for t in known:
        repair(t, moves[t], recorded_already=True)

    found = 0
    for ratio, title, i in pagemoves.suspects(series):
        # `handled` rather than a shape test: a stitch does not always flatten the series all the
        # way (Hanna Havrylets still steps 8x afterwards, because she died the month she was moved),
        # so a repaired title can still read as a suspect and would otherwise be investigated and
        # stitched a second time.
        if title in handled or not (title in refetched or title not in moves):
            continue
        report("   %-32s %.0fx step near %s — asking the move log" % (title, ratio, axis[i]))
        outcome = repair(title, pagemoves.find_moves(title, axis, log=report))
        if outcome == "stitched":
            found += 1
        elif outcome == "no-move":
            # ONLY here. The other way out of repair() is that the question is still open, and
            # saying "this article really had" about it would send the operator away satisfied.
            report("      no move that stuck; a %.0fx step in readership this article really had"
                   % ratio)
    if found:
        report("found %d page move(s) not previously recorded" % found)
    return {t: v for t, v in moves.items() if t in series}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--months", type=int, default=None,
                    help="how far back to consider stale (default: everything back to %s). NOT "
                         "how much is fetched: a title that needs fetching is always fetched over "
                         "the whole axis — see the header." % FLOOR)
    ap.add_argument("--end", help="last month of the window, YYYY-MM (default: last complete)")
    ap.add_argument("--force", action="store_true", help="refetch months already cached")
    ap.add_argument("--dry-run", action="store_true", help="write nothing")
    args = ap.parse_args()

    want = months_back(args.months, args.end)
    if not want:
        print("no months in range (the API has nothing before %s)" % FLOOR, file=sys.stderr)
        return 2
    # A MONTH IN PROGRESS IS NOT A MONTH. The API does not withhold the current month — asked on
    # the 6th it returns the first six days aggregated exactly like a finished month, with no flag
    # to say so — so nothing downstream can tell a six-day count from a thirty-day one, and it
    # would sit in the cache as a permanent trough. months_back() already ends at the last
    # COMPLETE month, so the clock is the guard and this is the one way past it.
    complete = months_back(1)[0]
    if args.end and args.end > complete:
        print("--end %s is not a complete month; the newest complete month is %s. The API would "
              "answer with the days so far as though they were the month." % (args.end, complete),
              file=sys.stderr)
        return 2

    with open(PEOPLE, encoding="utf-8") as f:
        people = json.load(f)
    titles = sorted({p["canonical"] for p in people.values()})

    cached = {"months": [], "series": {}}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            cached = json.load(f)
    # Read either on-disk form into one working shape: {title: {month: views|None}}. A list is the
    # current flat encoding, aligned to the cached axis; a dict is the older sparse one, which is
    # read here and written back flat.
    axis = cached.get("months") or []
    series = {t: (dict(zip(axis, v)) if isinstance(v, list) else dict(v))
              for t, v in (cached.get("series") or {}).items()}

    print("window %s .. %s (%d months), %d articles" % (want[0], want[-1], len(want), len(titles)))
    # The axis this run will WRITE, and therefore the window every fetch below asks for: everything
    # already cached plus everything wanted. Asking over anything narrower is what would write a
    # null for a month nobody asked about (see the header).
    axis_out = sorted(set(axis) | set(want))
    todo = [t for t in titles
            if args.force or any(m not in series.get(t, {}) for m in axis_out)]
    print("  %d need fetching, %d already complete" % (len(todo), len(titles) - len(todo)))

    missing, failed = [], []
    for i, t in enumerate(todo, 1):
        why = None
        try:
            got = fetch(t, axis_out)
        except Exception as e:                        # noqa: BLE001 - any transport failure
            # NEVER let one title abort the run: a 429 at title 300 used to raise out of main()
            # and discard 300 good fetches. (Which is also why a failure does not fail the whole
            # run below — the cache stays honest by dropping the ONE title, not the other 883.)
            why, got = e, None
        if why is not None:
            # The title AND the reason. The reason is what decides the operator's next move — a 429
            # means rerun in an hour, a timeout means check the network, a 500 that survived five
            # retries means something else — and since the run has just deleted those series,
            # "rerun" IS the recovery path.
            failed.append((t, why))
        elif got is None:
            missing.append(t)                         # 404: the title does not resolve at all
        else:
            series.setdefault(t, {}).update({m: got.get(m) for m in axis_out})
        if i % 25 == 0 or i == len(todo):
            print("  %d/%d" % (i, len(todo)), end="\r", flush=True)
        time.sleep(PAUSE)
    if todo:
        print()

    # A TITLE THAT DID NOT ANSWER MUST NOT BE WRITTEN AT ALL. The flatten at the end fills every
    # month on the axis with v.get(m), so a title that was already cached and failed THIS run gets
    # a null for the months it was asked about and never answered for — which reads back as
    # "asked, nothing there", so `todo` skips it forever and the "rerun to pick them up" advice
    # below is a lie. It also silenced the 404 report this file exists to keep printing: a bad
    # canonical in people.json was named exactly once and never again.
    #
    # Dropping the title instead makes it stale IN FULL next run, which is one request, and the
    # cost is visible rather than silent: that composer has no readership for one cycle instead of
    # a plausible-looking median short a month. Not `return 1` on any failure — that would discard
    # the other 883 good fetches, which is the thing the except above exists to prevent.
    stalled = [t for t, _ in failed] + missing
    forgotten = sorted(t for t in stalled if t in series)
    for t in stalled:
        series.pop(t, None)
    if forgotten:
        print("dropped %d cached series whose refetch did not answer, so the next run asks again "
              "in full: %s" % (len(forgotten), ", ".join(forgotten[:4])))

    if missing:
        print("%d articles returned no data - check the canonical title in data/people.json:"
              % len(missing))
        for t in missing:
            print("   " + t)
    if failed:
        print("%d failed after %d retries - rerun to pick them up:" % (len(failed), TRIES))
        for t, e in failed:
            print("   %s (%s)" % (t, e))

    # Every series is written over axis_out, and every series was ASKED over axis_out, so a null in
    # the file means exactly one thing. A title that has dropped off people.json is not asked for
    # any more, so it cannot keep that promise — and validate.py's stray-title check already fails
    # on a cached series with no canonical title behind it, so keeping one is not an option either.
    # Dropped rather than null-padded, and it comes back in full if the roster picks it up again.
    orphans = sorted(set(series) - set(titles))
    for t in orphans:
        del series[t]
    if orphans:
        print("dropped %d cached series no longer in data/people.json: %s"
              % (len(orphans), ", ".join(orphans[:4])))

    # THE MOVE REPAIR, on the flat form the detector reads and the file stores. It runs before
    # `covered` is counted and before the dry-run returns, because a run that reports numbers the
    # write would not produce is a run that lies. Every remaining series covers exactly axis_out —
    # a title missing a month is in `todo`, and one that did not answer has just been dropped — so
    # flattening here is lossless and flattening at the write below would be a second copy of the
    # same rule.
    flat = {t: [series[t].get(m) for m in axis_out] for t in series}
    moves = repair_moves(flat, axis_out, cached.get("moves"), set(todo) - set(stalled), print)
    series = {t: dict(zip(axis_out, v)) for t, v in flat.items()}

    covered = sum(1 for t in titles
                  if all(series.get(t, {}).get(m) is not None for m in axis_out))
    print("\n%d/%d articles have data for all %d months" % (covered, len(titles), len(axis_out)))

    if args.dry_run:
        print("dry run - data/pageviews.json unchanged")
        return 0

    out_axis = axis_out
    out = {
        "fetched": dt.date.today().isoformat(),
        "months": out_axis,
        "note": "monthly English Wikipedia page views (agent=user), by canonical article title; "
                "each series is aligned to `months`, null where the API had no datum and null at "
                "the month of a page move, which belongs to neither title. A month before a move "
                "is counted under the title the article held then; `moves` records which, and an "
                "empty list means the move log was asked and said none",
        "moves": {k: [list(x) for x in v] for k, v in sorted(moves.items())},
        "series": {k: [v.get(m) for m in out_axis] for k, v in sorted(series.items())},
    }
    with open(OUT, "w", encoding="utf-8") as f:
        # One line per composer: 884 changed lines on a monthly top-up instead of 118k, and a
        # quarter of the bytes of the indented object form.
        f.write("{\n")
        f.write('"fetched": %s,\n' % json.dumps(out["fetched"]))
        f.write('"months": %s,\n' % json.dumps(out["months"]))
        f.write('"note": %s,\n' % json.dumps(out["note"]))
        f.write('"moves": {\n')
        mv = list(out["moves"].items())
        for i, (k, v) in enumerate(mv):
            f.write("%s: %s%s\n" % (json.dumps(k, ensure_ascii=False),
                                    json.dumps(v, ensure_ascii=False, separators=(",", ":")),
                                    "," if i < len(mv) - 1 else ""))
        f.write("},\n")
        f.write('"series": {\n')
        items = list(out["series"].items())
        for i, (k, v) in enumerate(items):
            f.write("%s: %s%s\n" % (json.dumps(k, ensure_ascii=False),
                                    json.dumps(v, separators=(",", ":")),
                                    "," if i < len(items) - 1 else ""))
        f.write("}\n}\n")
    print("wrote data/pageviews.json (%d articles x %d months, %d moved, %d bytes)"
          % (len(series), len(out_axis), sum(1 for v in moves.values() if v),
             os.path.getsize(OUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
