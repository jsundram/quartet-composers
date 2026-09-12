// pwa-starter: app.js @ d2fad01  (SW version-tag + shell top-up plumbing kept verbatim;
// the render/data half is this app's own — see the note at DATA below.)
//
// index.html owns structure, styles.css owns looks, chart.js and table.js own their views;
// app.js owns boot and the ONE piece of state they both read: which composer is selected.
//
// WHAT WAS DELIBERATELY DROPPED from the skeleton, and why — this app's data is a 17 KB JSON file
// precached in sw.js's SHELL, not a live cross-origin endpoint:
//   data.js         stale-while-revalidate against a network endpoint. There is no endpoint. A V
//                   bump is what refreshes composers.json, exactly as sw.js documents for
//                   precached JSON, so SWR would be machinery guarding nothing.
//   the #stale tag  same reason: the data can never be "cached and N minutes old".
//   pullToRefresh   a refresh gesture that can only re-read a file that cannot have changed is a
//                   spinner that lies. The version tag in the header is the real update path.
//   the poll +      likewise; visibilitychange still re-checks the SW VERSION (below), which is
//   resume re-pull  the thing that actually can go stale on an installed copy.

const VER_PREFIX = "quartets-v";   // must match sw.js's V stem — the numeric tail is load-bearing
const DATA_URL = "./composers.json";
// The readership HISTORY, and the only file this app can finish without. composers.json is a boot
// dependency — no chart, no table, no page — so the 884 monthly series that draw the sparkline are
// not in it: they are ten times the roster's size for one panel decoration. This file is precached
// like everything else (sw.js SHELL) but deliberately NOT a boot dep, is fetched AFTER the first
// paint, and if it never arrives the panel is exactly what it was before.
const HIST_URL = "./readership.json";
const WIKI = name => "https://en.wikipedia.org/w/index.php?search=" + encodeURIComponent(name);

let META = {}, ROWS = [], selected = null, hovered = null, visible = null;
let HIST = null;                   // {months, series:{name:[views|null,…]}} once it lands, else null
// "" = everyone. Otherwise a Wikidata P21 label, matched against the row verbatim — the control,
// the data and the URL all carry the same word, so there is no third vocabulary to keep in step.
let gender = "";
let byName = new Map();

const $ = id => document.getElementById(id);

// ---- selection: the single shared piece of state ---------------------------
// preview = a hover on a real pointer. It repaints the detail panel but does NOT pin, so moving
// the mouse away restores whatever was actually selected. On touch there is no preview at all.
function show(i, preview) {
  if (preview) { hovered = i; renderDetail(i == null ? selected : i, i != null); return; }
  selected = i;
  hovered = null;
  Chart.setSelected(i);
  Table.select(i, true);
  renderDetail(i, false);
  writeHash();
}

function selectFromTable(i) {
  selected = i;
  Chart.setSelected(i);
  Table.select(i, false);          // no scroll: the user is already looking at this row
  renderDetail(i, false);
  writeHash();
}

// ---- readership, stated to the precision it actually has --------------------
// The view count is a MEASURE, not a tally: a median of monthly totals, any one of which runs ~12%
// off typical. "186,772" claims six significant figures for a number that has two, and it is stale
// the next time fetch_views.py runs. So the panel quantizes to two figures and rounds DOWN — "180k+"
// survives a refresh (invariant 9).
//
// The TABLE keeps the exact figure: it sorts on that column, and a column reading "1.2k+" eleven times
// hides the ordering it was sorted by.
function twoSig(n, dir) {                       // dir: -1 rounds down, +1 rounds up
  if (n < 100) return Math.round(n);            // already two figures or fewer
  const p = Math.pow(10, Math.floor(Math.log10(n)) - 1);
  return (dir < 0 ? Math.floor(n / p) : Math.ceil(n / p)) * p;
}
// The median rounds DOWN, which is what makes the "+" true. The 12-month range rounds OUTWARD —
// never inward — so it cannot come out narrower than the spread actually was, and so the median
// always sits inside the range printed beside it. Rounding both bounds to nearest would let
// views=999, lo=995 print "990+ (1k–2k)", a median below its own low bound.
const atLeast = v => Histogram.fmt(twoSig(v, -1)) + "+";
const spread = (lo, hi) => `${Histogram.fmt(twoSig(lo, -1))}–${Histogram.fmt(twoSig(hi, 1))}`;

// ---- readership history ----------------------------------------------------
// One line per composer, over every month the pageviews API has. The panel's numbers answer "how much
// read, now"; this answers what they cannot — steady, climbing, or one obituary.
//
// LINEAR y, zero-based, unlike the chart's log readership axis: the log scale is there because the
// roster spans orders of magnitude BETWEEN composers, while within one composer the question is
// proportion and a log baseline flattens exactly the spike the line exists to show. Zero-based for the
// same reason — a min-max sparkline turns a steady composer's 5% wobble into a mountain range.
const SPARK_W = 240, SPARK_H = 34;      // viewBox units; the CSS stretches it to the panel width
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthName = m => MONTHS[+m.slice(5, 7) - 1] + " " + m.slice(0, 4);

async function loadHistory() {
  try {
    const res = await fetch(HIST_URL, { cache: "no-cache" });
    if (!res.ok) return false;
    const j = await res.json();
    if (!j || !j.series || !Array.isArray(j.months) || !j.months.length) return false;
    HIST = j;
    return true;
  } catch (e) {
    return false;                       // offline on a first run: no sparkline, nothing else lost
  }
}

// Contiguous runs of real values, as [x, y] point lists. A null is a BREAK, not a zero: an
// article that did not exist yet must not draw a line down to the floor and back (invariant 10).
function sparkRuns(vals, max) {
  const runs = [];
  let run = null;
  for (let i = 0; i < vals.length; i++) {
    if (vals[i] == null) { run = null; continue; }
    const x = (i / (vals.length - 1)) * SPARK_W;
    // 1 unit of headroom at each end so the stroke is not clipped by the viewBox at the extremes.
    const y = SPARK_H - 1 - (vals[i] / max) * (SPARK_H - 2);
    if (!run) { run = []; runs.push(run); }
    run.push([x, y]);
  }
  return runs;
}

const svgEl = (tag, attrs) => {
  const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  return n;
};

// WHAT THE CAPTION NAMES: the spike if there is one, otherwise the trend. A fixed "peak N× typical"
// was the wrong sentence for most of the roster — the median composer's biggest month is 3.1× their
// typical one, because a composer read thirty times a month hits ninety by chance, so it cried spike
// about noise on half the list, and it buried the real story for the steady ones (Haydn's peak is 1.7×
// and meaningless; his line has slid a third since 2015).
//
// So the test is the peak against the 95th PERCENTILE of that composer's own months — how far the
// biggest month towers over even a busy one — which is scale-free, judging a small noisy article
// against its own noise. At 3× it fires on 18% of the roster and selects almost entirely obituaries.
const SPIKE = 3;

// Percent change between the first and last twelve months of the record. Needs two full years to
// mean anything; below that there is a peak to name and no trend.
function trendOf(known) {
  if (known.length < 24) return null;
  const early = d3.median(known.slice(0, 12)), late = d3.median(known.slice(-12));
  if (!early) return null;
  return late / early - 1;
}

// Returns a fragment, or null when there is no history for this composer — one roster entry has
// no Wikidata item and so no page views at all, and a fresh clone has no readership.json yet.
function sparkline(name) {
  const vals = HIST && HIST.series[name];
  if (!vals) return null;
  const known = vals.filter(v => v != null);
  if (known.length < 2) return null;
  const max = Math.max(...known);
  // An all-zero series has no line to draw: every y is 0/0, so the path is "MNaN,NaN…" and renders
  // as nothing at all under a caption reading "peak Mar 2019 — 0". Not reachable in today's data
  // (five series contain a zero month; none is all zeros), but the roster is rebuilt from a scrape
  // every month and the obscure tail is where this would first appear.
  if (max === 0) return null;
  const typical = d3.median(known);
  const p95 = d3.quantile(known.slice().sort(d3.ascending), 0.95);
  const peakAt = vals.indexOf(max);
  // typical > 0 as well as p95 > 0: the multiple below divides by the MEDIAN, so an article with
  // more than half its months at zero and one busy month printed "Infinity× typical" — the
  // Infinity sails through the `>= 10` branch and Math.round leaves it intact. Failing the spike
  // test drops it to the trend branch, which states the peak with no ratio, which is the honest
  // answer when there is no typical month to compare against.
  const spike = p95 > 0 && typical > 0 && max / p95 >= SPIKE;
  const trend = spike ? null : trendOf(known);
  const runs = sparkRuns(vals, max);

  const frag = document.createDocumentFragment();
  // preserveAspectRatio="none" lets one viewBox fit every panel width without measuring the DOM;
  // non-scaling-stroke is what keeps the line 1px through that stretch. The markers are VERTICAL
  // hairlines for the same reason — a circle would come out an ellipse.
  const svg = svgEl("svg", {
    class: "spark", viewBox: `0 0 ${SPARK_W} ${SPARK_H}`, preserveAspectRatio: "none",
    role: "img", tabindex: "0", "data-keys": "own",   // see the document keydown handler
    // Describes the CONTROL, not the data: the caption below states the findings, and labelling
    // both would read them twice.
    "aria-label": "Monthly readership over time. Use the arrow keys to read a month.",
  });
  // The peak marker is drawn ONLY when the caption names the peak. A hairline pointing at a month
  // nothing mentions is an annotation with no referent — and on a steady line it points at what is
  // simply the tallest bit of noise.
  if (spike) {
    const peakX = ((peakAt / (vals.length - 1)) * SPARK_W).toFixed(1);
    svg.appendChild(svgEl("line", { class: "spark-peak", x1: peakX, x2: peakX, y1: 0, y2: SPARK_H }));
  }
  for (const run of runs) {
    const d = run.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");
    svg.appendChild(svgEl("path", {
      class: "spark-area",
      d: `${d}L${run[run.length - 1][0].toFixed(1)},${SPARK_H}L${run[0][0].toFixed(1)},${SPARK_H}Z`,
    }));
    svg.appendChild(svgEl("path", { class: "spark-line", d, "vector-effect": "non-scaling-stroke" }));
  }
  const cursor = svgEl("line", { class: "spark-cursor", x1: 0, x2: 0, y1: 0, y2: SPARK_H });
  svg.appendChild(cursor);
  frag.appendChild(svg);

  // The span is stated as the RECORD's, not as the axis's. Every sparkline shares one month axis
  // so two composers are comparable, which means an article created in 2025 draws a line over the
  // last tenth of the box and leaves nine tenths blank — and blank under a line chart reads as
  // ZERO. 61 composers here are in that position. Saying "from Jul 2025" is what makes the empty
  // stretch mean "not written yet" instead of "nobody read it".
  const ax = document.createElement("p");
  ax.className = "spark-ax";
  const label = document.createElement("span"), span = document.createElement("span");
  label.textContent = "Monthly readers";
  const firstAt = vals.findIndex(v => v != null);
  span.textContent = firstAt === 0
    ? `${HIST.months[0].slice(0, 4)}–${HIST.months[HIST.months.length - 1].slice(0, 4)}`
    : `from ${monthName(HIST.months[firstAt])}`;
  ax.appendChild(label); ax.appendChild(span);
  frag.appendChild(ax);

  // EXACT counts here, and rounded ones in the <dl> above. Not an inconsistency: that number is
  // the MEDIAN, a smoothed estimate whose last four figures are noise, so it prints "2.7k+"
  // (invariant 9). A month on this line is a raw tally of one month — the same kind of number the
  // table carries exactly because it sorts on it — and rounding the thing you hovered to read
  // defeats the hovering.
  const summary = spike
    ? `peak ${monthName(HIST.months[peakAt])} — ${max.toLocaleString()}, `
      + `${max / typical >= 10 ? Math.round(max / typical) : (max / typical).toFixed(1)}× typical`
    : trend == null
      ? `peak ${monthName(HIST.months[peakAt])} — ${max.toLocaleString()}`
      : Math.abs(trend) < 0.1
        ? `steady since ${HIST.months[firstAt].slice(0, 4)}`
        : `${trend < 0 ? "down" : "up"} ${Math.round(Math.abs(trend) * 100)}% `
          + `since ${HIST.months[firstAt].slice(0, 4)}`;
  const cap = document.createElement("p");
  cap.className = "spark-cap";
  cap.textContent = summary;
  frag.appendChild(cap);

  // ---- reading a single month -----------------------------------------------------------
  // The readout REPLACES the caption rather than adding a line: the compact panel reserves a
  // fixed height for a hover preview (styles.css), so a box that grew under the pointer would
  // pump the legend below it — the same constraint the full-screen strip is built around.
  let at = -1;
  const show_ = i => {
    if (i === at) return;
    at = i;
    cursor.setAttribute("x1", ((i / (vals.length - 1)) * SPARK_W).toFixed(1));
    cursor.setAttribute("x2", ((i / (vals.length - 1)) * SPARK_W).toFixed(1));
    cursor.classList.add("on");
    cap.textContent = `${monthName(HIST.months[i])} · `
      + (vals[i] == null ? "no data" : vals[i].toLocaleString());
  };
  const clear_ = () => { at = -1; cursor.classList.remove("on"); cap.textContent = summary; };
  const fromX = e => {
    const r = svg.getBoundingClientRect();
    if (!r.width) return;
    const i = Math.round(((e.clientX - r.left) / r.width) * (vals.length - 1));
    show_(Math.max(0, Math.min(vals.length - 1, i)));
  };
  svg.addEventListener("pointermove", fromX);
  // A tap is a read too. On touch it STAYS up — pointerleave fires the moment the finger lifts, so
  // restoring there would make a tap flash the answer and take it away.
  svg.addEventListener("pointerdown", fromX);
  svg.addEventListener("pointerleave", e => { if ((e.pointerType || "mouse") === "mouse") clear_(); });
  // The keyboard path is the same readout, not a second mechanism. It is a READ-ONLY value
  // stepper, which is why arrow keys are right here and wrong for the readership brush (TODO):
  // there is no form control this reinvents.
  svg.addEventListener("focus", () => show_(peakAt));
  svg.addEventListener("blur", clear_);
  svg.addEventListener("keydown", e => {
    const step = { ArrowLeft: -1, ArrowRight: 1, Home: -Infinity, End: Infinity }[e.key];
    if (step === undefined) return;
    e.preventDefault();                  // ArrowLeft/Right would scroll the panel's box sideways
    const base = at < 0 ? peakAt : at;
    show_(Math.max(0, Math.min(vals.length - 1, step === -Infinity ? 0
      : step === Infinity ? vals.length - 1 : base + step)));
  });
  return frag;
}

// ---- detail panel ----------------------------------------------------------
// Percentile among the rows that HAVE the value. Counting nulls as zero would tell a composer
// with 3 quartets that they out-wrote the 105 composers whose count simply couldn't be read.
function pct(d, key) {
  if (d[key] == null) return null;
  const known = ROWS.filter(o => o[key] != null);
  const below = known.reduce((n, o) => n + (o[key] < d[key] ? 1 : 0), 0);
  // FLOOR, not round: the most-read composer beats 883 of 884, and rounding 99.9 printed "more
  // read than 100%" — a claim about the whole list that includes them, and so can't be true.
  return Math.floor((below / known.length) * 100);
}

// TIGHT is the full-screen strip: two lines in a fixed-height box above the chart, where every
// pixel it takes is a pixel of chart. It drops the percentile line, the Wikipedia link, Prev/Next
// and the 12-month range beside the median — all of which are back the moment you leave full
// screen. Fixed height and always present is the point: see placeDetail.
const tight = () => $("detail").classList.contains("compact")
                 && document.body.classList.contains("fs");

function renderDetail(i, preview) {
  const el = $("detail");
  const lean = tight();
  el.innerHTML = "";
  el.classList.toggle("on", i != null);      // .compact is hidden until something IS selected
  if (i == null) {
    const p = document.createElement("p");
    p.className = "empty";
    // The DOTS, not the roster: this sits beside the chart, so counting the 94 composers the
    // list page never gives a quartet count described a picture they are not in — and dated it
    // from a 1582 birth the x axis has no room for. The roster's own total is in #count and the
    // difference is explained in the provenance line.
    const st = Chart.plottedStats();
    p.textContent = lean
      ? "Select a dot for the details."
      : `${st.n} composers are plotted, born ${st.from}–${st.to}. `
        + `${st.living} are still living. Select a dot or a row for the details.`;
    el.appendChild(p);
    return;
  }
  const d = ROWS[i];

  const h = document.createElement("h2");
  h.textContent = d.name;
  el.appendChild(h);

  const dates = document.createElement("p");
  dates.className = "dates";
  // Age is read off the clock, not baked at build time, so a cached copy stays right next year.
  const life = d.living
    ? `b. ${d.birth} · living, age ${new Date().getFullYear() - d.birth}`
    : `${d.birth}–${d.death} · lived ${d.lifespan} years`;
  // In the strip the two <dl> rows collapse onto this line — one wrapped line beats a labelled
  // grid when the whole box is two lines tall.
  dates.textContent = lean
    ? [life,
       d.quartets == null ? "quartet count not stated" : `${d.quartets} quartet${d.quartets === 1 ? "" : "s"}`,
       d.views == null ? "no readership data" : `${atLeast(d.views)} readers/mo`].join(" · ")
    : life;
  el.appendChild(dates);
  if (lean) { navRow(el, preview, true); return; }

  const dl = document.createElement("dl");
  const add = (k, v) => {
    const dt = document.createElement("dt"); dt.textContent = k;
    const dd = document.createElement("dd"); dd.textContent = v;
    dl.appendChild(dt); dl.appendChild(dd);
  };
  add("Quartets", d.quartets == null ? "not stated on the list" : d.quartets);
  // The median, with its own 12-month range beside it — the spread is part of the measurement,
  // and hiding it implies a precision a page-view count does not have.
  add("EN readers / mo", d.views == null ? "no data"
      : `${atLeast(d.views)}  (${spread(d.lo, d.hi)})`);
  el.appendChild(dl);

  // Not in the full-screen strip: `lean` has already returned above. Its height is fixed because
  // #plot is flex:1 there, so anything that grows on select re-lays out the chart under the
  // finger that just tapped it.
  const spark = sparkline(d.name);
  if (spark) el.appendChild(spark);

  const rank = document.createElement("p");
  rank.className = "rank";
  const parts = [];
  const pq = pct(d, "quartets"), pv = pct(d, "views");
  if (pq != null) parts.push(`more quartets than ${pq}% of the list`);
  if (pv != null) parts.push(`more read than ${pv}%`);
  if (d.quartets == null) parts.push("not plotted — the list page doesn't state a count");
  rank.textContent = parts.join(" · ") + ".";
  el.appendChild(rank);

  const a = document.createElement("a");
  a.href = WIKI(d.name);
  a.target = "_blank";
  a.rel = "noopener";
  a.textContent = "Wikipedia →";
  a.style.fontSize = "13px";
  el.appendChild(a);

  navRow(el, preview, false);
}

// Prev/Next step through the table's order and are worth their width in the panel; in the strip
// only Clear survives, and it stays put during a hover preview so the one control there does not
// blink in and out as the pointer crosses the field.
function navRow(el, preview, lean) {
  if (preview && !(lean && selected != null)) return;
  const nav = document.createElement("div");
  nav.className = "detail-nav";
  if (!lean) {
    nav.appendChild(navBtn("‹ Prev", -1));
    nav.appendChild(navBtn("Next ›", 1));
  }
  const clear = navBtn("Clear", 0);
  clear.onclick = () => show(null, false);
  nav.appendChild(clear);
  el.appendChild(nav);
}

function navBtn(label, step) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "btn";
  b.textContent = label;
  if (step) b.onclick = () => step_(step);
  return b;
}

// Step through the TABLE's current order, not the raw data order — so after sorting by quartets,
// "next" means the next-most-prolific composer, which is what the user just asked to see.
function step_(dir) {
  const order = Table.ordered();
  if (!order.length) return;
  const at = order.indexOf(selected);
  const next = at === -1 ? (dir > 0 ? 0 : order.length - 1)
                         : (at + dir + order.length) % order.length;
  show(order[next], false);
}

// ---- legend ----------------------------------------------------------------
// Rebuilt on every theme change: the ramp is painted from the same JS-read tokens chart.js bakes
// into the dots, so a legend built once would drift out of agreement with the chart in dark mode.
function renderLegend() {
  const g = Theme.getCssColor;
  const el = $("legend");
  el.innerHTML = "";

  // The views do not encode the same things, so they cannot share a key. In the Fame view
  // size means nothing (readership is the y axis) and hue is emphasis, not lifespan — showing
  // the lifespan ramp and a size key there would label channels that are not carrying anything.
  if (Chart.getMode() === "fame") {
    const who = document.createElement("div");
    who.innerHTML =
      `<div class="swatches">` +
        `<span class="sw"><i style="background:${g("--sel")}"></i>` +
        // The FILL follows the filter now too, so the key that names it has to come from the same
        // place as the list -- see chart.js's REPERTOIRES. Hardcoding "the repertoire" here would
        // caption nine women as the set that contains Mozart.
        `${Chart.repertoireLabel()}</span>` +
        `<span class="sw"><i style="box-shadow:inset 0 0 0 2px ${g("--accent")}"></i>` +
        `some standouts</span>` +
        `<span class="sw"><i style="background:${g("--muted")};opacity:.3"></i>` +
        `the rest</span>` +
      `</div>`;
    el.appendChild(who);

    return;
  }

  const life = document.createElement("div");
  life.innerHTML =
    `<span class="lab">Lifespan</span>` +
    `<div class="ramp" style="background:linear-gradient(90deg,${g("--c-short")},${g("--c-mid")},${g("--c-long")})"></div>` +
    `<div class="ticks"><span>${Chart.lifeDomain()[0]} yrs</span>` +
    `<span>${Chart.lifeDomain()[2]} yrs</span></div>`;
  el.appendChild(life);

  // Size key. Circle AND label are laid out together in one SVG, each pair centred in a cell as
  // wide as the WIDER of the two. The old version stepped from circle to circle and then spread
  // the three numbers with `justify-content:space-between` over the same total width — two
  // different layouts for one row, so on a phone (where the circles shrink but the text does not)
  // the labels closed up into "1005k150k".
  const KEYS = [100, 5000, 150000];
  const lab = v => (v >= 1000 ? Math.round(v / 1000) + "k" : String(v));
  const FS = 10.5;                                   // px; ~0.62em per digit in the system UI font
  const rs = KEYS.map(v => Chart.radiusOf(v));
  const rMax = Math.max(...rs);
  const base = rMax * 2;                             // circles sit ON this line, biggest last
  let cx = 0, body = "";
  for (let k = 0; k < KEYS.length; k++) {
    const cell = Math.max(rs[k] * 2, lab(KEYS[k]).length * FS * 0.62) + 12;
    const c = cx + cell / 2;
    body += `<circle cx="${c.toFixed(1)}" cy="${(base - rs[k]).toFixed(1)}" r="${rs[k].toFixed(1)}" `
          + `fill="none" stroke="${g("--muted")}" stroke-width="1"/>`
          + `<text x="${c.toFixed(1)}" y="${(base + 13).toFixed(1)}" text-anchor="middle" `
          + `font-size="${FS}" fill="${g("--muted")}">${lab(KEYS[k])}</text>`;
    cx += cell;
  }
  const size = document.createElement("div");
  // The SVG is aria-hidden, so the three key values live again in a visually-hidden sentence —
  // moving them from a <div class="ticks"> into <text> nodes took the size key's only
  // quantitative content out of the accessibility tree, while the ramp above kept its readable
  // ticks. A screen reader heard the label and then nothing.
  size.innerHTML =
    `<span class="lab">EN Wikipedia readers / mo</span>` +
    `<svg width="${Math.ceil(cx)}" height="${Math.ceil(base + 17)}" aria-hidden="true" `
      + `style="display:block">${body}</svg>` +
    `<span class="sr-only">Circle area shows monthly readers; the keys drawn are `
      + `${KEYS.map(lab).join(", ")}.</span>`;
  el.appendChild(size);
}

// ---- where the detail panel lives -------------------------------------------
// Beside the chart in the second grid column on a wide screen; below 900px that column is a whole
// screen-height away, and in full screen it is display:none, so a tap produced no visible answer at
// all. On a phone, and in full screen at any width, the SAME element moves into the chart card —
// moved, never a second copy, so there is one selection and one set of Prev/Next buttons.
//
// The two in-card positions are NOT interchangeable:
//   phone, in flow   BELOW the plot, free to grow: nothing above it moves when it does.
//   full screen      ABOVE the plot at a FIXED height, drawn whether or not anything is pinned.
//                    Every pixel there is a pixel of chart, and a box that changed size would
//                    re-lay out the chart under the finger that just tapped it.
const WIDE = matchMedia("(min-width:900px)");

// The filter row is a sibling of .grid, which body.fs hides outright — so in full screen it moves
// into the chart card, where CSS drops its search half and keeps the readership brush. Same move
// as placeDetail, and it must run first so the two land in the right order.
function placeFilters() {
  const f = $("filters"), viz = $("viz");
  const fs = document.body.classList.contains("fs");
  const parent = fs ? viz : document.querySelector("main");
  // firstElementChild, whatever it happens to be — it is `.controls` now that those precede the
  // plot (issue 29), and it does not matter which: full screen lays #viz out with an explicit
  // `order` per child, so the DOM position only breaks ties between equal orders and this one has
  // none. placeDetail() below is the function that IS coupled to a specific sibling.
  const before = fs ? viz.firstElementChild : document.querySelector(".grid");
  if (f.parentNode === parent && f.nextElementSibling === before) return;
  parent.insertBefore(f, before);
}

// The third of these, on the same contract as placeFilters() and placeDetail(): one element, moved,
// never a second copy — #fs holds the pressed state and share() a timeout on its own label. They
// leave the row wherever it will not hold them on one line, which is what PAYS for Reset filters
// beside Reset zoom; CLAUDE.md's placeChartTools() bullet carries the rest of the why.
//
// THE ONLY COPY OF THIS BREAKPOINT: styles.css scopes the icon look to `#plot > #chart-tools`, so the
// look follows the DOM rather than re-deciding the width. Answering on width here drew the icon look
// in the row in every state where this had not run yet.
//
// TWO intervals, because the row's width is not monotonic in the viewport's: what decides it is the
// CARD, and the two-column grid at 900px takes 194px off that. Measured with the words in the row,
// stepping 4px; the parenthesised numbers allow for share()'s wider "Link copied", which is the state
// that matters — a row that wraps on the PRESS drops the plot 44px under the cursor:
//
//     641- 743   card  582- 681   two lines
//     744- 899   card  682- 837   ONE line (780 up)
//     900-1055   card  524- 679   two lines
//     1056+      card  680+       ONE line (1092 up)
//
// Both thresholds err toward ICONS, because the two mistakes are not equal: words that do not fit is
// that 44px shift, icons where words would have fitted costs 26px of data height and nothing else.
// One machine's font metrics, so ui.test.mjs presses Share at the first width in each band and fails
// if the row grows.
//
// TWO queries rather than one list, because only the second is about the grid: `body.fs .grid` is
// `display:block`, so full screen never pays the 194px and the squeezed interval is skipped there —
// it would spend the band off a flex:1 chart that is already the whole viewport.
const NARROW = matchMedia("(max-width:799px)");
const SQUEEZED = matchMedia("(min-width:900px) and (max-width:1100px)");
const iconsOnPlot = () =>
  NARROW.matches || (SQUEEZED.matches && !document.body.classList.contains("fs"));

// 40px of touch target, CENTRED on the axis title's line, with the whole target clear of the plot
// area. styles.css carries the derivation from the title's own box; what matters here is that the
// clearance is not cosmetic. The target is INVISIBLE, so anything it overlaps is a dot that silently
// stops being tappable — one pixel lower it shadowed 12 dots in the swarm, whose blob reaches the top
// of its box. Nothing is left over: a dot's clip is inset outward by a radius, so the sliver of an
// edge dot can still reach under the target during a pinch, though never its centre.
const TOOLS_BAND = 48;

function placeChartTools() {
  const tools = $("chart-tools"), viz = $("viz");
  const onPlot = iconsOnPlot();
  const parent = onPlot ? $("plot") : viz.querySelector(".controls");
  Chart.setTopReserve(onPlot ? TOOLS_BAND : 0);
  if (tools.parentNode === parent) return;
  parent.appendChild(tools);
}

function placeDetail() {
  const det = $("detail"), viz = $("viz");
  const fs = document.body.classList.contains("fs");
  const inCard = !WIDE.matches || fs;
  det.classList.toggle("compact", inCard);
  const parent = inCard ? viz : document.querySelector(".grid");
  // Anchored on the LEGEND, not on the controls: those moved above the plot (issue 29), and an
  // anchor that follows them would drop the panel above the chart it is answering about.
  const before = inCard ? (fs ? $("plot") : viz.querySelector(".legend")) : null;
  if (det.parentNode === parent && det.nextElementSibling === before) return;
  parent.insertBefore(det, before);            // insertBefore(x, null) === appendChild
  renderDetail(selected, false);               // the strip and the panel say different things
}

// ---- shareable state -------------------------------------------------------
// The URL carries the view, the search, and the pinned composer, so "look at this one" is a link
// rather than a paragraph of instructions. replaceState, not pushState: panning through composers
// shouldn't build a back-button history the reader has to escape one press at a time.
//
// The composer is keyed by NAME, not by row index. An index would silently point at a different
// person the first time scripts/fetch_views.py changes the row count — the classic way a shared
// link rots without anyone noticing it rotted.
function writeHash() {
  const p = new URLSearchParams();
  if (Chart.getMode() !== Chart.defaultMode()) p.set("v", Chart.getMode());
  const q = $("q").value.trim();
  if (q) p.set("q", q);
  const r = Histogram.getRange();
  if (r) p.set("r", Math.round(r[0]) + "-" + Math.round(r[1]));
  if (gender) p.set("g", gender);
  if (selected != null) p.set("c", ROWS[selected].name);
  const s = p.toString();
  history.replaceState(null, "", s ? "#" + s : location.pathname + location.search);
}

function readHash() {
  const p = new URLSearchParams(location.hash.replace(/^#/, ""));
  const r = (p.get("r") || "").match(/^(\d+)-(\d+)$/);
  return { v: p.get("v"), q: p.get("q") || "", c: p.get("c"),
           r: r ? [+r[1], +r[2]] : null,
           // Whitelisted, not trusted: a hand-edited #g=anything would otherwise leave three
           // unpressed pills over an empty table with no visible reason and no way back. The
           // whitelist is READ OFF THE PILLS rather than written out again — a second copy of the
           // vocabulary here is a copy that can disagree with the control it is filtering for.
           g: pillValues().includes(p.get("g")) ? p.get("g") : "" };
}

// The buttons that carry an icon keep their words in a `.btn-t` span, so writing a new label means
// writing to the SPAN. `btn.textContent = "..."` would replace every child, icon included — the
// same shape of trap as setProv() dropping its links, and it fails identically: silently, and only
// in the icon layout, where the icon is the visible half.
//
// The `title` goes with it. In the icon layout the span is clipped, so on a real pointer the
// tooltip is the only NAME a reader can get at — and that name is the one thing the words were
// still buying where the row had room for them. Written here rather than left in the markup
// because #fs's label changes with its state: a tooltip that still said "Full screen" over the
// exit glyph would be worse than none. One call, so the two can never disagree.
//
// Unconditionally, even where the word beside it is visible: scoping it to the clipped layout means
// asking which layout this is, a second copy of a breakpoint that lives in one place — and a tooltip
// echoing a visible label is what a browser does anyway.
function label(btn, text) {
  const t = btn.querySelector(".btn-t");
  if (!t) { btn.textContent = text; return; }
  t.textContent = text;
  btn.title = text;
}

// How long a clipboard write may take before the button acknowledges anyway. Past about a second
// with no feedback the control reads as dead, which is the failure this whole pair of branches is
// written to avoid; the URL bar is showing the link either way.
const STALL = 1000;

async function share() {
  const btn = $("share");
  writeHash();
  const payload = { title: document.title, url: location.href };
  // navigator.share is the right affordance on a phone (it opens the real share sheet) but is
  // absent or blocked on most desktops, and it REJECTS on user-cancel — which must not read as a
  // failure. Clipboard is the fallback, and the visible confirmation is the point either way.
  try {
    if (navigator.share) { await navigator.share(payload); return; }
    // A WRITE THAT NEVER SETTLES IS NOT A REJECTION, and there is no catch for one. Chrome under a
    // bare X server leaves writeText pending indefinitely — measured on this repo's own CI runner,
    // the promise still pending four seconds after the press. An unraced await is a Share button that
    // promises nothing, on a platform nobody would think to test.
    await Promise.race([navigator.clipboard.writeText(location.href),
                        new Promise((_, no) => setTimeout(no, STALL))]);
    copied(btn);
  } catch {
    copied(btn);                          // clipboard blocked: the URL bar already shows the link
  }
}

// The confirmation, in both halves of the button: in the icon layout .btn-t is the accessible NAME
// and not the face, so swapping its text wrote "Link copied" where nobody could see it. Never a
// phone-only gap — navigator.share returns before either branch on a real phone, so the branches that
// reach here are the ones that run where it is missing.
function copied(btn) {
  label(btn, "Link copied");
  btn.classList.add("copied");
  setTimeout(() => { label(btn, "Share"); btn.classList.remove("copied") }, 1600);
}

// ---- filters ---------------------------------------------------------------
// Two independent filters — the search box and the readership brush — combined by intersection.
// Neither knows the other exists; both hand back "a Set of indices, or null for everything", so
// this is the only place that has to reason about them together.
function intersect(a, b) {
  if (!a) return b;
  if (!b) return a;
  const out = new Set();
  for (const i of a) if (b.has(i)) out.add(i);
  return out;
}

// index.html's pills ARE the vocabulary: the values the UI can filter, read back rather than
// listed a second time anywhere in here.
const pillValues = () => [...document.querySelectorAll("#gender button")]
  .map(b => b.dataset.g).filter(Boolean);

// Every gender the data STATES that no pill can reach. fetch_wikidata.py labels more P21 items than
// index.html has pills, so the vocabularies can drift, and the drift is silent in the worst way: the
// composer is in neither filter while the provenance line, which counts only the composers with NO
// claim, implies everyone else is reachable. validate.py fails the build on it; this is the same
// assertion on the app's side, the job Chart.missingNames() does for the curated lists.
function unfilterableGenders() {
  const reach = new Set(pillValues());
  return [...new Set(ROWS.filter(d => d.gender != null && !reach.has(d.gender)).map(d => d.gender))];
}

// The same assertion one vocabulary over. chart.js keys its curated repertoires by gender pill
// VALUE, so a key no pill can reach is a list that can never be shown — silent in exactly the way
// an unreachable P21 value is, and worse, because the list looks maintained. The UI suite asserts
// this empty alongside Chart.missingNames() and Names.staleOverrides().
function unreachableRepertoires() {
  const reach = new Set(pillValues());
  return Chart.repertoireKeys().filter(k => !reach.has(k));
}

// The third filter, and the only one with no module of its own: nothing to render and no data to hold,
// three buttons and a string. Same contract as the other two, so intersect() never learns it exists.
//
// A composer with no P21 claim is in NEITHER set — the null rule (invariant 10) applied to a filter:
// "Women" means Wikidata says female, not "everyone we didn't call a man".
function genderMatches() {
  if (!gender) return null;
  const set = new Set();
  for (const d of ROWS) if (d.gender === gender) set.add(d.i);
  return set;
}

// The three filters, asked as one question. Read from the same places applyFilters() intersects, so
// a fourth filter that forgets to appear here leaves the button dark while it is active.
// TRIMMED, like Table.matches() itself, or the two answers disagree: a lone space (one stray tap
// on a phone, or a word deleted back to its leading space) filters nothing and leaves #count at
// "884 composers" while this lit the button accent-filled.
function anyFilter() {
  return !!$("q").value.trim() || !!Histogram.getRange() || !!gender;
}

// All three, search included: the name is plural and a typed query is a filter. The search box keeps
// its own × for clearing just the text.
//
// It does NOT focus the search box afterwards, though #clear does: #clear sits INSIDE the search row,
// so the focus it moves is already on screen, while this button is a card below, where focus() scrolls
// the viewport back up and opens the soft keyboard over a box the reader had left. In full screen #q
// is hidden outright, so the call would be a no-op.
//
// Exactly ONE applyFilters() runs, which is what the branch is for: d3-brush emits "end" for a
// programmatic move, so Histogram.clear() comes back through onChange on its own and calling it too
// would rebuild every table row twice. With no range there is nothing to emit.
function resetFilters() {
  $("q").value = "";
  setGender("", false);
  if (Histogram.getRange()) Histogram.clear();
  else applyFilters(true);
}

function setGender(g, apply = true) {
  gender = g;
  document.querySelectorAll("#gender button").forEach(b =>
    b.setAttribute("aria-pressed", String(b.dataset.g === g)));
  // The Fame view fills a CURATED set, and which one it should be filling is a function of who is
  // on screen: every name in the default repertoire is a man, so "Women" filled nothing until
  // chart.js gained a second list. Handing over the pill's raw value keeps the mapping in one
  // place -- chart.js falls back to the default for any value it has no list for, which is what
  // makes the women's set appear under that filter and nowhere else.
  Chart.setRepertoire(g);
  if (apply) applyFilters(true);
}

// `settled` is false during a brush DRAG. The chart repaint is cheap and watching the field thin
// out is the whole point of the control, but rebuilding ~880 table rows every frame is the one
// thing here that stutters — so the table waits for the gesture to end.
function applyFilters(settled) {
  const q = $("q").value;
  visible = intersect(intersect(Table.matches(q), Histogram.matches()), genderMatches());
  $("clear").hidden = !q;
  $("hist-read").textContent = Histogram.label();
  // ABOVE the guard on purpose, unlike the button this replaced: `disabled` and a class change
  // nothing about any box, so tracking the brush live is free feedback rather than a control that
  // moves under the finger dragging it. That is the whole reason this button lives in .controls and
  // is never hidden — see resetFilters() and issue 35.
  const on = anyFilter();
  $("reset-filters").disabled = !on;
  $("reset-filters").classList.toggle("on", on);
  // `settled` travels with it: the chart closes its frame in on what the filter kept, and that
  // must happen once at the end of a brush drag, not on every frame of one.
  Chart.setFilter(visible, settled);

  const n = visible ? visible.size : ROWS.length;
  $("count").textContent = visible ? `${n} of ${ROWS.length}` : `${ROWS.length} composers`;
  if (settled !== false) {
    // Inside the guard, not above it: appearing on the first frame of a brush drag would make this a
    // box that the press it is reacting to resizes. It shared line one of `.filterbar` with the
    // "Readership" label, so unhiding it dropped the brush 22.6px under the finger, with the pills and
    // the view switcher going too (#31). Waiting for the gesture costs nothing — the only caller that
    // passes false is Histogram's own mid-drag `onChange`, and the `#r=` deep link boots through
    // applyFilters(true).
    //
    // Its two siblings ABOVE the guard are safe, and the split is the first thing a reader will
    // question: `#hist-read` is `.sr-only`, so it writes into a box with no layout, and `#count` only
    // ever shortens, so `.tablehead` cannot gain a line. A third live write that HAS a box belongs
    // below the guard with this one.
    // The ring is derived from the filtered group, so the key that explains it and the row chips
    // that repeat it both move when the filter does. Table.render() repaints the chips anyway.
    renderLegend();
    Table.render(visible);
    // A pinned composer that a filter just excluded would leave a detail panel describing someone
    // invisible in both views. Drop the pin rather than the coherence.
    if (selected != null && visible && !visible.has(selected)) show(null, false);
    else Table.select(selected, false);
    writeHash();
  }
}

// ---- provenance ------------------------------------------------------------
// "Dates are Wikidata P569/P570" names a source a reader cannot check: P569 is jargon that means
// nothing until you can open it, and there is nowhere on the page to look it up. So every property
// id in the provenance line becomes a link to its own Wikidata definition.
//
// The LINE is linkified, rather than the two meta strings carrying anchors. composers.json is data
// and has no business holding markup; keeping the ids as plain text there means the pipeline can
// name a new property (P?? for a birthplace, say) and it is linked the moment it is printed,
// without a second place to remember. It is also why this builds nodes instead of setting
// innerHTML: the text is assembled from the data file, and data never becomes markup here.
const WD_PROP = /\bP[1-9]\d{0,6}\b/g;

// A part is either a STRING, scanned for property ids as above, or an explicit {text, href,
// title} anchor. Parts rather than a markup syntax in the string: the rule one paragraph up is
// that data never becomes markup here, and a line that parsed brackets would be parsing a string
// assembled from composers.json. It also keeps the two kinds of link honest about which is
// derived — the property links are found by pattern and cannot be forgotten, the list link is
// written once at the call site because there is exactly one of it.
function setProv(...parts) {
  const el = $("prov");
  el.textContent = "";
  for (const part of parts) {
    if (typeof part === "string") linkifyProps(el, part);
    else el.appendChild(anchor(part.text, part.href, part.title));
  }
}

function anchor(text, href, title) {
  const a = document.createElement("a");
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener";
  a.title = title;
  a.textContent = text;
  return a;
}

function linkifyProps(el, text) {
  let at = 0;
  for (const m of text.matchAll(WD_PROP)) {
    if (m.index > at) el.appendChild(document.createTextNode(text.slice(at, m.index)));
    // The id is the link text, so the sentence reads exactly as it did — and the title says what
    // the link is for, because "P569" is not a promise a reader can evaluate before clicking.
    el.appendChild(anchor(m[0], "https://www.wikidata.org/wiki/Property:" + m[0],
                          "Wikidata property " + m[0] + " — what this value means and where it comes from"));
    at = m.index + m[0].length;
  }
  el.appendChild(document.createTextNode(text.slice(at)));
}

// ---- full screen -----------------------------------------------------------
// CSS-first (see styles.css): iPhone Safari has no Fullscreen API, and that is the device this
// feature exists for. The API call is an ADDITIVE nicety where it exists — it drops the browser
// chrome too — and its failure is ignored, never surfaced.
function setFull(on) {
  document.body.classList.toggle("fs", on);
  placeFilters();                    // both are hidden by the full-screen layout where they live
  placeChartTools();
  placeDetail();
  $("fs").setAttribute("aria-pressed", String(on));
  label($("fs"), on ? "Exit full screen" : "Full screen");
  if (on && document.documentElement.requestFullscreen) {
    document.documentElement.requestFullscreen().catch(() => {});
  } else if (!on && document.fullscreenElement && document.exitFullscreen) {
    document.exitFullscreen().catch(() => {});
  }
  requestAnimationFrame(() => Chart.resize());
}

// ---- boot ------------------------------------------------------------------
async function load() {
  const res = await fetch(DATA_URL, { cache: "no-cache" });
  if (!res.ok) throw new Error("HTTP " + res.status);
  const j = await res.json();
  if (!j || !Array.isArray(j.rows) || !j.rows.length) throw new Error("empty payload");
  return j;
}

async function start() {
  let data;
  try {
    data = await load();
  } catch (e) {
    $("plot").innerHTML = "";
    const p = document.createElement("p");
    p.className = "hint";
    p.textContent = "Couldn't load composers.json. Reload with a connection once and this page "
      + "works offline afterwards.";
    $("plot").appendChild(p);
    return;
  }
  META = Object.assign({ views_months: [], views_note: "monthly English Wikipedia page views",
                         views_stat: "median", dates_source: "Wikidata", generated: "",
                         gender_source: "Wikidata P21, \u201csex or gender\u201d" },
                       data.meta || {});

  // FIRST: both the chart's labels and the table's name column are shortened by names.js, and it
  // needs the whole roster to know which surnames are shared. Neither module can display a name
  // before this runs.
  // Readership comes with the names: a surname only one composer is read for is printed bare on
  // the chart (DOMINANT_VIEWS there), which is a fact about the roster, not about one row.
  Names.setData(data.rows.map(r => r[0]), data.rows.map(r => r[4]));

  Chart.setData(data.rows);
  Chart.init({
    el: $("plot"),
    flag: $("flag"),
    onHover: i => show(i, true),
    // fromZoom = a repaint after a pan/zoom, not a click. It must not disturb the pin, but it
    // does need the table row and detail panel left exactly as they are.
    onSelect: i => show(i, false),
    onZoom: on => { $("reset").disabled = !on; },
  });
  // chart.js keeps its own decorated copy (jitter, radius); this is the plain one the table and
  // detail panel read. Both are indexed identically, and that index IS the shared selection key.
  ROWS = data.rows.map((r, i) => ({
    i, name: r[0], birth: r[1], death: r[2], quartets: r[3],
    views: r[4], lo: r[5], hi: r[6], gender: r[7],
    living: r[2] == null,
    lifespan: r[2] == null ? null : r[2] - r[1],
  }));

  // Loud, the way chart.js is about a renamed canon: the UI suite fails on a console error, so a
  // P21 value the pills cannot reach cannot ship quietly. See unfilterableGenders().
  const unreachable = unfilterableGenders();
  if (unreachable.length) console.error("app: genders no pill can filter:", unreachable);
  const orphanSets = unreachableRepertoires();
  if (orphanSets.length) console.error("app: curated sets no pill can reach:", orphanSets);

  // Written from the data: a hardcoded "884" sits inches from #count, which prints the real
  // number, so the next scrape would have them disagreeing in the same row.
  $("q").placeholder = `Search ${ROWS.length} composers…`;
  Table.init({ thead: $("thead"), tbody: $("tbody"), onSelect: selectFromTable });
  Table.setData(ROWS);

  byName = new Map(ROWS.map(d => [d.name, d.i]));

  Histogram.setData(ROWS);
  // onChange fires continuously while dragging; `done` marks the end of the gesture.
  Histogram.init({ el: $("hist"), onChange: (_range, done) => applyFilters(done) });

  // Restore whatever the link asked for BEFORE the first paint, so a shared URL never shows the
  // default view for a frame and then jump-cuts to the real one.
  const link = readHash();
  // "readers" was this view's name until it became "fame". writeHash() omits v for the
  // DEFAULT mode, which this is, so nothing the app ever produced carries it — but a link
  // shared back when the timeline was the default does, and dropping it would open that
  // link on the wrong chart rather than fail visibly.
  const v = link.v === "readers" ? "fame" : link.v;
  if (v && ["fame", "scatter", "swarm", "lens"].includes(v)) setMode(v);
  if (link.q) $("q").value = link.q;
  if (link.r) Histogram.setRange(link.r);
  if (link.g) setGender(link.g);

  renderLegend();
  placeFilters();
  placeChartTools();
  placeDetail();
  renderDetail(null, false);
  applyFilters(true);
  if (link.c && byName.has(link.c)) show(byName.get(link.c), false);
  $("hint").textContent = Chart.hint();
  // Say exactly what each channel is and when it was measured. Three sources with three
  // different freshnesses is precisely the situation where one date silently implies the others.
  // Provenance only: where each number came from and what it does not cover. The lede frames what
  // readership MEANS and the legend says which channel carries it, so neither is repeated here —
  // this paragraph used to restate both, and to say the word "median" twice in one clause.
  const mm = META.views_months || [];
  const span = mm.length ? `, ${mm[0]} to ${mm[mm.length - 1]}` : "";
  // The list link points at the REVISION, not at the live page: every number in this sentence was
  // scraped from that one document, and today's list is a different one. Built from list_source
  // rather than written out, so a pipeline that renames or moves the list carries the link with it.
  const rev = META.list_revid;
  const listUrl = META.list_source + (rev ? `?oldid=${rev}` : "");
  setProv(
    `${ROWS.length} composers from `,
    { text: `Wikipedia's List of String Quartet Composers${rev ? `, v${rev}` : ""}`,
      href: listUrl,
      title: "The list this page was built from, as it stood at that revision" },
    `; ${Chart.plottedStats().n} state a quartet `
    + `count and are plotted, the rest appear in the table only. Dates are ${META.dates_source}. `
    + `Readership is the ${META.views_stat} of the composer's English Wikipedia article${span} — `
    + `A lifespan written "83+" is the composer's age today. `
    // Whose statement this is, said plainly. The other two channels name a source because they
    // are measurements; this one names a source because it is about a person, and the page has no
    // business asserting it on its own account. The unknown count is stated for the same reason
    // the quartet nulls are: the filter cannot reach those rows, and silence would read as none.
    + `Gender is from ${META.gender_source}. `
    + `Built ${META.generated}.`);

  wire();

  // AFTER everything above has painted, and never awaited: the sparkline is the one thing on this
  // page that nothing else waits for. When it lands, repaint whatever the panel is showing —
  // hovering included, or a shared #c= link would sit there without one until the pointer moved.
  loadHistory().then(ok => {
    if (ok) renderDetail(hovered != null ? hovered : selected, hovered != null);
  });
}

function wire() {
  $("q").addEventListener("input", () => applyFilters(true));
  $("clear").onclick = () => { $("q").value = ""; applyFilters(true); $("q").focus(); };
  document.querySelectorAll("#gender button").forEach(b => {
    b.onclick = () => setGender(b.dataset.g);
  });

  // SCOPED to the chart card. `.seg` is a look — a pill group — and the gender filter wears it
  // too; an unscoped ".seg button" bound the view switcher's handler over the filter's, so a pill
  // called setMode(undefined) and the chart fell out of every named mode at once.
  document.querySelectorAll(".controls .seg button").forEach(b => {
    b.onclick = () => setMode(b.dataset.mode);
  });
  $("reset-filters").onclick = resetFilters;
  $("share").onclick = share;
  $("reset").onclick = () => { Chart.resetZoom(); setTimeout(() => { $("reset").disabled = !Chart.zoomed(); }, 450); };
  $("fs").onclick = () => setFull(!document.body.classList.contains("fs"));

  // Leaving fullscreen via Esc / the system gesture must also unwind our CSS class, or the page
  // stays in the fixed-position layout with no visible way out.
  document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement && document.body.classList.contains("fs")) setFull(false);
  });
  document.addEventListener("keydown", ev => {
    // Escape first, and unconditionally: it means "back out of this" wherever the focus is.
    if (ev.key === "Escape") {
      if (document.body.classList.contains("fs")) setFull(false); else show(null, false);
      return;
    }
    // The arrows step the SELECTION, but only when nothing focused is using them itself. The test
    // used to be `matches("input, textarea")`, which quietly stole the keys from the first
    // focusable thing that was neither: arrowing along the sparkline changed the composer instead
    // of the month, so the readout answered about someone else. [data-keys] is the contract —
    // anything that handles its own arrows marks itself, and the next one (the readership brush
    // still owes a keyboard path) needs no edit here.
    if (ev.target.closest("input, textarea, [data-keys]")) return;
    if (ev.key === "ArrowRight") { ev.preventDefault(); step_(1); }
    if (ev.key === "ArrowLeft") { ev.preventDefault(); step_(-1); }
  });

  // The chart is sized from its container, so anything that resizes the container — rotation,
  // a window drag, entering fullscreen, the URL bar collapsing on scroll — has to re-lay it out.
  let raf = 0;
  new ResizeObserver(() => {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => { Chart.resize(); Histogram.resize(); });
  }).observe($("plot"));

  // Theme: chart.js and the legend BAKE colors into SVG/inline styles, which a CSS variable swap
  // cannot reach. theme.js clears the color cache before calling us, so re-reading here is safe.
  Theme.subscribe(() => {
    themeLabel();
    Chart.rerender();
    Histogram.rerender();
    renderLegend();
    Table.render(visible);        // the row chips are baked too
    Table.select(selected, false);
  });
  WIDE.addEventListener("change", placeDetail);   // rotation / a window drag crosses the breakpoint
  NARROW.addEventListener("change", placeChartTools);
  SQUEEZED.addEventListener("change", placeChartTools);
  // A wheel over the glyphs is a wheel over the CHART — the zoom is bound to the svg and this group
  // is its sibling, so without this the corner is dead to a wheel and the page scrolls instead (see
  // Chart.wheelInto). Only while the group is ON the plot: in the controls row it is a button like
  // any other and the page is what a wheel there should move.
  //
  // preventDefault ONLY when the chart actually took it, which is why wheelInto reports back and
  // why this listener cannot be passive. "Took it" is narrower than "a zoom is bound" — at rest the
  // zoom declines every scroll DOWN, because k is already at scaleExtent's floor — and cancelling
  // on the wider test left a hole in the page's scrolling under these two buttons, in the resting
  // default view and in lens both.
  $("chart-tools").addEventListener("wheel", e => {
    if ($("chart-tools").parentNode !== $("plot")) return;
    if (Chart.wheelInto(e)) e.preventDefault();
  }, { passive: false });
  $("theme").onclick = () => Theme.cycle();
  themeLabel();
}

function setMode(mode) {
  document.querySelectorAll(".controls .seg button").forEach(o => o.setAttribute("aria-pressed", String(o.dataset.mode === mode)));
  Chart.setMode(mode);
  renderLegend();                    // the views encode different things and need different keys
  // The chips are painted from the view's encoding, but a full Table.render() empties tbody and
  // rebuilds ~880 rows -- which resets the scroll box to the top and destroys the focused row
  // under anyone who tabbed into the table. Only the colours change, so only repaint those.
  Table.repaintChips();
  $("hint").textContent = Chart.hint();
  $("reset").disabled = !Chart.zoomed();
  writeHash();
}

function themeLabel() {
  $("theme").textContent = "Theme: " + Theme.get().replace(/^./, c => c.toUpperCase());
}

// ---- service worker: version tag + shell top-up (pwa-starter plumbing) -----
async function checkVer() {
  const tag = $("ver");
  if (!tag) return;
  // HIGHEST version among caches that actually HOLD something — not the first key. Two caches
  // legitimately coexist while a new precache fills, caches.keys() is in creation order, and
  // sw.js opens the new (empty) cache before fetching anything. Ranking on names alone reports
  // the wrong generation as installed and hides the one affordance that unsticks a stale phone.
  let installed = "";
  try {
    const keys = (await caches.keys()).filter(k => k.startsWith(VER_PREFIX));
    const sized = await Promise.all(keys.map(async k => [(await (await caches.open(k)).keys()).length, k]));
    installed = sized.filter(([n]) => n > 0)
      .map(([, k]) => [parseInt(k.slice(VER_PREFIX.length), 10) || 0, k])
      .sort((a, b) => a[0] - b[0]).map(([, k]) => k).pop() || "";
  } catch {}
  if (!installed) { tag.hidden = true; return; }

  let latest = "";
  try {
    const src = await (await fetch("./sw.js?_=" + Date.now(), { cache: "no-store" })).text();
    // Parse the DECLARATION, not the first prefix-shaped string in the file: sw.js's comments
    // cite version names as examples, and an unanchored scan pins a permanent, useless tag.
    latest = (src.match(/const V\s*=\s*"([^"]*)"/) || ["", ""])[1];
  } catch {}

  const behind = latest && latest !== installed;
  tag.hidden = false;
  tag.className = "ver" + (behind ? " behind" : "");
  tag.textContent = behind ? `${installed} → ${latest}` : installed;
  tag.title = behind ? "New version available — tap to update" : "Up to date";
  tag.onclick = behind ? forceUpdate : null;
}

async function forceUpdate() {
  try { await Promise.all((await caches.keys()).map(k => caches.delete(k))); } catch {}
  location.reload();
}

// iOS can reclaim Cache API CONTENTS while leaving the registration in place, and sw.js only
// precaches on install (a V bump). Without this nudge a once-evicted cache stays empty forever
// and the app is permanently blank offline; with it, one online launch repairs it.
function requestShellTopUp() {
  if (!("serviceWorker" in navigator) || !navigator.onLine) return;
  navigator.serviceWorker.getRegistration()
    .then(reg => { if (reg && reg.active) reg.active.postMessage("ensure-shell"); })
    .catch(() => {});
}

function boot() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("./sw.js").catch(() => {});
    // A registration can exist with no ACTIVE worker for a moment (first install, or the swap
    // during an update). The top-up ping is fire-and-forget, so retry when one takes control.
    navigator.serviceWorker.addEventListener("controllerchange", requestShellTopUp);
  }
  Theme.init();
  start();
  checkVer();
  requestShellTopUp();
  // Installed copies RESUME rather than reload, so this is the only moment an already-open home
  // screen app finds out a new version shipped.
  addEventListener("visibilitychange", () => { if (!document.hidden) { checkVer(); requestShellTopUp(); } });
}

boot();
