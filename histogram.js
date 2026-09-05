// The readership filter: a log-scale histogram of page views with a drag-to-select brush.
//
// WHY IT EARNS ITS SPACE. Readership on this list spans 1 to 186,772 monthly views with a median
// of 233 — half the roster is composers essentially nobody reads, and at 884 dots they are most of
// the ink. A plain "minimum views" slider would hide them, but it would also hide WHERE the cut
// falls in the distribution, which is the thing you actually need to choose it. The histogram is
// the control and the context in one 56px strip.
//
// It is a second, independent filter alongside the search box. app.js intersects the two; neither
// knows about the other.
//
// Log x, because a linear axis puts 96% of the composers in the first pixel. Bin edges are
// geometric, so each bar covers the same MULTIPLICATIVE range — the shape you see is the real
// shape of the distribution rather than an artifact of the binning.

window.Histogram = (function () {
  const BINS = 36;
  const H = 42;                 // bar area
  const AXIS = 15;              // tick labels below it
  const PAD = 2;

  let el, cb, svg, gBars, gAxis, gEnds, brush, gBrush;
  let rows = [], counts = [], edges = [], x = null, y = null;
  let range = null;             // [lo, hi] in views, or null for "everything"
  let w = 0, C = {};

  const fmt = n => (n >= 1000 ? (n / 1000 >= 10 ? Math.round(n / 1000) : (n / 1000).toFixed(1)) + "k"
                              : String(Math.round(n)));

  function setData(r) {
    rows = r.filter(d => d.views != null);
    const vals = rows.map(d => d.views);
    const lo = Math.max(1, d3.min(vals)), hi = d3.max(vals);
    // Geometric edges. Math.max(1, …) because a log scale has no zero and one composer really does
    // sit at a single view per month.
    edges = d3.range(BINS + 1).map(i => Math.pow(10, Math.log10(lo) + (Math.log10(hi) - Math.log10(lo)) * i / BINS));
    counts = new Array(BINS).fill(0);
    for (const v of vals) {
      let k = Math.floor((Math.log10(Math.max(1, v)) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo)) * BINS);
      counts[Math.max(0, Math.min(BINS - 1, k))]++;
    }
  }

  function readColors() {
    const g = Theme.getCssColor;
    C = { bar: g("--line"), sel: g("--accent"), axis: g("--axis"), muted: g("--muted"), plot: g("--plot") };
  }

  // A bin is "in" the selection when it overlaps it at all, so the highlighted bars always cover
  // the composers the brush actually keeps — never a bar narrower than the selection under it.
  const inRange = i => !range || (edges[i + 1] >= range[0] && edges[i] <= range[1]);

  function draw() {
    if (!svg) return;
    const total = H;
    svg.attr("viewBox", `0 0 ${w} ${H + AXIS}`).attr("width", w).attr("height", H + AXIS);

    const maxC = d3.max(counts) || 1;
    y = d3.scaleSqrt().domain([0, maxC]).range([0, H - PAD]);   // sqrt: the tail stays visible

    const bars = gBars.selectAll("rect").data(counts);
    bars.exit().remove();
    bars.enter().append("rect").merge(bars)
      .attr("x", (d, i) => x(edges[i]))
      .attr("width", (d, i) => Math.max(1, x(edges[i + 1]) - x(edges[i]) - 1))
      .attr("y", d => total - y(d))
      .attr("height", d => y(d))
      .attr("fill", (d, i) => (inRange(i) ? C.sel : C.bar))
      .attr("opacity", (d, i) => (inRange(i) ? 0.75 : 0.5));

    // THE RANGE ANNOTATES ITS OWN END POINTS. It used to sit inline in the filter row as
    // "1.8k-30k views/mo", which put a readout among the controls, cost ~110px of a row that also
    // holds the gender pills, and appeared and disappeared as you brushed. Under the handles it
    // says the same thing about the thing it describes, and the row stays still.
    //
    // The two are placed before the ticks because they win: a tick label they would collide with
    // is dropped, not overlapped. The axis reads 1 / 10 / 100 / 1k / 10k / 100k, so a selection
    // edge lands on one of those often enough that overlap is the normal case, not the corner.
    const half = t => (t.length * 5.6) / 2 + 3;                      // 10px digits, estimated
    const clamp = v => Math.max(half(fmt(v)), Math.min(w - half(fmt(v)), x(v)));
    const ends = range ? [{ v: range[0], x: clamp(range[0]) }, { v: range[1], x: clamp(range[1]) }]
                       : [];
    // A narrow brush puts both labels on the same few pixels. Push them apart rather than
    // stacking them: the pair still reads as the two ends of one selection.
    if (ends.length === 2) {
      const need = half(fmt(ends[0].v)) + half(fmt(ends[1].v)) + 4;
      const gap = ends[1].x - ends[0].x;
      if (gap < need) {
        const mid = (ends[0].x + ends[1].x) / 2;
        ends[0].x = Math.max(half(fmt(ends[0].v)), mid - need / 2);
        ends[1].x = Math.min(w - half(fmt(ends[1].v)), mid + need / 2);
      }
    }
    const ticks = [1, 10, 100, 1000, 10000, 100000]
      .filter(t => t >= edges[0] && t <= edges[BINS])
      .filter(t => !ends.some(e => Math.abs(x(t) - e.x) < half(fmt(t)) + half(fmt(e.v)) + 3));
    const tk = gAxis.selectAll("text").data(ticks);
    tk.exit().remove();
    tk.enter().append("text").attr("font-size", 10).attr("text-anchor", "middle").merge(tk)
      .attr("x", t => x(t)).attr("y", H + 11).attr("fill", C.axis).text(fmt);

    // Keyed by INDEX, not by value: a drag changes both numbers every frame, so a value key would
    // exit and re-enter two <text> nodes per frame instead of updating the two that are there.
    const en = gEnds.selectAll("text").data(ends);
    en.exit().remove();
    en.enter().append("text").attr("font-size", 10).attr("font-weight", 600)
      .attr("text-anchor", "middle").merge(en)
      .attr("x", d => d.x).attr("y", H + 11).attr("fill", C.sel).text(d => fmt(d.v));

    // The <svg> is role="img", so nothing drawn inside it reaches a screen reader — including the
    // two numbers above. The label carries the state instead, and #hist-read keeps the sentence.
    svg.attr("aria-label", range
      ? `Distribution of monthly Wikipedia readership; drag to filter by it. `
        + `Filtered to ${label()}.`
      : "Distribution of monthly Wikipedia readership; drag to filter by it");
  }

  function measure() {
    w = Math.max(160, Math.round(el.getBoundingClientRect().width));
    x = d3.scaleLog().domain([edges[0], edges[BINS]]).range([0, w]).clamp(true);
  }

  function build() {
    d3.select(el).selectAll("svg").remove();
    svg = d3.select(el).append("svg").attr("role", "img")
      .attr("aria-label", "Distribution of monthly Wikipedia readership; drag to filter by it");
    gBars = svg.append("g").attr("class", "bars");
    gAxis = svg.append("g").attr("class", "axis");
    gEnds = svg.append("g").attr("class", "ends");   // the selected range, under its own handles

    // handleSize 20 so the grab edges clear the ~44px touch-target floor without a wider brush.
    brush = d3.brushX().extent([[0, 0], [w, H]]).handleSize(20)
      // Live on "brush": the chart repaint is cheap and the whole point of the control is watching
      // the field thin out as you drag. The TABLE is rebuilt only on "end" — ~880 rows per frame
      // is the one thing here that would actually stutter.
      .on("brush", ev => emit(ev.selection, false))
      .on("end", ev => {
        if (!ev.selection) { range = null; draw(); cb && cb(null, true); return; }
        emit(ev.selection, true);
      });
    gBrush = svg.append("g").attr("class", "brush").call(brush);
  }

  function emit(sel, done) {
    range = sel ? [x.invert(sel[0]), x.invert(sel[1])] : null;
    draw();
    cb && cb(range, done);
  }

  function init(opts) {
    el = opts.el; cb = opts.onChange;
    readColors(); measure(); build(); draw();
  }

  function resize() {
    if (!svg) return;
    const prev = w;
    measure();
    if (w === prev) return;
    brush.extent([[0, 0], [w, H]]);
    gBrush.call(brush);
    if (range) gBrush.call(brush.move, [x(range[0]), x(range[1])]);
    draw();
  }

  function rerender() { readColors(); draw(); }

  // Programmatic set, used when a shared URL carries a range. Moving the brush fires "end", which
  // would write the hash again — harmless (replaceState with identical state) and it keeps the
  // control, the filter and the URL in agreement through one code path.
  function setRange(r) {
    if (!svg) return;
    if (!r) { gBrush.call(brush.move, null); return; }
    range = r;
    gBrush.call(brush.move, [x(r[0]), x(r[1])]);
  }

  function clear() { if (svg) gBrush.call(brush.move, null); }

  // Indices inside the current range, or null for "no filter" — the same shape Table.matches()
  // returns, so app.js can intersect them without special-casing either.
  function matches() {
    if (!range) return null;
    const set = new Set();
    for (const d of rows) if (d.views >= range[0] && d.views <= range[1]) set.add(d.i);
    return set;
  }

  function label() {
    if (!range) return "";
    return `${fmt(range[0])}–${fmt(range[1])} views/mo`;
  }

  return { init, setData, resize, rerender, setRange, clear, matches, label,
           // Shared with the detail panel (app.js) so the brush readout and the panel say a
           // readership the same way — "17k" in one place and "17,314" in the other reads as two
           // different measurements of two different things.
           fmt,
           getRange: () => range };
})();
