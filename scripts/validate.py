#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Gate composers.json on the classes of error that have actually shipped from this repo.

    python3 scripts/validate.py              # structural + cross-file + drift vs the last commit
    python3 scripts/validate.py --strict     # warnings become errors
    python3 scripts/validate.py --no-drift   # skip the git baseline (fresh clone, or on purpose)
    python3 scripts/validate.py --root DIR --baseline FILE    # validate a copy (used by the tests)

WHY THIS EXISTS, SPECIFICALLY. Every serious bug this dataset has had was a DATA bug, and not one
was caught by a test — they were caught by a human noticing a number looked wrong, twice only after
it was already live:

  - "Bela Bartok" is a redirect, and the pageviews API answers per title, so it returned 41 views
    instead of Béla Bartók's 14,330. Status 200, no error, and the chart drew a famous composer as
    a dot nobody reads.
  - A bare "John Adams" resolves correctly and unambiguously to the second President of the United
    States. His 144,948 monthly views put him above Beethoven on a chart about string quartets.
  - Wikidata marks known-wrong values `deprecated` rather than deleting them; reading claims
    without checking rank reported Tania León — alive, Pulitzer 2021 — as dead since 1996.
  - The "living" flag was derived from the page-view month, so refreshing views to a new year would
    have silently reclassified every living composer as dead.

Every one produced PLAUSIBLE-LOOKING output. That is the whole problem: unit tests do not help,
code review does not help, and the only thing that reliably catches them is comparing the numbers
against something. So this compares them against three things — the schema, the other cached files,
and the previous commit — and fails the build rather than waiting for someone to notice.

Wired into .githooks/pre-commit (warn-only, so it nags) and CI (real exit code).
"""
import argparse
import datetime as dt
import json
import os
import re
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # overridable with --root, so the suite can validate a copy
THIS_YEAR = dt.date.today().year

ERRORS, WARNINGS = [], []

# A P21 value that never found a label in fetch_wikidata.py's GENDERS map. Matched structurally
# rather than against a copy of that map, so ADDING a label there needs no edit here and only the
# actual failure — an unlabelled value reaching the app — trips the gate.
GENDER_QID = re.compile(r"^Q\d+$")

# The values the UI can actually FILTER — the pills in index.html and the whitelist app.js accepts
# from the URL. fetch_wikidata.py's GENDERS map is deliberately larger than this (it labels eight
# P21 items), so the two vocabularies can drift apart, and a label that no pill can reach is a
# person the app cannot show and the footnote miscounts: they are in neither filter, while the
# provenance line only ever counts the composers with NO claim. Nothing else fails when that
# happens, which is why it fails here — the same job Chart.missingNames() does for the canon.
# Widening this means adding a pill in index.html AND the value to app.js's readHash whitelist.
FILTERABLE = ("female", "male")


def err(msg):
    ERRORS.append(msg)


def warn(msg):
    WARNINGS.append(msg)


def load(path, required=True):
    p = os.path.join(ROOT, path)
    if not os.path.exists(p):
        if required:
            err("missing %s — run the pipeline (see README)" % path)
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def baseline_rows(path=None):
    """The previous composers.json — an explicit file, else HEAD. The build's before/after picture."""
    if path:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    try:
        out = subprocess.run(["git", "-C", ROOT, "show", "HEAD:composers.json"],
                             capture_output=True, text=True, timeout=20)
        if out.returncode != 0:
            return None
        return json.loads(out.stdout)
    except Exception:                                  # noqa: BLE001 - no git, first commit, etc.
        return None


# --------------------------------------------------------------- structure
def check_structure(cur):
    fields = cur.get("fields") or []
    expect = ["name", "birth", "death", "quartets", "views", "views_lo", "views_hi", "gender"]
    if fields != expect:
        err("fields changed: %s (app.js and chart.js index these POSITIONALLY, so a reorder "
            "silently shifts every column)" % fields)
        return []
    rows = cur.get("rows") or []
    if not rows:
        err("composers.json has no rows")
        return []

    seen = {}
    for r in rows:
        if len(r) != len(expect):
            err("row has %d fields, expected %d: %r" % (len(r), len(expect), r[:2]))
            continue
        name, birth, death, quartets, views, lo, hi, gender = r
        if not name or not isinstance(name, str):
            err("row with no name: %r" % (r,))
        if name in seen:
            err("duplicate name %r — selection is keyed by name in the URL, so duplicates make a "
                "shared link ambiguous" % name)
        seen[name] = True
        if not isinstance(birth, int) or not (1400 <= birth <= THIS_YEAR):
            err("%s: implausible birth year %r" % (name, birth))
            continue
        if death is not None:
            if not isinstance(death, int):
                err("%s: non-integer death %r" % (name, death))
            elif death < birth:
                err("%s: died %d before born %d" % (name, death, birth))
            elif death > THIS_YEAR:
                err("%s: death year %d is in the future" % (name, death))
            elif death - birth > 115:
                warn("%s: lifespan of %d years" % (name, death - birth))
        if quartets is not None and not (isinstance(quartets, int) and 1 <= quartets <= 300):
            err("%s: implausible quartet count %r" % (name, quartets))
        if views is not None:
            if not isinstance(views, int) or views < 0:
                err("%s: bad view count %r" % (name, views))
            elif lo is None or hi is None or not (lo <= views <= hi):
                err("%s: median %r outside its own range [%r, %r]" % (name, views, lo, hi))
        # PRESENT BUT UNPARSED. P21's value arrives as a QID and fetch_wikidata.py labels it from a
        # map that cannot be exhaustive. An unmapped value passes the QID through on purpose — it
        # is a real, stated fact and nulling it would file a person under "Wikidata doesn't say" —
        # so this is where it has to stop, because a raw QID matches no filter and reads as noise
        # in the one place the UI prints it.
        if gender is not None:
            if not isinstance(gender, str) or not gender:
                err("%s: bad gender %r" % (name, gender))
            elif GENDER_QID.match(gender):
                err("%s: gender is the raw QID %s — add its label to GENDERS in "
                    "fetch_wikidata.py; shipped like this it matches no filter" % (name, gender))
            elif gender != gender.lower():
                err("%s: gender %r is not a Wikidata label as lowercased by fetch_wikidata.py"
                    % (name, gender))
            elif gender not in FILTERABLE:
                err("%s: gender %r is a value the UI cannot filter — add a pill for it in "
                    "index.html and the value to app.js's readHash whitelist, or the row is in "
                    "NEITHER filter while the footnote still counts only the composers with no "
                    "claim at all" % (name, gender))
    return rows


# Wikipedia's parenthetical disambiguator, stripped from displayed names by build_data.py. Shared
# by the two checks that compare a displayed name back to its cached canonical title.
QUALIFIER = re.compile(r"\s*\((?:composer|musician|conductor|violinist|pianist|[^)]*musician)\)$", re.I)


# --------------------------------------------------------------- cross-file
def check_sources(rows, meta, people, pv, listing):
    """The caches must agree with each other, and with what composers.json claims."""
    if not (people and pv and listing):
        warn("pipeline caches missing — skipping cross-file checks")
        return

    canon = {p["canonical"] for p in people.values() if p.get("canonical")}

    # THE BARTÓK CHECK. Page views are counted per title; a redirect is its own title with its own
    # tiny count. Every key in pageviews.json must be a CANONICAL title, or some row's dot is sized
    # by redirect traffic. This is the check that would have caught the bug before it shipped.
    stray = sorted(set(pv.get("series", {})) - canon)
    if stray:
        err("%d page-view series are keyed by a NON-canonical title (redirect traffic, not the "
            "article's): %s" % (len(stray), ", ".join(stray[:6])))

    unresolved = sorted(t for t, p in people.items() if not p.get("qid"))
    if unresolved:
        warn("%d titles have no Wikidata item, so their dates come from page prose only: %s"
             % (len(unresolved), ", ".join(unresolved[:6])))

    # THE TANIA LEÓN CHECK. A death year Wikidata reports must at least be possible.
    for t, p in people.items():
        wb, wd = p.get("wd_birth"), p.get("wd_death")
        if wd is not None and wb is not None and wd < wb:
            err("%s: Wikidata death %s precedes birth %s" % (t, wd, wb))
        if wd is not None and wd > THIS_YEAR:
            err("%s: Wikidata death year %s is in the future" % (t, wd))

    months = pv.get("months") or []
    stat = meta.get("views_months") or months[-12:]
    if len(stat) < 6:
        warn("the statistic is a median of only %d months; it is meant to smooth a year" % len(stat))
    if stat and months and months[-len(stat):] != stat:
        err("composers.json's statistic window ends %s, the cache ends %s — one of the two files "
            "is from an older run" % (stat[-1], months[-1]))
    # Completeness is measured over the STATISTIC's window, not the whole cache. The cache reaches
    # back to 2015-07 now and an article created in 2019 legitimately has nothing before it, so
    # judging that as a gap would fire this on a third of the roster forever. What has to be
    # complete is the twelve months every dot's size is computed from.
    complete = sum(1 for t in canon if all(m in pv.get("series", {}).get(t, {}) for m in stat))
    if canon and complete / len(canon) < 0.9:
        warn("only %d of %d articles have the full %d-month statistic window"
             % (complete, len(canon), len(stat)))
    deep = sum(1 for t in canon if len(pv.get("series", {}).get(t, {})) >= 24)
    if canon and deep / len(canon) < 0.7:
        warn("only %d of %d articles have 2+ years of history; the sparkline has little to draw"
             % (deep, len(canon)))

    # Coverage floors. Each of these dropping is a sign a parser or a fetch quietly broke, and the
    # symptom is a chart that looks fine with a third of its dots missing.
    n = len(rows)
    have_views = sum(1 for r in rows if r[4] is not None)
    have_q = sum(1 for r in rows if r[3] is not None)
    living = sum(1 for r in rows if r[2] is None)
    if have_views / n < 0.95:
        err("only %d/%d rows have page views (floor 95%%)" % (have_views, n))
    if have_q / n < 0.80:
        err("only %d/%d rows have a quartet count (floor 80%%)" % (have_q, n))
    if not 0.15 < living / n < 0.60:
        err("%d/%d rows read as living — outside the plausible 15-60%% band, which is how the "
            "'living' logic breaking looks" % (living, n))

    # Gender has one source and no fallback, so both ways it can break are silent: reading the
    # wrong property nulls the column (the filter matches nobody and the footnote's count is a
    # lie), and mis-reading the VALUE moves everyone into one bucket. Neither looks like an error.
    have_gender = sum(1 for r in rows if r[7] is not None)
    women = sum(1 for r in rows if r[7] == "female")
    if have_gender / n < 0.95:
        err("only %d/%d rows have a P21 value (floor 95%%) — the claim is on nearly every item, "
            "so this is a read that broke, not a gap in Wikidata" % (have_gender, n))
    # A separate `if`, not an `elif`: a partial read that ALSO mislabels values is two problems,
    # and chaining them reports the second only after the first is fixed.
    if not 0.15 < women / n < 0.50:
        err("%d/%d rows read as female — outside the plausible 15-50%% band. The list has run "
            "about 31%% women; a number outside this is a value being misread, not a re-scrape"
            % (women, n))

    # And it must be the CACHE's value, not one invented downstream — the same structural
    # assertion check_names() makes about the names, for the same reason.
    cached = {QUALIFIER.sub("", p["canonical"]): p.get("gender")
              for p in people.values() if p.get("canonical")}
    bad = [r[0] for r in rows if r[0] in cached and r[7] != cached[r[0]]]
    if bad:
        err("%d rows carry a gender that data/people.json does not state: %s"
            % (len(bad), ", ".join(bad[:6])))


# --------------------------------------------------------------- name sanity
def check_history(rows, meta, hist, pv):
    """readership.json — the sparkline's data — against composers.json and the cache behind both.

    These are two files describing one measurement, which is exactly the arrangement that drifts:
    rebuild one and not the other and every panel draws a decade of history that belongs to a
    different fetch than the number printed above it. Nothing in the app can notice, because both
    files are internally consistent. So the median, min and max of the LAST TWELVE points of each
    sparkline are recomputed here and must equal the views/views_lo/views_hi the row ships.
    """
    if hist is None:
        err("missing readership.json — scripts/build_data.py writes it alongside composers.json")
        return
    months = hist.get("months") or []
    stat = meta.get("views_months") or []
    if not months:
        err("readership.json states no months")
        return
    if months != sorted(months):
        err("readership.json's months are not in chronological order; the sparkline is drawn in "
            "array order, so it would be plotting time out of sequence")
    if stat and months[-len(stat):] != stat:
        err("readership.json ends %s but composers.json's statistic window ends %s — the two were "
            "built from different fetches" % (months[-1], stat[-1]))
    if pv and pv.get("months") and pv["months"] != months:
        err("readership.json covers %d months, data/pageviews.json caches %d — rebuild"
            % (len(months), len(pv["months"])))

    series = hist.get("series") or {}
    names = {r[0]: r for r in rows}
    stray = sorted(set(series) - set(names))
    if stray:
        err("%d readership series name nobody in composers.json (a rename that only landed in one "
            "file): %s" % (len(stray), ", ".join(stray[:6])))
    orphan = sorted(r[0] for r in rows if r[4] is not None and r[0] not in series)
    if orphan:
        err("%d composers ship a view count with no history behind it: %s"
            % (len(orphan), ", ".join(orphan[:6])))
    if len(rows) and len(series) / len(rows) < 0.95:
        err("only %d/%d composers have a readership series (floor 95%%)" % (len(series), len(rows)))

    k = len(stat) or 12
    disagree = []
    for name, vals in sorted(series.items()):
        row = names.get(name)
        if row is None:
            continue
        if not isinstance(vals, list) or len(vals) != len(months):
            err("%s: %r readership points for %d months" % (name, len(vals or []), len(months)))
            continue
        if any(v is not None and (not isinstance(v, int) or v < 0) for v in vals):
            err("%s: a readership value is not a view count" % name)
            continue
        tail = [v for v in vals[-k:] if v is not None]
        got = (int(statistics.median(tail)), min(tail), max(tail)) if tail else (None, None, None)
        if got != (row[4], row[5], row[6]):
            disagree.append("%s: history says %s, the row says %s" % (name, got, tuple(row[4:7])))
    if disagree:
        err("%d composers' sparkline and printed readership come from different data: %s"
            % (len(disagree), "; ".join(disagree[:3])))


def check_names(rows, people):
    """Every displayed name must BE a canonical Wikipedia title, minus its disambiguator.

    This replaced a heuristic that looked for implausible consonant runs — the tell of the 2014
    scrape, which deleted non-ASCII characters rather than transliterating them ("Lutoslawski").
    That fired on 25 perfectly good German names and would have been ignored within a week.

    The structural assertion is both precise and stronger: names come from the resolver now, so if
    one ISN'T a resolved title, something has started sourcing names from raw scrape text again —
    which is exactly how the mangled-name class would come back.
    """
    if not people:
        return
    valid = {QUALIFIER.sub("", p["canonical"]) for p in people.values() if p.get("canonical")}
    orphans = [r[0] for r in rows if r[0] not in valid]
    if orphans:
        err("%d names are not resolved Wikipedia titles — names must come from data/people.json, "
            "not from raw page text: %s" % (len(orphans), ", ".join(orphans[:6])))


# --------------------------------------------------------------- drift
def check_drift(rows, prev):
    """Compare against the previous commit. This is the John Adams check.

    A wrong-article join does not look wrong in isolation — it looks like a popular composer. It
    only looks wrong NEXT TO what the same row said last time. Ratios rather than differences,
    because the interesting failures are order-of-magnitude ones.
    """
    if not prev:
        warn("no committed composers.json to diff against — drift checks skipped")
        return
    old = {r[0]: r for r in prev.get("rows", [])}
    new = {r[0]: r for r in rows}

    gone, added = set(old) - set(new), set(new) - set(old)
    if len(gone) > max(20, 0.05 * len(old)):
        err("%d composers vanished since the last commit (>5%%): %s"
            % (len(gone), ", ".join(sorted(gone)[:6])))
    elif gone:
        warn("%d composers gone: %s" % (len(gone), ", ".join(sorted(gone)[:8])))
    if added:
        warn("%d composers added: %s" % (len(added), ", ".join(sorted(added)[:8])))

    for name in sorted(set(old) & set(new)):
        o, n = old[name], new[name]
        if o[1] != n[1]:
            warn("%s: birth year %s -> %s" % (name, o[1], n[1]))
        # A living composer acquiring a death date is normal and sad; the reverse means the
        # previous run invented one, which is the deprecated-rank bug.
        if o[2] is not None and n[2] is None:
            err("%s: had death year %s, now reads as LIVING — a death date was invented before, "
                "or is being dropped now" % (name, o[2]))
        if o[3] and n[3] and (n[3] / o[3] > 5 or o[3] / n[3] > 5):
            warn("%s: quartet count %s -> %s (>5x) — check the sentence in data/list.wiki"
                 % (name, o[3], n[3]))
        # A person's P21 does get corrected on Wikidata, and that correction should flow through.
        # But it is also what a wrong-item join looks like from the other side, so it is never
        # silent: this is a two-line diff to read, not a number to trust.
        #
        # Length-guarded because the BASELINE is whatever the last commit shipped, which is one
        # field shorter across any schema addition — the commit that adds a field is exactly the
        # one where a positional read of it crashes the gate that was meant to check it.
        if len(o) > 7 and len(n) > 7 and o[7] != n[7]:
            warn("%s: gender %r -> %r — a Wikidata correction, or the row joined to a different "
                 "person" % (name, o[7], n[7]))
        if o[4] and n[4] and (n[4] / o[4] > 20 or o[4] / n[4] > 20):
            err("%s: page views %s -> %s (>20x). A jump this size is a wrong article, not a change "
                "in readership — check the resolved title." % (name, o[4], n[4]))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    ap.add_argument("--no-drift", action="store_true", help="skip the git baseline comparison")
    ap.add_argument("--root", help="validate a different checkout (tests)")
    ap.add_argument("--baseline", help="explicit previous composers.json instead of git HEAD")
    args = ap.parse_args()
    if args.root:
        global ROOT
        ROOT = os.path.abspath(args.root)

    cur = load("composers.json")
    if cur is None:
        print("FAIL: %s" % ERRORS[0], file=sys.stderr)
        return 1

    rows = check_structure(cur)
    if rows:
        people = load("data/people.json", required=False)
        meta = cur.get("meta") or {}
        pv = load("data/pageviews.json", required=False)
        check_sources(rows, meta, people, pv, load("data/list.json", required=False))
        check_history(rows, meta, load("readership.json", required=False), pv)
        check_names(rows, people)
        if not args.no_drift:
            check_drift(rows, baseline_rows(args.baseline))

    for w in WARNINGS:
        print("  warn  %s" % w)
    for e in ERRORS:
        print("  ERROR %s" % e, file=sys.stderr)

    if ERRORS or (args.strict and WARNINGS):
        print("\nvalidate: %d error(s), %d warning(s)" % (len(ERRORS), len(WARNINGS)), file=sys.stderr)
        return 1
    print("validate: %d rows OK (%d warning(s))" % (len(rows), len(WARNINGS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
