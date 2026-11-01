#!/usr/bin/env python3
# pwa-starter: none — this script is this repo's own
# /// script
# requires-python = ">=3.9"
# ///
"""Who is on the chart: a yes or no for every entry the list page has ever had -> data/inclusion.json.

    python3 scripts/roster.py                         # record newcomers as no; run after fetch_wikidata.py
    python3 scripts/roster.py --brief --base REF      # the dossier on everyone new since REF, as markdown
    python3 scripts/roster.py --apply BODY --base REF # read the PR's ticked boxes into the decisions

THE LIST PAGE IS RE-READ EVERY MONTH, AND NOBODY JOINS UNREAD. A newcomer enters as no, so the build
ships without them until someone has looked; `build_rows()` refuses an entry with no decision at all,
which is what makes skipping this step a failure rather than a silent addition. The monthly PR
carries the dossier and one box per newcomer, and `.github/workflows/roster.yml` turns a tick into a
yes on the same branch. Merging with a box unticked leaves that no in place.

A RENAME IS NOT A NEWCOMER. An entry that resolves to the same Wikidata item as one that left the
list carries that one's decision, because the person was already decided on.

The dossier is evidence for a human, not a judgement: every flag below is a reason to read the
entry, and none of them decides anything.
"""
import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from build_data import QUALIFIER, STAT_MONTHS  # noqa: E402

ROSTER = os.path.join(ROOT, "data", "inclusion.json")
LIST = os.path.join(ROOT, "data", "list.json")
WIKI = os.path.join(ROOT, "data", "list.wiki")
PEOPLE = os.path.join(ROOT, "data", "people.json")
VIEWS = os.path.join(ROOT, "data", "pageviews.json")
IMSLP = os.path.join(ROOT, "data", "imslp-scrape.json")
SHIPPED = os.path.join(ROOT, "composers.json")
API = "https://en.wikipedia.org/w/api.php"
UA = "quartet-composers/1.0 (https://github.com/jsundram/quartet-composers)"

# The box and the title it decides travel on one line, so a reworded label cannot detach them.
BOX = re.compile(r"^\s*[-*]\s*\[([ xX])\].*<!--\s*roster:\s*(.+?)\s*-->\s*$", re.M)


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def at(ref, rel):
    """A file as it stood at a git ref, parsed, or None."""
    out = subprocess.run(["git", "-C", ROOT, "show", "%s:%s" % (ref, rel)],
                         capture_output=True, text=True)
    return json.loads(out.stdout) if out.returncode == 0 else None


def record(entries, people, roster):
    """Decide every undecided entry: a rename inherits, anyone else is a no. -> (roster, added, renamed)."""
    roster = dict(roster)
    listed = {e["title"] for e in entries}
    qid = lambda t: (people.get(t) or {}).get("qid")
    left = {qid(t): t for t in roster if t not in listed and qid(t)}
    added, renamed = [], []
    for e in entries:
        t = e["title"]
        if t in roster:
            continue
        was = left.get(qid(t)) if qid(t) else None
        if was is not None:
            roster[t] = roster[was]
            renamed.append((was, t))
        else:
            roster[t] = False
            added.append(t)
    return roster, added, renamed


def newcomers(entries, base_entries, people):
    """Titles on the list now and not at the base, less the renames. -> (new, renamed, gone)."""
    now = {e["title"] for e in entries}
    then = {e["title"] for e in base_entries}
    qid = lambda t: (people.get(t) or {}).get("qid")
    gone = {qid(t): t for t in then - now if qid(t)}
    new, renamed = [], []
    for t in sorted(now - then):
        if qid(t) and qid(t) in gone:
            renamed.append((gone.pop(qid(t)), t))
        else:
            new.append(t)
    return new, renamed, sorted(set(gone.values()) | {t for t in then - now if not qid(t)})


def ticks(body):
    """{title: ticked} for every roster box in a PR body."""
    return {m.group(2): m.group(1) != " " for m in BOX.finditer(body or "")}


def apply(roster, boxes, new):
    """Set the decisions the boxes state, for newcomers only — a body cannot reach anyone else."""
    roster, changed = dict(roster), []
    for t, yes in boxes.items():
        if t in new and roster.get(t) is not yes:
            roster[t] = yes
            changed.append((t, yes))
    return roster, changed


def save(roster):
    with open(ROSTER, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(roster.items())), f, ensure_ascii=False, indent=0)
        f.write("\n")


# ---------------------------------------------------------------- the dossier
def entry_line(wikitext, title):
    for line in (wikitext or "").splitlines():
        if re.match(r"^\*\s*\[\[%s(\||\]\])" % re.escape(title), line):
            return re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", line).strip()
    return None


def median_views(series):
    vals = [v for v in (series or [])[-STAT_MONTHS:] if v is not None]
    return (int(statistics.median(vals)), len(vals)) if vals else (None, 0)


def imslp_of(qid, title, scrape):
    """(category, quartet pages) for a person, through Wikidata's P839 or IMSLP's own biography link."""
    if not scrape:
        return None, 0
    cats = [c for c in (scrape.get("p839") or {}).get(qid) or []]
    if not cats:
        for cat, text in (scrape.get("wikitext") or {}).items():
            m = re.search(r"\[\[wikipedia:([^|\]]+)", text or "")
            if m and m.group(1).strip() == title:
                cats.append("Category:" + cat)
    if not cats:
        return None, 0
    name = cats[0][len("Category:"):] if cats[0].startswith("Category:") else cats[0]
    pages = sum(1 for _pid, _t, c in (scrape.get("works") or {}).get("orig") or [] if c == name)
    return name, pages


def ordinal(n):
    return "%d%s" % (n, "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))


def rank(value, values):
    return 1 + sum(1 for v in values if v is not None and v > value)


def facts(t, entry, person, series, scrape, rows):
    """Everything the dossier says about one newcomer, as data — `dossier()` only formats it."""
    canon = person.get("canonical")
    name = QUALIFIER.sub("", canon or t)
    views, months = median_views(series.get(canon) if canon else None)
    cat, pages = imslp_of(person.get("qid"), canon or t, scrape)
    q, birth, death = entry["quartets"], person.get("birth", entry["birth"]), person.get("death")
    counts = [r[3] for r in rows]
    flags = []
    if canon is None:
        flags.append("The list links to no Wikipedia article, so %s can have no readership." % name)
    if not person.get("qid"):
        flags.append("No Wikidata item: the dates come from the list's own prose.")
    if q is None:
        flags.append("The entry states no count we can read, so %s would be in the table only, "
                     "not on the chart." % name)
    elif rank(q, counts) <= 10:
        top = max(rows, key=lambda r: r[3] or 0)
        flags.append("%d quartets would rank %s on the roster (the most is %s, %d). Check the "
                     "sentence and its source." % (q, ordinal(rank(q, counts)), top[0], top[3]))
    if q is not None and pages > q:
        flags.append("IMSLP has more quartet pages (%d) than the entry states quartets (%d)."
                     % (pages, q))
    for kind, page, wd in (("birth", entry["birth"], person.get("wd_birth")),
                           ("death", entry["death"], person.get("wd_death"))):
        if page is not None and wd is not None and page != wd:
            flags.append("The list says %s %s, Wikidata %s; Wikidata wins." % (kind, page, wd))
    if death is None and birth is not None:
        flags.append("No death date on Wikidata, so %s would be drawn as living." % name)
    if person.get("gender") is None:
        flags.append("No P21 on Wikidata, so %s would be in neither gender filter." % name)
    if canon and 0 < months < STAT_MONTHS:
        flags.append("Only %d months of readership: a new article, or a recent move." % months)
    surname = name.split()[-1]
    same = sorted(r[0] for r in rows if r[0].split()[-1] == surname)
    if same:
        flags.append("Shares a surname with %s, so the chart's short names for them may change."
                     % ", ".join(same))
    return {"title": t, "name": name, "canon": canon, "qid": person.get("qid"), "birth": birth,
            "death": death, "gender": person.get("gender"), "quartets": q,
            "q_rank": rank(q, counts) if q is not None else None, "plotted": sum(c is not None for c in counts),
            "views": views, "months": months,
            "v_rank": rank(views, [r[4] for r in rows]) if views is not None else None,
            "imslp": cat, "pages": pages, "flags": flags, "roster": len(rows)}


def wiki_get(params):
    q = urllib.parse.urlencode(dict(params, format="json", formatversion=2))
    req = urllib.request.Request(API + "?" + q, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def provenance(titles, canons, old_rev, new_rev):
    """{title: {...}} — the list edit that added each newcomer, and the article's own age and size.

    Network, and optional: a failure costs the dossier these lines and nothing else."""
    out = {t: {} for t in titles}
    try:
        revs, cont = [], {}
        while True:
            d = wiki_get(dict({"action": "query", "prop": "revisions",
                               "titles": "List of string quartet composers", "rvdir": "newer",
                               "rvstartid": old_rev, "rvendid": new_rev, "rvlimit": 50,
                               "rvprop": "ids|timestamp|user|comment|content", "rvslots": "main"},
                              **cont))
            revs += d["query"]["pages"][0].get("revisions", [])
            if "continue" not in d:
                break
            cont = d["continue"]
        for t in titles:
            pat = re.compile(r"^\*\s*\[\[%s(\||\]\])" % re.escape(t), re.M)
            for r in revs:
                if pat.search(r["slots"]["main"].get("content", "")):
                    out[t]["edit"] = {k: r.get(k) for k in ("revid", "parentid", "timestamp",
                                                           "user", "comment")}
                    break
    except Exception as e:  # noqa: BLE001 — see the docstring
        print("  list history unavailable: %s" % e, file=sys.stderr)
    for t in titles:
        c = canons.get(t)
        if not c:
            continue
        try:
            p = wiki_get({"action": "query", "prop": "info|revisions", "titles": c,
                          "rvdir": "newer", "rvlimit": 1, "rvprop": "timestamp|user"})["query"]["pages"][0]
            first = (p.get("revisions") or [{}])[0]
            out[t]["article"] = {"length": p.get("length"), "created": first.get("timestamp"),
                                 "creator": first.get("user")}
        except Exception as e:  # noqa: BLE001
            print("  article info unavailable for %s: %s" % (c, e), file=sys.stderr)
    return out


def link(title):
    return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))


def dossier(f, entry_text, prov, ticked):
    life = "%s–%s" % (f["birth"] or "?", f["death"] or "")
    out = ["### %s (%s)" % (f["name"], life), "",
           "- [%s] **Include %s** <!-- roster: %s -->" % ("x" if ticked else " ", f["name"], f["title"]),
           ""]
    if entry_text:
        out += ["> " + entry_text, ""]
    q = ("%d — would rank %s of %d with a count" % (f["quartets"], ordinal(f["q_rank"]), f["plotted"])
         if f["quartets"] is not None else "none read from the entry")
    v = ("%s/mo median of %d months — would rank %s of %d"
         % (format(f["views"], ","), f["months"], ordinal(f["v_rank"]), f["roster"])
         if f["views"] is not None else "none")
    rows = [("Quartets, from the entry", q), ("Readership", v),
            ("Gender (Wikidata P21)", f["gender"] or "not stated"),
            ("IMSLP", "%s, %d quartet pages" % (f["imslp"], f["pages"]) if f["imslp"] else "no page found")]
    a, e = prov.get("article"), prov.get("edit")
    if a:
        rows.append(("Article", "%s bytes, created %s by %s"
                     % (format(a["length"] or 0, ","), (a["created"] or "?")[:10], a["creator"])))
    if e:
        rows.append(("Added to the list", "%s by %s%s"
                     % ((e["timestamp"] or "?")[:10], e["user"],
                        ' — "%s"' % e["comment"] if e.get("comment") else "")))
        if a and a.get("creator") and a["creator"] == e.get("user"):
            f["flags"].append("The same editor created the article and added it to the list.")
    out += ["| | |", "|---|---|"] + ["| %s | %s |" % r for r in rows] + [""]
    links = []
    if f["canon"]:
        links.append("[Wikipedia](%s)" % link(f["canon"]))
    if f["qid"]:
        links.append("[Wikidata](https://www.wikidata.org/wiki/%s)" % f["qid"])
    if f["imslp"]:
        links.append("[IMSLP](https://imslp.org/wiki/Category:%s)"
                     % urllib.parse.quote(f["imslp"].replace(" ", "_")))
    if e:
        links.append("[the edit](https://en.wikipedia.org/w/index.php?diff=%s&oldid=%s)"
                     % (e["revid"], e["parentid"]))
    out += [" · ".join(links), ""]
    if f["flags"]:
        out += ["Worth knowing:", ""] + ["- " + x for x in f["flags"]] + [""]
    return out


def changed(base_rows, rows):
    """Lines for existing composers whose dates, count or gender moved."""
    fields = (("birth", 1), ("death", 2), ("quartets", 3), ("gender", 7))
    old = {r[0]: r for r in base_rows or []}
    out = []
    for r in rows:
        o = old.get(r[0])
        if o is None:
            continue
        diffs = ["%s %s → %s" % (k, o[i], r[i]) for k, i in fields
                 if len(o) > i and len(r) > i and o[i] != r[i]]
        if diffs:
            out.append("- %s: %s" % (r[0], ", ".join(diffs)))
    return out


def brief(base, offline=False):
    listing, people = load(LIST), load(PEOPLE, {})
    base_list = at(base, "data/list.json") or {"entries": []}
    new, renamed, gone = newcomers(listing["entries"], base_list["entries"], people)
    roster = load(ROSTER, {})
    shipped = load(SHIPPED)
    rows = shipped["rows"]
    series = (load(VIEWS) or {}).get("series", {})
    scrape = load(IMSLP)
    wikitext = open(WIKI, encoding="utf-8").read() if os.path.exists(WIKI) else ""
    entries = {e["title"]: e for e in listing["entries"]}
    canons = {t: (people.get(t) or {}).get("canonical") for t in new}
    prov = ({} if offline or not new else
            provenance(new, canons, base_list.get("revid"), listing.get("revid")))

    out = []
    if new:
        out += ["## New on the list: %d" % len(new), "",
                "Each is held off the chart until its box is ticked. A tick commits the yes to "
                "`data/inclusion.json` on this branch and rebuilds; a box still unticked at merge is a no.",
                ""]
        for t in new:
            f = facts(t, entries[t], people.get(t) or {}, series, scrape, rows)
            out += dossier(f, entry_line(wikitext, t), prov.get(t, {}), roster.get(t) is True)
    if renamed:
        out += ["## Renamed on the list (same Wikidata item, decision carried over)", ""]
        out += ["- %s → %s" % pair for pair in renamed] + [""]
    if gone:
        out += ["## Gone from the list", ""] + ["- " + t for t in gone] + [""]
    edits = changed((at(base, "composers.json") or {}).get("rows"), rows)
    if edits:
        out += ["## Changed on existing composers", ""] + edits + [""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--brief", action="store_true", help="print the dossier for newcomers since --base")
    ap.add_argument("--apply", metavar="BODY", help="record the ticked boxes in a PR body file")
    ap.add_argument("--base", default="HEAD", help="the ref newcomers are counted from")
    ap.add_argument("--offline", action="store_true", help="skip the Wikipedia history lookups")
    a = ap.parse_args()

    if a.brief:
        print(brief(a.base, a.offline))
        return 0

    listing, people, roster = load(LIST), load(PEOPLE, {}), load(ROSTER, {})
    if a.apply:
        base_list = at(a.base, "data/list.json") or {"entries": []}
        new = newcomers(listing["entries"], base_list["entries"], people)[0]
        roster, changes = apply(roster, ticks(open(a.apply, encoding="utf-8").read()), set(new))
        for t, yes in changes:
            print("  %s: %s" % (t, "include" if yes else "leave out"))
        if changes:
            save(roster)
        else:
            print("  no decision changed")
        return 0

    roster, added, renamed = record(listing["entries"], people, roster)
    for t in added:
        print("  new on the list, held off the chart until decided: %s" % t)
    for was, t in renamed:
        print("  renamed on the list, decision carried over: %s -> %s" % (was, t))
    save(roster)
    print("wrote data/inclusion.json (%d entries, %d included)"
          % (len(roster), sum(v is True for v in roster.values())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
