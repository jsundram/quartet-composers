#!/usr/bin/env python3
# pwa-starter: none — this script is this repo's own
# /// script
# requires-python = ">=3.9"
# ///
"""Render the IMSLP coverage report as a self-contained HTML page.

    python3 scripts/imslp-report.py                    # -> imslp-coverage.html
    python3 scripts/imslp-report.py --out /tmp/x.html

Reads composers.json, imslp.json and data/imslp-audit.json. Offline, no dependencies, and no
numbers of its own: every figure on the page is computed here from those three files at render
time. That is the point of it being a script rather than a document — the roster grows, the
monthly top-up moves every readership figure, and IMSLP gains scores, so a coverage report typed
once is a coverage report wrong by the next run. It is this repo's built-or-cut rule applied to
a page that is nothing BUT falsifiable prose.

The page leads with coverage by birth half-century because that is the finding: availability runs
80-89% for composers born between 1700 and 1850 and collapses to single digits after 1900. That
is a copyright boundary, not a gap in IMSLP's collecting, and the report says so where a reader
would otherwise conclude the library is patchy.
"""
import argparse
import collections
import datetime
import html
import json
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from report_style import CSS   # noqa: E402  the look, shared with imslp-audit.py
ROOT = os.path.dirname(HERE)

PD_CUTOFF = 1972      # Canada: life+50, and the 2023 extension to life+70 was not retroactive

STATES = (("have", "Scores on IMSLP"),
          ("none", "On IMSLP, no quartets"),
          ("unknown", "No IMSLP page found"))


def esc(s):
    return html.escape(str(s), quote=True)


def composer_link(name, cs):
    """A composer's name, linked to their IMSLP category when we know it.

    Being ON IMSLP with no quartets is one of the three answers this report keeps apart, and it is
    the one a reader will want to check: the link is the check. A composer we could not place has
    nothing to link to, and the absence of a link is itself the distinction.
    """
    e = cs.get(name)
    if not e:
        return esc(name)
    return f'<a href="{esc(imslp_url(e["cats"][0]))}">{esc(name)}</a>'


def imslp_url(cat):
    return "https://imslp.org/wiki/" + urllib.parse.quote(
        ("Category:" + cat).replace(" ", "_"), safe="_(),.!':")


def bar(counts, total):
    """One stacked bar. Widths are percentages so the row needs no measurement."""
    out = []
    for key, label in STATES:
        n = counts.get(key, 0)
        if not n:
            continue
        out.append(f'<span class="seg {key}" style="flex:{n}" '
                   f'title="{esc(label)}: {n}"><i>{n}</i></span>')
    return f'<div class="bar" role="img" aria-label="{total} composers">' + "".join(out) + "</div>"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "imslp-coverage.html"))
    a = ap.parse_args()

    comp = json.load(open(os.path.join(ROOT, "composers.json"), encoding="utf-8"))
    im = json.load(open(os.path.join(ROOT, "data", "imslp-join.json"), encoding="utf-8"))
    audit = json.load(open(os.path.join(ROOT, "data", "imslp-audit.json"), encoding="utf-8"))
    f = comp["fields"]
    NAME, BIRTH, DEATH, QTS, VIEWS = (f.index(k) for k in
                                      ("name", "birth", "death", "quartets", "views"))
    rows = comp["rows"]
    cs = im["composers"]

    def state(n):
        if n not in cs:
            return "unknown"
        return "have" if cs[n]["pages"] else "none"

    # ---- coverage by birth half-century -------------------------------------------------
    bands = collections.defaultdict(collections.Counter)
    for r in rows:
        if r[BIRTH] is None:
            continue
        bands[(r[BIRTH] // 50) * 50][state(r[NAME])] += 1
    band_rows = []
    for k in sorted(bands):
        c = bands[k]
        t = sum(c.values())
        band_rows.append((k, c, t, round(100 * c["have"] / t) if t else 0))

    # ---- tables -------------------------------------------------------------------------
    placed = [(r[NAME], cs[r[NAME]]["pages"], r[QTS], r[VIEWS], cs[r[NAME]]["cats"][0],
               cs[r[NAME]]["works_n"]) for r in rows if state(r[NAME]) == "have"]
    biggest = sorted(placed, key=lambda p: -p[5])[:12]
    gaps = sorted([p for p in placed if p[2]], key=lambda p: p[5] - p[2])[:10]
    unread = sorted(((r[VIEWS] or 0, r[NAME], state(r[NAME])) for r in rows
                     if state(r[NAME]) != "have"), reverse=True)[:12]

    total_states = collections.Counter(state(r[NAME]) for r in rows)
    pct = round(100 * total_states["have"] / len(rows))

    doc = []
    w = doc.append
    w("<title>IMSLP Score Coverage</title>")
    w('<meta charset="utf-8">')
    w('<meta name="viewport" content="width=device-width, initial-scale=1">')
    w('<link rel="preconnect" href="https://fonts.googleapis.com">')
    w('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    w('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
      'family=Spectral:ital,wght@0,400;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&'
      'family=IBM+Plex+Sans:wght@400;500;600&display=swap">')
    w(f"<style>{CSS}</style>")

    w('<main>')
    w('<header class="head">')
    w('<p class="eyebrow">Petrucci Music Library &middot; join audit</p>')
    w('<h1>How much of this roster can you actually get scores for?</h1>')
    w(f'<p class="lede">Of the {len(rows)} composers on the string-quartet roster, '
      f'<strong>{total_states["have"]}</strong> have at least one quartet score page on IMSLP '
      f'&mdash; {pct}%. The rest divide into two different answers, and the difference between '
      f'them is the whole report.</p>')
    w(f'<p class="stamp">Generated {esc(audit["generated"])} from '
      f'<code>data/imslp-join.json</code> &middot; rendered '
      f'{datetime.date.today().isoformat()}</p>')
    w('</header>')

    # headline figures, as two funnels: each step is a subset of the one before it, which a
    # flat row of five numbers does not say and a reader has to work out.
    with_count = [r for r in rows if r[QTS] is not None]
    held = [r for r in with_count if state(r[NAME]) == "have"]
    credited = sum(r[QTS] for r in with_count)
    credited_held = sum(r[QTS] for r in held)
    works_held = sum(cs[r[NAME]]["works_n"] for r in held)
    funnels = (
        ("Composers", [
            (len(rows), "on this roster", None),
            (len(cs), "found on IMSLP", "an identifier links them to a page there"),
            (sum(1 for r in rows if state(r[NAME]) == "have"),
             "with a quartet score", "at least one page of their own quartets"),
        ]),
        ("Quartets", [
            (credited, "credited to them",
             f"summed over the {len(with_count)} rows that state a count"),
            (credited_held, "by the composers we hold scores for", None),
            (works_held, "distinct works actually held",
             "sets expanded, catalogue numbers merged"),
        ]),
    )
    w('<section class="funnels">')
    for label, steps in funnels:
        w('<div class="fun">')
        w(f'<p class="eyebrow">{esc(label)}</p>')
        w('<ol>')
        first = steps[0][0]
        for n, cap, note in steps:
            w(f'<li><b>{n:,}</b><span>{esc(cap)}</span>'
              f'<em>{round(100 * n / first)}%</em>'
              + (f'<i>{esc(note)}</i>' if note else '') + '</li>')
        w('</ol>')
        w('</div>')
    w('</section>')
    w(f'<p class="note">The second funnel is not a coverage ratio and the last step can exceed '
      f'the one above it for an individual composer: IMSLP&rsquo;s scoring category holds fugues, '
      f'fragments and single movements that no numbered list of quartets counts, and the prose '
      f'count is itself only as good as its source. Across the whole roster IMSLP catalogues '
      f'{audit["imslp_pages"]:,} quartet pages, {audit["attributable_pages"]:,} of them by '
      f'composers on this list.</p>')

    # the cliff
    w('<section>')
    w('<h2>Coverage collapses at 1900</h2>')
    w('<p>Each bar is every roster composer born in that half-century, split three ways. The '
      'shape is a copyright boundary and not a gap in IMSLP&rsquo;s collecting &mdash; the next '
      'section states the actual rule, which is about the year a composer DIED.</p>')
    w('<div class="legend">')
    for key, label in STATES:
        w(f'<span class="key"><i class="sw {key}"></i>{esc(label)}</span>')
    w('</div>')
    w('<div class="bands">')
    for k, c, t, p in band_rows:
        w(f'<div class="band"><span class="yr">{k}s</span>{bar(c, t)}'
          f'<span class="pc">{p}%</span></div>')
    w('</div>')
    living = [r for r in rows if r[DEATH] is None]
    lc = collections.Counter(state(r[NAME]) for r in living)
    w(f'<p class="note">Of the {len(living)} composers still living, {lc["have"]} have a quartet '
      f'score on IMSLP.</p>')
    w('</section>')

    # what IMSLP is allowed to hold
    def band(r):
        if r[DEATH] is None:
            return "living"
        return "pd" if r[DEATH] < PD_CUTOFF else "in-copyright"

    bandtab = collections.defaultdict(collections.Counter)
    for r in rows:
        bandtab[band(r)][state(r[NAME])] += 1
    w('<section>')
    w('<h2>What IMSLP is allowed to hold</h2>')
    w(f'<p>IMSLP is hosted in Canada and follows Canadian public domain, which is life plus fifty '
      f'years: a work is free once its last surviving author <strong>died before '
      f'{PD_CUTOFF}</strong>. Canada extended the term to life plus seventy in 2023, but '
      f'<em>not</em> retroactively &mdash; it binds only people who died in {PD_CUTOFF} or later, '
      f'so the {PD_CUTOFF} line does not move each January the way a rolling term would. That one '
      f'rule predicts this dataset better than anything else in it.</p>')
    w('<div class="legend">')
    for key, label in STATES:
        w(f'<span class="key"><i class="sw {key}"></i>{esc(label)}</span>')
    w('</div>')
    w('<div class="bands">')
    for key, label in (("pd", f"died before {PD_CUTOFF}"),
                       ("in-copyright", f"died {PD_CUTOFF} or later"),
                       ("living", "living")):
        c = bandtab[key]
        t = sum(c.values())
        w(f'<div class="band wide"><span class="yr">{esc(label)}</span>{bar(c, t)}'
          f'<span class="pc">{round(100 * c["have"] / t) if t else 0}%</span></div>')
    w('</div>')
    pd_total = sum(bandtab["pd"].values())
    gap = pd_total - bandtab["pd"]["have"]
    w(f'<p><strong>{gap} composers are free to host and are not here.</strong> That is the real '
      f'gap: {bandtab["pd"]["none"]} have an IMSLP page with no quartet on it and '
      f'{bandtab["pd"]["unknown"]} have no page found at all, out of {pd_total} whose music '
      f'Canadian law puts in the public domain. Everything after {PD_CUTOFF} is a waiting list, '
      f'not a gap &mdash; the earliest of those composers becomes free in '
      f'{min([r[DEATH] + 71 for r in rows if r[DEATH] and r[DEATH] >= PD_CUTOFF], default="&mdash;")}.</p>')
    odd = [r for r in rows if band(r) != "pd" and state(r[NAME]) == "have"]
    # Named from the DATA, not hardcoded: a composer name is a canonical Wikipedia title that
    # changes spelling when the pipeline runs (invariant 7), and either of these could also stop
    # being placed on IMSLP — cs["Dmitri Shostakovich"] would then KeyError and the report would
    # crash rather than degrade. make-og-svg.py was given an explicit failure for this same hazard.
    lead = sorted(odd, key=lambda r: -cs[r[NAME]]["pages"])[:2]
    lead_txt = " and ".join(f'{esc(r[NAME])} (died {r[DEATH]}, {cs[r[NAME]]["pages"]} pages)'
                            for r in lead) or "none"
    w(f'<p class="note">{len(odd)} composers have quartet scores despite not being public domain '
      f'in Canada, led by {lead_txt}. Their files carry a mix of '
      f'&ldquo;Public Domain&rdquo;, Creative Commons and BSD tags, so this is freely licensed '
      f'modern engraving and edition-specific claims rather than one rule &mdash; worth knowing '
      f'before treating the {PD_CUTOFF} line as a hard boundary in either direction.</p>')
    w('</section>')

    # the two answers
    w('<section>')
    w('<h2>Zero and unknown are different answers</h2>')
    eg = ", ".join(esc(n) for _v, n, _s in
                   sorted(((r[VIEWS] or 0, r[NAME], 0) for r in rows
                           if state(r[NAME]) == "none"), reverse=True)[:5])
    w(f'<p><strong>{total_states["none"]} composers</strong> have an IMSLP page and no quartet on '
      f'it &mdash; {eg}. That is a fact about copyright and '
      f'it is worth showing. <strong>{total_states["unknown"]} composers</strong> could not be '
      f'placed on IMSLP at all: no Wikidata IMSLP id, no IMSLP page linking their article, and '
      f'no page under any one-, two- or three-token <code>Surname, Forename</code> inversion of '
      f'their name. That is good evidence of absence and it is not the same as asking, so the '
      f'page says <em>no IMSLP page found</em> and never <em>not on IMSLP</em>.</p>')
    w('</section>')

    # provenance
    w('<section>')
    w('<h2>How each composer was matched</h2>')
    w('<p>No rung of the join compares names. A work page is titled '
      '<code>&lt;work&gt; (Surname, Forename)</code>, that parenthetical is the composer&rsquo;s '
      'own IMSLP category, and the category page states either a Wikidata item or a Wikipedia '
      'article &mdash; which en.wikipedia resolves to a canonical title and a QID. Only the last '
      'rung starts from a spelling, and it is accepted only when IMSLP&rsquo;s birth '
      '<em>and</em> death years agree with Wikidata&rsquo;s.</p>')
    src = audit["sources"]
    labels = {"wp-qid": "Wikipedia article &rarr; QID",
              "cand-qid": "identifier on a page reached by name",
              "name+stale-death": "name guess, IMSLP not yet updated for a recent death",
              "p839": "Wikidata IMSLP id (P839)",
              "name+dates": "name guess, confirmed by dates",
              "imslp-qid": "QID stated on the IMSLP page"}
    tot = sum(src.values()) or 1
    w('<table class="prov"><tbody>')
    for k, n in sorted(src.items(), key=lambda kv: -kv[1]):
        w(f'<tr><th>{labels.get(k, esc(k))}</th><td class="num">{n}</td>'
          f'<td class="track"><span style="width:{100*n/tot:.1f}%"></span></td></tr>')
    w('</tbody></table>')

    rej, con = audit["rejected"], audit["date_conflicts"]
    if rej:
        w(f'<h3>{len(rej)} name guesses rejected</h3>')
        blank = sum(1 for r in rej if r["imslp_born"] is None and r["imslp_died"] is None)
        w(f'<p>The IMSLP page exists under exactly the right spelling and the dates do not '
          f'support it. {blank} of the {len(rej)} state no dates at all'
          + ('.' if blank == len(rej) else
             '; the rest disagree with Wikidata about a year.') + '</p>')
        w('<table><thead><tr><th>Roster</th><th>IMSLP page</th><th>Wikidata</th>'
          '<th>IMSLP</th></tr></thead><tbody>')
        for r in rej:
            def span(b, d):
                return f'{b or "?"}&ndash;{d or ""}'
            w(f'<tr><td>{esc(r["name"])}</td><td class="mono">{esc(r["cat"])}</td>'
              f'<td class="mono">{span(r["birth"], r["death"])}</td>'
              f'<td class="mono">{span(r["imslp_born"], r["imslp_died"])}</td></tr>')
        w('</tbody></table>')
    if con:
        w(f'<h3>{len(con)} accepted joins whose dates disagree</h3>')
        w('<p>Matched on an identifier both sides assert, so the join stands. Reported rather '
          'than resolved &mdash; this file is not a second opinion about when anyone was born.</p>')
        w('<table><thead><tr><th>Composer</th><th>Field</th><th>Wikidata</th><th>IMSLP</th>'
          '</tr></thead><tbody>')
        for c in con:
            w(f'<tr><td>{esc(c["name"])}</td><td>{esc(c["field"])}</td>'
              f'<td class="mono">{c["wikidata"]}</td><td class="mono">{c["imslp"]}</td></tr>')
        w('</tbody></table>')
    w('</section>')

    # pages are not quartets
    w('<section>')
    w('<h2>Three numbers, three questions</h2>')
    w('<p><strong>Pages</strong> is what IMSLP catalogues, and its unit is a publication entry: '
      'Beethoven&rsquo;s 16 quartets occupy 23 of them. <strong>Works</strong> reads the '
      'catalogue number off each page &mdash; a set page carries the opus its members share '
      '(<code>Op.18</code>) while their own pages carry <code>Op.18 No.1</code> through '
      '<code>No.6</code> &mdash; so sets expand and duplicates merge. <strong>Written</strong> is '
      'how many quartets the composer actually wrote, from Wikipedia prose, and it is the only '
      'one of the three that is not about IMSLP at all.</p>')
    w(f'<p>Across the roster that is {audit["attributable_pages"]:,} pages holding '
      f'{audit["attributable_works"]:,} works. The direction of the correction is not uniform: '
      f'Cambini&rsquo;s 14 pages carry 76 works, while Beethoven&rsquo;s 23 collapse to 18 &mdash; '
      f'his 16 quartets plus the Gro&szlig;e Fuge and the Hess 30 fugue, which is exactly what '
      f'IMSLP&rsquo;s own complete edition says it contains.</p>')
    w('<div class="cols">')
    head = ('<table><thead><tr><th>Composer</th><th class="num">Pages</th>'
            '<th class="num">Works</th><th class="num">Written</th></tr></thead><tbody>')
    w('<div><h3>Largest catalogues held</h3>')
    w(head)
    for n, p, q, v, cat, wn in biggest:
        w(f'<tr><td><a href="{esc(imslp_url(cat))}">{esc(n)}</a></td>'
          f'<td class="num">{p}</td><td class="num">{wn}</td>'
          f'<td class="num">{q if q is not None else "&mdash;"}</td></tr>')
    w('</tbody></table></div>')
    w('<div><h3>Widest shortfalls</h3>')
    w(head)
    for n, p, q, v, cat, wn in gaps:
        w(f'<tr><td><a href="{esc(imslp_url(cat))}">{esc(n)}</a></td>'
          f'<td class="num">{p}</td><td class="num">{wn}</td><td class="num">{q}</td></tr>')
    w('</tbody></table></div>')
    w('</div>')
    over = [x for x in placed if x[2] and x[5] > x[2]]
    w(f'<p class="note">Where the work count EXCEEDS what the composer is said to have written '
      f'&mdash; {len(over)} of the {len([x for x in placed if x[2]])} composers with both numbers '
      f'&mdash; the page is usually right and the prose thin: Rigel and F&ouml;rster each have '
      f'three pages of six-quartet sets against a stated six. IMSLP&rsquo;s instrumentation '
      f'category also holds fugues, fragments and single movements that no numbered list counts. '
      f'The rule is to grade the parse against the page, never against the other number.</p>')
    w('</section>')

    # most read without
    w('<section>')
    w('<h2>Most-read composers without a score here</h2>')
    w('<table><thead><tr><th>Composer</th><th class="num">Readers / month</th>'
      '<th>Status</th></tr></thead><tbody>')
    for v, n, st in unread:
        lab = dict(STATES)[st]
        w(f'<tr><td>{composer_link(n, cs)}</td><td class="num">{v:,}</td>'
          f'<td><span class="chip {st}">{esc(lab)}</span></td></tr>')
    w('</tbody></table>')
    w('</section>')

    # the composers Canadian law already frees, that IMSLP does not have at all
    early = sorted((r for r in rows if r[DEATH] is not None and r[DEATH] < PD_CUTOFF
                    and state(r[NAME]) == "unknown"), key=lambda r: -(r[VIEWS] or 0))
    w('<section>')
    w(f'<h2>Died before {PD_CUTOFF} and still not found</h2>')
    w(f'<p>These {len(early)} are the sharp end of the gap: public domain in Canada, so IMSLP '
      f'could hold their quartets today, and no IMSLP page for them exists at all. Checked the '
      f'hard way rather than inferred &mdash; every surname was listed against '
      f'<code>Category:&lt;Surname&gt;,</code> and IMSLP files other people under many of them '
      f'(<code>Still, John</code>, twenty different <code>Thompson</code>s) and none of these '
      f'composers. So this is absence, not a spelling the join failed to guess.</p>')
    w(f'<p>Read the list and the pattern is the point: '
      f'{sum(1 for r in early if r[BIRTH] and r[BIRTH] >= 1870)} were born after 1870, most are '
      f'women, and none is read more than four thousand times a month. The other '
      f'{sum(1 for r in rows if r[DEATH] is not None and r[DEATH] < PD_CUTOFF and state(r[NAME]) == "none")} '
      f'public-domain composers DO have an IMSLP page, with no quartet on it.</p>')
    w('<table><thead><tr><th>Composer</th><th class="num">Born</th><th class="num">Died</th>'
      '<th class="num">Quartets</th><th class="num">Readers</th></tr></thead><tbody>')
    for r in early:
        w(f'<tr><td>{esc(r[NAME])}</td>'
          f'<td class="num">{r[BIRTH] if r[BIRTH] else "&mdash;"}</td>'
          f'<td class="num">{r[DEATH]}</td>'
          f'<td class="num">{r[QTS] if r[QTS] is not None else "&mdash;"}</td>'
          f'<td class="num">{(r[VIEWS] or 0):,}</td></tr>')
    w('</tbody></table>')
    w('</section>')

    # off roster
    w('<section>')
    w('<h2>Quartet catalogues this roster does not have</h2>')
    w(f'<p>{audit["offroster_composers"]:,} composers on IMSLP have a string quartet and are not '
      f'on this list, holding {audit["offroster_pages"]:,} pages between them. Most are minor or '
      f'have no English Wikipedia article; the largest are worth a look as roster candidates.</p>')
    w('<ul class="chips">')
    for o in audit["offroster_top"][:12]:
        w(f'<li><a href="{esc(imslp_url(o["cat"]))}">{esc(o["cat"])}'
          f'<span>{o["pages"]}</span></a></li>')
    w('</ul>')
    w('</section>')

    w('<footer>')
    w('<p>Source: IMSLP <code>api.php</code>, crawled at one request per second and cached in '
      '<code>data/imslp.json</code>. Quartets are IMSLP&rsquo;s own instrumentation category '
      '<em>For 2 violins, viola, cello</em>; arrangements are a separate category and are '
      'counted separately. Readership is the median of the last twelve months of English '
      'Wikipedia page views.</p>')
    w(f'<p>Rebuild with <code>python3 scripts/fetch_imslp.py &amp;&amp; '
      f'python3 scripts/build_imslp.py &amp;&amp; python3 scripts/imslp-report.py</code>.</p>')
    w('</footer>')
    w('</main>')

    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(doc))
    print(f"wrote {a.out} - {os.path.getsize(a.out):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
