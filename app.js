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
const WIKI = name => "https://en.wikipedia.org/w/index.php?search=" + encodeURIComponent(name);

let META = {}, ROWS = [], selected = null, hovered = null, visible = null;
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
// The view count is a MEASURE, not a tally: the median of twelve monthly page-view totals, where
// any single month runs about 12% off typical. "186,772" claims six significant figures for a
// number that has about two, and it is stale the next time fetch_views.py runs. So the panel
// quantizes to two figures and rounds DOWN — "180k+" is a claim that survives a refresh.
//
// The TABLE keeps the exact figure. That is the row-by-row data view: it sorts on this column, and
// a column reading "1.2k+" eleven times in a row hides the ordering it was sorted by.
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
      `<span class="lab">Named on the chart</span>` +
      `<div class="swatches">` +
        `<span class="sw"><i style="background:${g("--sel")}"></i>` +
        `the repertoire, in birth order</span>` +
        `<span class="sw"><i style="box-shadow:inset 0 0 0 2px ${g("--accent")}"></i>` +
        // The ring follows the filter (chart.js's refreshEmphasis), so the key has to say which
        // crowd it is talking about. Claiming "the outliers at either end" while ringing
        // women the curated set never contained would be labelling the wrong channel.
        `${Chart.derivedRings() ? "the ones that stand out in this group"
                                : "the outliers at either end"}</span>` +
        `<span class="sw"><i style="background:${g("--muted")};opacity:.3"></i>` +
        `the other ${Chart.famePlotted() - Chart.namedCount()} composers</span>` +
      `</div>`;
    el.appendChild(who);

    const dia = document.createElement("div");
    dia.innerHTML =
      `<span class="lab">Diagonals</span>` +
      `<div class="swatches"><span class="sw">readers per quartet — higher above a line is ` +
      `more read for what they wrote</span></div>`;
    el.appendChild(dia);
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

  const other = document.createElement("div");
  other.innerHTML =
    `<span class="lab">Also</span>` +
    `<div class="swatches">` +
      `<span class="sw"><i style="box-shadow:inset 0 0 0 1.5px ${g("--c-living")}"></i>` +
      `still living — final lifespan unknown, so no color</span>` +
    `</div>`;
  el.appendChild(other);
}

// ---- where the detail panel lives -------------------------------------------
// On a wide screen it is the second grid column, sitting beside the chart. Below 900px it is a
// full screen-height BELOW the chart — you tap a dot and the answer is somewhere off-screen — and
// in full screen the grid column is display:none, so a tap produced no visible answer at all.
// So on a phone, and in full screen at any width, the SAME element moves inside the chart card.
// Moving it rather than rendering a second compact copy keeps one detail view, one selection, and
// one set of Prev/Next buttons; styles.css does the rest.
//
// The two in-card positions are NOT interchangeable:
//   phone, in flow   BELOW the plot, free to be as tall as the content. Nothing above it moves
//                    when it grows, so the chart stays exactly where the eye left it.
//   full screen      ABOVE the plot, between the readership filter and the chart, at a FIXED
//                    height that is drawn whether or not anything is pinned. Every pixel there is
//                    a pixel of chart, and a box that changed size would re-lay out the chart on
//                    every tap and on every hover — the dot moving out from under the finger that
//                    just tapped it is exactly the churn this avoids.
const WIDE = matchMedia("(min-width:900px)");

// The filter row is a sibling of .grid, which body.fs hides outright — so in full screen it moves
// into the chart card, where CSS drops its search half and keeps the readership brush. Same move
// as placeDetail, and it must run first so the two land in the right order.
function placeFilters() {
  const f = $("filters"), viz = $("viz");
  const fs = document.body.classList.contains("fs");
  const parent = fs ? viz : document.querySelector("main");
  const before = fs ? viz.firstElementChild : document.querySelector(".grid");
  if (f.parentNode === parent && f.nextElementSibling === before) return;
  parent.insertBefore(f, before);
}

function placeDetail() {
  const det = $("detail"), viz = $("viz");
  const fs = document.body.classList.contains("fs");
  const inCard = !WIDE.matches || fs;
  det.classList.toggle("compact", inCard);
  const parent = inCard ? viz : document.querySelector(".grid");
  const before = inCard ? (fs ? $("plot") : viz.querySelector(".controls")) : null;
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

async function share() {
  const btn = $("share");
  writeHash();
  const payload = { title: document.title, url: location.href };
  // navigator.share is the right affordance on a phone (it opens the real share sheet) but is
  // absent or blocked on most desktops, and it REJECTS on user-cancel — which must not read as a
  // failure. Clipboard is the fallback, and the visible confirmation is the point either way.
  try {
    if (navigator.share) { await navigator.share(payload); return; }
    await navigator.clipboard.writeText(location.href);
    btn.textContent = "Link copied";
    setTimeout(() => { btn.textContent = "Share"; }, 1600);
  } catch {
    btn.textContent = "Link copied";      // clipboard blocked: the URL bar already shows the link
    setTimeout(() => { btn.textContent = "Share"; }, 1600);
  }
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

// Every gender the data STATES that no pill can reach. fetch_wikidata.py labels eight P21 items
// and index.html has two pills, so the two vocabularies can drift — and the drift is silent in the
// worst way: the composer is in neither filter while the provenance line, which counts only the
// composers with NO claim, still implies everyone else is reachable. validate.py fails the build
// on it; this is the same assertion on the app's side, and the UI suite asserts it empty. Exactly
// the job Chart.missingNames() and Names.staleOverrides() do for the other hardcoded vocabularies.
function unfilterableGenders() {
  const reach = new Set(pillValues());
  return [...new Set(ROWS.filter(d => d.gender != null && !reach.has(d.gender)).map(d => d.gender))];
}

// The third filter. It is the only one with no module of its own, because it has nothing to
// render and no data to hold — three buttons and a string. It still returns the same "a Set of
// indices, or null for everything" the other two do, so intersect() never learns it exists.
//
// A composer with no P21 claim is in NEITHER set. That is the null rule (invariant 10) applied to
// a filter: "Women" means Wikidata says female, not "everyone we didn't call a man".
function genderMatches() {
  if (!gender) return null;
  const set = new Set();
  for (const d of ROWS) if (d.gender === gender) set.add(d.i);
  return set;
}

function setGender(g) {
  gender = g;
  document.querySelectorAll("#gender button").forEach(b =>
    b.setAttribute("aria-pressed", String(b.dataset.g === g)));
  applyFilters(true);
}

// `settled` is false during a brush DRAG. The chart repaint is cheap and watching the field thin
// out is the whole point of the control, but rebuilding ~880 table rows every frame is the one
// thing here that stutters — so the table waits for the gesture to end.
function applyFilters(settled) {
  const q = $("q").value;
  visible = intersect(intersect(Table.matches(q), Histogram.matches()), genderMatches());
  $("clear").hidden = !q;
  $("hist-clear").hidden = !Histogram.getRange();
  $("hist-read").textContent = Histogram.label();
  // `settled` travels with it: the chart closes its frame in on what the filter kept, and that
  // must happen once at the end of a brush drag, not on every frame of one.
  Chart.setFilter(visible, settled);

  const n = visible ? visible.size : ROWS.length;
  $("count").textContent = visible ? `${n} of ${ROWS.length}` : `${ROWS.length} composers`;
  if (settled !== false) {
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

function setProv(text) {
  const el = $("prov");
  el.textContent = "";
  let at = 0;
  for (const m of text.matchAll(WD_PROP)) {
    if (m.index > at) el.appendChild(document.createTextNode(text.slice(at, m.index)));
    const a = document.createElement("a");
    a.href = "https://www.wikidata.org/wiki/Property:" + m[0];
    a.target = "_blank";
    a.rel = "noopener";
    // The id is the link text, so the sentence reads exactly as it did — and the title says what
    // the link is for, because "P569" is not a promise a reader can evaluate before clicking.
    a.title = "Wikidata property " + m[0] + " — what this value means and where it comes from";
    a.textContent = m[0];
    el.appendChild(a);
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
  placeDetail();
  $("fs").setAttribute("aria-pressed", String(on));
  $("fs").textContent = on ? "Exit full screen" : "Full screen";
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
  Names.setData(data.rows.map(r => r[0]));

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
  const unknownGender = ROWS.filter(d => d.gender == null).length;
  const span = mm.length ? `, ${mm[0]} to ${mm[mm.length - 1]}` : "";
  const rev = META.list_revid ? ` (revision ${META.list_revid})` : "";
  setProv(
    `${ROWS.length} composers from Wikipedia's list${rev}; ${Chart.plottedStats().n} state a quartet `
    + `count and are plotted, the rest appear in the table only. Dates are ${META.dates_source}. `
    + `Readership is the ${META.views_stat} of the composer's English Wikipedia article${span} — `
    + `twelve rather than one because a single month runs about 12% off typical, and English only `
    + `because the pageviews API counts per title, so a composer read mostly in another language `
    + `is undercounted. A lifespan written "83+" is the composer's age today. `
    // Whose statement this is, said plainly. The other two channels name a source because they
    // are measurements; this one names a source because it is about a person, and the page has no
    // business asserting it on its own account. The unknown count is stated for the same reason
    // the quartet nulls are: the filter cannot reach those rows, and silence would read as none.
    + `Gender is ${META.gender_source} as Wikidata records it, reported here rather than claimed `
    + `by this page and never inferred from a name; ${unknownGender} `
    + `composer${unknownGender === 1 ? " has" : "s have"} no such claim and `
    + `${unknownGender === 1 ? "is" : "are"} in neither filter. `
    + `Built ${META.generated}.`);

  wire();
}

function wire() {
  $("q").addEventListener("input", () => applyFilters(true));
  $("clear").onclick = () => { $("q").value = ""; applyFilters(true); $("q").focus(); };
  $("hist-clear").onclick = () => Histogram.clear();   // fires "end" -> applyFilters
  document.querySelectorAll("#gender button").forEach(b => {
    b.onclick = () => setGender(b.dataset.g);
  });

  // SCOPED to the chart card. `.seg` is a look — a pill group — and the gender filter wears it
  // too; an unscoped ".seg button" bound the view switcher's handler over the filter's, so a pill
  // called setMode(undefined) and the chart fell out of every named mode at once.
  document.querySelectorAll(".controls .seg button").forEach(b => {
    b.onclick = () => setMode(b.dataset.mode);
  });
  $("share").onclick = share;
  $("reset").onclick = () => { Chart.resetZoom(); setTimeout(() => { $("reset").disabled = !Chart.zoomed(); }, 450); };
  $("fs").onclick = () => setFull(!document.body.classList.contains("fs"));

  // Leaving fullscreen via Esc / the system gesture must also unwind our CSS class, or the page
  // stays in the fixed-position layout with no visible way out.
  document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement && document.body.classList.contains("fs")) setFull(false);
  });
  document.addEventListener("keydown", ev => {
    if (ev.target.matches("input, textarea")) return;
    if (ev.key === "Escape") { if (document.body.classList.contains("fs")) setFull(false); else show(null, false); }
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
