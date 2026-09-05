#!/usr/bin/env python3
"""Assemble the .dc.html artboards. Chrome matches the shipped app: same tokens out of
styles.css, same system-ui ramp, same 12px radius cards."""
import json, os
D = os.path.dirname(os.path.abspath(__file__))   # artboards live beside this script
svg = lambda n: open(os.path.join(D, f"chart-{n}.svg")).read()
S = json.load(open(os.path.join(D, "stats.json")))
fmt = lambda n: f"{n:,}"

HEAD = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <style>
    body { margin: 0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
           line-height: 1.45; background: #f6f5f2; color: #191919;
           -webkit-font-smoothing: antialiased; }
    a { color: #1f6f9f; } a:hover { color: #17547a; }
    .board { padding: 26px 26px 22px; display: flex; flex-direction: column; gap: 14px; }
    .kicker { font: 600 11px/1 system-ui, sans-serif; letter-spacing: .09em;
              text-transform: uppercase; color: #5f6560; }
    h2 { margin: 0; font-size: 23px; font-weight: 650; letter-spacing: -.015em; }
    .card { background: #ffffff; border: 1px solid #e2ded6; border-radius: 12px; padding: 14px; }
    .note { display: flex; flex-direction: column; gap: 7px; }
    .note p { margin: 0; font-size: 13px; color: #5f6560; max-width: 74ch; }
    .note b { color: #191919; font-weight: 600; }
    .keys { display: flex; flex-wrap: wrap; gap: 6px 18px; align-items: center;
            font-size: 12px; color: #5f6560; margin-top: 10px; }
    .key { display: flex; align-items: center; gap: 7px; }
    .dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
  </style>
</helmet>
"""
TAIL = """</x-dc>
<script data-dc-script data-props='{}'>
class Component extends DCLogic {
  renderVals() { return {}; }
}
</script>
</body>
</html>
"""

def keys(items):
    out = ['<div class="keys">']
    for style, text in items:
        out.append(f'<div class="key"><span class="dot" style="{style}"></span>'
                   f'<span>{text}</span></div>')
    out.append("</div>")
    return "\n".join(out)

def board(kicker, title, body, says, costs, width):
    return (HEAD
            + f'<div class="board" style="width: {width}px">\n'
            + f'  <div><div class="kicker">{kicker}</div>\n  <h2>{title}</h2></div>\n'
            + body + "\n"
            + '  <div class="note">\n'
            + f'    <p><b>What it says.</b> {says}</p>\n'
            + f'    <p><b>What it costs.</b> {costs}</p>\n'
            + "  </div>\n</div>\n" + TAIL)

CANON_KEY = ('background:#c2410c', 'the seven, joined in birth order')
FORGOT_KEY = ('box-shadow: inset 0 0 0 2px #1f6f9f', 'wrote the most, read the least')
ONEHIT_KEY = ('box-shadow: inset 0 0 0 2px #1f6f9f', 'wrote one, read by everyone')
SIZE_KEY = ('background:#5f6560; opacity:.25', 'everyone else — size is monthly readers')

# ---------------------------------------------------------------- Today
open(os.path.join(D, "Today.dc.html"), "w").write(board(
    "Baseline", "Today",
    '  <div class="card">' + svg("today") + '</div>',
    "Birth year and quartet count as position, readership as size, lifespan as hue, an open "
    "circle for the living. Every variable the dataset has, encoded at once.",
    "Nothing is emphasised, so nothing is argued. Haydn, Mozart and Beethoven are in there at "
    "the same visual weight as the other 787, and the loudest channel — hue — is spent on "
    "lifespan, which is the one thing nobody came here to compare.",
    788))

# ---------------------------------------------------------------- A
open(os.path.join(D, "Main.dc.html"), "w").write(board(
    "Direction A", "The canon, drawn",
    '  <div class="card">' + svg("a")
    + keys([CANON_KEY, FORGOT_KEY, SIZE_KEY]) + '</div>',
    "Keeps the historical spine and spends hue on the argument instead of on lifespan. The seven "
    "are joined in birth order, so the line <i>is</i> the claim: Richter to Shostakovich, two "
    "centuries in one gesture. Ringed in blue, the composers who wrote the most and are read the "
    "least — Cambini at 149 quartets and 216 readers a month, Ellerton at 100 and 53.",
    "Readership is still only circle size, so &ldquo;Bart&oacute;k is read 76&times; more per "
    "quartet than Cambini&rdquo; is asserted, not shown — the eye cannot measure it off two "
    "circles. It is the smallest change to what ships, and the weakest form of the argument.",
    788))

# ---------------------------------------------------------------- B
open(os.path.join(D, "OptionB.dc.html"), "w").write(board(
    "Direction B", "Output against attention",
    '  <div class="card">' + svg("b")
    + keys([CANON_KEY, FORGOT_KEY, ('background:#5f6560; opacity:.25', 'everyone else')])
    + '</div>',
    "Makes the claim geometric. Across is what they wrote, up is how much they are read, and the "
    "diagonals are readers per quartet — so <b>height above the diagonal is the whole argument, "
    "measurable off an axis</b>. Mozart and Beethoven sit near 10,000 readers per quartet; "
    "Cambini, Krommer and Ellerton sit on the 1-reader line at the far right. Haydn and "
    "Boccherini are the genuinely rare corner: enormous output <i>and</i> attention.",
    "Birth year stops being a position — it becomes hue, or a hover. That is a real loss for a "
    "chart about a form that has a history. And the vertical axis is fame, not merit: an English "
    "Wikipedia count under-reads every composer whose readers are on another language's site, so "
    "the page has to keep saying so out loud.",
    788))

# ---------------------------------------------------------------- C
def row(n, note=""):
    d = S[n]
    return (f'<div style="display:grid; grid-template-columns: 1fr auto auto; gap: 0 16px; '
            f'align-items: baseline; padding: 9px 0; border-bottom: 1px solid #e2ded6">'
            f'<div><div style="font-size:14px; font-weight:600">{n}</div>'
            f'<div style="font-size:11.5px; color:#5f6560">b. {d["born"]}{note}</div></div>'
            f'<div style="font-variant-numeric: tabular-nums; font-size:14px; text-align:right; '
            f'min-width:44px">{d["q"]}</div>'
            f'<div style="font-variant-numeric: tabular-nums; font-size:14px; text-align:right; '
            f'min-width:74px">{fmt(d["v"])}</div></div>')

hdr = ('<div style="display:grid; grid-template-columns: 1fr auto auto; gap: 0 16px; '
       'font-size:11px; font-weight:600; letter-spacing:.06em; text-transform:uppercase; '
       'color:#5f6560; padding-bottom:6px; border-bottom:1px solid #e2ded6">'
       '<div>Composer</div><div style="text-align:right; min-width:44px">Quartets</div>'
       '<div style="text-align:right; min-width:74px">Readers / mo</div></div>')

cbody = ('  <div class="card" style="display:flex; flex-direction:column; gap:18px">\n'
         '    <div>\n'
         '      <div style="font-size:15px; font-weight:600; margin-bottom:2px">The seven</div>\n'
         '      <div style="font-size:12.5px; color:#5f6560; margin-bottom:10px">Two centuries '
         'of the form, in the order they were born.</div>\n' + hdr
         + "".join(row(n) for n in ["Franz Xaver Richter", "Joseph Haydn", "Luigi Boccherini",
                                    "Wolfgang Amadeus Mozart", "Ludwig van Beethoven",
                                    "Béla Bartók", "Dmitri Shostakovich"]) + '\n    </div>\n'
         '    <div>\n'
         '      <div style="font-size:15px; font-weight:600; margin-bottom:2px">Wrote the most. '
         'Read the least.</div>\n'
         '      <div style="font-size:12.5px; color:#5f6560; margin-bottom:10px">Cambini wrote '
         'more quartets than Haydn, Mozart and Beethoven put together.</div>\n' + hdr
         + "".join(row(n) for n in ["Giuseppe Cambini", "Franz Krommer",
                                    "John Lodge Ellerton"]) + '\n    </div>\n'
         '    <div>\n'
         '      <div style="font-size:15px; font-weight:600; margin-bottom:2px">Wrote one. '
         'Everybody knows it.</div>\n'
         '      <div style="font-size:12.5px; color:#5f6560; margin-bottom:10px">Which is why '
         '&ldquo;readers per quartet&rdquo; cannot be the measure: it ranks Debussy above '
         'Mozart, 34,987 to 8,121.</div>\n' + hdr
         + "".join(row(n) for n in ["Claude Debussy", "George Gershwin",
                                    "Maurice Ravel"]) + '\n    </div>\n  </div>')

open(os.path.join(D, "OptionC.dc.html"), "w").write(board(
    "Direction C", "The argument in numbers",
    cbody,
    "Not a chart. Three named groups and two columns, which is all the argument actually needs — "
    "and the only form of it that works at a glance on a phone. It also lets the page admit the "
    "thing the scatters cannot: readers-per-quartet is <b>not</b> a greatness measure, because "
    "writing exactly one famous quartet maximises it.",
    "Editorial, not exploratory. It answers the one question it was written for and cannot be "
    "asked another — no 884th composer, no &ldquo;who else is up there&rdquo;. It belongs "
    "<i>above</i> a chart, not instead of one.",
    560))

# ---------------------------------------------------------------- Page structure
PILL = ("font: 500 13px/1 system-ui, sans-serif; color:#5f6560; background:transparent; "
        "border:1px solid #e2ded6; border-radius:999px; padding:0 13px; height:36px; "
        "display:flex; align-items:center; white-space:nowrap")
page = (HEAD + '<div style="width:376px; background:#f6f5f2; padding:16px 14px 20px; '
        'display:flex; flex-direction:column; gap:12px">\n'
        # header
        '  <div style="display:flex; align-items:baseline; gap:8px; flex-wrap:wrap">'
        '<h2 style="font-size:22px">String Quartet Composers</h2></div>\n'
        '  <p style="margin:0; font-size:13.5px; color:#5f6560">Everyone on Wikipedia\'s list — '
        '<b style="color:#191919">884 composers</b>, by when they were born and how much they '
        'wrote. Seven names carry the form; one you have never heard of wrote 149.</p>\n'
        # ONE filter row, above everything it scopes
        '  <div class="card" style="padding:10px 12px; display:flex; flex-direction:column; '
        'gap:8px">\n'
        '    <div style="display:flex; gap:8px; align-items:center">\n'
        '      <div style="flex:1 1 auto; height:38px; border:1px solid #e2ded6; '
        'border-radius:999px; background:#f6f5f2; display:flex; align-items:center; '
        'padding:0 13px; font-size:14px; color:#8b9188">Search 884 composers…</div>\n'
        '      <div style="' + PILL + '">Filters</div>\n    </div>\n'
        '    <div style="display:flex; align-items:center; gap:10px">\n'
        '      <span style="font-size:11.5px; color:#5f6560; white-space:nowrap">Readership</span>\n'
        '      <div style="flex:1 1 auto; height:26px; background:linear-gradient(90deg,'
        '#e2ded6 0 18%,#1f6f9f33 18% 82%,#e2ded6 82%); border-radius:4px"></div>\n'
        '      <span style="font: 500 11px/1 ui-monospace, monospace; color:#1f6f9f">all</span>\n'
        '    </div>\n  </div>\n'
        # chart
        '  <div class="card" style="padding:12px 10px">\n' + svg("a-phone") + '\n'
        '    <div style="display:flex; gap:6px; margin-top:10px">\n'
        '      <div style="' + PILL + '; height:32px; background:#1f6f9f; color:#fff; '
        'border-color:#1f6f9f">Scatter</div>\n'
        '      <div style="' + PILL + '; height:32px">Swarm</div>\n'
        '      <div style="' + PILL + '; height:32px">Lens</div>\n'
        '      <div style="flex:1 1 auto"></div>\n'
        '      <div style="' + PILL + '; height:32px">Full screen</div>\n'
        '    </div>\n  </div>\n'
        # pinned detail
        '  <div class="card" style="padding:11px 13px">\n'
        '    <div style="font-size:15px; font-weight:650">Joseph Haydn</div>\n'
        '    <div style="font-size:12.5px; color:#5f6560; margin-top:2px">1732&ndash;1809 · '
        'lived 77 years · 68 quartets · 29k+ readers/mo</div>\n  </div>\n'
        '</div>\n' + TAIL)
open(os.path.join(D, "Page.dc.html"), "w").write(page)

CANVAS = {
  "artboards": [
    {"file": "Today.dc.html",   "x": 0,    "y": 0, "w": 788, "h": 620, "title": "Today"},
    {"file": "Main.dc.html",    "x": 848,  "y": 0, "w": 788, "h": 660, "title": "A · The canon, drawn"},
    {"file": "OptionB.dc.html", "x": 1696, "y": 0, "w": 788, "h": 660, "title": "B · Output against attention"},
    {"file": "OptionC.dc.html", "x": 2544, "y": 0, "w": 560, "h": 800, "title": "C · The argument in numbers"},
    {"file": "Page.dc.html",    "x": 3164, "y": 0, "w": 376, "h": 800, "title": "Page structure"}
  ],
  "annotations": [
    {"id": "brief", "x": 0, "y": -150, "w": 700,
     "text": "The brief: assert why the greats are great — Richter, Haydn, Boccherini, Mozart, "
             "Beethoven, Bartok, Shostakovich — and surface the outliers like Cambini.\n\n"
             "All four charts are drawn from composers.json, not sketched: same scales, same 0.35 "
             "radius exponent, same jitter hash as the app. Pick a direction and I build it."}
  ],
  "launch": {"view": "canvas"}
}
json.dump(CANVAS, open(os.path.join(D, "canvas.json"), "w"), indent=1)
for f in ("Today", "Main", "OptionB", "OptionC", "Page"):
    p = os.path.join(D, f + ".dc.html")
    print(f"{f+'.dc.html':22} {os.path.getsize(p)/1024:6.1f} KB")
