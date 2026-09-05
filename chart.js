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

  const X_DOMAIN = [1580, 2000];        // data runs 1582..1989; pad so no dot sits on an axis
  const Y_DOMAIN = [0.85, 170];         // log; the largest stated count is 149 (Cambini)
  const Y_TICKS = [1, 2, 3, 5, 10, 20, 30, 50, 100];
  let LIFE_MID = 72;                    // median completed lifespan; recomputed from the data

  let el, flagEl, cbHover, cbSelect, cbZoom;
  let rows = [], mode = "scatter", visible = null, selected = null, hovered = null;
  let svg, gPlot, gDots, gLabels, gAxX, gAxY, gGrid, gLens, gSel;
  let w = 0, h = 0, m = { top: 22, right: 14, bottom: 32, left: 46 };
  let x0, y0, rScale, colorScale, C = {};
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

  // [name, birth, death, quartets, views, views_lo, views_hi]; death and quartets may be null.
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
      };
    });
    // The diverging ramp pivots on the MEDIAN completed lifespan of whoever is actually in the
    // data, rather than a number baked in when the dataset was half this size.
    const lived = rows.filter(d => d.lifespan != null).map(d => d.lifespan).sort((a, b) => a - b);
    if (lived.length) LIFE_MID = lived[lived.length >> 1];
    swarmY = null;
  }

  // ---- colors -------------------------------------------------------------
  function readColors() {
    const g = Theme.getCssColor;
    C = {
      short: g("--c-short"), mid: g("--c-mid"), long: g("--c-long"), living: g("--c-living"),
      plot: g("--plot"), grid: g("--grid"), axis: g("--axis"), line: g("--dot-line"),
      ink: g("--ink"), muted: g("--muted"), sel: g("--sel"),
    };
    colorScale = d3.scaleLinear()
      .domain([20, LIFE_MID, 104])
      .range([C.short, C.mid, C.long])
      .interpolate(d3.interpolateLab)
      .clamp(true);
  }

  // Living composers are NOT on the ramp, because their final lifespan does not exist yet —
  // colouring a 40-year-old as "died young" states something untrue. They get an open circle: a
  // SHAPE difference, which also satisfies "never encode meaning in color alone" and survives
  // both color-blindness and a black-and-white print.
  function fillOf(d) { return d.living ? C.plot : colorScale(d.lifespan); }
  function strokeOf(d) { return d.living ? C.living : C.line; }
  function colorOf(d) { return d.living ? C.living : colorScale(d.lifespan); }

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
    const aspect = mode === "swarm" ? (narrow ? 0.58 : 0.44) : (narrow ? 0.82 : 0.6);
    const ch = full
      ? Math.max(240, Math.round(box.height))
      : Math.round(Math.max(260, Math.min(540, cw * aspect)));
    m.left = cw < 480 ? 38 : 46;
    m.bottom = cw < 480 ? 40 : 44;
    w = cw - m.left - m.right;
    h = ch - m.top - m.bottom;
    x0 = d3.scaleLinear().domain(X_DOMAIN).range([0, w]);
    y0 = d3.scaleLog().domain(Y_DOMAIN).range([h, 0]);
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

  // Screen positions for the current mode + transform. One function, three modes — everything
  // downstream (dots, labels, Delaunay hit-testing, the selection ring) reads only this.
  function layout() {
    const tx = transform.rescaleX(x0);
    const out = new Array(rows.length);
    if (mode === "swarm") {
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
  const isVisible = d => plottable(d) && (!visible || visible.has(d.i));

  // ---- labels -------------------------------------------------------------
  // Greedy, most-viewed first, first-come-first-served on space. This is what makes the STATIC
  // view worth looking at: with no interaction the chart already says "Haydn, Boccherini, Cambini,
  // Beethoven". Width is estimated rather than measured — a getBBox() per candidate would force
  // ~30 synchronous layouts per frame during a zoom, and being 10% off just costs a little
  // whitespace. The selected composer is placed FIRST so it never loses its label to a rival.
  function pickLabels(p) {
    // Full screen earns more labels, but not proportionally more: a phone in full screen is TALL
    // and narrow, and 40+ names there collide with dots even when they miss each other.
    const full = document.body.classList.contains("fs");
    const cap = full ? (w < 560 ? 20 : 42) : Math.max(4, Math.round(w / 62));
    const cands = rows.filter(isVisible).sort((a, b) => b.views - a.views);
    if (selected != null && rows[selected] && isVisible(rows[selected])) {
      cands.splice(cands.indexOf(rows[selected]), 1);
      cands.unshift(rows[selected]);
    }
    const placed = [], boxes = [];
    for (const d of cands) {
      if (placed.length >= cap) break;
      const q = p[d.i];
      const tw = d.name.length * 5.5 + 6, th = 12;
      const bx = q.x - tw / 2, by = q.y - q.r - 4 - th;
      if (bx < 0 || bx + tw > w || by < 0) continue;
      if (boxes.some(o => bx < o.x + o.w && bx + tw > o.x && by < o.y + o.h && by + th > o.y)) continue;
      boxes.push({ x: bx - 2, y: by - 1, w: tw + 4, h: th + 2 });
      placed.push({ d, x: q.x, y: by + th - 2 });
    }
    return placed;
  }

  // ---- render -------------------------------------------------------------
  function build() {
    d3.select(el).selectAll("svg").remove();
    svg = d3.select(el).append("svg").attr("role", "img");
    gPlot = svg.append("g");
    gPlot.append("rect").attr("class", "bg");
    gGrid = gPlot.append("g");
    gAxY = gPlot.append("g");
    gAxX = gPlot.append("g");
    gLens = gPlot.append("circle").attr("fill", "none").attr("pointer-events", "none").style("display", "none");
    gDots = gPlot.append("g");
    gSel = gPlot.append("g").attr("pointer-events", "none");
    gLabels = gPlot.append("g").attr("pointer-events", "none");

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

    // axes ---------------------------------------------------------------
    const tx = transform.rescaleX(x0);
    const ty = mode === "scatter" ? transform.rescaleY(y0) : y0;
    const xTicks = tx.ticks(Math.max(3, Math.round(w / 90)));
    const yTicks = Y_TICKS.filter(v => v >= ty.domain()[0] && v <= ty.domain()[1]);

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

    const lx = gAxX.selectAll("text").data(xTicks, String);
    lx.exit().remove();
    lx.enter().append("text").attr("text-anchor", "middle").attr("font-size", 11).merge(lx)
      .attr("x", tx).attr("y", h + 15).attr("fill", C.axis).text(d3.format("d"));
    // The title sits on its own line BELOW the ticks. Sharing their baseline put it on top of the
    // rightmost tick label at almost every width — the axis ends where the plot ends, so there is
    // never spare room out there.
    gAxX.selectAll("text.ttl").remove();
    gAxX.append("text").attr("class", "ttl").attr("x", w).attr("y", h + 33)
      .attr("text-anchor", "end").attr("font-size", 11).attr("font-weight", 600)
      .attr("fill", C.muted).text("birth year →");

    const ly = gAxY.selectAll("text").data(mode === "swarm" ? [] : yTicks, String);
    ly.exit().remove();
    ly.enter().append("text").attr("text-anchor", "end").attr("font-size", 11).merge(ly)
      .attr("x", -7).attr("y", d => ty(d) + 4).attr("fill", C.axis).text(String);
    // Horizontal, ABOVE the plot rather than rotated beside it. Rotated it has to live inside
    // m.left, which on a phone is only wide enough for the tick labels — the two overlapped and
    // "100" rendered as "00". Above the plot it also just reads better at any width.
    gAxY.selectAll("text.ttl").remove();
    if (mode !== "swarm") {
      gAxY.append("text").attr("class", "ttl")
        .attr("x", -m.left + 4).attr("y", -8).attr("text-anchor", "start")
        .attr("font-size", 11).attr("font-weight", 600).attr("fill", C.muted)
        .text("↑ quartets written (log scale)");
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
      .attr("stroke-width", d => (d.living ? 1.4 : 1))
      .attr("opacity", d => (visible && !visible.has(d.i) ? 0.12 : 0.92));

    // selection ring + labels ---------------------------------------------
    gSel.selectAll("*").remove();
    const cur = selected != null && rows[selected] && isVisible(rows[selected]) ? rows[selected] : null;
    if (cur) {
      gSel.append("circle").attr("class", "sel-ring")
        .attr("cx", pos[cur.i].x).attr("cy", pos[cur.i].y).attr("r", pos[cur.i].r + 5)
        .attr("fill", "none").attr("stroke", C.sel).attr("stroke-width", 2.2);
    }

    const labs = pickLabels(pos);
    const lb = gLabels.selectAll("text").data(labs, d => d.d.i);
    lb.exit().remove();
    lb.enter().append("text")
      .attr("text-anchor", "middle").attr("font-size", 10.5).attr("paint-order", "stroke")
      .attr("stroke-width", 3).attr("stroke-linejoin", "round")
      .merge(lb)
      .attr("x", d => d.x).attr("y", d => d.y)
      .attr("stroke", C.plot)
      .attr("fill", d => (cur && d.d.i === cur.i ? C.sel : C.ink))
      .attr("font-weight", d => (cur && d.d.i === cur.i ? 700 : 500))
      .text(d => d.d.name);

    gLens.attr("class", "lens-edge")
      .style("display", mode === "lens" && lens ? null : "none")
      .attr("cx", lens ? lens.x : 0).attr("cy", lens ? lens.y : 0).attr("r", lensRadius())
      .attr("stroke", C.grid).attr("stroke-dasharray", "3 4");

    // Hit-test index over the CURRENT screen positions and the CURRENT visible subset — this is
    // what makes the whole canvas a tap target instead of the 2.2px discs. Rebuilt every draw;
    // Delaunay.from on 466 points is well under a millisecond.
    idx = vis.map(d => d.i);
    delaunay = idx.length > 1 ? d3.Delaunay.from(idx, i => pos[i].x, i => pos[i].y) : null;
  }

  function ariaLabel() {
    const n = (visible ? visible.size : rows.length);
    return `Scatter plot of ${n} string quartet composers by birth year and number of quartets written. `
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

  function setFilter(set) { visible = set; draw(); }
  function setSelected(i) { selected = i; draw(); }
  function resetZoom() { if (mode === "lens") { lens = null; draw(); return; } svg.transition().duration(400).call(zoom.transform, d3.zoomIdentity); }
  function zoomed() { return mode !== "lens" && transform.k !== 1; }
  function getMode() { return mode; }

  const HINTS = {
    scatter: "Fixed axes. Drag to pan, scroll or pinch to zoom, tap or click a dot to pin it. Ties are nudged by up to half a year so overlapping composers stay separately clickable.",
    swarm: "Composers pushed apart until nothing overlaps. Vertical position means nothing here — the quartet count is dropped, and size (views) and color (lifespan) are unchanged. Read it as a timeline of how crowded each generation was. Drag or pinch to spread it further.",
    lens: "A circular magnifier over a fixed chart: the axes never move. Move the pointer (or drag on a touch screen) to aim it; tap to pin a composer.",
  };
  function hint() { return HINTS[mode]; }

  return { init, setData, setMode, getMode, setFilter, setSelected, resize, rerender,
           resetZoom, zoomed, colorOf, hint, midLife: () => LIFE_MID, TOUCH,
           // How many rows the chart can actually place — the table shows more (see isVisible).
           plotted: () => rows.filter(plottable).length,
           // So the legend can draw its size key at the radii the chart ACTUALLY uses, rather
           // than three hand-picked circles that quietly stop matching when the scale changes.
           radiusOf: v => (rScale ? rScale(v) : 0) };
})();
