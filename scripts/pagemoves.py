#!/usr/bin/env python3
# pwa-starter: none — this script is this repo's own
# /// script
# requires-python = ">=3.9"
# ///
"""A page MOVE is a hole in a page-view series, and this is the one rule for finding it.

Views are counted per TITLE, not per article: the API answers for the string that was requested,
and it has no idea two strings were the same page. Invariant 5 covers half of that — never ask for
a redirect, because a redirect is its own title with its own tiny count (Bartók returned 41 instead
of 14,330). This file is the other half, and it is the mirror image: asking for the RIGHT title
still undercounts every month the article was not sitting there yet.

Fanny Hensel is the case that made it visible. Her article was at "Fanny Mendelssohn" until March
2026, so ten years of her history was filed under a title that was, at the time, a redirect nobody
followed — about fifty views a month against the real 5,400. The canonical title was correct on every run.
The shipped median of 500 was not a readership at all: it was the midpoint of a series that is half
pre-move noise and half post-move reality, and the app then NARRATED the artefact, because 5,198
against a 95th percentile of 149 fires `SPIKE` in app.js at 34.9x and captions a rename as an
obituary. That is the plausible-looking wrong number this pipeline is arranged against, with a
confident sentence on top of it.

THE RULE: count the title the article actually occupied that month. Not the current title (that is
the bug), and not the sum of every title that reaches the article (that is a different policy, and
scripts/audit_redirects.py measures it: the median correction from summing redirects is 1.024x,
which is invisible on a five-decade log axis, and the price is that a composer's readership starts
depending on how many aliases their article happened to accumulate — an artefact of edit history
rather than of readership). A move is not an alias. The article LIVED at the old title, so its
views there are the same measurement under a different string, and they belong to the composer.

THREE PARTS, DELIBERATELY SPLIT.

`step()` and `suspects()` are OFFLINE and read only the cache, so validate.py can run them at the
gate with no network. They find the SHAPE of a move — a sustained level shift, not a spike — and
they are a suspect generator, nothing more: the shape has no clean threshold (a real move here runs
9x to 1163x; genuine growth reaches 8x, because the Chevalier de Saint-Georges got a film), and
tuning one would be choosing which real moves to miss.

`find_moves()` is ONLINE and is the arbiter of whether a move HAPPENED. It reads the MediaWiki
move log, which states the source title and the timestamp as structured fields rather than leaving
them to be inferred from the numbers — the same reason fetch_wikidata.py reads a P569 claim instead
of parsing prose. A suspect the log does not name is genuine growth and is left alone.

`confirm()` is offline again, and it is the arbiter of whether the move STUCK. The log records
events, not tenures: a move reverted twenty minutes later leaves the same two entries a permanent
one does, and a chain walked from the log alone put Roberto Gerhard at a title he never occupied.
Only a hop where the traffic actually changed hands is stitched.

WHY THE SEARCH IS OVER REDIRECTS AND NOT OVER THE PAGE'S OWN LOG. `list=logevents` is indexed by
the title a move came FROM, and what we have is the title it went TO, so the log of the canonical
title lists the moves AWAY from it and not the one we are looking for. The old title is however
still reachable: a move leaves a redirect behind, so the titles an article used to live at are
almost all in its own redirect list today. The exception is a move that DISAMBIGUATES — "Franz
Schmidt" -> "Franz Schmidt (composer)" leaves a disambiguation PAGE behind, not a redirect, and
that composer's series is the second-worst in this dataset (2 views a month before the move, 886
after) — so the qualifier-stripped form is always tried as well. The canonical title itself is in
the candidate set too, because an article that was moved away and back (Takemitsu, three times)
has the middle leg of that journey logged under its own name.
"""
import json
import re
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request

WIKI_API = "https://en.wikipedia.org/w/api.php"
UA = "quartet-composers/1.0 (https://github.com/jsundram/quartet-composers)"
PAUSE = 0.05
TRIES = 4
BACKOFF = [2, 5, 15]

# Wikipedia's parenthetical disambiguator. Same expression build_data.py and validate.py carry, for
# a different job: here it reconstructs the title an article was moved AWAY from when it was
# disambiguated, which is the one old title that is not left behind as a redirect.
QUALIFIER = re.compile(r"\s*\((?:composer|musician|conductor|violinist|pianist|[^)]*musician)\)$", re.I)

# The window each half of the shift is measured over, and how much of it has to be there. Twelve
# months on each side because that is the statistic's own window; six and three because a move can
# land near either end of the axis and still be the largest thing in the series (Fanny's is five
# months from the end).
SPAN = 12
MIN_BEFORE = 6
MIN_AFTER = 3

# A shift is only worth a network round trip if the article is READ after it. An article that goes
# from 0 to 8 views a month has multiplied by infinity and told us nothing, and the roster's tail
# is full of them.
SUSPECT_FLOOR = 20
SUSPECT_STEP = 4.0

# What the GATE treats as unexplained (validate.py). Higher on both counts than the suspect
# threshold, because this one fails a build: every confirmed move in this dataset that reaches it
# is 44x or more, while the largest step that turned out to be real readership — a film about the
# Chevalier de Saint-Georges — is 7.7x. The floor is what keeps a noisy 30-views-a-month article
# out of it. See validate.py's check_moves for what an unexplained one is actually asserting.
GATE_FLOOR = 100
GATE_STEP = 20.0


def step(vals, floor=SUSPECT_FLOOR):
    """(ratio, index) of the largest sustained level shift in one series, or (0, None).

    A MOVE IS A STEP, NOT A SPIKE, and that distinction is the whole detector. An obituary doubles
    a month and decays; a move raises the floor and leaves it there, because the readers never went
    anywhere — only the string they were counted under did. So both halves are MEDIANS over a
    window, which a single month cannot move, and the break month itself is dropped: a move lands
    mid-month and splits that month's traffic across two titles, so it belongs to neither side.

    The returned index is where the shift is largest, which is NOT reliably where the move
    happened — with a before-window of ones, every split scores about the same and the argmax
    wanders (Koželuch's lands three months early). It is a place to look, not a date. Use the log.
    """
    best = (0.0, None)
    for i in range(1, len(vals) - MIN_AFTER + 1):
        before = [v for v in vals[:i] if v is not None][-SPAN:]
        after = [v for v in vals[i + 1:] if v is not None][:SPAN]
        if len(before) < MIN_BEFORE or len(after) < MIN_AFTER:
            continue
        hi = statistics.median(after)
        if hi < floor:
            continue
        # A median of 0 is a real reading — the article existed and nobody opened it — so it cannot
        # divide, but it also must not disqualify: Koželuch's before-window is ones and zeros and
        # his is the largest move in the roster. Half a view stands in for "less than one".
        ratio = hi / max(statistics.median(before), 0.5)
        if ratio > best[0]:
            best = (ratio, i)
    return best


def suspects(series, minimum=SUSPECT_STEP, floor=SUSPECT_FLOOR):
    """[(ratio, title, index)] worth asking the move log about, largest first."""
    out = []
    for title, vals in series.items():
        if not isinstance(vals, list):
            continue
        ratio, i = step(vals, floor)
        if ratio >= minimum:
            out.append((ratio, title, i))
    return sorted(out, reverse=True)


# ------------------------------------------------------------------ the arbiter (network)
def _api(params):
    q = urllib.parse.urlencode(dict(params, format="json"))
    req = urllib.request.Request(WIKI_API + "?" + q,
                                 headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(TRIES):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.load(r)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            if attempt == TRIES - 1:
                raise
            wait = BACKOFF[min(attempt, len(BACKOFF) - 1)]
            if isinstance(e, urllib.error.HTTPError):
                try:
                    wait = max(wait, int(e.headers.get("Retry-After", 0)))
                except (TypeError, ValueError):
                    pass
            time.sleep(wait)
    return {}


def redirects(title):
    """Every mainspace title that currently redirects to `title`."""
    d = _api({"action": "query", "prop": "redirects", "rdnamespace": 0, "rdlimit": "max",
              "titles": title}).get("query", {}).get("pages", {})
    out = []
    for p in d.values():
        out += [r["title"] for r in p.get("redirects", [])]
    return out


def _move_log(title):
    """[(YYYY-MM-DDTHH:MM:SSZ, source, target)] for every mainspace move away from `title`."""
    events = _api({"action": "query", "list": "logevents", "letype": "move", "letitle": title,
                   "lelimit": "max", "leprop": "title|timestamp|details"})
    out = []
    for e in events.get("query", {}).get("logevents", []):
        target = (e.get("params") or {}).get("target_title")
        if target and (e.get("params") or {}).get("target_ns") == 0:
            out.append((e["timestamp"], e["title"], target))
    return out


# How far back the walk will follow a chain. Six is far more than any article here needs
# (Takemitsu, the longest, uses three) and exists so a cycle in the log cannot hang the run.
MAX_HOPS = 6


def find_moves(canonical, months, log=None):
    """[(YYYY-MM, title it moved FROM)] oldest first — the article's tenure inside `months`.

    Three distinct returns, and the caller must keep them distinct:
      - a non-empty list: this is where the article lived.
      - an EMPTY list: investigated, and the log says it has sat where it is for the whole window.
        fetch_views.py records that, and validate.py reads it as the difference between genuine
        growth nobody need look at again and a rename nobody has ever checked.
      - None: the log could not be READ this run. Not the same answer as "no move", and recording
        it as one would retire the question on the strength of a 429.

    Walks BACKWARDS from today, taking at each step the latest move that landed on the title the
    article was at. Backwards rather than forwards because only the end of the chain is known, and
    latest-first because an article can be moved away and back (Takemitsu went to the macron in
    2018, back in 2019 and to it again in 2020) — following the first edge into a title would loop
    between the two names instead of walking out of the window.
    """
    say = log or (lambda *_: None)
    # EVERY request here is guarded and any failure abandons the question rather than answering it
    # from a partial log: a missing redirect list loses the candidate the real hop is logged under,
    # and a missing move log loses the hop itself. Both would come back as a confident empty list.
    try:
        candidates = [canonical] + redirects(canonical)
    except Exception as e:                             # noqa: BLE001 - any transport failure
        say("      redirect list for %r failed (%s); not recording an answer" % (canonical, e))
        return None
    bare = QUALIFIER.sub("", canonical)
    if bare != canonical and bare not in candidates:
        candidates.append(bare)                        # the move that disambiguated; see the header
    edges = []
    for t in candidates:
        try:
            edges += _move_log(t)
        except Exception as e:                         # noqa: BLE001 - any transport failure
            say("      move log for %r failed (%s); not recording an answer" % (t, e))
            return None
        time.sleep(PAUSE)

    floor, ceiling = months[0], months[-1]
    chain, at, before = [], canonical, "9999"
    for hop in range(MAX_HOPS + 1):
        inbound = [e for e in edges if e[2] == at and e[0][:7] < before and e[0][:7] <= ceiling]
        if not inbound:
            break
        when, src, _ = max(inbound)
        # The floor FIRST. `inbound` is filtered by the ceiling but not by the axis start, so an
        # article with a full chain inside the window plus any older logged move would otherwise
        # be reported as truncated and thrown away — six real hops discarded, and the message
        # false, because walking out of the window is how a complete chain ends.
        if when[:7] < floor:
            break                                      # older than the axis: the window is all one title
        if hop == MAX_HOPS:
            # Truncating in silence would be the failure confirm() exists to prevent, one level up:
            # tenures() hands every month before the oldest surviving hop to that hop's source, so
            # a cut chain puts the article at a title it did not hold and looks complete on disk.
            say("      %r has more than %d moves inside the window; the chain is truncated and "
                "the months before %s are attributed to %r on no evidence"
                % (canonical, MAX_HOPS, before, at))
            return None
        chain.append((when[:7], src))
        at, before = src, when[:7]
    return sorted(chain)


# How far either side of a hop the handover is measured, how much the two titles' shares have to
# trade places for it to count, and how much traffic there has to be to trade. The statistic is the
# ratio OF the ratios — how the old title stood against the new one before, over how it stands
# after — because neither side alone is decisive: an old name keeps a lot of the traffic for months
# after a move (Dohnányi's drew 805 a month against the new title's 1,529) and a new one can be the
# smaller half of a disambiguation it was just split out of. What no revert does is trade places.
# The real hops in this dataset run 15x to a million; the reverted ones sit under 1.
CONFIRM_SPAN = 3
CONFIRM_SWAP = 5.0
CONFIRM_FLOOR = 20


def confirm(months, by_title, canonical, chain, log=None):
    """The hops in `chain` the page-view numbers actually support, in order.

    THE LOG STATES EVENTS, NOT TENURES, and that is the gap this closes. A move that was reverted
    twenty minutes later is two log entries exactly like a move that stuck, so a chain walked from
    the log alone can put an article somewhere it never really lived: Roberto Gerhard's log has
    three moves between "Robert" and "Roberto" and the article sat at "Roberto" through all of
    them — stitching that chain would have handed him a decade of a near-empty redirect's traffic
    and made his series worse than leaving it alone. Takemitsu's has the same pattern around a move
    that did stick.

    So each hop is put to the test the issue that opened this described: the traffic has to CHANGE
    HANDS. How the old title stood against the new one over the months before the move, divided by
    how it stands over the months after, has to be at least `CONFIRM_SWAP` — the month of the move
    itself excluded, because it is split between the two names and is the one month that cannot
    settle the question. A missing median is a zero, not a mystery: a destination with no readers
    at all before the move is a title that did not exist yet, which is the strongest evidence a hop
    can have rather than a reason to abstain.

    Hops are judged independently and a failing one is simply dropped, which is what lets a chain
    that is half real survive intact — Takemitsu was moved to the macron in 2018, back five months
    later and to it again in 2020, and all three of those are in his series; Gerhard's log has the
    same shape and only two of his three happened.
    """
    say = log or (lambda *_: None)
    idx = {m: i for i, m in enumerate(months)}
    titles = [src for _, src in chain] + [canonical]

    def med(title, lo, hi):
        vals = [v for v in (by_title.get(title) or [])[lo:hi] if v is not None]
        return statistics.median(vals) if vals else None

    kept = []
    for k, (month, src) in enumerate(chain):
        dst = titles[k + 1]
        i = idx.get(month)
        if i is None:
            continue
        was = [med(t, max(0, i - CONFIRM_SPAN), i) or 0 for t in (src, dst)]
        now = [med(t, i + 1, i + 1 + CONFIRM_SPAN) or 0 for t in (src, dst)]
        swap = (was[0] * now[1]) / (max(was[1], 0.5) * max(now[0], 0.5))
        if was[0] < CONFIRM_FLOOR or now[1] < CONFIRM_FLOOR or swap < CONFIRM_SWAP:
            say("      %s %s -> %s: logged, but the traffic did not change hands "
                "(%g/%g before, %g/%g after) — a revert, or a move of some other page"
                % (month, src, dst, was[0], was[1], now[0], now[1]))
            continue
        kept.append((month, src))
    return kept


def collapse(canonical, moves):
    """`moves` with the hops that did not actually change the title removed.

    confirm() judges hops independently, so an alternating chain can lose its middle one and leave
    two entries naming the same title in a row — or a last entry naming the canonical itself. Both
    say "the article moved here" about a boundary it did not cross, and a record that says so is
    wrong twice over: `tenures()` would open two spans where there is one, and validate.py's gate
    asserts a null at every month the record names, which stitch() rightly does not write when the
    title either side of the boundary is the same. Collapsing at the source is what keeps the
    record, the series and the gate saying one thing.
    """
    chain = list(moves)
    titles = [src for _, src in chain] + [canonical]
    return [hop for k, hop in enumerate(chain) if titles[k] != titles[k + 1]]


def tenures(canonical, moves):
    """[(title, first month it held, last month it held or None)] oldest first.

    `moves` is what find_moves returned: each entry names the month the article ARRIVED at the next
    title, so it is both the end of one tenure and the start of the next. The overlap is on purpose
    — a move happens on a day, and the month it happens in was read under both names.

    ADJACENT SPANS UNDER ONE TITLE ARE MERGED — by collapse(), which is the same rule stated on the
    chain instead of on the spans — because `confirm()` judges hops independently and an alternating
    chain can lose its middle one: A -> B -> A with the first hop rejected leaves two consecutive
    tenures both named A, and `stitch()` would then find A holding the boundary month twice and
    count it twice. Latent rather than theoretical — Gerhard and Takemitsu both happen to alternate
    cleanly today — and the symptom would be one plausible month, not a crash. This still collapses
    even though fetch_views.py collapses before recording, because a chain reaching here need not
    have come from that path.
    """
    spans, start = [], None
    for month, src in collapse(canonical, moves):
        spans.append((src, start, month))
        start = month
    spans.append((canonical, start, None))
    return spans


def stitch(months, by_title, canonical, moves):
    """One series over `months`: each month counted under the title the article was at.

    THE MONTH OF THE MOVE IS NULL, because it is the one month the rule cannot answer for. A move
    happens on a day, so those readers are split across both names — Fanny's March 2026 is 852
    under the new title and 6,556 under the old — and none of the three available numbers is the
    month: either title alone is a partial month, and the sum quietly adds the redirect share that
    every OTHER month excludes. For an ASCII-to-diacritic rename that share is large, so summing
    invented a peak rather than a rounding error — Takemitsu's 2020-10 came out at 5,366 against
    neighbours of ~3,500, 53% high. That matters because of invariant 9: the sparkline prints
    EXACT counts on hover, so a reader hovering it would have read a month that never happened,
    in a file whose whole argument is that a step nobody can explain is an artefact.

    `null` already means exactly this here — asked, and there is no answer to give (invariant 10) —
    the sparkline already breaks its path at one, and build_data.py already drops it from the
    median rather than counting it as zero. One month of twelve for one composer is a cheaper
    price than a fabricated peak.
    """
    spans = tenures(canonical, moves)
    idx = {m: i for i, m in enumerate(months)}
    out = []
    for m in months:
        held = [t for t, lo, hi in spans
                if (lo is None or m >= lo) and (hi is None or m <= hi)]
        if len(held) != 1:
            out.append(None)                           # the month of the move; see the docstring
            continue
        v = by_title.get(held[0]) or []
        out.append(v[idx[m]] if idx[m] < len(v) else None)
    return out
