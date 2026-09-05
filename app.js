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
let byName = new Map();
const fmt = new Intl.NumberFormat();

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

// ---- detail panel ----------------------------------------------------------
// Percentile among the rows that HAVE the value. Counting nulls as zero would tell a composer
// with 3 quartets that they out-wrote the 105 composers whose count simply couldn't be read.
function pct(d, key) {
  if (d[key] == null) return null;
  const known = ROWS.filter(o => o[key] != null);
  const below = known.reduce((n, o) => n + (o[key] < d[key] ? 1 : 0), 0);
  return Math.round((below / known.length) * 100);
}

function renderDetail(i, preview) {
  const el = $("detail");
  el.innerHTML = "";
  if (i == null) {
    const p = document.createElement("p");
    p.className = "empty";
    const living = ROWS.filter(d => d.living).length;
    p.textContent = `${ROWS.length} composers, born ${d3.min(ROWS, d => d.birth)}–`
      + `${d3.max(ROWS, d => d.birth)}. ${living} are still living. `
      + `Select a dot or a row for the details.`;
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
  dates.textContent = d.living
    ? `b. ${d.birth} · living, age ${new Date().getFullYear() - d.birth}`
    : `${d.birth}–${d.death} · lived ${d.lifespan} years`;
  el.appendChild(dates);

  const dl = document.createElement("dl");
  const add = (k, v) => {
    const dt = document.createElement("dt"); dt.textContent = k;
    const dd = document.createElement("dd"); dd.textContent = v;
    dl.appendChild(dt); dl.appendChild(dd);
  };
  add("Quartets", d.quartets == null ? "not stated on the list" : d.quartets);
  // The median, with its own 12-month range beside it — the spread is part of the measurement,
  // and hiding it implies a precision a page-view count does not have.
  add("Views / mo", d.views == null ? "no data"
      : `${fmt.format(d.views)}  (${fmt.format(d.lo)}–${fmt.format(d.hi)})`);
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

  if (!preview) {
    const nav = document.createElement("div");
    nav.className = "detail-nav";
    nav.appendChild(navBtn("‹ Prev", -1));
    nav.appendChild(navBtn("Next ›", 1));
    const clear = navBtn("Clear", 0);
    clear.onclick = () => show(null, false);
    nav.appendChild(clear);
    el.appendChild(nav);
  }
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

  const life = document.createElement("div");
  life.innerHTML =
    `<span class="lab">Lifespan</span>` +
    `<div class="ramp" style="background:linear-gradient(90deg,${g("--c-short")},${g("--c-mid")},${g("--c-long")})"></div>` +
    `<div class="ticks"><span>20 yrs</span><span>${Chart.midLife()} (median)</span><span>104</span></div>`;
  el.appendChild(life);

  const KEYS = [1000, 20000, 150000];
  const rs = KEYS.map(v => Chart.radiusOf(v));
  const rMax = rs[rs.length - 1];
  let cx = 2, circles = "", ticks = "";
  for (let k = 0; k < KEYS.length; k++) {
    cx += rs[k];
    circles += `<circle cx="${cx.toFixed(1)}" cy="${(rMax * 2 - rs[k]).toFixed(1)}" r="${rs[k].toFixed(1)}" `
             + `fill="none" stroke="${g("--muted")}" stroke-width="1"/>`;
    ticks += `<span>${KEYS[k] >= 1000 ? Math.round(KEYS[k] / 1000) + "k" : KEYS[k]}</span>`;
    cx += rs[k] + 5;
  }
  const size = document.createElement("div");
  size.innerHTML =
    `<span class="lab">Views / month</span>` +
    `<svg width="${Math.ceil(cx)}" height="${Math.ceil(rMax * 2 + 1)}" aria-hidden="true" `
      + `style="display:block">${circles}</svg>` +
    `<div class="ticks" style="width:${Math.ceil(cx)}px">${ticks}</div>`;
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
  if (Chart.getMode() !== "scatter") p.set("v", Chart.getMode());
  const q = $("q").value.trim();
  if (q) p.set("q", q);
  if (selected != null) p.set("c", ROWS[selected].name);
  const s = p.toString();
  history.replaceState(null, "", s ? "#" + s : location.pathname + location.search);
}

function readHash() {
  const p = new URLSearchParams(location.hash.replace(/^#/, ""));
  return { v: p.get("v"), q: p.get("q") || "", c: p.get("c") };
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

// ---- search ----------------------------------------------------------------
function applySearch() {
  const q = $("q").value;
  visible = Table.matches(q);
  $("clear").hidden = !q;
  Chart.setFilter(visible);
  const n = Table.render(visible);
  $("count").textContent = visible ? `${n} of ${ROWS.length}` : `${ROWS.length} composers`;
  // A pinned composer that the search just filtered out would leave a detail panel describing
  // someone invisible in both views. Drop the pin rather than the coherence.
  if (selected != null && visible && !visible.has(selected)) show(null, false);
  else Table.select(selected, false);
  writeHash();
}

// ---- full screen -----------------------------------------------------------
// CSS-first (see styles.css): iPhone Safari has no Fullscreen API, and that is the device this
// feature exists for. The API call is an ADDITIVE nicety where it exists — it drops the browser
// chrome too — and its failure is ignored, never surfaced.
function setFull(on) {
  document.body.classList.toggle("fs", on);
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
                         views_stat: "median", dates_source: "Wikidata", generated: "" },
                       data.meta || {});

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
    views: r[4], lo: r[5], hi: r[6],
    living: r[2] == null,
    lifespan: r[2] == null ? null : r[2] - r[1],
  }));

  Table.init({ thead: $("thead"), tbody: $("tbody"), onSelect: selectFromTable });
  Table.setData(ROWS);

  byName = new Map(ROWS.map(d => [d.name, d.i]));

  // Restore whatever the link asked for BEFORE the first paint, so a shared URL never shows the
  // default view for a frame and then jump-cuts to the real one.
  const link = readHash();
  if (link.v && ["swarm", "lens"].includes(link.v)) setMode(link.v);
  if (link.q) $("q").value = link.q;

  renderLegend();
  renderDetail(null, false);
  applySearch();
  if (link.c && byName.has(link.c)) show(byName.get(link.c), false);
  $("hint").textContent = Chart.hint();
  // Say exactly what each channel is and when it was measured. Three sources with three
  // different freshnesses is precisely the situation where one date silently implies the others.
  const mm = META.views_months || [];
  $("prov").textContent =
    `${ROWS.length} composers from the Wikipedia list (${Chart.plotted()} have a stated quartet `
    + `count and are plotted; the rest are in the table only). Dates from ${META.dates_source}. `
    + `Size is the ${META.views_stat} ${mm.length ? `from ${mm[0]} to ${mm[mm.length - 1]}` : ""} `
    + `— ${META.views_note}; a median rather than one month because a single month runs about 12% `
    + `off typical. A lifespan written "83+" is the composer's age today. Built ${META.generated}.`;

  wire();
}

function wire() {
  $("q").addEventListener("input", applySearch);
  $("clear").onclick = () => { $("q").value = ""; applySearch(); $("q").focus(); };

  document.querySelectorAll(".seg button").forEach(b => {
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
    raf = requestAnimationFrame(() => Chart.resize());
  }).observe($("plot"));

  // Theme: chart.js and the legend BAKE colors into SVG/inline styles, which a CSS variable swap
  // cannot reach. theme.js clears the color cache before calling us, so re-reading here is safe.
  Theme.subscribe(() => {
    themeLabel();
    Chart.rerender();
    renderLegend();
    Table.render(visible);        // the row chips are baked too
    Table.select(selected, false);
  });
  $("theme").onclick = () => Theme.cycle();
  themeLabel();
}

function setMode(mode) {
  document.querySelectorAll(".seg button").forEach(o => o.setAttribute("aria-pressed", String(o.dataset.mode === mode)));
  Chart.setMode(mode);
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
