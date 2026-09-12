// The chart: three ways to read the same ~880 dots, sharing one layout + hit-test core, plus a
// magnifier that can be switched on over any of them.
//
// WHY THREE. The 2014 original had exactly one: a *cartesian* fisheye that distorted both axes
// continuously under the cursor. It magnified beautifully and read terribly — with the axes
// moving there was no stable picture to look at, and a screenshot of it is nonsense. So:
//
//   fame     the default and the one that makes the page's claim: quartets written across,
//            monthly readers up, so readers-per-quartet is a diagonal.
//   scatter  the honest overview. Axes are FIXED (birth year, log quartets) so the static view is
//            a real chart you can screenshot, print, or link. Detail comes from ordinary pan/zoom
//            you opt into, not from a distortion that is always on.
//   swarm    force-collided along the birth-year axis. Nothing overlaps, ever — the answer to
//            "most composers here wrote three quartets or fewer and pile onto three log bands".
//            Costs the quartet-count axis, which is why it isn't the default.
//
// THE LENS IS NOT A FOURTH VIEW. It was one, and the difference between it and the timeline came
// to two things: that view drew a CIRCULAR fisheye over the base picture, and it had no zoom. But
// a magnifier is not a way of reading the data — it is a way of reading a crowd, and all three of
// these pictures have crowds (the Fame view's is the worst of them, ~600 dots in the low-left
// corner). So it is a toggle that applies over whatever mode is drawn: `layout()` lays the picture
// out and the warp is applied LAST, in screen space, which is what lets one fisheye serve three
// modes with no per-mode case at all. What it keeps from the old view is the contract that made it
// readable: while it is on, the base picture is FIXED (see applyZoomBehavior).
//
// Two things are shared by every view and are most of the value:
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

  // ---- the Fame view -------------------------------------------------------
  // Output ACROSS, attention UP, so readers-per-quartet is a diagonal and the distance a composer
  // sits above one is the argument: Mozart near 10,000 readers a quartet, Cambini on 1. The other
  // views ask "when, and how much"; this one asks "and did it land".
  const QX_DOMAIN = [0.85, 200];        // quartets written; largest stated is 149
  const QX_TICKS = [1, 2, 3, 5, 10, 20, 30, 50, 100];
  // Floor at 10: under ten readers a month is not a readership worth resolving, and a fixed floor
  // does not move when the roster does (issue 38).
  const VY_DOMAIN = [10, 260000];       // readers/mo
  const FUZZ = 1e-6;                    // px, for comparisons against a rescaled edge
  const VY_TICKS = [1, 10, 100, 1000, 10000, 100000];
  const RATIOS = [1, 10, 100, 1000, 10000];   // the readers-per-quartet diagonals

  // THE REPERTOIRE: the composers a quartet actually plays, in birth order, and the only
  // hardcoded composer NAMES in the app. Deliberately NOT a count -- it was "the seven" until
  // Tchaikovsky, Debussy and Prokofiev joined it, and every place that printed the number went
  // stale in the same commit. Prokofiev is here on two quartets and Debussy on one: the claim is
  // that the quartets are played, not that the composer wrote many. They are canonical
  // Wikipedia titles, which change spelling when the pipeline runs (see invariant 4), so a name
  // that stops resolving is reported by missingNames() and asserted empty in the UI suite rather
  // than quietly dropping a composer out of the argument.
  const CANON = ["Franz Xaver Richter", "Joseph Haydn", "Luigi Boccherini",
                 "Wolfgang Amadeus Mozart", "Ludwig van Beethoven",
                 "Pyotr Ilyich Tchaikovsky", "Claude Debussy", "Béla Bartók",
                 "Sergei Prokofiev", "Dmitri Shostakovich"];
  const OUTLIERS = ["Giuseppe Cambini", "Franz Krommer", "John Lodge Ellerton"];

  // A SECOND repertoire, shown only while the Women filter is on (issue #7).
  //
  // #7 asked two questions and they got different answers. Should the curated set be computed?
  // No -- a canon is a claim about what gets played, which is taste, and TODO records that no
  // single ranking reproduces one (the best recovers 8 of 13). Should the RING be computed? Yes --
  // "wrote a lot and is read little" is a property of whatever crowd is on screen, and it has been
  // derived per filter since 2026-09-05. So the fill stays hand-written and the ring stays earned.
  //
  // That left the women's group filled with nothing, because every name in CANON is a man. The
  // answer is not to derive one: it is to write a second list, by the same taste, about the group
  // the filter is showing. Nine, in birth order, spanning 1805 to 1962.
  //
  // GATED TO THE FILTER, and that is the whole design. Not one of the nine clears 10,000 readers a
  // month -- Price tops them at 8,001, where CANON's median is Tchaikovsky at 58,023 -- so at rest
  // they would be nine filled dots low in the densest part of a 790-dot cloud, under a key reading
  // "the repertoire", claiming to be the same set as Mozart and Beethoven. They are not the same
  // claim. They are a claim about the women, and it is legible exactly when the women are the
  // picture. So the resting view and the share card are untouched (invariant 14 draws the view AT
  // REST, so this never reaches the card), "Men" is untouched, and "Women" swaps the claim rather
  // than diluting it.
  //
  // Keyed by the gender pill VALUE, so this table and index.html's pills are one vocabulary --
  // a key no pill can reach is dead code, which app.js asserts against exactly as it does for
  // an unfilterable P21 value (invariant 7).
  const WOMEN_CANON = ["Fanny Hensel", "Amy Beach", "Rebecca Clarke", "Florence Price",
                       "Elizabeth Maconchy", "Grażyna Bacewicz", "Sofia Gubaidulina",
                       "Elena Kats-Chernin", "Jennifer Higdon"];
  // The list and the sentence that names it are ONE editorial claim, so they live together: a key
  // that still said "the repertoire" while filling nine women the repertoire never contained would
  // be labelling the wrong channel, which is the failure invariant 8 exists to prevent.
  // `noun` is separate from the legend's phrasing because two sentences need it in two shapes —
  // the key says "<noun>, in birth order", the lede says "<noun>, 1709 to 1906". One noun, so
  // they cannot come to disagree about what the filled dots ARE.
  const REPERTOIRES = { female: { names: WOMEN_CANON, noun: "the notables" } };
  const DEFAULT_REPERTOIRE = { names: CANON, noun: "the notables" };
  let repertoire = DEFAULT_REPERTOIRE;
  // Sets, not arrays: isCanon/named are called per DOT per FRAME from layout() and from all four
  // paint functions -- about 4,000 calls a frame in the Fame view, and an Array.includes scan
  // in each of them is work a phone does not need to do while a pinch is in flight.
  let canonIdx = [], outlierIdx = [], canonSet = new Set(), namedSet = new Set(), missing = [];
  // What the view is RINGING right now. Unfiltered that is exactly `namedSet`, the curated
  // thirteen; under a filter it is the curated ones the filter kept plus enough derived ones to
  // refill the ring budget (refreshEmphasis). `named()` reads this, not namedSet, so every channel
  // that follows the emphasis — fill, stroke, radius, opacity, label colour, the table chip —
  // follows the filter with no further wiring.
  let ringIdx = [], emphOrder = [], emphSet = new Set();
  // name -> row index, kept from setData so a repertoire swap does not need the raw rows again.
  let at = new Map();
  const resolve = list => list.filter(n => at.has(n)).map(n => at.get(n));

  let el, flagEl, cbHover, cbSelect, cbZoom;
  // The Fame view is the DEFAULT: it is the one that makes the page's claim. The timeline is
  // one tap away and still the honest overview of when the form was written.
  const DEFAULT_MODE = "fame";
  let rows = [], mode = DEFAULT_MODE, visible = null, selected = null, hovered = null;
  let svg, gPlot, gDots, gLabels, gAxX, gAxY, gGrid, gLens, gSel;
  let w = 0, h = 0, m = { top: 22, right: 14, bottom: 32, left: 46 };
  // Extra room at the TOP, requested by whoever draws something there. app.js asks for it when it
  // moves Share and Full screen onto the plot (placeChartTools), so those buttons sit in the same
  // band as the y-axis title instead of floating over the dots. It is a REQUEST rather than a media
  // query read here, because the breakpoint that decides it belongs to the code doing the drawing —
  // two copies of it is two things that can disagree, and this file would be the one that silently
  // kept reserving space for a control that had moved away. That paid off the day the breakpoint
  // moved from 640 to 1100: nothing in here changed.
  let topReserve = 0;
  let x0, y0, qx, vy, rScale, colorScale, C = {};
  let transform = d3.zoomIdentity, zoom;
  let swarmY = null, swarmKey = "";      // memo: the sim is expensive, size/radius are its inputs
  let lens = null;                       // {x,y} focus in plot coords, or null
  let lensOn = false;                    // the magnifier toggle; orthogonal to `mode`
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

  // Quartet counts are integers, so on the Fame view's log x every composer with the same count
  // lands on one vertical stripe — and Fame is the view with NO y jitter (layout() plots the raw
  // readership), so this offset is the only thing holding apart two composers who wrote the same
  // number of quartets and are read about equally. A hash cannot do that job. It is an independent
  // uniform draw per name, which separates ties on AVERAGE and not in particular: Debussy and
  // Gershwin (one quartet each, 0.5% apart in readership) drew 0.47px apart, close enough that the
  // Delaunay bisector ran through the middle of the visible disc and its right half selected the
  // composer you could not see (#45).
  //
  // So rank instead of hash. Within a stripe, order by readership and walk the golden ratio: by the
  // three-distance theorem consecutive terms of frac(k·φ) sit ~0.382 or ~0.618 of the range apart,
  // so the dots ADJACENT IN Y — the only ones that can collide — are pushed as far apart in x as
  // the range allows. Still deterministic, still stable between renders, and the amplitude is
  // untouched, so the nudge still cannot be read as data.
  //
  // Ordered by readership and then by NAME, never by row order: build_data.py is free to reorder
  // its rows, and a jitter that followed that would move dots when nothing about the data changed.
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
      // the extreme −0.045 decades and every stripe leans left. A stripe of ONE then drew a lone
      // dot a full 9.8% below its own count while having no tie to break at all — Cambini's 149
      // quartets rendered at 134, on a dot the view rings and labels. Eleven stripes have one
      // member and they are the whole sparse right end of the axis. A constant shift leaves every
      // consecutive-rank gap untouched, so the separation this function exists for is unchanged.
      const off = grp.map((_, k) => ((k * PHI) % 1) * 2 - 1);
      const mid = off.reduce((a, b) => a + b, 0) / off.length;
      grp.forEach((d, k) => { d.jq = Math.pow(10, (off[k] - mid) * 0.045); });
    }
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
        jq: 1,                                              // set by spreadJq, below
      };
    });
    spreadJq();
    at = new Map(rows.map(d => [d.name, d.i]));
    outlierIdx = resolve(OUTLIERS);
    applyRepertoire();
    // EVERY curated list, not just the active one: a rename inside WOMEN_CANON would otherwise go
    // unreported until somebody pressed the pill, which is the silent drop invariant 7 exists to
    // catch. Same reason missingNames() is asserted empty by the UI suite.
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

  // Living composers are NOT on the ramp, because their final lifespan does not exist yet —
  // colouring a 40-year-old as "died young" states something untrue. They get an open circle: a
  // SHAPE difference, which also satisfies "never encode meaning in color alone" and survives
  // both color-blindness and a black-and-white print.
  // The Fame view spends colour on the ARGUMENT rather than on lifespan: the repertoire filled
  // in the selection orange, the outliers ringed in the accent, and the rest in one recessive
  // grey. Emphasis, not eight hues — the point of the view is a handful of names against a field.
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
  // A FILTER HERE IS A HIGHLIGHT, not a subtraction: nothing is removed, the rest drops to 0.07.
  // So in the Fame view the filtered-IN dots have to carry the answer, and at the resting 0.22
  // they could not — 219 women at 0.22 against 571 ghosts at 0.07 is a difference you have to
  // hunt for, in the one view whose whole point is where a group sits against the field. While a
  // filter is on they come up to 0.55; with no filter, 0.22 is right, because then the recessive
  // mass IS the field the thirteen named composers are being read against.
  function opacityOf(d) {
    if (visible && !visible.has(d.i)) return 0.07;
    if (mode !== "fame") return 0.92;
    if (named(d.i)) return 1;
    return visible ? 0.55 : 0.22;
  }
  // Both branches are Fame-only: --sel is the PINNED colour, so tinting the repertoire with it in
  // Timeline or Swarm made ten composers look pinned with nothing pinned, and made the real
  // pin unidentifiable once there was one.
  function labelColorOf(d) {
    if (mode !== "fame") return C.ink;
    return isCanon(d.i) ? C.sel : named(d.i) ? C.accent : C.ink;
  }
  // table.js paints its row chip with this, on the promise that a row and its dot are
  // recognisably the same thing. So it follows the CURRENT view's encoding, not lifespan always —
  // in the Fame view that means the thirteen named composers are findable in the table by
  // colour, and everyone else is the same recessive grey they are on the chart.
  function colorOf(d) {
    if (mode === "fame") return isCanon(d.i) ? C.sel : named(d.i) ? C.accent : C.muted;
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

  // THE RING FOLLOWS THE FILTER. Every one of the curated thirteen is a man, so "Women" used to
  // ring nobody: it dimmed every accented dot to 0.07 and offered the group no emphasis of its
  // own, in the one view whose whole job is picking a few names out of a field. The ring now says
  // the same thing about whatever group is on screen — "these are the ones standing out from the
  // crowd they are drawn in" — which is what it always meant; it was just frozen to one crowd.
  //
  // Same seed-then-rank shape as the label budget, and deliberately the same size as OUTLIERS:
  // THREE rings, filled first by the curated outliers the filter kept and then by prominence. So
  // filtering to the men (who include all three) changes nothing, and filtering to the women
  // derives all three. It was six until Debussy, Gershwin and Ravel left this set for the
  // repertoire; keep the two in step, or "Women" gets more emphasis than the resting view has.
  // Only the ring is derived — the repertoire filled in --sel is an editorial claim about which
  // quartets are played, which is not a thing a ranking can recompute (see issue #7).
  // The one place the curated fill is built. setData() calls it for the opening view and
  // setRepertoire() calls it when the filter swaps the claim; both then go through
  // refreshEmphasis(), so the ring budget is re-derived against whatever is now curated -- which
  // is why filling Kats-Chernin and Price hands their ring slots to Vrebalov and Monk instead of
  // ringing a dot that is already filled.
  function applyRepertoire() {
    canonIdx = resolve(repertoire.names);
    canonSet = new Set(canonIdx);
    namedSet = new Set(canonIdx.concat(outlierIdx));
    emphOrder = canonIdx.concat(outlierIdx);
    emphSet = new Set(emphOrder);
  }

  const RINGS = 3;
  // A ring means "stands out from the crowd", so it needs a crowd. Below this the filtered group
  // IS the picture — every dot is already legible and separately labelled — and ringing three of
  // eight would be pointing at almost everything.
  const MIN_FIELD = 20;
  // ...and it has to stand APART. Prominence is distance from the CENTRE of the visible cloud, so
  // a corner full of composers all scores high and the tie was broken by nothing visual at all:
  // under "Women" the ring landed on Meredith Monk, whose disc came within 4px of Amy Beach's —
  // two 6.75px dots with a hairline between them, one filled and one ringed. A ring that close to
  // a dot the view has already picked out says nothing the picture was not already saying, and
  // reads as clutter rather than as emphasis. The closest ring/fill pair is 30px clear now.
  //
  // So a derived ring must clear every dot already emphasised, and every ring derived before it,
  // by 3% of the plot's diagonal. Measured in SCREEN space because "on top of" is a claim about
  // pixels, not about data — and as a FRACTION of the plot so it means the same thing on a phone
  // and in full screen. The exact number is not delicate: anything from about 2.5% to 5% picks the
  // same three on a desktop.
  //
  // It changes what the ring finds, and for the better: the three it now derives under "Women" are
  // all "wrote a lot, read little", which is exactly what the CURATED outliers mean at rest.
  // The other end of that group is not lost, it is carried by the other channel — Price and Beach
  // are filled.
  const MIN_SEP = 0.03;
  // ...and a fraction of the diagonal alone does not mean the same thing at every size, because
  // the fame dot radius is FLOORED at 3.2: as the plot shrinks the dots stop shrinking with it, so
  // the same fraction buys steadily less daylight relative to the things it is separating. At
  // 320px the fraction works out at ~11.8px against a bar of 10.6 — a margin of about one pixel.
  //
  // This is a GUARD, not a fix for anything observed: probed across eight viewports from 320px to
  // 1100px, the fraction alone still clears the bar by 20px or more on today's data. What was
  // actually producing a 5.7px violation on a phone was the STALE GEOMETRY above — rings chosen
  // for one box and drawn in another — and that is fixed where it was caused, in setMode/resize.
  // The floor stays because a threshold that sits a pixel above the bar it has to satisfy is not
  // a threshold. Stated in DOTS to say so: centres at least 4 named radii apart, i.e. a whole
  // dot's width of daylight between the edges, which is the bar ui.test.mjs measures. On a
  // desktop the fraction is the larger of the two and nothing changes.
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
      // Positions, not the scales: three modes lay the same dots out three ways, and "too close"
      // is a question about the picture that is actually drawn. layout() reads named() for the
      // fame RADIUS, which this function is in the middle of changing — only x and y are used
      // here, and those depend on nothing but the data and the mode, so the answer does not
      // depend on what happened to be ringed a moment ago.
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
      // Fewer than the budget is the honest outcome when nothing else stands clear — a ring means
      // "stands out", and inventing a third by dropping the rule would be pointing at a crowd.
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
    // The swarm is naturally short — it only needs the height its collisions demand — so giving
    // it the scatter's aspect ratio leaves a third of the panel empty above and below the blob.
    // A portrait phone gets a TALLER scatter (0.8): the same 0.6 that reads well on a laptop
    // squeezes 466 dots into ~200px there and the log bands merge into stripes.
    const narrow = cw < 560;
    // The Fame view is a square-ish cloud over five decades of y and two of x, so it wants a
    // taller box than the timeline, which is naturally wide.
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

  // Screen positions for the current mode + transform, with the lens applied LAST if it is on and
  // aimed. One function, three modes — everything downstream (dots, labels, Delaunay hit-testing,
  // the selection ring) reads only this, which is why the magnifier needs no wiring of its own:
  // what it warps is pixels, so what you click is what you see.
  function layout() {
    const tx = transform.rescaleX(x0);
    const out = new Array(rows.length);
    if (mode === "fame") {
      // Size is FREE here: readership is the y axis, so a radius that repeated it would double-
      // encode one variable and spend the only channel left. Emphasis carries the argument
      // instead. A composer with no page-view figure has no y at all, so park them off-frame and
      // let inFrame() drop them from the paint, the hit test and the labels.
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
    } else {
      const ty = transform.rescaleY(y0);
      for (const d of rows) out[d.i] = { x: tx(d.birth + d.jx), y: ty((d.quartets || 1) * d.jy), r: rScale(d.views) };
    }
    return lensOn && lens ? warp(out) : out;
  }

  // The fisheye, over a picture that is already laid out. The RADIUS follows the local
  // magnification and not just the position: a dot pushed outward but drawn the same size reads as
  // displaced rather than as nearer, which is the artefact that made the 2014 chart hard to read.
  // Clamped at 2.6 because the focus magnifies ~6x and a 6x dot is a blob with a name under it.
  function warp(out) {
    const f = makeLens(lensRadius(), 2.2);
    for (const p of out) {
      if (!p.r) continue;                  // parked at -9e9: no position to warp (see fame, above)
      const q = f(p.x, p.y, lens.x, lens.y);
      p.x = q.x; p.y = q.y; p.r *= Math.max(1, Math.min(q.z, 2.6));
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
  // Greedy, most-viewed first, first-come-first-served on space. This is what makes the STATIC
  // view worth looking at: with no interaction the chart already says "Haydn, Boccherini, Cambini,
  // Beethoven". Width is estimated rather than measured — a getBBox() per candidate would force
  // ~30 synchronous layouts per frame during a zoom, and being 10% off just costs a little
  // whitespace. The selected composer is placed FIRST so it never loses its label to a rival.
  //
  // A label prints the SHORT name (names.js), not the canonical Wikipedia title: 7 characters on
  // average instead of 15. That is not only tidier — the placer is first-come-first-served on
  // space, so halving every box is what lets the ones behind it find room at all. The full title
  // is still one hover or tap away in the detail panel, and the flag prints it on the way.
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
    // AT FIRST SIGHT the Fame view says exactly what it is about: the thirteen curated names,
    // and nothing else. That set is a judgment no single ranking reproduces — the best one
    // recovers eight of them — so it stays as the SEED rather than being derived away, and this
    // one case pins the budget to it so the resting picture is what it always was.
    //
    // Every other state fills the budget from the seed and then by prominence: zoomed in, where
    // the space is real and the reader has asked for detail, and filtered, where the seed is
    // mostly gone — every one of the thirteen is a man, so "Women" used to leave 219 emphasised
    // dots with no name on any of them, answering "where are they" while refusing to say "who".
    // The derived rings are seeds too: a dot the view has decided to ring and then declined to
    // name is pointing at a composer it refuses to identify, which is the exact complaint that
    // put the rings on the filtered view in the first place.
    const seeds = emphOrder.map(i => rows[i]).filter(isVisible);
    const first = mode === "fame" && !visible && transform.k === 1;
    if (first) cap = seeds.length;
    const cands = mode === "fame"
      ? seeds.concat(first ? []
          : rows.filter(d => isVisible(d) && !named(d.i) && prom.has(d.i))
                .sort((a, b) => prom.get(b.i) - prom.get(a.i)))
      : rows.filter(isVisible).sort((a, b) => b.views - a.views);
    // The selected composer is placed FIRST so it never loses its label to a rival -- but it is
    // only in `cands` if it was a candidate. In the Fame view the list is the 13 named, so
    // pinning any of the other 777 gave indexOf === -1, and splice(-1, 1) deletes the LAST
    // element: Ravel silently lost his label every time you clicked an unnamed dot.
    if (selected != null && rows[selected] && isVisible(rows[selected])) {
      const at = cands.indexOf(rows[selected]);
      if (at >= 0) cands.splice(at, 1);
      // A PIN IS A GUEST, not a replacement. In the resting view the budget is exactly the seed
      // count, so unshifting a composer who is NOT a seed spends a slot the seeds were promised
      // and the last one placed loses its name. That was invisible while two seeds failed to fit
      // anyway — the left-edge dots left slack in the budget — and became a real defect the
      // moment the diagonal spots let all thirteen place: pinning any ordinary dot un-named
      // Ellerton.
      else if (first) cap += 1;
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
      const text = Names.short(d.name);
      const tw = text.length * 5.5 + 6, th = 12;
      // Above, then below, then beside, then the four diagonals. "Above" alone silently dropped
      // exactly the composers the chart is about: Mozart sits 2.6% from the top of the Fame view,
      // Cambini hard against the right edge, Debussy against the left — every one of them had a
      // dot and no room over it, so the name went missing from the argument it was making.
      //
      // The diagonals answer the LEFT EDGE (issue #10). A dot at x = 1 quartet sits ~9px from the
      // plot's left side, so a centred box (above, below) starts at a negative x and the
      // left-hand spot is worse: only "beside, right" is on the plot at all, one slot for a
      // column that holds Debussy, Gershwin and Ravel. Whoever came first took it and the rest
      // were ringed with no name — the exact thing the rings exist to avoid. Four corners cost
      // nothing (the loop breaks on the first fit) and take the resting desktop view from 11
      // names of 13 to 13 of 13.
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
  // A filter closes the frame in on what it kept. That reads as a subtraction only if you forget
  // that a filter here is a HIGHLIGHT: the other 600 dots are still drawn at 0.07, so what fills
  // the box is the group you asked for against the GHOST of the field it came from, which is the
  // comparison the filter was asking for in the first place. Clearing the filter opens back out.
  //
  // It also feeds the labels. The budget is a function of the zoom (pickLabels), so closing in on
  // 219 women is what buys them names instead of an anonymous emphasised cloud.
  //
  // Measured from a layout() at zoomIdentity rather than from the scales, so the box is in the
  // same geometry the dots are drawn in — three modes, one source of truth, and a fourth encoding
  // cannot forget to update this. Costs one extra pass over 884 rows per settled filter change.
  // The picture at rest: no transform, and no LENS either. Both callers — the fit in
  // computeResting() and the MIN_SEP separation refreshEmphasis() ranks rings by — are asking
  // about the chart, not about where the pointer happens to be sitting. A warped answer would fit
  // the frame to a magnified cloud and choose rings that stand apart only while the lens is aimed
  // at them, and both results outlive the pointer move that produced them.
  function baseLayout() {
    const t = transform, aim = lens;
    transform = d3.zoomIdentity; lens = null;
    const p = layout();
    transform = t; lens = aim;
    return p;
  }

  // Fewer kept dots than this and the frame does not move at all — see computeResting().
  const MIN_FIT = 4;

  // Where the chart RESTS for the current filter: identity with no filter, the fitted box with
  // one. resetZoom() returns here and zoomed() is measured against it, so a filter that fits at
  // 4x does not light up the reset button as though the reader had pinched.
  //
  // MEMOIZED, because zoomed() is asked on every frame of a pinch (it drives the reset button) and
  // computing it means a second full layout pass over 884 rows. Invalidated by the only three
  // things it depends on: the filter, the mode and the box.
  let restingT = null;
  function restingTransform() {
    if (!restingT) restingT = computeResting();
    return restingT;
  }

  function computeResting() {
    if (!visible || !rows.length) return d3.zoomIdentity;
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
    // A handful of dots is not a box worth fitting. One match has a zero-width box, so fit()
    // returns Infinity on both axes and k lands on the 24x clamp — searching a composer threw the
    // reader to maximum magnification, where the surrounding cloud they are being compared
    // AGAINST is off screen. Below MIN_FIT the fit is skipped and the filter does its other job:
    // the match comes up to 0.55 while the field it belongs to stays drawn at 0.07 behind it.
    // Counted from the dots this chart can actually PLACE, not from visible.size — a filter can
    // keep rows the Fame view has no y for.
    //
    // Skipping the fit means the FULL EXTENT, not the reader's current transform: a reader
    // pinched to 6x who then searches a name is zoomed back out to see where that dot sits in the
    // field. That is deliberate and not a detail of this guard — restingTransform() has to be a
    // pure function of the filter, the mode and the box or the memo above is meaningless and
    // "reset" has nothing to return to. It is also the same thing clearing a filter does.
    if (n < MIN_FIT) return d3.zoomIdentity;
    // Pad by the largest dot so the discs at the edge are whole, plus a little air for a label.
    const pad = rMaxSeen + 10;
    const fit = (span, px) => (span > 0 ? (px - pad * 2) / span : Infinity);
    // The swarm's y is NOT under the zoom — its collisions are solved once at k=1 and only x is
    // rescaled (see ensureSwarm) — so fitting it vertically would compute a scale that the dots
    // then ignore.
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
    // BY REFERENCE, not by query. `selectAll("svg")` is a DESCENDANT query, and #plot also hosts
    // #chart-tools in the icon layout (placeChartTools) — so it matched the chart's svg and the
    // three .ico glyphs inside Share and Full screen, and removed all four. Nothing showed it,
    // because build() only runs from init() and init() runs before the move; the day anything
    // rebuilds the svg the icons vanish wherever the group is on the plot. This removes the one
    // svg this module made, which no overlay can ever be.
    if (svg) svg.remove();
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

  // A wheel that starts over the chart's own two buttons is a wheel over the CHART. The zoom is
  // bound to the SVG and app.js parks #chart-tools in #plot as a SIBLING of it, so such a wheel
  // reaches no zoom listener at all: it bubbles to the document and scrolls the page, two pixels
  // from a spot in the same band that zooms. It cost nothing while the icons were a phone layout —
  // there is no wheel on a phone, and the trade-off measured for that layout was all about dots
  // COVERED — and became a dead corner under a mouse the moment the layout reached a laptop.
  // The event is re-dispatched into the CURRENT svg rather than app.js holding a reference to one:
  // build() makes a new svg on every setData/setMode, and a captured node is the same stale-handle
  // trap that `selectAll("svg")` was.
  //
  // It reports whether the zoom TOOK the event, not whether one is bound, because the caller may
  // cancel the page scroll only in the first case. Those are different far more often than they
  // look: `scaleExtent` starts at 1 and the resting view is already there, so every scroll DOWN at
  // rest asks for a scale d3 will not go to — it declines and, correctly, does NOT cancel, leaving
  // the page to scroll. A forward that reported "bound" cancelled those too, and the DEFAULT view
  // at rest got an 86x40 hole where scrolling the page down did nothing while a pixel to the left
  // it worked. Measured at 1024: 0px under the glyphs against 120px beside them.
  //
  // ASKING is the whole point. d3-zoom cancels what it acts on, so the synthetic event carries the
  // answer and no second copy of d3's clamp has to live here — predicting "would this move k?" is
  // exactly the duplication that goes stale when scaleExtent changes. It also makes the LENS fall
  // out rather than be named: applyZoomBehavior() binds nothing while it is on, so nothing cancels,
  // so this returns false and the page scrolls, which is what the bare plot does there.
  function wheelInto(e) {
    if (!svg) return false;
    const w = new WheelEvent("wheel", e);
    svg.node().dispatchEvent(w);
    return w.defaultPrevented;
  }

  // THE LENS SUSPENDS THE ZOOM rather than composing with it, which is the one thing the old lens
  // VIEW is worth keeping: a fisheye is a magnifier over a picture that holds still, and the 2014
  // chart's lesson is that a magnified view of a moving one cannot be read at all. On a touch
  // screen the two are also the same gesture — one finger aims the lens — so a pan would fight
  // every drag for it. The transform is left exactly where it was rather than reset, so the lens
  // magnifies whatever the reader had framed and unchecking the box hands the zoom back unchanged.
  function applyZoomBehavior() {
    if (!svg) return;
    svg.on(".zoom", null);
    if (!lensOn) {
      zoom.extent([[0, 0], [w, h]]).translateExtent([[0, 0], [w, h]]);
      svg.call(zoom);
    }
    // The node's own __zoom is synced whether the behaviour is bound or not: goTo() tweens FROM
    // it, so a frame fitted to a filter while the lens was on would otherwise animate from a
    // transform nothing has drawn since.
    svg.call(zoom.transform, transform);
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
    const fame = mode === "fame";
    const tx = fame ? transform.rescaleX(qx) : transform.rescaleX(x0);
    // The swarm's y is not under the zoom and draws no ticks at all (see below), so it does not
    // need a case here — the one that used to sit here was the lens, whose base picture was
    // unzoomable by construction and is now the timeline's, transform and all.
    const ty = fame ? transform.rescaleY(vy) : transform.rescaleY(y0);
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

    // The readers-per-quartet diagonals. Both axes are log, so v = ratio x q is a straight line
    // on screen and two endpoints define it -- but those endpoints are usually far outside the
    // box, so each is trimmed to the plot rather than drawn and clipped: gGrid is not clipped,
    // and the label has to sit where the line actually ENTERS the picture.
    const diag = [];
    if (fame) {
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
      .text(d => d.text);

    gLens.attr("class", "lens-edge")
      .style("display", lensOn && lens ? null : "none")
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
      if (lensOn && (!TOUCH || down)) {                   // on touch the lens is dragged, not followed
        lens = (p.x >= -40 && p.x <= w + 40 && p.y >= -40 && p.y <= h + 40) ? p : null;
        draw();
      }
      if (TOUCH) return;
      const i = nearest(p.x, p.y);
      if (i !== hovered) { hovered = i; showFlag(i, p); cbHover && cbHover(i); }
      else if (i != null) showFlag(i, p);
    });
    svg.on("pointerleave", () => {
      if (lensOn && !TOUCH) { lens = null; draw(); }
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
      if (TOUCH && lensOn) { lens = p; draw(); }
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
    // Same reason as setMode: the box changed, so the separation the rings were chosen for is not
    // the separation they are drawn with. A rotation is the case that matters — the fame plot goes
    // from wide to tall and the dots close up.
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
    // The lens SURVIVES a view change; its aim does not. The focus is a point in screen space and
    // the next mode puts different composers under it, so keeping it would magnify a spot the
    // reader chose in a picture that is gone. The pointer re-aims it on the next move.
    mode = mNew; lens = null; transform = d3.zoomIdentity;
    measure();
    restingT = null;
    // The ring is derived against the PICTURE — MIN_SEP is a distance in the layout that is
    // actually on screen — and every mode lays the same dots out differently, in a differently
    // shaped box. refreshEmphasis() was reached only from setFilter(), so a filter applied in the
    // timeline picked its three rings from a geometry where nothing is ringed at all (fill,
    // stroke, width, opacity and the label colour are all Fame-only), and those picks were then
    // drawn unchanged in Fame. `#v=scatter&g=female` then Fame put a ring 3.1px from a filled dot,
    // against a bar of 13.5 — the exact defect MIN_SEP exists to remove, reachable from a link.
    refreshEmphasis();
    // Each view fits its own filter: the same 219 composers occupy a different box in a timeline
    // than in a log-log readership cloud, so the frame is recomputed rather than carried over.
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
  // The magnifier, over whichever view is drawn. It needs no measure(): the plot's box is a
  // function of the MODE (see measure()), so switching the lens on and off moves nothing — which
  // is what lets its control live in the row above the plot, where a box that resized under the
  // press that caused it would break the rule that row exists to keep (see index.html).
  function setLens(on) {
    on = !!on;
    if (on === lensOn) return;
    lensOn = on; lens = null;
    applyZoomBehavior();
    draw();
    cbZoom && cbZoom(zoomed());
  }
  function setSelected(i) { selected = i; draw(); }
  // "Reset" means back to where this filter opens, not back to the whole field: the fitted box IS
  // the resting view while a filter is on, and dropping the reader out to the full extent would
  // undo the filter's answer rather than their pinch.
  // Idempotent, because placeChartTools() calls it on every boot, rotation and full-screen toggle
  // and a re-measure at this size is a full re-layout of 790 dots.
  function setTopReserve(px) {
    if (px === topReserve) return;
    topReserve = px;
    resize();
  }

  // Neither of these asks about the lens. "Zoomed" is a claim about the FRAME, and the frame is
  // still whatever the reader left it at while the magnifier is on — a button that greyed out
  // there would be lying about a chart it can still return to, and resetZoom() still gets there
  // because goTo() drives zoom.transform, which does not need the behaviour bound to fire.
  function resetZoom() { goTo(restingTransform(), true); }
  function zoomed() { return !sameTransform(transform, restingTransform()); }
  function getMode() { return mode; }

  // Two halves per view: what it shows, and how to drive it. The lens REPLACES the second half
  // rather than adding a sentence to it — it suspends the zoom, so "scroll or pinch to zoom" is an
  // instruction the chart would no longer obey, and a hint that tells you to do something that
  // does nothing is worse than a shorter one.
  const SHOWS = {
    fame: "Views vs Quartets written.",
    scatter: "Fixed axes: birth year across, quartets written up.",
    swarm: "A timeline of how crowded each generation was.",
  };
  const DRIVE = {
    fame: "Drag to pan, scroll or pinch to zoom, tap a dot for more info and to pin it.",
    scatter: "Drag to pan, scroll or pinch to zoom, tap or click a dot to pin it.",
    swarm: "Drag or pinch to spread it further.",
  };
  const LENS_HINT = "The magnifier follows the pointer — drag it on a touch screen — and the "
                  + "picture underneath holds still. Tap a dot to pin it.";
  function hint() { return SHOWS[mode] + " " + (lensOn ? LENS_HINT : DRIVE[mode]); }

  return { init, setData, setMode, getMode, setFilter, setSelected, resize, rerender,
           setLens, lensOn: () => lensOn,
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
           // How many of the rings the current filter derived. Nothing on the page reads it now
           // that the legend has stopped captioning the ring; the suite asks it to tell a derived
           // set from the curated one.
           derivedRings: () => ringIdx.length,
           // What the chart can actually place — the table shows more (see isVisible). The birth
           // extent is the PLOTTABLE one and the living count is of those same rows, because the
           // empty detail panel describes the dots: it read "884 composers, born 1582-1989" over
           // a chart whose x axis starts at 1709, the three names born before 1700 having no
           // quartet count. Static on purpose — a filter changes what is highlighted, not what
           // the chart can draw.
           plottedStats: () => {
             const p = rows.filter(plottable);
             return { n: p.length, from: d3.min(p, d => d.birth), to: d3.max(p, d => d.birth),
                      living: p.filter(d => d.living).length };
           },
           // So the legend can draw its size key at the radii the chart ACTUALLY uses, rather
           // than three hand-picked circles that quietly stop matching when the scale changes.
           radiusOf: v => (rScale ? rScale(v) : 0) };
})();
