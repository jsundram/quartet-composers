#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Render assets/og.svg — the share card — from composers.json.

The card is a REAL rendering of the dataset, not a logo on a colored rectangle: same axes, same
radius exponent, same lifespan ramp as chart.js. Two reasons that is worth a script instead of a
hand-drawn SVG. It cannot go stale — rebuild the data and the preview follows — and the thing
someone sees in a chat thread is the thing they get when they tap.

Pipeline:  scripts/make-og-svg.py  ->  assets/og.svg  ->  scripts/make-og.sh  ->  assets/og.png
The PNG is what index.html references; scrapers reject SVG and relative URLs alike.

Keep the constants below in agreement with chart.js — they are duplicated, not shared, because
the app must not ship a build step and this must not ship a JS runtime.
"""
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

W, H = 1200, 630
PLOT = {"x": 520, "y": 96, "w": 608, "h": 446}      # chart panel, right of the title block
QX_DOMAIN = (0.85, 200)                              # quartets written, log -- as chart.js
VY_DOMAIN = (0.85, 260000)                           # EN readers / month, log
R_CONTEXT, R_NAMED = 3.6, 7.5                        # uniform: readership is the Y AXIS here

BG, PANEL, INK, MUTED, GRID = "#14161a", "#191c21", "#eceef0", "#9aa3a8", "#2b313a"
SEL, ACCENT = "#fb923c", "#7ec2f0"                   # dark --sel / --accent, as the app bakes them
RATIOS = (1, 10, 100, 1000, 10000)                   # readers-per-quartet diagonals
CANON = ("Franz Xaver Richter", "Joseph Haydn", "Luigi Boccherini", "Wolfgang Amadeus Mozart",
         "Ludwig van Beethoven", "Pyotr Ilyich Tchaikovsky", "Claude Debussy", "Béla Bartók",
         "Sergei Prokofiev", "Dmitri Shostakovich")
OUTLIERS = ("Giuseppe Cambini", "Franz Krommer", "John Lodge Ellerton")

# Labelled by hand: the point of the card is that a reader recognizes a name in it, and "top 6 by
# pageviews" would print Beethoven/Mozart/Tchaikovsky — famous, but not famous *as quartet
# composers*, which is what the chart is about. The four most prolific sit almost on top of each
# other (Cambini, Boccherini and Haydn are all born within 14 years and all in the top band), so
# placement is explicit rather than automatic: (name, anchor, dx, dy) around the dot.
LABELS = [
    ("Wolfgang Amadeus Mozart", "middle", 0, "above"),
    ("Ludwig van Beethoven",    "end",   -9, "beside"),
    ("Joseph Haydn",            "middle", 0, "above"),
    ("Luigi Boccherini",        "middle", 0, "below"),
    ("Béla Bartók",              "middle", 0, "above"),
    ("Giuseppe Cambini",        "end",   -9, "beside"),
]


# names.js's display rule, duplicated for the same reason the scales are: the card must not ship a
# JS runtime, and a label here that disagrees with the one on the page is exactly the mismatch
# invariant 14 exists to prevent. Surname alone, an initial where a surname is shared, the full
# title where even that is ambiguous.
SUFFIXES = {"junior", "jr", "jr.", "sr", "sr.", "ii", "iii", "iv"}
SURNAME_OVERRIDES = {
    "Ralph Vaughan Williams": "Vaughan Williams",
    "David Vaughan Thomas": "Vaughan Thomas",
    "Peter Maxwell Davies": "Maxwell Davies",
    "Vincenza Garelli della Morea": "Garelli della Morea",
    "Tera de Marez Oyens": "de Marez Oyens",
    "Alicia Van Buren": "Van Buren",
    "Nancy Van de Vate": "Van de Vate",
    "Chen Yi": "Chen",
}


def bare(name):
    """Drop a Wikipedia disambiguator: 'Samuel Wesley (composer, born 1766)'."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", name)


def surname_of(name):
    if name in SURNAME_OVERRIDES:
        return SURNAME_OVERRIDES[name]
    parts = bare(name).split()
    end, suffix = len(parts) - 1, ""
    if end > 0 and parts[end].lower() in SUFFIXES:
        suffix, end = " " + parts[end], end - 1
    return parts[end] + suffix


def short_names(names):
    """canonical title -> the label the page's chart would print."""
    groups = {}
    for n in names:
        groups.setdefault(surname_of(n), []).append(n)
    out = {}
    for sur, members in groups.items():
        fores = {n: bare(n).replace(sur, "").strip() for n in members}
        initials = {}
        for f in fores.values():
            initials[f[:1]] = initials.get(f[:1], 0) + 1
        for n in members:
            f = fores[n]
            if len(members) < 2 or not f:
                out[n] = sur
            elif bare(n).startswith(sur):          # family-name-first title; leave the order alone
                out[n] = bare(n)
            elif initials[f[0]] == 1:
                out[n] = "%s. %s" % (f[0], sur)
            else:
                out[n] = bare(n)
    return out


def jitter(name):
    """chart.js's FNV-1a name hash, in log space: quartet counts are integers, so without this the
    card draws the same hard vertical stripes the app deliberately breaks up (313 composers sit on
    "1"). Same encoding on both sides, per the note at the top of this file."""
    a = 2166136261
    for ch in name:
        a ^= ord(ch)
        a = (a * 16777619) & 0xFFFFFFFF
    return 10 ** (((a / 4294967295) * 2 - 1) * 0.045)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main():
    with open(os.path.join(ROOT, "composers.json")) as f:
        data = json.load(f)
    rows = data["rows"]
    plotted = [r for r in rows if r[3] is not None and r[4] is not None]
    by_name0 = {r[0]: r for r in rows}

    def logscale(dom, px, origin, flip=False):
        lo, hi = math.log10(dom[0]), math.log10(dom[1])
        def f(v):
            t = (math.log10(max(v, dom[0])) - lo) / (hi - lo)
            return origin + (px - t * px if flip else t * px)
        return f

    sx = logscale(QX_DOMAIN, PLOT["w"], PLOT["x"])
    sy = logscale(VY_DOMAIN, PLOT["h"], PLOT["y"], flip=True)

    # Trim a segment to the plot rect (Liang-Barsky), same job as chart.js's trim(): a diagonal's
    # endpoints are far outside the box and there is no clip path in a static SVG.
    def clip(ax, ay, bx, by):
        t0, t1, dx, dy = 0.0, 1.0, bx - ax, by - ay
        for p_, q_ in ((-dx, ax - PLOT["x"]), (dx, PLOT["x"] + PLOT["w"] - ax),
                       (-dy, ay - PLOT["y"]), (dy, PLOT["y"] + PLOT["h"] - ay)):
            if p_ == 0:
                if q_ < 0: return None
                continue
            r_ = q_ / p_
            if p_ < 0:
                if r_ > t1: return None
                t0 = max(t0, r_)
            else:
                if r_ < t0: return None
                t1 = min(t1, r_)
        return (ax + t0 * dx, ay + t0 * dy, ax + t1 * dx, ay + t1 * dy)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
           '  <!-- GENERATED by scripts/make-og-svg.py — do not hand-edit; rerun the script. -->',
           f'  <rect width="{W}" height="{H}" fill="{BG}"/>',
           f'  <rect x="{PLOT["x"] - 26}" y="{PLOT["y"] - 26}" width="{PLOT["w"] + 52}" '
           f'height="{PLOT["h"] + 52}" rx="16" fill="{PANEL}"/>']

    for q in (1, 3, 10, 30, 100):
        out.append(f'  <line x1="{sx(q):.1f}" y1="{PLOT["y"]}" x2="{sx(q):.1f}" '
                   f'y2="{PLOT["y"] + PLOT["h"]}" stroke="{GRID}" stroke-width="1"/>')
        out.append(f'  <text x="{sx(q):.1f}" y="{PLOT["y"] + PLOT["h"] + 26}" fill="{MUTED}" '
                   f'font-family="system-ui,sans-serif" font-size="17" text-anchor="middle">{q}</text>')
    for v, lab in ((1, "1"), (100, "100"), (10000, "10k"), (100000, "100k")):
        out.append(f'  <line x1="{PLOT["x"]}" y1="{sy(v):.1f}" x2="{PLOT["x"] + PLOT["w"]}" '
                   f'y2="{sy(v):.1f}" stroke="{GRID}" stroke-width="1"/>')
        out.append(f'  <text x="{PLOT["x"] - 12}" y="{sy(v) + 6:.1f}" fill="{MUTED}" '
                   f'font-family="system-ui,sans-serif" font-size="17" text-anchor="end">{lab}</text>')

    # The readers-per-quartet diagonals: the distance a dot sits above one IS the card's claim.
    for k in RATIOS:
        seg = clip(sx(QX_DOMAIN[0]), sy(k * QX_DOMAIN[0]), sx(QX_DOMAIN[1]), sy(k * QX_DOMAIN[1]))
        if seg:
            out.append(f'  <line x1="{seg[0]:.1f}" y1="{seg[1]:.1f}" x2="{seg[2]:.1f}" '
                       f'y2="{seg[3]:.1f}" stroke="{GRID}" stroke-width="1"/>')

    named = set(CANON) | set(OUTLIERS)
    # `*_` rather than naming all eight: the card draws four of these fields, and a row that grew
    # a column it does not draw (gender did) should not stop the share card from rendering.
    for name, birth, death, quartets, views, *_ in sorted(rows, key=lambda r: -(r[4] or 0)):
        if quartets is None or views is None or name in named:
            continue                                  # not plottable; the app omits it too
        out.append(f'  <circle cx="{sx(quartets * jitter(name + "q")):.1f}" '
                   f'cy="{sy(views):.1f}" r="{R_CONTEXT}" fill="{MUTED}" opacity=".22"/>')
    for name in OUTLIERS:
        r = by_name0[name]
        out.append(f'  <circle cx="{sx(r[3] * jitter(name + "q")):.1f}" cy="{sy(r[4]):.1f}" '
                   f'r="{R_NAMED}" fill="none" stroke="{ACCENT}" stroke-width="2.4"/>')
    for name in CANON:
        r = by_name0[name]
        out.append(f'  <circle cx="{sx(r[3] * jitter(name + "q")):.1f}" cy="{sy(r[4]):.1f}" '
                   f'r="{R_NAMED}" fill="{SEL}" stroke="{PANEL}" stroke-width="1.6"/>')

    # A label that silently vanishes degrades the one image people see before they click, so this
    # is fatal, not a warning. It fires when a name changes spelling — which fetch_views.py now
    # does routinely, having corrected 79 of them in one run.
    by_name = {r[0]: r for r in rows}
    absent = [n for n, _, _, _ in LABELS if n not in by_name] \
           + [n for n in CANON + OUTLIERS if n not in by_name]
    if absent:
        print("ERROR: labelled composers are not in composers.json: %s\n"
              "       (names are canonical Wikipedia titles now — check the spelling)"
              % ", ".join(absent), file=sys.stderr)
        return 1

    short = short_names([r[0] for r in rows])
    for name, anchor, dx, where in LABELS:
        r = by_name[name]
        cx, cy, rad = sx(r[3] * jitter(r[0] + "q")), sy(r[4]), R_NAMED
        tx = cx + (dx + (rad if dx > 0 else -rad) if where == "beside" else 0)
        ty = {"above": cy - rad - 9, "below": cy + rad + 21}.get(where, cy + 6)
        # Halo painted in the PAGE background, not the panel's: a "beside" label can hang off the
        # panel's left edge, and a panel-colored halo would show as a visible smear out there.
        out.append(f'  <text x="{tx:.1f}" y="{ty:.1f}" fill="{INK}" '
                   f'font-family="system-ui,sans-serif" font-size="18" font-weight="600" '
                   f'text-anchor="{anchor}" stroke="{BG}" stroke-width="4" '
                   f'paint-order="stroke" stroke-linejoin="round">{esc(short[name])}</text>')

    out += [
        f'  <text x="72" y="192" fill="{INK}" font-family="Georgia,serif" font-size="54" '
        f'font-weight="700">String Quartet</text>',
        f'  <text x="72" y="254" fill="{INK}" font-family="Georgia,serif" font-size="54" '
        f'font-weight="700">Composers</text>',
        f'  <text x="72" y="316" fill="{MUTED}" font-family="system-ui,sans-serif" font-size="24">'
        f'{len(plotted)} composers, {min(r[1] for r in plotted)}–{max(r[1] for r in plotted)}.</text>',
        f'  <text x="72" y="350" fill="{MUTED}" font-family="system-ui,sans-serif" font-size="24">'
        f'Quartets written × readers.</text>',
        f'  <text x="72" y="384" fill="{MUTED}" font-family="system-ui,sans-serif" font-size="24">'
        f'Diagonals = readers per quartet.</text>',
        f'  <circle cx="80" cy="424" r="7.5" fill="{SEL}"/>',
        f'  <text x="98" y="430" fill="{MUTED}" font-family="system-ui,sans-serif" font-size="17">'
        f'the repertoire, in birth order</text>',
        f'  <circle cx="80" cy="456" r="7.5" fill="none" stroke="{ACCENT}" stroke-width="2.4"/>',
        f'  <text x="98" y="462" fill="{MUTED}" font-family="system-ui,sans-serif" font-size="17">'
        f'wrote the most, read the least</text>',
        f'  <text x="72" y="540" fill="{MUTED}" font-family="system-ui,sans-serif" font-size="18">'
        f'jsundram.github.io/quartet-composers</text>',
        '</svg>',
    ]

    path = os.path.join(ROOT, "assets", "og.svg")
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")
    print("wrote assets/og.svg (%d composers, %d bytes)" % (len(rows), os.path.getsize(path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
