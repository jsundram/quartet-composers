// The chart: four ways to read one roster of dots (fame, scatter, swarm, lens — README says what
// each is for), sharing one layout + hit-test core.
//
// Two things shared by all four, and most of the value: hit-testing via a Delaunay over the CURRENT
// screen positions, so a dot's tap target is its whole Voronoi cell rather than its radius — on a
// phone, the difference between usable and not — and greedy collision-avoided labels, so the chart
// says something with no interaction at all.
//
// Colors are read INTO JS here (Theme.getCssColor), so a theme flip cannot reach them via CSS: app.js
// calls rerender() on every theme change and this file re-reads them (invariant 3).

window.Chart = (function () {
  const TOUCH = !matchMedia("(hover: hover) and (pointer: fine)").matches;

  // From the data, over the PLOTTABLE rows only: including the roster's earliest births spent a third of
  // the width where the chart can never draw a dot. Snapped to a 50-year grid so the ticks stay round,
  // and make-og-svg.py derives it the same way (invariant 14).
  let X_DOMAIN = [1700, 2000];
  const Y_DOMAIN = [0.85, 170];         // log, with headroom over the largest stated count
  const Y_TICKS = [1, 2, 3, 5, 10, 20, 30, 50, 100];
  // FIXED stops: the middle one used to be the median recomputed from the data, so the same composer
  // changed colour when somebody else joined the list.
  const LIFE_DOMAIN = [20, 62, 104];

  // ---- the Fame view -------------------------------------------------------
  // Output ACROSS, attention UP, so readers-per-quartet is a diagonal and the distance above one is
  // the argument. The other views ask "when, and how much"; this one asks "and did it land".
  const QX_DOMAIN = [0.85, 200];        // quartets written, with the same headroom
  const QX_TICKS = [1, 2, 3, 5, 10, 20, 30, 50, 100];
  // A FIXED floor: a readership this low is not worth resolving, and a fixed one does not move when
  // the roster does (issue 38).
  const VY_DOMAIN = [10, 260000];       // readers/mo
  const FUZZ = 1e-6;                    // px, for comparisons against a rescaled edge
  const VY_TICKS = [1, 10, 100, 1000, 10000, 100000];
  const RATIOS = [1, 10, 100, 1000, 10000];   // the readers-per-quartet diagonals

  // THE REPERTOIRE: the composers a quartet actually plays, in birth order, and the only hardcoded
  // composer NAMES here (invariant 7). Deliberately NOT a count -- it was "the seven" until three more
  // joined, and every place that printed the number went stale in the same commit. Debussy is on it for
  // one quartet: the claim is that the quartets are PLAYED, not that the composer wrote many.
  const CANON = ["Franz Xaver Richter", "Joseph Haydn", "Luigi Boccherini",
                 "Wolfgang Amadeus Mozart", "Ludwig van Beethoven",
                 "Pyotr Ilyich Tchaikovsky", "Claude Debussy", "Béla Bartók",
                 "Sergei Prokofiev", "Dmitri Shostakovich"];
  const OUTLIERS = ["Giuseppe Cambini", "Franz Krommer", "John Lodge Ellerton"];

  // A SECOND repertoire, in birth order, shown only under the Women filter (#7): every name in CANON is
  // a man, so that group was filled with nothing at all. Hand-written for the same reason CANON is, and
  // GATED to the filter because none of them is read near CANON's scale — at rest they would be filled
  // dots low in the densest part of the cloud under a key that holds Mozart. Keyed by the gender pill
  // VALUE, so this table and index.html's pills are one vocabulary (invariant 7).
  const WOMEN_CANON = ["Fanny Hensel", "Amy Beach", "Rebecca Clarke", "Florence Price",
                       "Elizabeth Maconchy", "Grażyna Bacewicz", "Sofia Gubaidulina",
                       "Elena Kats-Chernin", "Jennifer Higdon"];
  // The list and the sentence naming it are ONE editorial claim, so they live together (invariant 8).
  const REPERTOIRES = { female: { names: WOMEN_CANON, noun: "the notables" } };
  const DEFAULT_REPERTOIRE = { names: CANON, noun: "the notables" };
  let repertoire = DEFAULT_REPERTOIRE;
  // Sets, not arrays: isCanon/named run per DOT per FRAME from layout() and all four paint
  // functions, so an Array.includes scan in each is work a phone does not need during a pinch.
  let canonIdx = [], outlierIdx = [], canonSet = new Set(), namedSet = new Set(), missing = [];
  // What the view is RINGING right now. `named()` reads this and not `namedSet`, which stays the curated
  // set: that is what makes every channel following emphasis follow the filter with no further wiring.
  let ringIdx = [], emphOrder = [], emphSet = new Set();
  // name -> row index, kept from setData so a repertoire swap does not need the raw rows again.
  let at = new Map();
  const resolve = list => list.filter(n => at.has(n)).map(n => at.get(n));

  let el, flagEl, cbHover, cbSelect, cbZoom;
  // Fame is the DEFAULT because it is the view that makes the page's claim; the timeline is one tap
  // away and still the honest overview.
  const DEFAULT_MODE = "fame";
  let rows = [], mode = DEFAULT_MODE, visible = null, selected = null, hovered = null;
  let svg, gPlot, gDots, gLabels, gAxX, gAxY, gGrid, gLens, gSel;
  let w = 0, h = 0, m = { top: 22, right: 14, bottom: 32, left: 46 };
  // Extra room at the TOP, REQUESTED by whoever draws there rather than decided from a media query
  // here: the breakpoint belongs to the code doing the drawing, and a second copy would leave this file
  // reserving space for a control that had moved away. It has survived one move of it with no edit.
  let topReserve = 0;
  let x0, y0, qx, vy, rScale, colorScale, C = {};
  let transform = d3.zoomIdentity, zoom;
  let swarmY = null, swarmKey = "";      // memo: the sim is expensive, size/radius are its inputs
  let lens = null;                       // {x,y} focus in plot coords, or null
  let pos = [], idx = [], delaunay = null;

  // ---- data prep ----------------------------------------------------------
  // A deterministic offset per row, so ties separate without the picture changing between renders.
  // Ties are common, and an un-jittered scatter hides them completely: one dot is drawn over
  // another and the one underneath can never be hovered, tapped or counted by eye. Kept small — half
  // a year, inside the gap between adjacent integer counts — and disclosed in the hint.
  //
  function hash(s) {
    let a = 2166136261;
    for (let i = 0; i < s.length; i++) { a ^= s.charCodeAt(i); a = Math.imul(a, 16777619); }
    return ((a >>> 0) / 4294967295) * 2 - 1;     // -1..1
  }

  // RANKED, not hashed (#45). Fame has NO y jitter, so this offset is the only thing holding apart two
  // composers with the same count who are read about equally — and a hash, being an independent draw
  // per name, separates ties on AVERAGE and not in particular: Debussy and Gershwin drew 0.47px apart,
  // close enough that the Delaunay bisector ran through the visible disc and its right half selected
  // the composer you could not see. Ranking inside the stripe and walking frac(k·φ) pushes the dots
  // ADJACENT IN Y — the only ones that can collide — maximally apart in x instead; TODO.md has the
  // three-distance argument, and make-og-svg.py duplicates this (invariant 14). By readership then
  // NAME, never row order: build_data.py is free to reorder its rows.
  const PHI = (Math.sqrt(5) - 1) / 2;
  function spreadJq() {
    const stripes = new Map();
    // Only the rows Fame can place. A row with no readership has no y, so it is never drawn here
    // and must not consume a rank — that would push every dot above it along the sequence.
    for (const d of rows) {
      if (d.quartets == null || d.views == null) continue;
      if (!stripes.has(d.quartets)) stripes.set(d.quartets, []);
      stripes.get(d.quartets).push(d);
    }
    for (const grp of stripes.values()) {
      grp.sort((a, b) => a.views - b.views || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
      // Recentred on the stripe's own mean, because frac(0·φ) is 0: un-shifted, the first term is
      // the extreme of the range and every stripe leans left. A stripe of ONE then drew its lone dot
      // ~9.8% below its own count with no tie to break at all — Cambini's 149 quartets rendered at
      // 134, on a dot the view rings and labels. A constant shift leaves every consecutive-rank gap
      // untouched.
      const off = grp.map((_, k) => ((k * PHI) % 1) * 2 - 1);
      const mid = off.reduce((a, b) => a + b, 0) / off.length;
      grp.forEach((d, k) => { d.jq = Math.pow(10, (off[k] - mid) * 0.045); });
    }
  }

  // [name, birth, death, quartets, views, views_lo, views_hi, gender]; death, quartets and gender
  // may be null. This comment IS the schema for every positional read below — keep it in step with
  // build_data.py's `fields`, which validate.py pins. "living" is the ABSENCE of a death date on
  // Wikidata, a fact about today, not the 2014 dataset's inference from a field that overloaded
  // lifespan with age-in-2014.
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
        jq: 1,                                              // set by spreadJq, below
      };
    });
    spreadJq();
    at = new Map(rows.map(d => [d.name, d.i]));
    outlierIdx = resolve(OUTLIERS);
    applyRepertoire();
    // EVERY curated list, not just the active one, or a rename inside the unshown list sits unreported
    // until somebody presses the pill (invariant 7).
    missing = CANON.concat(OUTLIERS, WOMEN_CANON).filter(n => !at.has(n));
    if (missing.length) console.error("Chart: named composers missing from the data:", missing);

    const yrs = rows.filter(plottable).map(d => d.birth);
    if (yrs.length) {
      X_DOMAIN = [Math.floor((d3.min(yrs) - 8) / 50) * 50, Math.ceil((d3.max(yrs) + 8) / 50) * 50];
    }
    swarmY = null;
    restingT = null;
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

  // Living composers are NOT on the ramp: their final lifespan does not exist yet, and colouring a
  // 40-year-old as "died young" states something untrue. They get an open circle — a SHAPE
  // difference, which also survives colour-blindness and a black-and-white print.
  // The Fame view spends colour on the ARGUMENT instead of on lifespan: the repertoire filled in the
  // selection orange, the outliers ringed in the accent, the rest one recessive grey. Emphasis, not
  // hues — the point of the view is a handful of names against a field.
  function fillOf(d) {
    if (mode !== "fame") return d.living ? C.plot : colorScale(d.lifespan);
    return isCanon(d.i) ? C.sel : named(d.i) ? "none" : C.muted;
  }
  function strokeOf(d) {
    if (mode !== "fame") return d.living ? C.living : C.line;
    return isCanon(d.i) ? C.plot : named(d.i) ? C.accent : "none";
  }
  function widthOf(d) {
    if (mode !== "fame") return d.living ? 1.4 : 1;
    return isCanon(d.i) ? 1.6 : named(d.i) ? 2 : 0;
  }
  // A FILTER HERE IS A HIGHLIGHT, not a subtraction: nothing is removed, the rest drops to 0.07. So
  // the filtered-IN dots carry the answer, and at the resting 0.22 they could not — a fifth of the
  // roster at 0.22 against the rest at 0.07 is a difference you have to hunt for, in the one view
  // whose point is where a group sits against the field. Under a filter they come up to 0.55;
  // unfiltered, 0.22 is right, because then the recessive mass IS the field the named composers are
  // being read against.
  function opacityOf(d) {
    if (visible && !visible.has(d.i)) return 0.07;
    if (mode !== "fame") return 0.92;
    if (named(d.i)) return 1;
    return visible ? 0.55 : 0.22;
  }
  // Fame-only, both branches: --sel is the PINNED colour, so tinting the repertoire with it in
  // Timeline/Swarm/Lens made a handful of composers look pinned with nothing pinned, and made the
  // real pin unidentifiable once there was one.
  function labelColorOf(d) {
    if (mode !== "fame") return C.ink;
    return isCanon(d.i) ? C.sel : named(d.i) ? C.accent : C.ink;
  }
  // table.js paints its row chip with this, on the promise that a row and its dot are recognisably
  // the same thing — so it follows the CURRENT view's encoding rather than lifespan always. In Fame
  // that makes the named composers findable in the table by colour, and everyone else the same
  // recessive grey they are on the chart.
  function colorOf(d) {
    if (mode === "fame") return isCanon(d.i) ? C.sel : named(d.i) ? C.accent : C.muted;
    return d.living ? C.living : colorScale(d.lifespan);
  }

  // ---- label priority -----------------------------------------------------
  // PROMINENCE is z-scored distance from the centre of the VISIBLE cloud — z-scored because the axes
  // have different spreads and a rule that ignores that ranks whichever is wider, and recomputed per
  // filter so a group is ranked against ITSELF. That is why it beats readership here: filtered to the
  // women, readership names whoever has the largest ARTICLE (famous for other work, one quartet each)
  // while prominence finds the ones who wrote dozens.
  let prom = new Map();
  // Below this a "prominent" dot is a data hole rather than a composer: prominence is distance
  // from the centre, so an article with no real number ranks high on one it does not have. Still
  // drawn and still selectable — it just cannot win a LABEL.
  const MIN_VIEWS = 5;

  function scoreProminence() {
    prom = new Map();
    const vis = rows.filter(d => plottable(d) && d.views > 0 && (!visible || visible.has(d.i)));
    if (vis.length < 2) { refreshEmphasis(); return; }   // no ranking, so no derived rings either
    const lq = vis.map(d => Math.log10(d.quartets)), lv = vis.map(d => Math.log10(d.views));
    const mean = a => a.reduce((t, v) => t + v, 0) / a.length;
    const sd = (a, m) => Math.sqrt(mean(a.map(v => (v - m) * (v - m)))) || 1;
    const mq = mean(lq), mv = mean(lv), sq = sd(lq, mq), sv = sd(lv, mv);
    for (const d of vis) {
      if (d.views < MIN_VIEWS) continue;
      prom.set(d.i, Math.hypot((Math.log10(d.quartets) - mq) / sq, (Math.log10(d.views) - mv) / sv));
    }
    // The ring is ranked off `prom`, so it is refreshed here rather than by every caller — there
    // is exactly one place the visible set changes, and this is downstream of it.
    refreshEmphasis();
  }

  // THE RING FOLLOWS THE FILTER: "stands out from the crowd it is drawn in" is what it always meant,
  // and it was frozen to one crowd (#7). The budget IS the size of OUTLIERS, so "Men" derives nothing
  // and "Women" derives the lot.
  function applyRepertoire() {
    canonIdx = resolve(repertoire.names);
    canonSet = new Set(canonIdx);
    namedSet = new Set(canonIdx.concat(outlierIdx));
    emphOrder = canonIdx.concat(outlierIdx);
    emphSet = new Set(emphOrder);
  }

  // DERIVED, not a literal: the budget has to equal the curated set's size, or a filter carries more
  // emphasis than the resting view (fewer names here) or less (more). Two independent constants asked
  // a reader to keep them in step; this cannot drift.
  const RINGS = OUTLIERS.length;
  // A ring means "stands out from the crowd", so it needs a crowd: below this the filtered group IS the
  // picture and ringing the budget would point at almost everything.
  const MIN_FIELD = 20;
  // ...and it has to stand APART from every dot already emphasised and every ring derived before it.
  // In SCREEN space, because "on top of" is a claim about pixels; a FRACTION, so it means the same on a
  // phone as in full screen. Not delicate — 2.5% to 5% picks the same dots.
  const MIN_SEP = 0.03;
  //
  // The floor in DOTS is a guard, not a fix for anything observed: probed across eight viewports the
  // fraction alone still cleared the bar by 20px or more, and the violation seen on a phone came from
  // STALE GEOMETRY, fixed where it was caused in setMode/resize. Stated in dot radii to say what it
  // buys — a dot's width of daylight between the edges, which is what ui.test.mjs measures.
  const GAP_DOTS = 4;
  // ONE definition, shared with layout(): the separation floor is expressed in the radius of the
  // dot it is separating, so the two cannot drift.
  const NAMED_R = 1.65;
  const dotRadius = () => Math.max(3.2, Math.min(5, w / 190));
  function refreshEmphasis() {
    const kept = outlierIdx.filter(i => isVisible(rows[i]));
    const derived = [];
    if (visible && kept.length < RINGS) {
      const pool = rows.filter(d => isVisible(d) && !namedSet.has(d.i) && prom.has(d.i));
      // Only x and y: layout() derives the fame RADIUS from named(), which this function is in the
      // middle of changing, while x and y depend on nothing but the data and the mode.
      const ready = pool.length >= MIN_FIELD && w > 0 && h > 0 && !!qx && !!x0;
      if (ready) {
        const p = baseLayout();
        const near = i => !(p[i].r > 0) || !Number.isFinite(p[i].x);
        const gap = Math.max(MIN_SEP * Math.hypot(w, h), GAP_DOTS * dotRadius() * NAMED_R);
        const apart = (i, others) => others.every(j =>
          Math.hypot(p[i].x - p[j].x, p[i].y - p[j].y) >= gap);
        // Everything the reader can already see picked out, so a ring never lands on one.
        // Only the VISIBLE ones: a dimmed dot at 0.07 is not something a ring collides with.
        const taken = canonIdx.concat(kept).filter(i => isVisible(rows[i]) && !near(i));
        for (const d of pool.sort((a, b) => prom.get(b.i) - prom.get(a.i))) {
          if (derived.length >= RINGS - kept.length) break;
          if (near(d.i) || !apart(d.i, taken)) continue;
          derived.push(d.i); taken.push(d.i);
        }
      }
      // Fewer than the budget is the honest outcome when nothing else stands clear.
    }
    ringIdx = derived;
    // Curated first so the label placer still spends its budget on them before the derived ones.
    emphOrder = canonIdx.concat(outlierIdx, derived);
    emphSet = new Set(emphOrder);
  }

  // ---- geometry -----------------------------------------------------------
  function measure() {
    const box = el.getBoundingClientRect();
    const full = document.body.classList.contains("fs");
    const cw = Math.max(240, Math.round(box.width));
    // The swarm needs only the height its collisions demand, so the scatter's ratio leaves a third of the
    // panel empty around the blob; a portrait phone gets a TALLER scatter, because the laptop ratio
    // squeezes the cloud into ~200px and the log bands merge into stripes.
    const narrow = cw < 560;
    // Fame is a square-ish cloud over five decades of y and two of x, so it wants a taller box than
    // the timeline, which is naturally wide.
    const aspect = mode === "swarm" ? (narrow ? 0.58 : 0.44)
                 : mode === "fame" ? (narrow ? 0.98 : 0.62)
                 : (narrow ? 0.82 : 0.6);
    // The full-screen floor is 120, not the 240 the windowed branch can afford. In full screen the
    // SVG is height:100% of its box, so a viewBox TALLER than the box does not scroll or crop — it
    // LETTERBOXES, scaling the whole chart down, fonts included, and centring it in a band of
    // empty card. A phone in landscape is 390px tall and the plot box lands under 240, so the
    // floor meant to protect the chart was the thing shrinking it.
    const ch = full
      ? Math.max(120, Math.round(box.height))
      : Math.round(Math.max(260, Math.min(540, cw * aspect)));
    // The band absorbs the reservation rather than the card growing to fit it: ch is a function of
    // the aspect ratio, so the plot's outer box is exactly the height it was and the DATA area is
    // what gives up the pixels. Growing ch instead would spend a phone's first screen, which is the
    // thing moving these buttons onto the chart was buying back.
    m.top = Math.max(22, topReserve);
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
    // Exponent 0.35, not the textbook 0.5: readership spans orders of magnitude, and a true area
    // encoding collapses the whole middle of the distribution onto the minimum radius. This keeps the
    // top obviously large and the median composer still visibly a disc.
    rScale = d3.scalePow().exponent(0.35).domain([0, maxViews]).range([2.2, rMax]).clamp(true);
    return ch;
  }

  // Beeswarm: one force run, memoized on the inputs that can change it. The whole roster x 220 ticks
  // is ~40ms — fine once, not on every zoom frame. Hence the memo, and hence zoom in swarm mode
  // rescaling x only: widening the axis can only REDUCE collisions, never create them.
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
    if (mode === "fame") {
      // Size is FREE here: readership is the y axis, so a radius repeating it would double-encode one
      // variable and spend the only channel left. Emphasis carries the argument instead. A composer
      // with no page-view figure has no y, so park them off-frame and let inFrame() drop them from
      // the paint, the hit test and the labels.
      const rx = transform.rescaleX(qx), ry = transform.rescaleY(vy);
      const base = dotRadius();
      for (const d of rows) {
        out[d.i] = (d.quartets == null || d.views == null)
          ? { x: -9e9, y: -9e9, r: 0 }
          : { x: rx(d.quartets * d.jq), y: ry(Math.max(VY_DOMAIN[0], d.views)),
              r: named(d.i) ? base * NAMED_R : base };
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
  const named = i => emphSet.has(i);
  const isVisible = d => plottable(d) && (!visible || visible.has(d.i));
  // On screen for real: a zoom pans dots clean out of the plot, and one whose centre has left it
  // must not be painted, hit-tested or labelled. Reads the CURRENT layout, so it is only valid
  // after layout() has run.
  // Tolerant at the edges for the reason inDom() is: a dot sitting exactly ON the frame — a
  // composer pinned to the readership floor — comes back a fraction outside it once the transform
  // has been through a pixel inversion, and silently stops being painted, hit-tested and labelled.
  const inFrame = p => p.x >= -FUZZ && p.x <= w + FUZZ && p.y >= -FUZZ && p.y <= h + FUZZ;

  // ---- labels -------------------------------------------------------------
  // Greedy, most-viewed first, first-come-first-served on space — which is what makes the STATIC view
  // worth looking at. Width is ESTIMATED rather than measured: a getBBox() per candidate would force a
  // synchronous layout per candidate per frame during a zoom, and being 10% off costs whitespace.
  function pickLabels(p, diag) {
    // Full screen earns more labels, but not proportionally: a phone in full screen is TALL and
    // narrow, and a desktop-sized budget there collides with dots even where the names miss each
    // other.
    const full = document.body.classList.contains("fs");
    const base = full ? (w < 560 ? 20 : 42) : Math.max(4, Math.round(w / 62));
    // THE BUDGET GROWS WITH THE ZOOM. Pinching in is a request for detail, and answering it with
    // the same names larger is what made the zoom decorative. Log, not linear: a 24x zoom earns
    // about five times the names, not twenty-four times, and the greedy placer still has to find
    // room for each one.
    let cap = Math.round(base * (1 + Math.log2(Math.max(1, transform.k))));
    // AT REST the budget is pinned to the seed, so the view says exactly what it is about — and it is
    // the state make-og-svg.py draws (invariant 14). Every other state fills from the seed and then by
    // prominence: zoomed in, where the reader has asked for detail, and filtered, where the seed is
    // mostly gone — "Women" used to emphasise a fifth of the roster and name none of it, answering
    // "where are they" while refusing to say "who".
    const seeds = emphOrder.map(i => rows[i]).filter(isVisible);
    const first = mode === "fame" && !visible && transform.k === 1;
    if (first) cap = seeds.length;
    const cands = mode === "fame"
      ? seeds.concat(first ? []
          : rows.filter(d => isVisible(d) && !named(d.i) && prom.has(d.i))
                .sort((a, b) => prom.get(b.i) - prom.get(a.i)))
      : rows.filter(isVisible).sort((a, b) => b.views - a.views);
    // The selected composer is placed FIRST so it never loses its label to a rival -- but it is only
    // in `cands` if it was a candidate. At rest in Fame the list is the seeds alone, so pinning any
    // other dot gave indexOf === -1, and splice(-1, 1) deletes the LAST element: one seed silently
    // lost its label every time you clicked an unnamed dot.
    if (selected != null && rows[selected] && isVisible(rows[selected])) {
      const at = cands.indexOf(rows[selected]);
      if (at >= 0) cands.splice(at, 1);
      // A PIN IS A GUEST, not a replacement. At rest the budget is exactly the seed count, so
      // unshifting a non-seed spends a slot the seeds were promised and the last one placed loses its
      // name. Invisible while some seeds failed to fit anyway — the left-edge dots left slack in the
      // budget — and a real defect the moment the diagonal spots let them all place.
      else if (first) cap += 1;
      cands.unshift(rows[selected]);
    }
    const placed = [], boxes = [];
    // The diagonal captions are drawn in the grid layer, so they were never candidates and nothing
    // kept a name off them: a composer's name printed straight through "10k readers per quartet".
    // Rare while only the seeds were named, since those sit in open space — systematic the moment a
    // filter puts names in the crowded left band, where those captions start. Same width estimate the
    // names use, one font size down.
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
      const text = Names.short(d.name);
      const tw = text.length * 5.5 + 6, th = 12;
      // Above, then below, then beside, then the four diagonals. "Above" alone silently dropped
      // exactly the composers the chart is about, the ones at the edges of the cloud where the
      // argument is: a dot, no room over it, name gone. The diagonals answer the LEFT EDGE (#10) —
      // a dot at one quartet sits ~9px from the plot's side, so a centred box starts at a negative x
      // and only "beside, right" is on the plot at all, one slot for a whole column. Four corners cost
      // nothing (the loop breaks on the first fit) and are what let every seed place at rest.
      const spots = [[q.x - tw / 2, q.y - q.r - 4 - th],
                     [q.x - tw / 2, q.y + q.r + 4],
                     [q.x + q.r + 5, q.y - th / 2],
                     [q.x - q.r - 5 - tw, q.y - th / 2],
                     [q.x + q.r + 3, q.y - q.r - 3 - th],
                     [q.x + q.r + 3, q.y + q.r + 3],
                     [q.x - q.r - 3 - tw, q.y - q.r - 3 - th],
                     [q.x - q.r - 3 - tw, q.y + q.r + 3]];
      let put = null;
      for (const [bx, by] of spots) {
        if (bx < 0 || bx + tw > w || by < 0 || by + th > h) continue;
        if (boxes.some(o => bx < o.x + o.w && bx + tw > o.x && by < o.y + o.h && by + th > o.y)) continue;
        put = { bx, by }; break;
      }
      if (!put) continue;
      boxes.push({ x: put.bx - 2, y: put.by - 1, w: tw + 4, h: th + 2 });
      placed.push({ d, text, x: put.bx + tw / 2, y: put.by + th - 2 });
    }
    return placed;
  }

  // ---- fitting the frame to the filter ------------------------------------
  // Measured from a layout() at zoomIdentity rather than from the scales, so the box is in the same
  // geometry the dots are drawn in and a fourth encoding cannot forget to update this.
  function baseLayout() {
    const t = transform;
    transform = d3.zoomIdentity;
    const p = layout();
    transform = t;
    return p;
  }

  // Fewer kept dots than this and the frame does not move at all — see computeResting().
  const MIN_FIT = 4;

  // Where the chart RESTS for the current filter, which is what resetZoom() returns to and what
  // zoomed() is measured against. MEMOIZED because zoomed() is asked on every frame of a pinch, and
  // invalidated by the only three things it depends on: the filter, the mode and the box.
  let restingT = null;
  function restingTransform() {
    if (!restingT) restingT = computeResting();
    return restingT;
  }

  function computeResting() {
    if (mode === "lens" || !visible || !rows.length) return d3.zoomIdentity;
    const p = baseLayout();
    let x1 = Infinity, x2 = -Infinity, y1 = Infinity, y2 = -Infinity, rMaxSeen = 0, n = 0;
    for (const d of rows) {
      if (!isVisible(d)) continue;
      const q = p[d.i];
      // r === 0 is layout()'s park for a dot it cannot place at all (the Fame view has no y
      // for a composer with no view count), and it parks them at -9e9 — one of those in the box
      // would fit the frame to a point nine billion pixels off screen.
      if (!(q.r > 0) || !Number.isFinite(q.x) || !Number.isFinite(q.y)) continue;
      x1 = Math.min(x1, q.x); x2 = Math.max(x2, q.x);
      y1 = Math.min(y1, q.y); y2 = Math.max(y2, q.y);
      rMaxSeen = Math.max(rMaxSeen, q.r);
      n++;
    }
    if (x1 > x2) return d3.zoomIdentity;      // the filter kept nothing this chart can place
    // One match is a zero-width box, so fit() returns Infinity on both axes and k lands on the 24x
    // clamp. Counted from the dots this chart can PLACE, not from visible.size — a filter can keep rows
    // the Fame view has no y for. Skipping the fit means the FULL EXTENT rather than the reader's
    // current transform, because restingTransform() has to stay a pure function of the filter, the mode
    // and the box or the memo is meaningless. CLAUDE.md has the rest.
    if (n < MIN_FIT) return d3.zoomIdentity;
    // Pad by the largest dot so the discs at the edge are whole, plus a little air for a label.
    const pad = rMaxSeen + 10;
    const fit = (span, px) => (span > 0 ? (px - pad * 2) / span : Infinity);
    // The swarm's y is NOT under the zoom — its collisions are solved once at k=1 and only x is
    // rescaled (see ensureSwarm), so fitting it vertically computes a scale the dots then ignore.
    const k = Math.max(1, Math.min(24, mode === "swarm" ? fit(x2 - x1, w)
                                     : Math.min(fit(x2 - x1, w), fit(y2 - y1, h))));
    // Centre the box, then hold the frame inside the data the way translateExtent does for a drag:
    // panning past the edge of the domain is not a thing this chart lets you do by hand either.
    const clamp = (v, px) => Math.max(px - k * px, Math.min(0, v));
    return d3.zoomIdentity
      .translate(clamp((w - k * (x1 + x2)) / 2, w),
                 mode === "swarm" ? 0 : clamp((h - k * (y1 + y2)) / 2, h))
      .scale(k);
  }

  const sameTransform = (a, b) => Math.abs(a.k - b.k) < 1e-3
                               && Math.abs(a.x - b.x) < 0.5 && Math.abs(a.y - b.y) < 0.5;

  function goTo(t, animate) {
    if (sameTransform(t, transform)) return;              // already there; don't restart a tween
    if (animate) svg.transition().duration(420).call(zoom.transform, t);
    else svg.call(zoom.transform, t);
  }

  // ---- render -------------------------------------------------------------
  function build() {
    // BY REFERENCE, not by query: `selectAll("svg")` also matched the .ico glyphs #plot hosts in the
    // icon layout. Dormant, because build() runs from init() and init() runs before the move — the day
    // anything else rebuilds the svg, the icons vanish.
    if (svg) svg.remove();
    svg = d3.select(el).append("svg").attr("role", "img");
    // Everything the zoom moves is clipped to the plot rectangle. styles.css stops the <svg> itself from
    // overflowing, but that only catches what escapes the whole FRAME and the margins are inside it. The
    // axes and grid are drawn from the current transform's ticks, so they are inside by construction.
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

  // Re-dispatched into the CURRENT svg rather than a node app.js captured: build() makes a new one on
  // every setData/setMode, the `selectAll("svg")` trap again.
  //
  // It reports whether the zoom TOOK the event, not whether one is BOUND, because the caller may cancel
  // the page scroll only in the first case. ASKING is the point: d3-zoom cancels what it acts on, so
  // the synthetic event carries the answer and no copy of d3's clamp lives here. A scroll down at rest
  // is already at scaleExtent's floor, declines, and correctly scrolls the page; reporting "bound"
  // cancelled those and left a dead hole in the default view. Lens falls out for free — nothing is
  // bound there, so this returns false and the page scrolls.
  function wheelInto(e) {
    if (!svg) return false;
    const w = new WheelEvent("wheel", e);
    svg.node().dispatchEvent(w);
    return w.defaultPrevented;
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
    // Inset OUTWARD by one maximum radius, because a dot sits ON its value and not inside it: a
    // one-quartet composer's centre is a hair above the bottom edge, and a tight clip sliced those dots
    // flat where nothing had displaced them. Strays are left to the frame test — a dot belongs on screen
    // when its CENTRE is.
    const over = rScale.range()[1];
    svg.select("clipPath rect.clip")
       .attr("x", -over).attr("y", -over).attr("width", w + over * 2).attr("height", h + over * 2);

    // axes ---------------------------------------------------------------
    const fame = mode === "fame";
    const tx = fame ? transform.rescaleX(qx) : transform.rescaleX(x0);
    const ty = fame ? transform.rescaleY(vy)
             : mode === "scatter" ? transform.rescaleY(y0) : y0;
    // Tolerant at the ends: rescaleY() recomputes the domain from inverted pixels, so a tick lying
    // exactly ON the floor comes back a hair outside it and the axis stops labelling its own bottom.
    const inDom = (sc, v) => { const [a, b] = sc.domain();
                               return v >= a * (1 - 1e-9) && v <= b * (1 + 1e-9); };
    const xTicks = fame ? QX_TICKS.filter(v => inDom(tx, v))
                        : tx.ticks(Math.max(3, Math.round(w / 90)));
    const yTicks = fame ? VY_TICKS.filter(v => inDom(ty, v))
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

    // The readers-per-quartet diagonals. Both axes are log, so v = ratio x q is a straight line and
    // two endpoints define it -- but those endpoints are usually far outside the box, so each is
    // trimmed to the plot rather than drawn and clipped: gGrid is unclipped, and the label has to sit
    // where the line ENTERS the picture.
    const diag = [];
    if (fame) {
      for (const k of RATIOS) {
        const [q1, q2] = tx.domain();
        const seg = trim({ x: tx(q1), y: ty(k * q1) }, { x: tx(q2), y: ty(k * q2) });
        // Built here rather than in the .text() call because pickLabels has to MEASURE it.
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
      .text(fame ? String : d3.format("d"));
    // The title sits on its own line BELOW the ticks. Sharing their baseline put it on top of the
    // rightmost tick label at almost every width — the axis ends where the plot ends, so there is
    // never spare room out there.
    gAxX.selectAll("text.ttl").remove();
    gAxX.append("text").attr("class", "ttl").attr("x", w).attr("y", h + 33)
      .attr("text-anchor", "end").attr("font-size", 11).attr("font-weight", 600)
      .attr("fill", C.muted).text(fame ? "quartets written →" : "birth year →");

    const ly = gAxY.selectAll("text").data(mode === "swarm" ? [] : yTicks, String);
    ly.exit().remove();
    ly.enter().append("text").attr("text-anchor", "end").attr("font-size", 11).merge(ly)
      .attr("x", -7).attr("y", d => ty(d) + 4).attr("fill", C.axis)
      .text(fame ? vfmt : String);
    // Horizontal, ABOVE the plot rather than rotated beside it. Rotated it has to live inside
    // m.left, which on a phone is only wide enough for the tick labels — the two overlapped and
    // "100" rendered as "00". Above the plot it also just reads better at any width.
    gAxY.selectAll("text.ttl").remove();
    if (mode !== "swarm") {
      gAxY.append("text").attr("class", "ttl")
        .attr("x", -m.left + 4).attr("y", -8).attr("text-anchor", "start")
        .attr("font-size", 11).attr("font-weight", 600).attr("fill", C.muted)
        .text(fame ? "↑ English Wikipedia readers / month"
                   : "↑ quartets written (log scale)");
    }

    // dots ---------------------------------------------------------------
    // EVERY row is drawn, not just the visible ones: a search dims the rest rather than deleting
    // them, so "the three Haydns" reads as three dots in a field instead of three dots in an empty
    // box. Only hit-testing and labels honour the filter.
    // Sorted big-behind-small so a large famous disc never buries a small one it fully covers.
    const order = rows.filter(plottable).sort((a, b) => b.views - a.views);
    const sel = gDots.selectAll("circle.dot").data(order, d => d.i);
    sel.exit().remove();
    sel.enter().append("circle").attr("class", "dot").attr("stroke-width", 1)
      .merge(sel)
      .attr("cx", d => pos[d.i].x).attr("cy", d => pos[d.i].y).attr("r", d => pos[d.i].r)
      .attr("fill", fillOf).attr("stroke", strokeOf)
      .attr("stroke-width", widthOf)
      // 0.07, not the 0.12 that read fine on half this roster: the filtered-out mass is most of the
      // ink, and the readership brush exists to get it out of the way. Still drawn rather than
      // removed, so you can see WHERE in the field the survivors sit.
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
      .text(d => d.text);

    gLens.attr("class", "lens-edge")
      .style("display", mode === "lens" && lens ? null : "none")
      .attr("cx", lens ? lens.x : 0).attr("cy", lens ? lens.y : 0).attr("r", lensRadius())
      .attr("stroke", C.grid).attr("stroke-dasharray", "3 4");

    // Hit-test index over the CURRENT screen positions and the CURRENT visible subset — what makes the
    // whole canvas a tap target instead of the bare discs. Rebuilt every draw; Delaunay.from over
    // this roster is well under a millisecond.
    idx = vis.filter(d => inFrame(pos[d.i])).map(d => d.i);
    delaunay = idx.length > 1 ? d3.Delaunay.from(idx, i => pos[i].x, i => pos[i].y) : null;
  }

  function ariaLabel() {
    const n = (visible ? visible.size : rows.length);
    const axes = mode === "fame"
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
    // Measured BEFORE the resize, because the resting box is a function of the box it is fitted
    // to: a reader who had not pinched keeps a fitted frame across a rotation, and one who had
    // keeps their own.
    const resting = !zoomed();
    measure();
    if (w === pw && h === ph) return;
    swarmY = null;
    restingT = null;
    // Same reason as setMode: the box changed, so the separation the rings were chosen for is not the one
    // they are drawn with. Rotation is the case that matters — wide to tall, and the dots close up.
    refreshEmphasis();
    if (resting) transform = restingTransform();
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
    measure();
    restingT = null;
    // Re-derived because the ring is chosen against the PICTURE and each mode lays the same dots out
    // differently. Reachable from a link: `#v=scatter&g=female` then Fame put a ring 3.1px from a
    // filled dot against a bar of 13.5, because the picks were made in a geometry where nothing is
    // ringed at all (fill, stroke, width, opacity and label colour are Fame-only).
    refreshEmphasis();
    // Each view fits its own filter: the same composers occupy a different box in a timeline than in
    // a log-log readership cloud, so the frame is recomputed rather than carried over.
    transform = restingTransform();
    applyZoomBehavior(); draw();
  }

  // `settled` is false during a brush DRAG. The dimming follows every frame — watching the field
  // thin out is the whole point of the control — but the frame closes in once, when the gesture
  // ends. Re-fitting per frame would fly the chart around under a finger that is still moving.
  let fitted = false;
  function setFilter(set, settled) {
    visible = set;
    restingT = null;
    scoreProminence();
    draw();
    // The FIRST fit snaps. A shared link arrives with its filter already applied, and animating
    // there would show the unfiltered field for a beat and then jump-cut — the same reason the
    // hash is read before the first paint.
    if (settled !== false) { goTo(restingTransform(), fitted); fitted = true; }
  }
  // Which curated fill the view is making its claim with. app.js hands over the gender pill's
  // value on every change, so this is the only place that decides -- and an unknown value (no
  // filter, "male", anything a future pill adds without a list) falls back to the repertoire,
  // which is what "only under the Women filter" means in code.
  function setRepertoire(key) {
    const next = REPERTOIRES[key] || DEFAULT_REPERTOIRE;
    if (next === repertoire) return;
    repertoire = next;
    if (!rows.length) return;        // setData() will apply it when the data lands
    applyRepertoire();
    refreshEmphasis();
    draw();
  }
  function setSelected(i) { selected = i; draw(); }
  // Idempotent, because placeChartTools() calls it on every boot, rotation and full-screen toggle, and
  // a re-measure is a full re-layout of every plottable dot.
  function setTopReserve(px) {
    if (px === topReserve) return;
    topReserve = px;
    resize();
  }

  // To the RESTING view, not the full extent: while a filter is on, dropping the reader all the way out
  // would undo the filter's answer rather than their pinch.
  function resetZoom() {
    if (mode === "lens") { lens = null; draw(); return; }
    goTo(restingTransform(), true);
  }
  function zoomed() { return mode !== "lens" && !sameTransform(transform, restingTransform()); }
  function getMode() { return mode; }

  const HINTS = {
    fame: "Views vs Quartets written. Drag to pan, scroll or pinch to "
        + "zoom, tap a dot for more info and to pin it.",
    scatter: "Fixed axes. Drag to pan, scroll or pinch to zoom, tap or click a dot to pin it.",
    swarm: "A timeline of how crowded each generation was. Drag or pinch to spread it further.",
    lens: "A circular magnifier over a fixed chart: the axes never move. Move the pointer (or drag on a touch screen) to aim it; tap to pin a composer.",
  };
  function hint() { return HINTS[mode]; }

  return { init, setData, setMode, getMode, setFilter, setSelected, resize, rerender,
           defaultMode: () => DEFAULT_MODE,
           // Empty unless a pipeline run renamed one of the composers the Fame view argues
           // about; the UI suite asserts it, so a rename fails loudly instead of dropping a dot.
           missingNames: () => missing.slice(),
           setRepertoire,
           // The ACTIVE curated list plus the outliers, for the suite: the resting Fame view must
           // show these and only these, and a zoom must show something else. The ACTIVE one, not
           // CANON — the seed is whatever the view is currently asserting — so the checks read it
           // rather than naming composers.
           seedNames: () => repertoire.names.concat(OUTLIERS),
           // The sentence for the fill swatch, kept beside the list it names (invariant 8).
           repertoireLabel: () => repertoire.noun,
           // Every gender pill value that swaps the claim, so app.js can assert they are reachable.
           repertoireKeys: () => Object.keys(REPERTOIRES),
           resetZoom, zoomed, colorOf, hint, setTopReserve, wheelInto,
           // The current zoom scale, for the suite: "the frame closed in on the filter" is a
           // claim about this number, and reading it off the axis ticks would be reading a
           // rendering of it.
           zoomK: () => transform.k,
           lifeDomain: () => LIFE_DOMAIN.slice(),
           // How many rings the current filter derived — for the suite, to tell a derived set from the
           // curated one.
           derivedRings: () => ringIdx.length,
           // What the chart can PLACE; the table shows more. Static on purpose — a filter changes what is
           // highlighted, not what the chart can draw.
           plottedStats: () => {
             const p = rows.filter(plottable);
             return { n: p.length, from: d3.min(p, d => d.birth), to: d3.max(p, d => d.birth),
                      living: p.filter(d => d.living).length };
           },
           // So the legend can draw its size key at the radii the chart ACTUALLY uses, rather
           // than three hand-picked circles that quietly stop matching when the scale changes.
           radiusOf: v => (rScale ? rScale(v) : 0) };
})();
