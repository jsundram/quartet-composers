// The chart: three ways to read the same ~880 dots, sharing one layout + hit-test core.
//
// WHY THREE. The 2014 original had exactly one: a *cartesian* fisheye that distorted both axes
// continuously under the cursor. It magnified beautifully and read terribly — with the axes
// moving there was no stable picture to look at, and a screenshot of it is nonsense. So:
//
//   scatter  the default and the honest one. Axes are FIXED (birth year, log quartets) so the
//            static view is a real chart you can screenshot, print, or link. Detail comes from
//            ordinary pan/zoom you opt into, not from a distortion that is always on.
//   swarm    force-collided along the birth-year axis. Nothing overlaps, ever — the answer to
//            "most composers here wrote three quartets or fewer and pile onto three log bands".
//            Costs the quartet-count axis, which is why it isn't the default.
//   lens     the experiment, rehabilitated. A CIRCULAR fisheye over a fixed base chart: the
//            axes never move, the magnifier is a lens you drag around. This is what the original
//            was reaching for.
//
// Two things are shared by all three and are most of the value:
//   - hit-testing via a Delaunay over the CURRENT screen positions, so the tap target for a dot
//     is its whole Voronoi cell rather than its 2.5px radius. On a phone that is the difference
//     between "usable" and "not".
//   - greedy collision-avoided labels, so the chart says something with no interaction at all.
//
// Colors are read INTO JS here (Theme.getCssColor), so a theme flip can't reach them via CSS —
// app.js calls rerender() on every theme change and this file re-reads them. See theme.js.

window.Chart = (function () {
  const TOUCH = !matchMedia("(hover: hover) and (pointer: fine)").matches;

  // Set from the data in setData(). It covers the PLOTTABLE rows only, which is not the same as
  // the roster: the three names born before 1700 (Allegri 1582, Scarlatti 1660, Telemann 1681)
  // have no stated quartet count, so a domain starting at 1580 spent a third of the width on a
  // stretch where the chart can never draw a dot. Snapped out to a 50-year grid so the ticks stay
  // round; make-og-svg.py derives the same domain the same way.
  let X_DOMAIN = [1700, 2000];
  const Y_DOMAIN = [0.85, 170];         // log; the largest stated count is 149 (Cambini)
  const Y_TICKS = [1, 2, 3, 5, 10, 20, 30, 50, 100];
  // The colour ramp's stops are FIXED, evenly spaced across the lifespan range. They used to sit
  // at [20, median, 104] with the median recomputed from the data, which meant the same composer
  // changed colour when somebody else joined the list -- the same "the pivot moves when the data
  // does" problem the diverging ramp had, surviving the switch to a sequential one.
  const LIFE_DOMAIN = [20, 62, 104];

  // ---- the readers view ----------------------------------------------------
  // Output ACROSS, attention UP, so readers-per-quartet is a diagonal and the distance a composer
  // sits above one is the argument: Mozart near 10,000 readers a quartet, Cambini on 1. The other
  // views ask "when, and how much"; this one asks "and did it land".
  const QX_DOMAIN = [0.85, 200];        // quartets written; largest stated is 149
  const QX_TICKS = [1, 2, 3, 5, 10, 20, 30, 50, 100];
  const VY_DOMAIN = [0.85, 260000];     // readers/mo; 1 .. 186,772 today
  const VY_TICKS = [1, 10, 100, 1000, 10000, 100000];
  const RATIOS = [1, 10, 100, 1000, 10000];   // the readers-per-quartet diagonals

  // The editorial spine, and the only hardcoded composer NAMES in the app. They are canonical
  // Wikipedia titles, which change spelling when the pipeline runs (see invariant 4), so a name
  // that stops resolving is reported by missingNames() and asserted empty in the UI suite rather
  // than quietly dropping a composer out of the argument.
  const CANON = ["Franz Xaver Richter", "Joseph Haydn", "Luigi Boccherini",
                 "Wolfgang Amadeus Mozart", "Ludwig van Beethoven", "Béla Bartók",
                 "Dmitri Shostakovich"];
  const OUTLIERS = ["Giuseppe Cambini", "Franz Krommer", "John Lodge Ellerton",
                    "Claude Debussy", "George Gershwin", "Maurice Ravel"];
  // Sets, not arrays: isCanon/named are called per DOT per FRAME from layout() and from all four
  // paint functions -- about 4,000 calls a frame in the readers view, and an Array.includes scan
  // in each of them is work a phone does not need to do while a pinch is in flight.
  let canonIdx = [], outlierIdx = [], canonSet = new Set(), namedSet = new Set(), missing = [];

  let el, flagEl, cbHover, cbSelect, cbZoom;
  // The readers view is the DEFAULT: it is the one that makes the page's claim. The timeline is
  // one tap away and still the honest overview of when the form was written.
  const DEFAULT_MODE = "readers";
  let rows = [], mode = DEFAULT_MODE, visible = null, selected = null, hovered = null;
  let svg, gPlot, gDots, gLabels, gAxX, gAxY, gGrid, gLens, gSel;
  let w = 0, h = 0, m = { top: 22, right: 14, bottom: 32, left: 46 };
  let x0, y0, qx, vy, rScale, colorScale, C = {};
  let transform = d3.zoomIdentity, zoom;
  let swarmY = null, swarmKey = "";      // memo: the sim is expensive, size/radius are its inputs
  let lens = null;                       // {x,y} focus in plot coords, or null
  let pos = [], idx = [], delaunay = null;

  // ---- data prep ----------------------------------------------------------
  // Deterministic jitter from the name, so ties separate without the picture changing between
  // renders. Ties are very common (many cells hold several composers at one birth year AND count) and
  // an un-jittered scatter hides them completely — one dot is drawn over another and the one
  // underneath can never be hovered, tapped, or counted by eye. Kept small (half a year; ~9% in
  // count-space, well inside the gap between adjacent integer counts) and disclosed in the hint.
  function hash(s) {
    let a = 2166136261;
    for (let i = 0; i < s.length; i++) { a ^= s.charCodeAt(i); a = Math.imul(a, 16777619); }
    return ((a >>> 0) / 4294967295) * 2 - 1;     // -1..1
  }

  // [name, birth, death, quartets, views, views_lo, views_hi, gender]; death, quartets and gender
  // may be null. This comment IS the schema for every positional read below — keep it in step with
  // build_data.py's `fields`, which validate.py pins.
  // "living" is now simply the absence of a death date on Wikidata — a fact about today, not the
  // 2014 dataset's inference from a field that overloaded lifespan with age-in-2014.
  function setData(raw) {
    rows = raw.map((r, i) => {
      const j = hash(r[0]);
      return {
        i, name: r[0], birth: r[1], death: r[2], quartets: r[3],
        views: r[4], lo: r[5], hi: r[6],
        living: r[2] == null,
        lifespan: r[2] == null ? null : r[2] - r[1],
        jx: j * 0.5,                                        // years
        jy: Math.pow(10, hash(r[0] + "y") * 0.04),          // multiplicative, log-uniform
        // Quartet counts are integers, so on the readers view's log x they land in hard vertical
        // stripes — 313 of the 790 sit on "1". Same idea as jx, in log space so the nudge is a
        // constant PROPORTION of the axis rather than a constant number of quartets.
        jq: Math.pow(10, hash(r[0] + "q") * 0.045),
      };
    });
    const at = new Map(rows.map(d => [d.name, d.i]));
    const resolve = list => list.filter(n => at.has(n)).map(n => at.get(n));
    canonIdx = resolve(CANON);
    outlierIdx = resolve(OUTLIERS);
    canonSet = new Set(canonIdx);
    namedSet = new Set(canonIdx.concat(outlierIdx));
    missing = CANON.concat(OUTLIERS).filter(n => !at.has(n));
    if (missing.length) console.error("Chart: named composers missing from the data:", missing);

    const yrs = rows.filter(plottable).map(d => d.birth);
    if (yrs.length) {
      X_DOMAIN = [Math.floor((d3.min(yrs) - 8) / 50) * 50, Math.ceil((d3.max(yrs) + 8) / 50) * 50];
    }
    swarmY = null;
    scoreProminence();
  }

  // ---- colors -------------------------------------------------------------
  function readColors() {
    const g = Theme.getCssColor;
    C = {
      short: g("--c-short"), mid: g("--c-mid"), long: g("--c-long"), living: g("--c-living"),
      plot: g("--plot"), grid: g("--grid"), axis: g("--axis"), line: g("--dot-line"),
      ink: g("--ink"), muted: g("--muted"), sel: g("--sel"), accent: g("--accent"),
    };
    colorScale = d3.scaleLinear()
      .domain(LIFE_DOMAIN)
      .range([C.short, C.mid, C.long])
      .interpolate(d3.interpolateLab)
      .clamp(true);
  }

  // Living composers are NOT on the ramp, because their final lifespan does not exist yet —
  // colouring a 40-year-old as "died young" states something untrue. They get an open circle: a
  // SHAPE difference, which also satisfies "never encode meaning in color alone" and survives
  // both color-blindness and a black-and-white print.
  // The readers view spends colour on the ARGUMENT rather than on lifespan: the seven filled in
  // the selection orange, the outliers ringed in the accent, and the other 780 in one recessive
  // grey. Emphasis, not eight hues — the point of the view is a handful of names against a field.
  function fillOf(d) {
    if (mode !== "readers") return d.living ? C.plot : colorScale(d.lifespan);
    return isCanon(d.i) ? C.sel : named(d.i) ? "none" : C.muted;
  }
  function strokeOf(d) {
    if (mode !== "readers") return d.living ? C.living : C.line;
    return isCanon(d.i) ? C.plot : named(d.i) ? C.accent : "none";
  }
  function widthOf(d) {
    if (mode !== "readers") return d.living ? 1.4 : 1;
    return isCanon(d.i) ? 1.6 : named(d.i) ? 2 : 0;
  }
  // A FILTER HERE IS A HIGHLIGHT, not a subtraction: nothing is removed, the rest drops to 0.07.
  // So in the readers view the filtered-IN dots have to carry the answer, and at the resting 0.22
  // they could not — 219 women at 0.22 against 571 ghosts at 0.07 is a difference you have to
  // hunt for, in the one view whose whole point is where a group sits against the field. While a
  // filter is on they come up to 0.55; with no filter, 0.22 is right, because then the recessive
  // mass IS the field the thirteen named composers are being read against.
  function opacityOf(d) {
    if (visible && !visible.has(d.i)) return 0.07;
    if (mode !== "readers") return 0.92;
    if (named(d.i)) return 1;
    return visible ? 0.55 : 0.22;
  }
  // Both branches are readers-only: --sel is the PINNED colour, so tinting the seven with it in
  // Timeline/Swarm/Lens made seven composers look pinned with nothing pinned, and made the real
  // pin unidentifiable once there was one.
  function labelColorOf(d) {
    if (mode !== "readers") return C.ink;
    return isCanon(d.i) ? C.sel : named(d.i) ? C.accent : C.ink;
  }
  // table.js paints its row chip with this, on the promise that a row and its dot are
  // recognisably the same thing. So it follows the CURRENT view's encoding, not lifespan always —
  // in the readers view that means the thirteen named composers are findable in the table by
  // colour, and everyone else is the same recessive grey they are on the chart.
  function colorOf(d) {
    if (mode === "readers") return isCanon(d.i) ? C.sel : named(d.i) ? C.accent : C.muted;
    return d.living ? C.living : colorScale(d.lifespan);
  }

  // ---- label priority -----------------------------------------------------
  // LABELS ARE A FUNCTION OF ZOOM, like a map. A fixed set answers a pinch with the same names
  // larger, which makes the zoom decorative: the interaction promises detail and delivers scale.
  // So the budget grows with the zoom (pickLabels) and this decides who fills it.
  //
  // PROMINENCE is how far a dot stands out from the crowd it is drawn in: z-scored on each axis,
  // then the distance from the centre. Z-scores rather than raw decades because the two axes have
  // different spreads, and a rule that ignores that just ranks whichever axis is wider.
  //
  // Recomputed over the VISIBLE set, so a filter ranks that group against ITSELF. That is the
  // whole reason it beats readership here: filtered to the women, readership names whoever has
  // the largest article (Beach, Monk — famous for other work, one quartet each), while prominence
  // names Kats-Chernin and Vrebalov, who wrote 25 and 18 of them. Neither is wrong; only one is
  // about this chart. Against the full roster it recovers eight of the thirteen curated names,
  // including the prolific end (Cambini, Ellerton, Krommer) that readership is blind to.
  let prom = new Map();
  // Below this a "prominent" dot is a data hole rather than a composer: Fernand de la Tombelle
  // sits at 1 quartet and 1 view/month because he is the one row with no Wikidata item at all,
  // and he outranks Shostakovich on distance alone. He is still drawn, and still selectable — he
  // just cannot win a label on the strength of a number nobody has.
  const MIN_VIEWS = 5;

  function scoreProminence() {
    prom = new Map();
    const vis = rows.filter(d => plottable(d) && d.views > 0 && (!visible || visible.has(d.i)));
    if (vis.length < 2) return;
    const lq = vis.map(d => Math.log10(d.quartets)), lv = vis.map(d => Math.log10(d.views));
    const mean = a => a.reduce((t, v) => t + v, 0) / a.length;
    const sd = (a, m) => Math.sqrt(mean(a.map(v => (v - m) * (v - m)))) || 1;
    const mq = mean(lq), mv = mean(lv), sq = sd(lq, mq), sv = sd(lv, mv);
    for (const d of vis) {
      if (d.views < MIN_VIEWS) continue;
      prom.set(d.i, Math.hypot((Math.log10(d.quartets) - mq) / sq, (Math.log10(d.views) - mv) / sv));
    }
  }

  // ---- geometry -----------------------------------------------------------
  function measure() {
    const box = el.getBoundingClientRect();
    const full = document.body.classList.contains("fs");
    const cw = Math.max(240, Math.round(box.width));
    // The swarm is naturally short — it only needs the height its collisions demand — so giving
    // it the scatter's aspect ratio leaves a third of the panel empty above and below the blob.
    // A portrait phone gets a TALLER scatter (0.8): the same 0.6 that reads well on a laptop
    // squeezes 466 dots into ~200px there and the log bands merge into stripes.
    const narrow = cw < 560;
    // The readers view is a square-ish cloud over five decades of y and two of x, so it wants a
    // taller box than the timeline, which is naturally wide.
    const aspect = mode === "swarm" ? (narrow ? 0.58 : 0.44)
                 : mode === "readers" ? (narrow ? 0.98 : 0.62)
                 : (narrow ? 0.82 : 0.6);
    // The full-screen floor is 120, not the 240 the windowed branch can afford. In full screen the
    // SVG is height:100% of its box, so a viewBox TALLER than the box does not scroll or crop — it
    // LETTERBOXES, scaling the whole chart down, fonts included, and centring it in a band of
    // empty card. A phone in landscape is 390px tall and the plot box lands under 240, so the
    // floor meant to protect the chart was the thing shrinking it.
    const ch = full
      ? Math.max(120, Math.round(box.height))
      : Math.round(Math.max(260, Math.min(540, cw * aspect)));
    m.left = cw < 480 ? 38 : 46;
    m.bottom = cw < 480 ? 40 : 44;
    w = cw - m.left - m.right;
    h = ch - m.top - m.bottom;
    x0 = d3.scaleLinear().domain(X_DOMAIN).range([0, w]);
    y0 = d3.scaleLog().domain(Y_DOMAIN).range([h, 0]);
    qx = d3.scaleLog().domain(QX_DOMAIN).range([0, w]);
    vy = d3.scaleLog().domain(VY_DOMAIN).range([h, 0]);
    const maxViews = d3.max(rows, d => d.views) || 1;
    const rMax = Math.max(11, Math.min(26, w / 44));
    // Exponent 0.35, not the textbook 0.5: views span three orders of magnitude, and a true area
    // encoding collapses the entire middle of the distribution onto the minimum radius. This keeps
    // Mozart obviously large and the median composer still visibly a disc.
    rScale = d3.scalePow().exponent(0.35).domain([0, maxViews]).range([2.2, rMax]).clamp(true);
    return ch;
  }

  // Beeswarm: one force run, memoized on the inputs that can change it. 466 nodes x 220 ticks is
  // ~40ms — fine once, not fine on every zoom frame, hence the memo and hence why zoom in swarm
  // mode only rescales x (widening the axis can only REDUCE collisions, never create them).
  function ensureSwarm() {
    const key = w + "x" + h + ":" + rScale.range()[1];
    if (swarmY && swarmKey === key) return;
    const nodes = rows.filter(plottable).map(d => ({ d, x: x0(d.birth), y: h / 2 }));
    d3.forceSimulation(nodes)
      .force("x", d3.forceX(n => x0(n.d.birth)).strength(1))
      .force("y", d3.forceY(h / 2).strength(0.045))
      .force("collide", d3.forceCollide(n => rScale(n.d.views) + 1.1).iterations(3))
      .stop()
      .tick(220);
    swarmY = new Float64Array(rows.length);
    const pad = 4;
    nodes.forEach(n => { swarmY[n.d.i] = Math.max(pad, Math.min(h - pad, n.y)); });
    swarmKey = key;
  }

  // Circular fisheye — Mike Bostock's d3-plugins/fisheye, inlined (the plugin is d3 v3-only).
  // The 2014 chart used the *scale* variant on both axes at once; this is the circular one, which
  // is a lens over a fixed picture instead of a permanent warp of the coordinate system.
  function makeLens(radius, distortion) {
    const e = Math.exp(distortion), k0 = e / (e - 1) * radius, k1 = distortion / radius;
    return (px, py, fx, fy) => {
      const dx = px - fx, dy = py - fy, dd = Math.sqrt(dx * dx + dy * dy);
      if (!dd || dd >= radius) return { x: px, y: py, z: 1 };
      const k = k0 * (1 - Math.exp(-dd * k1)) / dd * 0.75 + 0.25;
      return { x: fx + dx * k, y: fy + dy * k, z: Math.min(k, 6) };
    };
  }

  function lensRadius() { return Math.min(w, h) * 0.34; }

  const vfmt = n => (n >= 1000 ? (n / 1000 >= 10 ? Math.round(n / 1000) : n / 1000) + "k"
                               : String(n));

  // Trim a segment to the plot box (Liang-Barsky). Returns null when it misses entirely.
  function trim(a, b) {
    let t0 = 0, t1 = 1;
    const dx = b.x - a.x, dy = b.y - a.y;
    for (const [p, q] of [[-dx, a.x], [dx, w - a.x], [-dy, a.y], [dy, h - a.y]]) {
      if (p === 0) { if (q < 0) return null; continue; }
      const r = q / p;
      if (p < 0) { if (r > t1) return null; if (r > t0) t0 = r; }
      else { if (r < t0) return null; if (r < t1) t1 = r; }
    }
    return { a: { x: a.x + t0 * dx, y: a.y + t0 * dy },
             b: { x: a.x + t1 * dx, y: a.y + t1 * dy } };
  }

  // Screen positions for the current mode + transform. One function, three modes — everything
  // downstream (dots, labels, Delaunay hit-testing, the selection ring) reads only this.
  function layout() {
    const tx = transform.rescaleX(x0);
    const out = new Array(rows.length);
    if (mode === "readers") {
      // Size is FREE here: readership is the y axis, so a radius that repeated it would double-
      // encode one variable and spend the only channel left. Emphasis carries the argument
      // instead. A composer with no page-view figure has no y at all, so park them off-frame and
      // let inFrame() drop them from the paint, the hit test and the labels.
      const rx = transform.rescaleX(qx), ry = transform.rescaleY(vy);
      const base = Math.max(3.2, Math.min(5, w / 190));
      for (const d of rows) {
        out[d.i] = (d.quartets == null || d.views == null)
          ? { x: -9e9, y: -9e9, r: 0 }
          : { x: rx(d.quartets * d.jq), y: ry(Math.max(1, d.views)),
              r: named(d.i) ? base * 1.65 : base };
      }
    } else if (mode === "swarm") {
      ensureSwarm();
      for (const d of rows) out[d.i] = { x: tx(d.birth + d.jx), y: swarmY[d.i], r: rScale(d.views) };
    } else if (mode === "lens" && lens) {
      const f = makeLens(lensRadius(), 2.2);
      for (const d of rows) {
        const p = f(x0(d.birth + d.jx), y0((d.quartets || 1) * d.jy), lens.x, lens.y);
        out[d.i] = { x: p.x, y: p.y, r: rScale(d.views) * Math.max(1, Math.min(p.z, 2.6)) };
      }
    } else if (mode === "lens") {
      for (const d of rows) out[d.i] = { x: x0(d.birth + d.jx), y: y0((d.quartets || 1) * d.jy), r: rScale(d.views) };
    } else {
      const ty = transform.rescaleY(y0);
      for (const d of rows) out[d.i] = { x: tx(d.birth + d.jx), y: ty((d.quartets || 1) * d.jy), r: rScale(d.views) };
    }
    return out;
  }

  // A composer whose quartet count the list page never states cannot be placed on a log axis at
  // all. Those rows stay in the TABLE — they are real composers — but are absent from the chart,
  // its hit-testing and its labels. Everything downstream reads plottability from here.
  const plottable = d => d.quartets != null;
  const isCanon = i => canonSet.has(i);
  const named = i => namedSet.has(i);
  const isVisible = d => plottable(d) && (!visible || visible.has(d.i));
  // On screen for real: a zoom pans dots clean out of the plot, and one whose centre has left it
  // must not be painted, hit-tested or labelled. Reads the CURRENT layout, so it is only valid
  // after layout() has run.
  const inFrame = p => p.x >= 0 && p.x <= w && p.y >= 0 && p.y <= h;

  // ---- labels -------------------------------------------------------------
  // Greedy, most-viewed first, first-come-first-served on space. This is what makes the STATIC
  // view worth looking at: with no interaction the chart already says "Haydn, Boccherini, Cambini,
  // Beethoven". Width is estimated rather than measured — a getBBox() per candidate would force
  // ~30 synchronous layouts per frame during a zoom, and being 10% off just costs a little
  // whitespace. The selected composer is placed FIRST so it never loses its label to a rival.
  function pickLabels(p, diag) {
    // Full screen earns more labels, but not proportionally more: a phone in full screen is TALL
    // and narrow, and 40+ names there collide with dots even when they miss each other.
    const full = document.body.classList.contains("fs");
    const base = full ? (w < 560 ? 20 : 42) : Math.max(4, Math.round(w / 62));
    // THE BUDGET GROWS WITH THE ZOOM. Pinching in is a request for detail, and answering it with
    // the same names larger is what made the zoom decorative. Log, not linear: a 24x zoom earns
    // about five times the names, not twenty-four times, and the greedy placer still has to find
    // room for each one.
    let cap = Math.round(base * (1 + Math.log2(Math.max(1, transform.k))));
    // AT FIRST SIGHT the readers view says exactly what it is about: the thirteen curated names,
    // and nothing else. That set is a judgment no single ranking reproduces — the best one
    // recovers eight of them — so it stays as the SEED rather than being derived away, and this
    // one case pins the budget to it so the resting picture is what it always was.
    //
    // Every other state fills the budget from the seed and then by prominence: zoomed in, where
    // the space is real and the reader has asked for detail, and filtered, where the seed is
    // mostly gone — every one of the thirteen is a man, so "Women" used to leave 219 emphasised
    // dots with no name on any of them, answering "where are they" while refusing to say "who".
    const seeds = canonIdx.concat(outlierIdx).map(i => rows[i]).filter(isVisible);
    const first = mode === "readers" && !visible && transform.k === 1;
    if (first) cap = seeds.length;
    const cands = mode === "readers"
      ? seeds.concat(first ? []
          : rows.filter(d => isVisible(d) && !named(d.i) && prom.has(d.i))
                .sort((a, b) => prom.get(b.i) - prom.get(a.i)))
      : rows.filter(isVisible).sort((a, b) => b.views - a.views);
    // The selected composer is placed FIRST so it never loses its label to a rival -- but it is
    // only in `cands` if it was a candidate. In the readers view the list is the 13 named, so
    // pinning any of the other 777 gave indexOf === -1, and splice(-1, 1) deletes the LAST
    // element: Ravel silently lost his label every time you clicked an unnamed dot.
    if (selected != null && rows[selected] && isVisible(rows[selected])) {
      const at = cands.indexOf(rows[selected]);
      if (at >= 0) cands.splice(at, 1);
      cands.unshift(rows[selected]);
    }
    const placed = [], boxes = [];
    // The diagonal captions are drawn in the grid layer, so they were never candidates and nothing
    // kept a name off them: "Florence Price" printed straight through "10k readers per quartet".
    // Rare before, because the thirteen sit in open space — systematic the moment a filter puts
    // ten names in the crowded left band, which is where those captions start. Same width estimate
    // the names use, one font size down (9.5 vs 10.5).
    for (const d of (diag || [])) {
      boxes.push({ x: d.a.x + 2, y: d.a.y - 16, w: d.label.length * 5 + 6, h: 13 });
    }
    for (const d of cands) {
      if (placed.length >= cap) break;
      const q = p[d.i];
      // A dot the zoom has pushed off the plot must not keep its label: the label box can still
      // land inside the frame while the dot it names is outside it, which prints a name pointing
      // at nothing.
      if (!inFrame(q)) continue;
      const tw = d.name.length * 5.5 + 6, th = 12;
      // Above, then below, then beside. "Above" alone silently dropped exactly the composers the
      // chart is about: Mozart sits 2.6% from the top of the readers view, Cambini hard against
      // the right edge, Debussy and Gershwin against the left — every one of them had a dot and
      // no room over it, so the name went missing from the argument it was making.
      const spots = [[q.x - tw / 2, q.y - q.r - 4 - th],
                     [q.x - tw / 2, q.y + q.r + 4],
                     [q.x + q.r + 5, q.y - th / 2],
                     [q.x - q.r - 5 - tw, q.y - th / 2]];
      let put = null;
      for (const [bx, by] of spots) {
        if (bx < 0 || bx + tw > w || by < 0 || by + th > h) continue;
        if (boxes.some(o => bx < o.x + o.w && bx + tw > o.x && by < o.y + o.h && by + th > o.y)) continue;
        put = { bx, by }; break;
      }
      if (!put) continue;
      boxes.push({ x: put.bx - 2, y: put.by - 1, w: tw + 4, h: th + 2 });
      placed.push({ d, x: put.bx + tw / 2, y: put.by + th - 2 });
    }
    return placed;
  }

  // ---- render -------------------------------------------------------------
  function build() {
    d3.select(el).selectAll("svg").remove();
    svg = d3.select(el).append("svg").attr("role", "img");
    // Everything that MOVES under a zoom is clipped to the plot rectangle. Without this a pinch
    // pushed dots and their labels out into the margins, over the axis ticks and the y-axis title,
    // where they read as stray ink belonging to no chart. (styles.css also stops the <svg> itself
    // from overflowing, but that only catches what escapes the whole frame — the margins are
    // inside it.) The axes and the grid are drawn from the CURRENT transform's ticks, so they are
    // inside the box by construction and are left unclipped.
    svg.append("defs").append("clipPath").attr("id", "plot-clip").append("rect").attr("class", "clip");
    gPlot = svg.append("g");
    gPlot.append("rect").attr("class", "bg");
    gGrid = gPlot.append("g");
    gLens = gPlot.append("circle").attr("fill", "none").attr("pointer-events", "none")
      .attr("clip-path", "url(#plot-clip)").style("display", "none");
    gDots = gPlot.append("g").attr("clip-path", "url(#plot-clip)");
    gSel = gPlot.append("g").attr("pointer-events", "none").attr("clip-path", "url(#plot-clip)");
    // The axes are drawn AFTER the dots so their tick labels stay readable under the half-dot
    // that legitimately overhangs the frame (see the clip note in draw()).
    gAxY = gPlot.append("g");
    gAxX = gPlot.append("g");
    gLabels = gPlot.append("g").attr("pointer-events", "none").attr("clip-path", "url(#plot-clip)");

    zoom = d3.zoom().scaleExtent([1, 24])
      .on("zoom", ev => { transform = ev.transform; draw(); cbZoom && cbZoom(zoomed()); });
    bindPointer();
  }

  function applyZoomBehavior() {
    if (!svg) return;
    svg.on(".zoom", null);
    if (mode === "lens") { transform = d3.zoomIdentity; return; }
    zoom.extent([[0, 0], [w, h]]).translateExtent([[0, 0], [w, h]]);
    svg.call(zoom).call(zoom.transform, transform);
  }

  function draw() {
    pos = layout();
    const vis = rows.filter(isVisible);

    svg.attr("viewBox", `0 0 ${w + m.left + m.right} ${h + m.top + m.bottom}`)
       .attr("width", w + m.left + m.right).attr("height", h + m.top + m.bottom)
       .attr("aria-label", ariaLabel());
    gPlot.attr("transform", `translate(${m.left},${m.top})`);
    gPlot.select("rect.bg").attr("width", w).attr("height", h).attr("fill", C.plot).attr("rx", 4);
    // The clip lives in <defs> but is referenced from inside gPlot, so it is measured in gPlot's
    // (translated) coordinate system — the same one the dots are placed in.
    //
    // It is inset OUTWARD by one maximum radius rather than drawn on the frame. A dot sits on its
    // value, not inside it: Y_DOMAIN starts at 0.85, so a one-quartet composer's centre is ~1.3%
    // of h above the bottom edge and a tight clip sliced Gershwin, Debussy and Ravel flat where
    // they were never displaced by anything. Strays are handled by the frame test below instead,
    // which is the right test anyway — a dot belongs on screen when its CENTRE is on screen.
    const over = rScale.range()[1];
    svg.select("clipPath rect.clip")
       .attr("x", -over).attr("y", -over).attr("width", w + over * 2).attr("height", h + over * 2);

    // axes ---------------------------------------------------------------
    const readers = mode === "readers";
    const tx = readers ? transform.rescaleX(qx) : transform.rescaleX(x0);
    const ty = readers ? transform.rescaleY(vy)
             : mode === "scatter" ? transform.rescaleY(y0) : y0;
    const inDom = (sc, v) => v >= sc.domain()[0] && v <= sc.domain()[1];
    const xTicks = readers ? QX_TICKS.filter(v => inDom(tx, v))
                           : tx.ticks(Math.max(3, Math.round(w / 90)));
    const yTicks = readers ? VY_TICKS.filter(v => inDom(ty, v))
                           : Y_TICKS.filter(v => inDom(ty, v));

    const gx = gGrid.selectAll("line.gx").data(xTicks, String);
    gx.exit().remove();
    gx.enter().append("line").attr("class", "gx").merge(gx)
      .attr("x1", tx).attr("x2", tx).attr("y1", 0).attr("y2", h)
      .attr("stroke", C.grid).attr("stroke-width", 1);
    const gy = gGrid.selectAll("line.gy").data(mode === "swarm" ? [] : yTicks, String);
    gy.exit().remove();
    gy.enter().append("line").attr("class", "gy").merge(gy)
      .attr("y1", ty).attr("y2", ty).attr("x1", 0).attr("x2", w)
      .attr("stroke", C.grid).attr("stroke-width", 1);

    // The readers-per-quartet diagonals. Both axes are log, so v = ratio x q is a straight line
    // on screen and two endpoints define it -- but those endpoints are usually far outside the
    // box, so each is trimmed to the plot rather than drawn and clipped: gGrid is not clipped,
    // and the label has to sit where the line actually ENTERS the picture.
    const diag = [];
    if (readers) {
      for (const k of RATIOS) {
        const [q1, q2] = tx.domain();
        const seg = trim({ x: tx(q1), y: ty(k * q1) }, { x: tx(q2), y: ty(k * q2) });
        // The caption is built here rather than in the .text() call because pickLabels has to
        // MEASURE it: these sit in the grid layer, are not label candidates, and so were invisible
        // to the collision pass that keeps names off each other.
        if (seg) diag.push({ k, ...seg, label: w < 560 ? `${vfmt(k)}/quartet`
                                                       : `${vfmt(k)} reader${k === 1 ? "" : "s"} per quartet` });
      }
    }
    const dg = gGrid.selectAll("line.dg").data(diag, d => d.k);
    dg.exit().remove();
    dg.enter().append("line").attr("class", "dg").merge(dg)
      .attr("x1", d => d.a.x).attr("y1", d => d.a.y).attr("x2", d => d.b.x).attr("y2", d => d.b.y)
      .attr("stroke", C.grid).attr("stroke-width", 1);
    const dl = gGrid.selectAll("text.dl").data(diag, d => d.k);
    dl.exit().remove();
    dl.enter().append("text").attr("class", "dl").attr("font-size", 9.5).merge(dl)
      .attr("x", d => d.a.x + 4).attr("y", d => d.a.y - 5)
      .attr("text-anchor", "start").attr("fill", C.axis).attr("opacity", 0.9)
      .text(d => d.label);

    const lx = gAxX.selectAll("text").data(xTicks, String);
    lx.exit().remove();
    lx.enter().append("text").attr("text-anchor", "middle").attr("font-size", 11).merge(lx)
      .attr("x", tx).attr("y", h + 15).attr("fill", C.axis)
      .text(readers ? String : d3.format("d"));
    // The title sits on its own line BELOW the ticks. Sharing their baseline put it on top of the
    // rightmost tick label at almost every width — the axis ends where the plot ends, so there is
    // never spare room out there.
    gAxX.selectAll("text.ttl").remove();
    gAxX.append("text").attr("class", "ttl").attr("x", w).attr("y", h + 33)
      .attr("text-anchor", "end").attr("font-size", 11).attr("font-weight", 600)
      .attr("fill", C.muted).text(readers ? "quartets written →" : "birth year →");

    const ly = gAxY.selectAll("text").data(mode === "swarm" ? [] : yTicks, String);
    ly.exit().remove();
    ly.enter().append("text").attr("text-anchor", "end").attr("font-size", 11).merge(ly)
      .attr("x", -7).attr("y", d => ty(d) + 4).attr("fill", C.axis)
      .text(readers ? vfmt : String);
    // Horizontal, ABOVE the plot rather than rotated beside it. Rotated it has to live inside
    // m.left, which on a phone is only wide enough for the tick labels — the two overlapped and
    // "100" rendered as "00". Above the plot it also just reads better at any width.
    gAxY.selectAll("text.ttl").remove();
    if (mode !== "swarm") {
      gAxY.append("text").attr("class", "ttl")
        .attr("x", -m.left + 4).attr("y", -8).attr("text-anchor", "start")
        .attr("font-size", 11).attr("font-weight", 600).attr("fill", C.muted)
        .text(readers ? "↑ English Wikipedia readers / month"
                      : "↑ quartets written (log scale)");
    }

    // dots ---------------------------------------------------------------
    // EVERY row is drawn, not just the visible ones: a search dims the rest to 12% rather than
    // deleting them, so "the three Haydns" still reads as three dots in a field of 466 instead of
    // three dots floating in an empty box. Only hit-testing and labels honor the filter.
    // Sorted big-behind-small so a large famous disc never buries a small one it fully covers.
    const order = rows.filter(plottable).sort((a, b) => b.views - a.views);
    const sel = gDots.selectAll("circle.dot").data(order, d => d.i);
    sel.exit().remove();
    sel.enter().append("circle").attr("class", "dot").attr("stroke-width", 1)
      .merge(sel)
      .attr("cx", d => pos[d.i].x).attr("cy", d => pos[d.i].y).attr("r", d => pos[d.i].r)
      .attr("fill", fillOf).attr("stroke", strokeOf)
      .attr("stroke-width", widthOf)
      // 0.07, not the 0.12 that read fine at 466 dots: at 884 the filtered-out mass is most of
      // the ink, and the readership brush exists precisely to get it out of the way. Still drawn
      // rather than removed, so you can see WHERE in the field the survivors sit.
      .attr("opacity", opacityOf)
      .attr("display", d => (inFrame(pos[d.i]) ? null : "none"));

    // selection ring + labels ---------------------------------------------
    gSel.selectAll("*").remove();
    const cur = selected != null && rows[selected] && isVisible(rows[selected])
             && inFrame(pos[selected]) ? rows[selected] : null;
    if (cur) {
      gSel.append("circle").attr("class", "sel-ring")
        .attr("cx", pos[cur.i].x).attr("cy", pos[cur.i].y).attr("r", pos[cur.i].r + 5)
        .attr("fill", "none").attr("stroke", C.sel).attr("stroke-width", 2.2);
    }

    const labs = pickLabels(pos, diag);
    const lb = gLabels.selectAll("text").data(labs, d => d.d.i);
    lb.exit().remove();
    lb.enter().append("text")
      .attr("text-anchor", "middle").attr("font-size", 10.5).attr("paint-order", "stroke")
      .attr("stroke-width", 3).attr("stroke-linejoin", "round")
      .merge(lb)
      .attr("x", d => d.x).attr("y", d => d.y)
      .attr("stroke", C.plot)
      .attr("fill", d => (cur && d.d.i === cur.i ? C.sel : labelColorOf(d.d)))
      .attr("font-weight", d => (cur && d.d.i === cur.i ? 700 : 500))
      .text(d => d.d.name);

    gLens.attr("class", "lens-edge")
      .style("display", mode === "lens" && lens ? null : "none")
      .attr("cx", lens ? lens.x : 0).attr("cy", lens ? lens.y : 0).attr("r", lensRadius())
      .attr("stroke", C.grid).attr("stroke-dasharray", "3 4");

    // Hit-test index over the CURRENT screen positions and the CURRENT visible subset — this is
    // what makes the whole canvas a tap target instead of the 2.2px discs. Rebuilt every draw;
    // Delaunay.from on 466 points is well under a millisecond.
    idx = vis.filter(d => inFrame(pos[d.i])).map(d => d.i);
    delaunay = idx.length > 1 ? d3.Delaunay.from(idx, i => pos[i].x, i => pos[i].y) : null;
  }

  function ariaLabel() {
    const n = (visible ? visible.size : rows.length);
    const axes = mode === "readers"
      ? "by number of quartets written and monthly English Wikipedia readers"
      : mode === "swarm" ? "by birth year, spread apart so none overlap"
      : "by birth year and number of quartets written";
    return `Scatter plot of ${n} string quartet composers ${axes}. `
         + `The table below the chart carries the same data in a readable form.`;
  }

  // ---- interaction --------------------------------------------------------
  // The touch double-fire (a tap synthesizes mouseover AND click) is designed out rather than
  // worked around: there is no hover bubble to fire. A tap goes straight to the persistent detail
  // panel; on a real pointer, hovering PREVIEWS into that same panel and clicking pins it.
  function nearest(mx, my) {
    if (!delaunay) return null;
    const k = delaunay.find(mx, my);
    if (k == null) return null;
    const i = idx[k], p = pos[i];
    const d = Math.hypot(p.x - mx, p.y - my);
    return d <= Math.max(p.r + 18, 42) ? i : null;
  }

  function local(ev) {
    const p = d3.pointer(ev, gPlot.node());
    return { x: p[0], y: p[1] };
  }

  function bindPointer() {
    let down = null, moved = false;

    svg.on("pointerdown", ev => { down = local(ev); moved = false; });
    svg.on("pointermove", ev => {
      const p = local(ev);
      if (down && Math.hypot(p.x - down.x, p.y - down.y) > 8) moved = true;
      if (mode === "lens" && (!TOUCH || down)) {          // on touch the lens is dragged, not followed
        lens = (p.x >= -40 && p.x <= w + 40 && p.y >= -40 && p.y <= h + 40) ? p : null;
        draw();
      }
      if (TOUCH) return;
      const i = nearest(p.x, p.y);
      if (i !== hovered) { hovered = i; showFlag(i, p); cbHover && cbHover(i); }
      else if (i != null) showFlag(i, p);
    });
    svg.on("pointerleave", () => {
      if (mode === "lens" && !TOUCH) { lens = null; draw(); }
      if (TOUCH) return;
      hovered = null; showFlag(null); cbHover && cbHover(null);
    });
    svg.on("pointerup", ev => {
      const p = local(ev);
      const wasTap = !moved;
      down = null;
      if (!wasTap) return;                                 // a pan/pinch is not a selection
      const i = nearest(p.x, p.y);
      cbSelect && cbSelect(i, false);
      if (TOUCH && mode === "lens") { lens = p; draw(); }
    });
    svg.on("pointercancel", () => { down = null; });
  }

  function showFlag(i, p) {
    if (!flagEl) return;
    if (i == null) { flagEl.classList.remove("on"); return; }
    const d = rows[i];
    flagEl.innerHTML = "";
    flagEl.appendChild(document.createTextNode(d.name));
    const s = document.createElement("small");
    s.textContent = `${d.quartets} quartet${d.quartets === 1 ? "" : "s"} · b. ${d.birth}`;
    flagEl.appendChild(s);
    flagEl.style.left = (pos[i].x + m.left) + "px";
    flagEl.style.top = (pos[i].y + m.top) + "px";
    flagEl.classList.add("on");
  }

  // ---- public -------------------------------------------------------------
  // Guarded because the ResizeObserver watches the very element the <svg> sizes: without the
  // early-out, a redraw that changes the SVG's height re-fires the observer, which redraws again.
  function resize() {
    if (!svg) return;
    const pw = w, ph = h;
    measure();
    if (w === pw && h === ph) return;
    swarmY = null;
    applyZoomBehavior();
    draw();
  }
  function rerender() { readColors(); if (svg) draw(); }

  function init(opts) {
    el = opts.el; flagEl = opts.flag;
    cbHover = opts.onHover; cbSelect = opts.onSelect; cbZoom = opts.onZoom;
    readColors(); measure(); build(); applyZoomBehavior(); draw();
  }

  function setMode(mNew) {
    if (mNew === mode) return;
    mode = mNew; lens = null; transform = d3.zoomIdentity;
    measure(); applyZoomBehavior(); draw();
  }

  function setFilter(set) { visible = set; scoreProminence(); draw(); }
  function setSelected(i) { selected = i; draw(); }
  function resetZoom() { if (mode === "lens") { lens = null; draw(); return; } svg.transition().duration(400).call(zoom.transform, d3.zoomIdentity); }
  function zoomed() { return mode !== "lens" && transform.k !== 1; }
  function getMode() { return mode; }

  const HINTS = {
    readers: "Across is how many quartets a composer wrote; up is how much their English Wikipedia "
           + "article is read. The diagonals are readers per quartet, so how far a dot sits ABOVE "
           + "one is the whole point: Mozart and Beethoven are read about ten thousand times a "
           + "month per quartet they wrote, Cambini about once. Drag to pan, scroll or pinch to "
           + "zoom, tap a dot for the rest.",
    scatter: "Fixed axes. Drag to pan, scroll or pinch to zoom, tap or click a dot to pin it. Ties are nudged by up to half a year so overlapping composers stay separately clickable.",
    swarm: "Composers pushed apart until nothing overlaps. Vertical position means nothing here — the quartet count is dropped, and size (views) and color (lifespan) are unchanged. Read it as a timeline of how crowded each generation was. Drag or pinch to spread it further.",
    lens: "A circular magnifier over a fixed chart: the axes never move. Move the pointer (or drag on a touch screen) to aim it; tap to pin a composer.",
  };
  function hint() { return HINTS[mode]; }

  return { init, setData, setMode, getMode, setFilter, setSelected, resize, rerender,
           defaultMode: () => DEFAULT_MODE,
           // Empty unless a pipeline run renamed one of the composers the readers view argues
           // about; the UI suite asserts it, so a rename fails loudly instead of dropping a dot.
           missingNames: () => missing.slice(),
           // The curated thirteen, for the suite: the resting readers view must show these and
           // only these, and a zoom must show something else.
           seedNames: () => CANON.concat(OUTLIERS),
           resetZoom, zoomed, colorOf, hint,
           lifeDomain: () => LIFE_DOMAIN.slice(),
           // How many dots the readers view actually emphasises, and how many it can place at
           // all (it needs a view count as well as a quartet count). The legend used to hardcode
           // 13 and subtract it from plotted(), which is a different denominator.
           namedCount: () => namedSet.size,
           readersPlotted: () => rows.filter(d => d.quartets != null && d.views != null).length,
           // How many rows the chart can actually place — the table shows more (see isVisible).
           plotted: () => rows.filter(plottable).length,
           // So the legend can draw its size key at the radii the chart ACTUALLY uses, rather
           // than three hand-picked circles that quietly stop matching when the scale changes.
           radiusOf: v => (rScale ? rScale(v) : 0) };
})();
