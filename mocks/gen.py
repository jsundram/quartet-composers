#!/usr/bin/env python3
"""Generate the chart SVGs for the design directions, from the real data and the real scales.
Duplicates chart.js's geometry on purpose (same domains, same 0.35 radius exponent, same jitter
hash) so a mockup is a picture of the actual dataset, not an impression of one."""
import json, math, os

OUT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(OUT)
rows = json.load(open(os.path.join(ROOT, "composers.json")))["rows"]

# --- app tokens (light), lifted from styles.css ---
T = dict(plot="#fbfaf8", grid="#e8e4dc", axis="#6b7169", ink="#191919", muted="#5f6560",
         line="#e2ded6", accent="#1f6f9f", sel="#c2410c", card="#ffffff",
         c_short="#b35806", c_mid="#cec7ba", c_long="#542788", living="#8b9188")

CANON = ["Franz Xaver Richter", "Joseph Haydn", "Luigi Boccherini", "Wolfgang Amadeus Mozart",
         "Ludwig van Beethoven", "Béla Bartók", "Dmitri Shostakovich"]
FORGOTTEN = ["Giuseppe Cambini", "John Lodge Ellerton", "Franz Krommer"]
ONEHIT = ["Claude Debussy", "George Gershwin", "Maurice Ravel"]

by = {r[0]: r for r in rows}
plot_rows = [r for r in rows if r[3] is not None and r[4] is not None]
MAXV = max(r[4] for r in rows if r[4] is not None)

def hash_(s):                                    # chart.js's FNV-1a, for the same jitter
    a = 2166136261
    for ch in s:
        a ^= ord(ch); a = (a * 16777619) & 0xFFFFFFFF
    return (a / 4294967295) * 2 - 1

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def r_of(v, rmax):
    return 2.2 + (rmax - 2.2) * (v / MAXV) ** 0.35

def lifecolor(r):
    """The shipped diverging ramp, for the 'Today' board only."""
    if r[2] is None: return None
    span, mid = r[2] - r[1], 75
    v = max(20, min(104, span))
    def mix(a, b, t):
        A = [int(a[i:i+2], 16) for i in (1, 3, 5)]; B = [int(b[i:i+2], 16) for i in (1, 3, 5)]
        return "#%02x%02x%02x" % tuple(round(A[i] + (B[i]-A[i]) * t) for i in range(3))
    return mix(T["c_short"], T["c_mid"], (v-20)/(mid-20)) if v <= mid \
      else mix(T["c_mid"], T["c_long"], (v-mid)/(104-mid))

def label(x, y, txt, fill, anchor="middle", size=10.5, weight=600):
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" paint-order="stroke" stroke="{T["plot"]}" '
            f'stroke-width="3.5" stroke-linejoin="round">{esc(txt)}</text>')

# ---------------------------------------------------------------- birth-year × quartets frame
def frame_xy(W, H, M):
    w, h = W - M["l"] - M["r"], H - M["t"] - M["b"]
    sx = lambda yr: (yr - 1700) / 300 * w
    lo, hi = math.log10(0.85), math.log10(170)
    sy = lambda q: h - (math.log10(q) - lo) / (hi - lo) * h
    return w, h, sx, sy

def axes_xy(w, h, sx, sy):
    o = []
    for yr in range(1700, 2001, 50):
        o.append(f'<line x1="{sx(yr):.1f}" y1="0" x2="{sx(yr):.1f}" y2="{h}" stroke="{T["grid"]}"/>')
        o.append(f'<text x="{sx(yr):.1f}" y="{h+15}" text-anchor="middle" font-size="11" '
                 f'fill="{T["axis"]}">{yr}</text>')
    for q in (1, 2, 3, 5, 10, 20, 30, 50, 100):
        o.append(f'<line x1="0" y1="{sy(q):.1f}" x2="{w}" y2="{sy(q):.1f}" stroke="{T["grid"]}"/>')
        o.append(f'<text x="-7" y="{sy(q)+4:.1f}" text-anchor="end" font-size="11" '
                 f'fill="{T["axis"]}">{q}</text>')
    o.append(f'<text x="{w}" y="{h+33}" text-anchor="end" font-size="11" font-weight="600" '
             f'fill="{T["muted"]}">birth year →</text>')
    return "\n".join(o)

def open_svg(W, H, M):
    return (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg" '
            f'style="display:block">\n<g transform="translate({M["l"]},{M["t"]})">')

def bg(w, h):
    return f'<rect width="{w}" height="{h}" rx="4" fill="{T["plot"]}"/>'

# ================================================================ TODAY (what ships)
def today(W=760, H=430):
    M = dict(l=42, r=14, t=26, b=40)
    w, h, sx, sy = frame_xy(W, H, M)
    rmax = max(11, min(26, w / 44))
    o = [open_svg(W, H, M), bg(w, h), axes_xy(w, h, sx, sy),
         f'<text x="{-M["l"]+4}" y="-9" font-size="11" font-weight="600" fill="{T["muted"]}">'
         f'↑ quartets written (log scale)</text>']
    for r in sorted(plot_rows, key=lambda r: -r[4]):
        cx = sx(r[1] + hash_(r[0]) * 0.5)
        cy = sy(r[3] * (10 ** (hash_(r[0] + "y") * 0.04)))
        rr = r_of(r[4], rmax)
        c = lifecolor(r)
        o.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rr:.1f}" fill="{c or T["plot"]}" '
                 f'stroke="{T["living"] if c is None else "#ffffff"}" stroke-width="1" opacity="0.92"/>')
    # the shipped greedy labeller, most-read first
    boxes, n = [], 0
    for r in sorted(plot_rows, key=lambda r: -r[4]):
        if n >= 12: break
        cx = sx(r[1] + hash_(r[0]) * 0.5); cy = sy(r[3] * (10 ** (hash_(r[0]+"y") * 0.04)))
        tw = len(r[0]) * 5.5 + 6; bx = cx - tw/2; byy = cy - r_of(r[4], rmax) - 16
        if bx < 0 or bx + tw > w or byy < 0: continue
        if any(bx < b[0]+b[2] and bx+tw > b[0] and byy < b[1]+b[3] and byy+12 > b[1] for b in boxes):
            continue
        boxes.append((bx-2, byy-1, tw+4, 14)); n += 1
        o.append(label(cx, byy + 10, r[0], T["ink"], size=10.5, weight=500))
    o.append("</g></svg>")
    return "\n".join(o)

# ================================================================ A — canon path
def option_a(W=760, H=430):
    M = dict(l=42, r=14, t=26, b=40)
    w, h, sx, sy = frame_xy(W, H, M)
    rmax = max(11, min(26, w / 44))
    pt = lambda r: (sx(r[1] + hash_(r[0])*0.5), sy(r[3] * (10 ** (hash_(r[0]+"y")*0.04))))
    o = [open_svg(W, H, M), bg(w, h), axes_xy(w, h, sx, sy),
         f'<text x="{-M["l"]+4}" y="-9" font-size="11" font-weight="600" fill="{T["muted"]}">'
         f'↑ quartets written (log scale)</text>']
    named = set(CANON) | set(FORGOTTEN) | set(ONEHIT)
    for r in sorted(plot_rows, key=lambda r: -r[4]):
        if r[0] in named: continue
        cx, cy = pt(r)
        o.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_of(r[4], rmax):.1f}" '
                 f'fill="{T["muted"]}" opacity="0.20"/>')
    path = " ".join(("M" if i == 0 else "L") + f"{pt(by[n])[0]:.1f},{pt(by[n])[1]:.1f}"
                    for i, n in enumerate(CANON))
    o.append(f'<path d="{path}" fill="none" stroke="{T["sel"]}" stroke-width="1.4" '
             f'opacity="0.42" stroke-linejoin="round"/>')
    for n in FORGOTTEN + ONEHIT:
        r = by[n]; cx, cy = pt(r)
        o.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_of(r[4], rmax):.1f}" fill="none" '
                 f'stroke="{T["accent"]}" stroke-width="2"/>')
    for n in CANON:
        r = by[n]; cx, cy = pt(r)
        o.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_of(r[4], rmax):.1f}" '
                 f'fill="{T["sel"]}" stroke="#ffffff" stroke-width="1.5"/>')
    # Placed by hand: Haydn and Boccherini are 11 years and 23 quartets apart, so "always above"
    # crossed their labels over each other's dot. "above" | "below" | "left" | "right".
    def put(n, where, color, size=10.5, txt=None):
        r = by[n]; cx, cy = pt(r); rr = r_of(r[4], rmax)
        t = txt or ("Richter" if n == "Franz Xaver Richter" else n.split()[-1])
        if where == "above":  o.append(label(cx, cy - rr - 7, t, color, size=size))
        elif where == "below": o.append(label(cx, cy + rr + 14, t, color, size=size))
        elif where == "left":  o.append(label(cx - rr - 6, cy + 4, t, color, "end", size))
        else:                  o.append(label(cx + rr + 6, cy + 4, t, color, "start", size))
    for n, w_ in (("Franz Xaver Richter", "left"), ("Joseph Haydn", "left"),
                  ("Luigi Boccherini", "above"), ("Wolfgang Amadeus Mozart", "above"),
                  ("Ludwig van Beethoven", "below"), ("Béla Bartók", "below"),
                  ("Dmitri Shostakovich", "above")):
        put(n, w_, T["sel"])
    for n, w_ in (("Giuseppe Cambini", "right"), ("John Lodge Ellerton", "right"),
                  ("Franz Krommer", "left"), ("Claude Debussy", "above"),
                  ("George Gershwin", "above"), ("Maurice Ravel", "above")):
        put(n, w_, T["accent"], 10)
    o.append("</g></svg>")
    return "\n".join(o)

# ================================================================ B — output vs attention
def option_b(W=760, H=430):
    M = dict(l=52, r=16, t=26, b=42)
    w, h = W - M["l"] - M["r"], H - M["t"] - M["b"]
    qlo, qhi = math.log10(0.85), math.log10(200)
    vlo, vhi = math.log10(20), math.log10(260000)
    sx = lambda q: (math.log10(q) - qlo) / (qhi - qlo) * w
    sy = lambda v: h - (math.log10(max(v, 20)) - vlo) / (vhi - vlo) * h
    rmax = 13
    o = [open_svg(W, H, M), bg(w, h)]
    for ratio, lab in ((1, "1 reader"), (10, "10 readers"), (100, "100 readers"),
                       (1000, "1,000 readers"), (10000, "10,000 readers")):
        pts = [(sx(q), sy(q * ratio)) for q in (0.85, 200) if 20 <= q*ratio <= 260000]
        if len(pts) < 2:
            qa = max(0.85, 20/ratio); qb = min(200, 260000/ratio)
            if qb <= qa: continue
            pts = [(sx(qa), sy(qa*ratio)), (sx(qb), sy(qb*ratio))]
        o.append(f'<line x1="{pts[0][0]:.1f}" y1="{pts[0][1]:.1f}" x2="{pts[1][0]:.1f}" '
                 f'y2="{pts[1][1]:.1f}" stroke="{T["grid"]}" stroke-width="1"/>')
        lx, ly = pts[0]
        o.append(f'<text x="{lx+4:.1f}" y="{ly-5:.1f}" text-anchor="start" font-size="9.5" '
                 f'fill="{T["axis"]}" opacity="0.9">{lab} per quartet</text>')
    for q in (1, 3, 10, 30, 100):
        o.append(f'<text x="{sx(q):.1f}" y="{h+15}" text-anchor="middle" font-size="11" '
                 f'fill="{T["axis"]}">{q}</text>')
    for v, lab in ((100, "100"), (1000, "1k"), (10000, "10k"), (100000, "100k")):
        o.append(f'<text x="-8" y="{sy(v)+4:.1f}" text-anchor="end" font-size="11" '
                 f'fill="{T["axis"]}">{lab}</text>')
    o.append(f'<text x="{w}" y="{h+34}" text-anchor="end" font-size="11" font-weight="600" '
             f'fill="{T["muted"]}">quartets written →</text>')
    o.append(f'<text x="{-M["l"]+4}" y="-9" font-size="11" font-weight="600" fill="{T["muted"]}">'
             f'↑ English Wikipedia readers / month</text>')
    # Quartet counts are integers, so on a log x they land in hard vertical stripes -- 313 of the
    # 790 sit on "1". Same deterministic name-hash jitter the app already uses for ties, in log
    # space so it is a constant proportion of the axis.
    jx = lambda r: sx(r[3] * (10 ** (hash_(r[0]) * 0.045)))
    named = set(CANON) | set(FORGOTTEN) | set(ONEHIT)
    for r in sorted(plot_rows, key=lambda r: -r[4]):
        if r[0] in named: continue
        o.append(f'<circle cx="{jx(r):.1f}" cy="{sy(r[4]):.1f}" r="3.2" fill="{T["muted"]}" '
                 f'opacity="0.22"/>')
    for n in FORGOTTEN + ONEHIT:
        r = by[n]
        o.append(f'<circle cx="{jx(r):.1f}" cy="{sy(r[4]):.1f}" r="6" fill="none" '
                 f'stroke="{T["accent"]}" stroke-width="2"/>')
    for n in CANON:
        r = by[n]
        o.append(f'<circle cx="{jx(r):.1f}" cy="{sy(r[4]):.1f}" r="6.5" fill="{T["sel"]}" '
                 f'stroke="#ffffff" stroke-width="1.5"/>')
    def putb(n, where, color, size=10.5):
        r = by[n]; x, y = jx(r), sy(r[4])
        t = "Richter" if n == "Franz Xaver Richter" else n.split()[-1]
        if where == "above":  o.append(label(x, y - 11, t, color, size=size))
        elif where == "below": o.append(label(x, y + 17, t, color, size=size))
        elif where == "left":  o.append(label(x - 10, y + 4, t, color, "end", size))
        else:                  o.append(label(x + 10, y + 4, t, color, "start", size))
    for n, w_ in (("Wolfgang Amadeus Mozart", "above"), ("Ludwig van Beethoven", "below"),
                  ("Dmitri Shostakovich", "below"), ("Béla Bartók", "above"),
                  ("Joseph Haydn", "above"), ("Luigi Boccherini", "below"),
                  ("Franz Xaver Richter", "below")):
        putb(n, w_, T["sel"])
    for n, w_ in (("Giuseppe Cambini", "left"), ("John Lodge Ellerton", "left"),
                  ("Franz Krommer", "left"), ("Claude Debussy", "above"),
                  ("George Gershwin", "right"), ("Maurice Ravel", "below")):
        putb(n, w_, T["accent"], 10)
    o.append("</g></svg>")
    return "\n".join(o)

for name, fn in (("today", today), ("a", option_a), ("b", option_b)):
    open(os.path.join(OUT, f"chart-{name}.svg"), "w").write(fn())
    print("wrote chart-%s.svg" % name)

stats = {n: dict(born=by[n][1], q=by[n][3], v=by[n][4], per=by[n][4]/by[n][3])
         for n in CANON + FORGOTTEN + ONEHIT}
json.dump(stats, open(os.path.join(OUT, "stats.json"), "w"), indent=1, ensure_ascii=False)
print("plotted:", len(plot_rows), " max views:", MAXV)

# ================================================================ A, phone width
def option_a_phone(W=376, H=300):
    M = dict(l=30, r=10, t=22, b=32)
    w, h, sx, sy = frame_xy(W, H, M)
    rmax = max(8, min(26, w / 44))
    pt = lambda r: (sx(r[1] + hash_(r[0])*0.5), sy(r[3] * (10 ** (hash_(r[0]+"y")*0.04))))
    o = [open_svg(W, H, M), bg(w, h)]
    for yr in range(1700, 2001, 100):
        o.append(f'<line x1="{sx(yr):.1f}" y1="0" x2="{sx(yr):.1f}" y2="{h}" stroke="{T["grid"]}"/>')
        o.append(f'<text x="{sx(yr):.1f}" y="{h+14}" text-anchor="middle" font-size="10" '
                 f'fill="{T["axis"]}">{yr}</text>')
    for q in (1, 3, 10, 30, 100):
        o.append(f'<line x1="0" y1="{sy(q):.1f}" x2="{w}" y2="{sy(q):.1f}" stroke="{T["grid"]}"/>')
        o.append(f'<text x="-6" y="{sy(q)+3.5:.1f}" text-anchor="end" font-size="10" '
                 f'fill="{T["axis"]}">{q}</text>')
    named = set(CANON) | set(FORGOTTEN)
    for r in sorted(plot_rows, key=lambda r: -r[4]):
        if r[0] in named: continue
        cx, cy = pt(r)
        o.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_of(r[4], rmax):.1f}" '
                 f'fill="{T["muted"]}" opacity="0.20"/>')
    path = " ".join(("M" if i == 0 else "L") + f"{pt(by[n])[0]:.1f},{pt(by[n])[1]:.1f}"
                    for i, n in enumerate(CANON))
    o.append(f'<path d="{path}" fill="none" stroke="{T["sel"]}" stroke-width="1.2" opacity="0.42"/>')
    for n in FORGOTTEN:
        r = by[n]; cx, cy = pt(r)
        o.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_of(r[4], rmax):.1f}" fill="none" '
                 f'stroke="{T["accent"]}" stroke-width="1.8"/>')
    for n in CANON:
        r = by[n]; cx, cy = pt(r)
        o.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_of(r[4], rmax):.1f}" '
                 f'fill="{T["sel"]}" stroke="#ffffff" stroke-width="1.2"/>')
    for n, dx, dy, anc in (("Joseph Haydn", -6, 3.5, "end"), ("Wolfgang Amadeus Mozart", 0, -9, "middle"),
                           ("Dmitri Shostakovich", 0, -9, "middle"), ("Giuseppe Cambini", 6, 3.5, "start")):
        r = by[n]; cx, cy = pt(r); rr = r_of(r[4], rmax)
        col = T["accent"] if n in FORGOTTEN else T["sel"]
        x = cx + (dx - rr if anc == "end" else dx + rr if anc == "start" else 0)
        o.append(label(x, cy + (dy - rr if dy < 0 else dy), n.split()[-1], col, anc, 9.5))
    o.append("</g></svg>")
    return "\n".join(o)

open(os.path.join(OUT, "chart-a-phone.svg"), "w").write(option_a_phone())
print("wrote chart-a-phone.svg")
