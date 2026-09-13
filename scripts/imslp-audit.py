#!/usr/bin/env python3
# pwa-starter: none — this script is this repo's own
# /// script
# requires-python = ">=3.9"
# ///
"""Grade the catalogue parse for the composers the chart highlights.

    python3 scripts/imslp-audit.py            # -> imslp-audit.html

Every work page of the 22 curated composers, with the RAW `Opus/Catalogue Number` field IMSLP
serves printed beside the work ids this repo made of it, and a link to the page so a disagreement
can be settled by looking. That is invariant 11's rule applied to a second parser: the measure of
`build_imslp.py`'s counting is a human reading it against the page, not its agreement with the
quartet count in composers.json, which answers a different question and is itself prose.

WHY THESE 22. `CANON`, `OUTLIERS` and `WOMEN_CANON` in chart.js are the composers the Fame view
draws filled and named, so they are the rows a reader looks at, the rows any error is seen in
first, and — being ten canonical composers, three deliberate outliers and nine women whose
catalogues are the least well served by reference works — a fair spread of the ways this parse can
go wrong. The lists are READ from chart.js rather than copied, because they change spelling when
the pipeline runs (invariant 7) and a copy here would quietly stop matching.

Rows are marked where the parse deserves a second look: a page with no catalogue number at all, an
anthology dropped for having none, and any page whose expansion produced more works than its title
implies.
"""
import argparse
import datetime
import html
import json
import os
import re
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from report_style import CSS, EXTRA                          # noqa: E402
import build_imslp as bi                                     # noqa: E402

LISTS = ("CANON", "OUTLIERS", "WOMEN_CANON")
# No sizes here. This file reads the lists out of chart.js precisely so they cannot drift, and
# then typing "ten"/"three"/"nine" beside them would reintroduce the drift one line down.
BLURB = {"CANON": "the repertoire — composers a quartet actually plays, in birth order",
         "OUTLIERS": "picked out for writing far more than they are read",
         "WOMEN_CANON": "shown only under the Women filter"}


def esc(s):
    return html.escape(str(s), quote=True)


def curated():
    """The three lists, read out of chart.js. Never copied — see the header."""
    src = open(os.path.join(ROOT, "chart.js"), encoding="utf-8").read()
    out = {}
    for name in LISTS:
        m = re.search(r"const\s+%s\s*=\s*\[(.*?)\]" % name, src, re.S)
        if not m:
            raise SystemExit(f"{name} is no longer an array literal in chart.js — fix this reader")
        out[name] = re.findall(r'"([^"]+)"', m.group(1))
    return out


RUN = re.compile(r"^(.*?)(\d+)([a-z]?)$")


def compress(ids):
    """"Op.72 No.1", "Op.72 No.2", "Op.72 No.3"  ->  "Op.72 No.1-3".

    A set of six reads as one designation and a span, which is how the page itself writes it
    ("6 String Quartets, Op.18"). Only CONSECUTIVE numbers on an identical stem collapse, so a
    gap stays visible — a run printed over a missing number would hide exactly the thing this
    page exists to show.
    """
    out, run = [], []

    def flush():
        if not run:
            return
        stem, first, last = run[0][0], run[0][1], run[-1][1]
        out.append(f"{stem}{first}" if len(run) == 1 else f"{stem}{first}\u2013{last}")
        run.clear()

    for i in ids:
        m = RUN.match(i)
        if not m or m.group(3):                 # no trailing number, or a lettered one (417b)
            flush()
            out.append(i)
            continue
        stem, n = m.group(1), int(m.group(2))
        if run and run[-1][0] == stem and n == run[-1][1] + 1:
            run.append((stem, n))
        else:
            flush()
            run.append((stem, n))
    flush()
    return out


def url_for(title, cat):
    return page_url(title + " (" + cat + ")")


def page_url(title):
    return "https://imslp.org/wiki/" + urllib.parse.quote(
        title.replace(" ", "_"), safe="_(),.!':")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "imslp-audit.html"))
    a = ap.parse_args()

    cache = json.load(open(os.path.join(ROOT, "data", "imslp.json"), encoding="utf-8"))
    im = json.load(open(os.path.join(ROOT, "data", "imslp-join.json"), encoding="utf-8"))["composers"]
    comp = json.load(open(os.path.join(ROOT, "composers.json"), encoding="utf-8"))
    f = comp["fields"]
    NAME, QTS = f.index("name"), f.index("quartets")
    stated = {r[NAME]: r[QTS] for r in comp["rows"]}
    wi = cache["workinfo"]
    lists = curated()
    n_curated = sum(len(v) for v in lists.values())

    doc = []
    w = doc.append
    w("<title>Highlighted Catalogue Audit</title>")
    w('<meta charset="utf-8">')
    w('<meta name="viewport" content="width=device-width, initial-scale=1">')
    w('<link rel="preconnect" href="https://fonts.googleapis.com">')
    w('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    w('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
      'family=Spectral:ital,wght@0,400;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&'
      'family=IBM+Plex+Sans:wght@400;500;600&display=swap">')
    w(f"<style>{CSS}{EXTRA}</style>")
    w('<main>')
    w('<header class="head">')
    w('<p class="eyebrow">IMSLP join &middot; parse audit</p>')
    w('<h1>What the catalogue parser made of every highlighted composer</h1>')
    w(f'<p class="lede">The chart fills and names {n_curated} composers. Here is every quartet '
      f'page IMSLP holds for them, the catalogue field as IMSLP serves it, and the work ids this repo derived '
      '&mdash; side by side, with a link to settle any disagreement by looking.</p>')
    w(f'<p class="stamp">Rendered {datetime.date.today().isoformat()} &middot; '
      f'lists read from <code>chart.js</code></p>')
    w('</header>')

    tot_pages = tot_works = nocat = odd = unread = dropped = 0
    for lname in LISTS:
        w('<section>')
        w(f'<h2>{esc(lname)}</h2>')
        w(f'<p>{len(lists[lname])} composers &mdash; {esc(BLURB[lname])}.</p>')
        for name in lists[lname]:
            e = im.get(name)
            w('<div class="who">')
            if not e:
                w(f'<h3>{esc(name)} <span class="tag">no IMSLP page found</span></h3>')
                w('</div>')
                continue
            cat = e["cats"][0]
            st = stated.get(name)
            w(f'<h3><a href="{esc(page_url("Category:" + cat))}">'
              f'{esc(name)}</a>'
              f'<span class="tally"><b>{e["pages"]}</b> pages &middot; '
              f'<b>{e["works_n"]}</b> works &middot; '
              f'{st if st is not None else "&mdash;"} written &middot; '
              f'joined by {esc(e["how"][0])}</span></h3>')
            tot_pages += e["pages"]
            tot_works += e["works_n"]
            if not e["works"]:
                w('<p class="empty">On IMSLP, but no quartet pages.</p></div>')
                continue
            w('<table class="audit"><thead><tr>'
              '<th style="width:34%"><button type="button">Page</button></th>'
              '<th style="width:22%"><button type="button">IMSLP catalogue field</button></th>'
              '<th style="width:32%"><button type="button">Work ids derived</button></th>'
              '<th class="num" style="width:12%" data-n><button type="button">Works</button></th>'
              '</tr></thead><tbody>')
            for title, _pid, _fl, ci in sorted(e["works"]):
                raw = wi.get(title + " (" + e["cats"][ci] + ")")
                fields = bi.info_fields(raw)
                cf = fields.get("Opus/Catalogue Number", "")
                members = bi.members_of(title, fields)
                groups = bi.work_ids(cf, members)
                ids = [sorted(g)[0] for g in groups]
                coll = fields.get("Page Type") == "Collection"
                cls, note = "", ""
                if not groups and cf:
                    # A field that IS there and could not be read is a PARSE FAILURE, and
                    # calling it "no catalogue number" is the one mislabel this page cannot
                    # afford — surfacing exactly these is what it is for. Live example:
                    # {{HaydnHob|n383|III:1-83}}, a three-argument template the reader does not match.
                    cls, note = "flag", "catalogue stated but not read"
                    unread += 1
                elif groups and "<" in cf:
                    # K<sup>9</sup>.Anh.H 12,17 reduces to "K.9" once the tags are stripped, which
                    # is not a catalogue number anyone wrote. Rare, and flagged rather than
                    # special-cased: the point of this page is that a human sees it.
                    cls = "flag"
                    odd += 1
                elif not groups:
                    if coll:
                        cls, note = "drop", "anthology, no catalogue — dropped"
                        dropped += 1
                    else:
                        cls, note = "flag", "no catalogue number — counted as one"
                        nocat += 1
                short = compress(ids)
                shown = ", ".join(short[:8]) + (f" +{len(short)-8} more" if len(short) > 8 else "")
                w(f'<tr class="{cls}"><td><a href="{esc(url_for(title, e["cats"][ci]))}">'
                  f'{esc(title)}</a>'
                  + (f' <span class="tag">collection</span>' if coll else '') + '</td>'
                  f'<td class="raw">{esc(cf) if cf else "&mdash;"}</td>'
                  f'<td class="ids">{esc(shown) if shown else "<i>" + note + "</i>"}</td>'
                  f'<td class="num">{len(groups) if groups else (0 if coll else 1)}</td></tr>')
            w('</tbody></table>')
            w('</div>')
        w('</section>')

    w('<section>')
    w('<h2>How to read a flagged row</h2>')
    w('<p>A <span class="tag">collection</span> tag is IMSLP&rsquo;s own <code>Page Type</code>. '
      'A shaded row is one the parse could not fully account for, and there are three kinds. '
      'A page stating <em>no</em> catalogue number counts as a single work. An anthology stating '
      'none is dropped entirely, because it reprints works that already have pages of their own. '
      'And a page that <em>states</em> one the parser could not read is a PARSE FAILURE, labelled '
      'as one rather than as an absent field &mdash; <code>{{HaydnHob|n383|III:1-83}}</code> is a '
      'three-argument template the <code>{{X|Y}}</code> reader does not match. Surfacing those is '
      'what this page is for, so calling them &ldquo;no catalogue number&rdquo; was the one '
      'mislabel it could not afford.</p>')
    w(f'<p class="note">{tot_pages} pages and {tot_works} works across the {n_curated}. '
      f'{nocat} state no catalogue number and count as one work; {dropped} are anthologies '
      f'stating none and are dropped; <strong>{unread} state one the parser could not '
      f'read</strong>; {odd} state one carrying markup it has to strip first.</p>')
    w('</section>')
    w('<footer><p>Generated by <code>scripts/imslp-audit.py</code> from '
      '<code>data/imslp.json</code>, <code>data/imslp-join.json</code> and <code>chart.js</code>. '
      'The parse it grades lives in <code>scripts/build_imslp.py</code>.</p></footer>')
    w('</main>')
    w(f"<script>{SORT_JS}</script>")

    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(doc))
    print(f"wrote {a.out} - {os.path.getsize(a.out):,} bytes; {tot_pages} pages, "
          f"{tot_works} works, {nocat} uncatalogued, {dropped} anthologies, "
          f"{unread} stated-but-unread, {odd} with markup")
    return 0


# Each composer's table sorts on its own, because the question is always "does THIS catalogue read
# correctly" — a sort across the page would interleave composers and answer nothing. No library:
# the CSP admits no external script and this is thirty lines.
SORT_JS = """
document.querySelectorAll('table.audit').forEach(function (t) {
  var body = t.tBodies[0];
  t.querySelectorAll('th button').forEach(function (b, col) {
    b.addEventListener('click', function () {
      var th = b.parentNode;
      var dir = th.getAttribute('aria-sort') === 'ascending' ? -1 : 1;
      t.querySelectorAll('th').forEach(function (o) { o.removeAttribute('aria-sort'); });
      th.setAttribute('aria-sort', dir === 1 ? 'ascending' : 'descending');
      var num = th.hasAttribute('data-n');
      var rows = Array.prototype.slice.call(body.rows);
      rows.sort(function (x, y) {
        var a = x.cells[col].textContent.trim(), c = y.cells[col].textContent.trim();
        if (num) { return (parseFloat(a) - parseFloat(c)) * dir; }
        return a.localeCompare(c, undefined, { numeric: true }) * dir;
      });
      rows.forEach(function (r) { body.appendChild(r); });
    });
  });
});
"""


if __name__ == "__main__":
    sys.exit(main())
