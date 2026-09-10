#!/usr/bin/env node
// UI tests: drives a real headless Chrome over the DevTools Protocol and asserts what the app
// actually DOES — the lens magnifies, a tap pins, a theme flip re-bakes the SVG fills, the table
// fits a 390px phone, an offline reload still paints every dot.
//
// No dependencies: node >= 22 ships a global WebSocket, so the whole CDP client is the ~25 lines
// below. Run it through scripts/ui-test.sh, which starts the server and the browser for you.
//
//     scripts/ui-test.sh
//
// Every check here exists because something was WRONG. In order of how long each took to find:
//   - selecting a dot called scrollIntoView, which scrolled the whole document and pushed the
//     chart you just clicked off the screen ("document did NOT scroll on select")
//   - a search DELETED the non-matching dots instead of dimming them, so "haydn" showed three
//     dots in an empty box with no sense of where they sat ("search dims non-matching dots")
//   - the y-axis title was rotated inside a 34px left margin on a phone and overlapped the tick
//     labels, rendering "100" as "00" ("y-axis tick labels are not clipped")
//   - six table columns overflowed 390px and pushed Quartets off the right edge
//   - a pinch pushed dots out of the plot rectangle and left them lying in the margins
//   - the x axis started at 1580 for a chart whose first PLOTTABLE composer is born 1709
//   - the size legend's three numbers ran together into "1005k150k" on a phone
//   - tapping a dot on a phone answered in a panel a full screen-height below the chart, and in
//     full screen answered nowhere at all
//
// NB the runner uses a FRESH browser profile every time. sw.js serves the shell cache-first, so a
// reused profile happily runs the previous edit's chart.js until V is bumped. That cost two
// confusing test rounds during the build; it is the service worker working exactly as documented.

import { writeFileSync, readFileSync } from "node:fs";

const [,, PORT, OUTDIR, ORIGIN] = process.argv;

const targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
const page = targets.find(t => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener("open", r));

let id = 0; const pending = new Map(); const logs = [];
ws.addEventListener("message", e => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); p.resolve(m); }
  if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error")
    logs.push("console.error: " + m.params.args.map(a => a.value ?? a.description).join(" "));
  if (m.method === "Runtime.exceptionThrown")
    logs.push("EXCEPTION: " + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
});
// A CDP call that never answers used to end the whole run as node's "unsettled top-level await"
// with ZERO lines of output — no check results, no page errors, no name for the call that died.
// That is the worst failure shape this file has, and it is the one this file's own comments argue
// against everywhere else. It is not hypothetical: `shot("print")` asked this Chromium for a
// 2560x69872 image (~179 megapixels, the print stylesheet un-scrolls the table) and it dropped the
// page target and closed the socket with 1006 (#50). The clip below fixes that particular ask; the
// watchdog is what turns any future one into a sentence instead of silence.
const CDP_TIMEOUT = 60000;
let closed = null;
const send = (method, params = {}) => new Promise((res, rej) => {
  // Most of a run is spent BETWEEN calls — the 25ms poll inside settle(), the TWEEN wait, writing
  // a PNG — and a socket that dies in one of those gaps leaves `pending` empty, so the handler
  // below has nothing to reject. `send()` on a CLOSED WebSocket then neither throws nor delivers:
  // per spec it discards the frame and returns, so the call would wait out the full timeout and
  // report the generic message a minute later, having thrown away the close code that explains
  // it. The flag is what makes the two entrances agree.
  if (closed) return rej(new Error(closed));
  const i = ++id;
  const t = setTimeout(() => { pending.delete(i); rej(new Error(`CDP ${method} did not answer in ${CDP_TIMEOUT}ms`)); }, CDP_TIMEOUT);
  pending.set(i, { resolve: m => { clearTimeout(t); res(m); }, reject: e => { clearTimeout(t); rej(e); } });
  ws.send(JSON.stringify({ id: i, method, params }));
});
// The socket dying is that same failure arriving a minute sooner AND naming its cause, so say it
// instead of waiting the watchdog out: a dropped target closes with 1006 and no pending reply is
// ever coming. Rejecting rather than resolving matters — a resolve would hand the caller
// `undefined` and the check after it would fail on a dereference, blaming the app.
ws.addEventListener("close", e => {
  closed = `DevTools socket closed (code ${e.code}) mid-run`;
  const waiting = [...pending.values()];
  pending.clear();
  for (const r of waiting) r.reject(new Error(closed));
});
const sleep = ms => new Promise(r => setTimeout(r, ms));
// A wait here is a POLL, not a budget (issue 48). The suite used to sleep ~100 of its ~110 seconds
// — 116 fixed waits, most of them 1.7–2x the longest animation the app has, following DOM work that
// animates nothing at all — and a budget is wrong in the other direction too: a cold CI runner can
// miss 700ms. `settle` re-asks the page every 25ms until `expr` is truthy and returns what it got.
// On timeout it returns the LAST value rather than throwing, so the check that follows fails with
// its own message instead of this one's, and every check after it still runs.
async function settle(expr, timeout = 4000) {
  const t0 = Date.now(); let v;
  while (!(v = await ev(expr)) && Date.now() - t0 < timeout) await sleep(25);
  return v;
}
// The one thing a poll cannot see is a NON-event — "nothing moved", "hover does not pin" — so
// those keep a fixed wait, and it is this one: a frame past chart.js's 420ms zoom tween, which is
// the longest thing the app animates. Anything longer was waiting for nothing.
const TWEEN = 450;
// Whatever the app defers by requestAnimationFrame has run: setFull's resize, and the
// ResizeObserver's, which is scheduled from a frame's layout step and so lands one frame later
// than a plain rAF registered before it — hence a frame, a task, and a frame.
const laidOut = () => ev(`new Promise(r => requestAnimationFrame(() => setTimeout(() => requestAnimationFrame(r))))`);
// No d3 transition is in flight on the chart. d3 keeps its schedule on the node and deletes the
// property when the last one ends, so this is the zoom tween's own "done" rather than a guess at
// it, and it is what the fit-the-filter checks below wait on.
const idle = () => settle(`!document.querySelector('#plot svg').__transition`);
// NB every expression here is a TEMPLATE LITERAL, so a backslash is consumed before the browser
// ever sees it: `/\s+/` arrives as `/s+/` and `/\d/` as `/d/`. Both are still valid regexes, so
// nothing throws — the check just quietly matches the wrong thing or nothing at all, and passes.
// Write `\\s` for a `\s` that reaches the page, or avoid the escape entirely (`[0-9]`,
// `.includes(...)`, the SVG DOM). This has cost three debugging rounds; grep for `\\s` above to
// see the shape that works.
async function ev(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.error) throw new Error(r.error.message + " :: " + expr);
  if (r.result?.exceptionDetails) throw new Error(r.result.exceptionDetails.text + " :: " + expr);
  return r.result.result.value;
}
const shots = [];
async function shot(name, params = {}) {
  const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, ...params });
  const png = Buffer.from(r.result.data, "base64");
  writeFileSync(`${OUTDIR}/${name}.png`, png);
  // Off the IHDR rather than off the request, so a clip that did not do what it meant to is still
  // measured by what landed on disk. 9b reads these.
  shots.push({ name, w: png.readUInt32BE(16), h: png.readUInt32BE(20) });
}
// Print un-scrolls the table, so the page is 884 rows tall — ~35,000px, which at DSF is a
// 179-megapixel ask that this Chromium answers by dropping the page target (#50).
// Clip the HEIGHT, and NOT the scale, which was the first answer and the wrong one. Whoever reads
// these is reading a resized copy (see 9b): fewer megapixels buys nothing, because the long edge
// is what the resize is driven by, and a taller capture therefore spends WIDTH. Full-page at half
// scale is 1280x34,936 and lands 94px wide — the same 94px as full scale. What makes the shot
// readable is that it is SHORT, so it runs to the Nth row and stops. Everything print changes is
// above the fold — the hidden chrome, the white card, and the table running on past where its
// scroll box used to end — and the rest is the same row 850 more times. The row is measured on
// the page rather than assumed, so a font change carries the clip with it.
const printClip = async (rows = 30) => ({ scale: 1, x: 0, y: 0,
  width: await ev(`document.documentElement.clientWidth`),
  height: await ev(`(()=>{const r = document.querySelectorAll('tbody tr')[${rows}];
    return r ? Math.ceil(r.getBoundingClientRect().bottom + scrollY)
             : document.documentElement.scrollHeight})()`) });
async function goto(url) {
  // A navigation that changes only the FRAGMENT is same-document: the app never re-runs, so
  // goto(BASE + "#v=scatter") from BASE quietly left the previous section's view in place and the
  // checks that followed tested the wrong chart.
  //
  // Forcing it with a follow-up Page.reload fixed that and introduced a RACE. The app rewrites its
  // own URL on boot (writeHash -> replaceState) and drops anything it did not accept — an invalid
  // "#g=chicken" becomes a bare path. When that rewrite landed between the navigate and the
  // reload, the reload re-read the CLEANED url, the page came up in the DEFAULT Fame view, and
  // a later section asking for #legend .ramp dereferenced null and killed the whole run: every
  // check after it silently never ran. It failed intermittently, which is worse than always.
  //
  // about:blank first makes every goto a real cross-document load, so the fragment is on the URL
  // the app boots from and there is nothing to race. Do not "simplify" this back to one navigate.
  await send("Page.navigate", { url: "about:blank" });
  await send("Page.navigate", { url });
  // Booted means DRAWN. The dots and the rows are the last synchronous thing start() produces, and
  // laidOut() on top covers the ResizeObserver's deferred re-layout; anything later — the
  // sparkline, a zoom tween — is polled for by the section that needs it. Polled rather than
  // budgeted, and not thrown on: a page that never draws (section 8 offline) should fail the
  // checks written for it, not abort the run.
  await settle(`document.querySelectorAll('#plot svg circle.dot').length > 0
    && document.querySelectorAll('tbody tr').length > 0`, 10000);
  await laidOut();
  // Cheap proof the navigation actually happened. Nothing asserts the fragment SURVIVED, because
  // the app is allowed to rewrite it — it strips a value it rejects — and the sections that care
  // check the state it produced instead.
  if (await ev(`location.href`) === "about:blank") throw new Error("goto never left about:blank: " + url);
}
async function mouse(type, x, y) {
  await send("Input.dispatchMouseEvent", { type, x, y, button: type === "mouseMoved" ? "none" : "left",
    buttons: 0, clickCount: type === "mouseMoved" ? 0 : 1, pointerType: "mouse" });
}
// Real key events, not element.dispatchEvent: the app's arrow handling is a DOCUMENT listener,
// and a synthetic event on one node does not prove the one that actually fires reaches it.
const VK = { ArrowLeft: 37, ArrowUp: 38, ArrowRight: 39, ArrowDown: 40, Home: 36, End: 35 };
async function key(k) {
  for (const type of ["keyDown", "keyUp"]) {
    await send("Input.dispatchKeyEvent", { type, key: k, code: k, windowsVirtualKeyCode: VK[k] || 0,
      nativeVirtualKeyCode: VK[k] || 0 });
  }
}
// A DESKTOP call here means a fine pointer, and that is not something this file can arrange.
// `Emulation.setEmulatedMedia` takes a `features` list and TODO.md prescribed hover/pointer
// overrides through it — they are accepted with an empty result and change nothing, because
// Blink's media-feature overrides cover prefers-color-scheme and its neighbours and not the
// pointer ones. Nor does `mobile: true` below make a pointer coarse; only
// `setTouchEmulationEnabled` does, which is why every phone section calls it.
//
// So the pointer is a PLATFORM fact: macOS reports fine unconditionally, and a headless Linux
// Chrome reports NONE, which fails `(hover:hover) and (pointer:fine)` and takes the lens, every
// hover preview and the panel's reserved height with it — chart.js reads that query once into
// `TOUCH`, and styles.css reserves the panel behind it. `ui-test.sh` answers it where it can be
// answered, by running the browser on an Xvfb display, and section 2 asserts the answer arrived
// rather than trusting it (#50).
const DSF = 2;
async function viewport(w, h, mobile = false) {
  await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: DSF, mobile });
}

await send("Page.enable"); await send("Runtime.enable"); await send("Log.enable");

const BASE = (ORIGIN || "http://127.0.0.1:8765") + "/";
const results = [];
// `extra` prints either way, which is right for a MEASUREMENT — "34 dots grew >1.5x" reads
// correctly under `ok` and `FAIL` alike, and that is what almost every call site passes. It is
// wrong for a DIAGNOSIS, and there are exactly two of those: the checks with no measurement to
// report, because the number IS the assertion. Both printed their own failure text on a GREEN run
// before this slot existed (#52 review, twice — the second one after the first was hand-folded,
// which is why this is a mechanism and not another ternary). `fail` is appended only when the
// check actually failed, so the third diagnosis has somewhere to go.
const check = (name, cond, extra = "", fail = "") => {
  const note = cond ? extra : (fail || extra);
  results.push(`${cond ? "ok  " : "FAIL"} ${name}${note ? " — " + note : ""}`);
};

// Every exit goes through here, so a run that DIES still prints the checks that had already run
// and the section it got to. `ev` has always thrown on an evaluation error too, and that took the
// same silent path.
function report(died) {
  console.log(results.join("\n"));
  if (died) console.log(`\nDIED after ${results.length} checks: ${died}`);
  console.log(logs.length ? "\nPAGE ERRORS:\n" + logs.join("\n") : "\nno page errors");
  process.exit(died || logs.length || results.some(r => r.startsWith("FAIL")) ? 1 : 0);
}
// A rejected TOP-LEVEL await lands on `uncaughtException`, not on `unhandledRejection` — node
// treats the module's own evaluation promise as the main script throwing. Both are registered
// because a stray un-awaited promise takes the other door, and either way the point is the same:
// print what we have instead of the bare "unsettled top-level await" the tail of this suite spent
// an issue producing.
for (const door of ["uncaughtException", "unhandledRejection"])
  process.on(door, e => report(e?.stack || String(e)));

// --- 1. lens mode: aim the magnifier at the crowded low bands -----------------
await viewport(1280, 900);
await goto(BASE + "#v=lens");
const box = await ev(`(()=>{const r=document.querySelector('#plot svg').getBoundingClientRect();
  return {x:r.x,y:r.y,w:r.width,h:r.height}})()`);
// Radii of every dot BEFORE the lens exists, keyed by the label d3 bound to them.
const before = await ev(`(()=>{const o={};document.querySelectorAll('#plot svg circle.dot')
  .forEach((e,i)=>o[i]=+e.getAttribute('r'));return o})()`);
await mouse("mouseMoved", box.x + box.w * 0.55, box.y + box.h * 0.72);
await settle(`document.querySelector('#plot svg circle.lens-edge')?.style.display === ''`);
check("lens draws its boundary circle", await ev(`document.querySelectorAll('#plot svg circle.lens-edge').length === 1 &&
                 document.querySelector('#plot svg circle.lens-edge').style.display !== 'none'`));
const after = await ev(`(()=>{const o={};document.querySelectorAll('#plot svg circle.dot')
  .forEach((e,i)=>o[i]=+e.getAttribute('r'));return o})()`);
const grew = Object.keys(before).filter(k => after[k] > before[k] * 1.5).length;
const same = Object.keys(before).filter(k => after[k] === before[k]).length;
check("lens magnifies dots under the focus", grew > 20, grew + " dots grew >1.5x");
check("lens leaves dots outside its radius alone", same > 150, same + " unchanged");
await shot("lens-active");

// --- 2. hover flag on a real pointer -----------------------------------------
await goto(BASE);
// The premise of this section, of 7c2, 7d and 7e, and of the panel's reserved height — asserted
// once, up front, rather than left to be inferred from a scatter of later checks failing at a
// layout the app is right to be drawing. There is no CDP override for this (see viewport()): a headless Linux
// Chrome reports no pointer at all, so `ui-test.sh` runs the browser on an Xvfb display to give
// it a real one, and this is where that either arrived or did not. It is the mirror of "the phone
// viewport really reports a touch pointer" in section 7.
// A diagnosis, not a measurement, so it goes in `check`'s `fail` slot: an `ok` line reading "no
// fine pointer" is the exact misreading this check exists to prevent, printed where a reader
// looks for the answer.
check("the desktop viewport really reports a fine pointer",
      await ev(`matchMedia('(hover:hover) and (pointer:fine)').matches`), "",
      "no fine pointer: chart.js's TOUCH is true, so nothing below hovers, and styles.css never "
      + "reserves the panel's height. On Linux the browser is headless, or is "
      + "chrome-headless-shell, which reports none even under a display — see ui-test.sh");
const dot = await ev(`(()=>{const s=document.querySelector('#plot svg');const r=s.getBoundingClientRect();
  const c=[...s.querySelectorAll('circle.dot')].sort((a,b)=>+b.getAttribute('r')-+a.getAttribute('r'))[0];
  const b=c.getBoundingClientRect(); return {x:b.x+b.width/2, y:b.y+b.height/2}})()`);
// Whoever is most-read: the table defaults to views-descending, so row 0 IS the biggest dot.
// Deliberately NOT hardcoded — the first `fetch_views.py` refresh moved Beethoven (-33% since
// 2014) below Mozart (-3%) and broke two assertions that were asserting 2014 trivia, not behavior.
// The cell TEXT is now the surname; the cell's title carries the full canonical name, which is
// what the hash and the detail panel use.
const top = (await ev(`document.querySelector('tbody tr td').title`)).trim();
await mouse("mouseMoved", dot.x, dot.y);
await settle(`document.getElementById('flag').classList.contains('on')`);
check("hover shows the name flag", await ev(`document.getElementById('flag').classList.contains('on')`),
      await ev(`document.getElementById('flag').textContent`));
check("hover previews into the detail panel",
      (await ev(`document.getElementById('detail').textContent`)).includes(top), "expected " + top);
check("hover does NOT pin (no ring yet)", await ev(`!location.hash.includes('c=')`));

// --- 3. click pins ------------------------------------------------------------
await mouse("mousePressed", dot.x, dot.y); await mouse("mouseReleased", dot.x, dot.y);
await settle(`location.hash.includes('c=')`);
check("click pins to the URL",
      (await ev(`decodeURIComponent(location.hash).split("+").join(" ")`)).includes("c=" + top),
      await ev(`decodeURIComponent(location.hash)`));
check("click rings the dot", await ev(`document.querySelectorAll('#plot svg circle.sel-ring').length === 1`));
check("selected row is marked in the table", await ev(`!!document.querySelector('tbody tr[aria-selected="true"]')`));
// Readership is a median of twelve monthly counts, so the panel states two significant figures
// and a "+" — "186,772" claimed six figures for a number that has about two, and was stale the
// next time fetch_views.py ran. The TABLE still carries the exact value: it sorts on it.
const exactViews = (await ev(`document.querySelector('tbody tr td:last-child').textContent`)).trim();
const panelText = await ev(`document.getElementById('detail').textContent`);
check("the panel rounds readership instead of claiming six figures",
      !panelText.includes(exactViews) && /\dk?\+/.test(panelText),
      `table ${exactViews}; panel ` + await ev(`[...document.querySelectorAll('#detail dd')].pop().textContent`));
check("the table keeps the exact figure it sorts on", /^[\d,]+$/.test(exactViews), exactViews);
check("the most-read composer is not said to out-read 100% of the list",
      !panelText.includes("100%"),
      await ev(`document.querySelector('#detail .rank').textContent`));
check("document did NOT scroll on select", await ev(`window.scrollY === 0`), "scrollY=" + await ev("window.scrollY"));

// --- 3b. the readership sparkline ---------------------------------------------
// readership.json is fetched AFTER the first paint and is not a boot dep, so the panel is
// correct before it lands and grows the line when it does. Everything here waits for that.
const sparkLine = `document.querySelectorAll('#detail svg.spark path.spark-line').length`;
await settle(sparkLine + " >= 1");
check("the panel draws a readership sparkline",
      await ev(`document.querySelectorAll('#detail svg.spark path.spark-line').length >= 1`),
      "spark paths=" + await ev(`document.querySelectorAll('#detail svg.spark path.spark-line').length`));
check("the sparkline spans the whole cached history, not the statistic's twelve months",
      await ev(`(()=>{const ax=[...document.querySelectorAll('#detail .spark-ax span')].map(s=>s.textContent);
        const m = ax[1] && ax[1].match(/^(\\d{4})–(\\d{4})$/);
        return ax.length===2 && !!m && +m[2] - +m[1] >= 5})()`),
      await ev(`[...document.querySelectorAll('#detail .spark-ax span')].map(s=>s.textContent).join(" ")`));
// The caption names the SPIKE when there is one and the TREND otherwise — a fixed "peak N×
// typical" called noise a spike on half the roster (the median composer's biggest month is 3.1x
// their typical one) and buried the real story for the steady ones. Mozart's line has no spike by
// the peak/p95 >= 3 test, so his caption is a trend.
const capOf = () => ev(`document.querySelector('#detail .spark-cap').textContent`);
check("a composer with no spike is captioned by trend, not by a meaningless peak",
      /^(up|down) \d+% since \d{4}$|^steady since \d{4}$/.test(await capOf()), await capOf());
// …and the peak hairline is drawn ONLY when the caption names the peak. An annotation pointing at
// a month nothing mentions has no referent.
check("no peak marker on a line whose caption does not name one",
      await ev(`document.querySelectorAll('#detail .spark-peak').length === 0`));

// Saariaho died in June 2023 and her article went from ~2,000 readers a month to 42,195. That is
// what the spike branch is for, and it is the case a 12-month window structurally cannot show.
await goto(BASE + "#c=" + encodeURIComponent("Kaija Saariaho"));
await settle(`!!document.querySelector('#detail .spark-cap')`);
check("a real spike is captioned by its peak month and how far above typical it stood",
      /^peak [A-Z][a-z]{2} \d{4} — [\d,]+, [\d.]+× typical$/.test(await capOf()), await capOf());
check("a captioned peak gets a marker on the line",
      await ev(`document.querySelectorAll('#detail .spark-peak').length === 1`));
// EXACT here, ROUNDED in the <dl> above, and that is the point: the dl carries the MEDIAN, a
// smoothed estimate whose last four figures are noise ("2.7k+"), while a month on this line is a
// raw tally of one month. Rounding the number you hovered to read defeats the hovering.
check("the sparkline prints raw monthly tallies where the measure above it rounds",
      (await capOf()).includes("42,195")
      && /\dk\+/.test(await ev(`[...document.querySelectorAll('#detail dd')].pop().textContent`)),
      await capOf() + "  |  " + await ev(`[...document.querySelectorAll('#detail dd')].pop().textContent`));

// --- 3c. reading one month off the sparkline ----------------------------------
// The readout REPLACES the caption instead of adding a line, because the compact panel reserves a
// fixed height for a hover preview — a box that grew under the pointer would pump the legend.
const sbox = await ev(`(()=>{const r=document.querySelector('#detail svg.spark').getBoundingClientRect();
  return {x:r.x,y:r.y,w:r.width,h:r.height}})()`);
const capH = await ev(`document.querySelector('#detail .spark-cap').getBoundingClientRect().height`);
await mouse("mouseMoved", sbox.x + sbox.w * 0.72, sbox.y + sbox.h / 2);
const readout = `document.querySelector('#detail .spark-cap').textContent.includes(' · ')`;
await settle(readout);
check("hovering the sparkline reads out that month and its count",
      /^[A-Z][a-z]{2} \d{4} · [\d,]+$/.test(await capOf()), await capOf());
check("the hovered month is marked on the line",
      await ev(`document.querySelector('#detail .spark-cursor').classList.contains('on')`));
check("the readout does not change the panel's height",
      Math.abs(await ev(`document.querySelector('#detail .spark-cap').getBoundingClientRect().height`) - capH) < 1);
await mouse("mouseMoved", sbox.x - 40, sbox.y - 40);
const summary = `document.querySelector('#detail .spark-cap').textContent.startsWith('peak')`;
await settle(summary);
check("leaving the sparkline puts the summary back",
      (await capOf()).startsWith("peak"), await capOf());

// The keyboard gets the same readout, not a second mechanism. This is a READ-ONLY value stepper,
// which is why arrow keys are right here and wrong for the readership brush (see TODO).
await ev(`document.querySelector('#detail svg.spark').focus()`);
await settle(readout);
check("focusing the sparkline starts the readout at the peak",
      (await capOf()).startsWith("Jun 2023"), await capOf());
const whoBefore = await ev(`document.querySelector('#detail h2').textContent`), atPeak = await capOf();
await key("ArrowLeft"); await key("ArrowLeft"); await key("ArrowLeft");
await settle(`document.querySelector('#detail .spark-cap').textContent !== ${JSON.stringify(atPeak)}`);
check("arrow keys step a month, not a composer",
      /^[A-Z][a-z]{2} \d{4} · [\d,]+$/.test(await capOf())
      && await ev(`document.querySelector('#detail h2').textContent`) === whoBefore,
      await capOf() + " | still " + await ev(`document.querySelector('#detail h2').textContent`));
await key("Home");
await settle(`document.querySelector('#detail .spark-cap').textContent.startsWith('Jul 2015')`);
check("Home reads the first month on the axis", (await capOf()).startsWith("Jul 2015"), await capOf());
await ev(`document.querySelector('#detail svg.spark').blur()`);
await settle(summary);

// --- 3d. the arithmetic edges, forced ------------------------------------------
// Not reachable in today's readership.json — five series contain a zero month, none has a zero
// median — but the roster is rebuilt from a scrape every month and the obscure tail is where a
// zero median would first appear. Both of these rendered visible garbage before they were guarded.
// The shape has to clear p95 > 0 as well as put the MEDIAN at zero, or the spike test
// short-circuits on p95 and the Infinity is never reached: a majority of dead months, a tail of
// live ones, and one big one. (A series with a single non-zero month has p95 == 0 and was always
// safe — which is why the fixture is built deliberately rather than by intuition.)
const zeroMedianCap = await ev(`(()=>{
  const name = document.querySelector('#detail h2').textContent;
  window.__realSeries = HIST.series[name];
  const n = window.__realSeries.length;
  const z = Array.from({length: n}, (_, i) => i < n * 0.55 ? 0 : 10);
  z[n - 1] = 500;
  HIST.series[name] = z;
  renderDetail(selected, false);
  const c = document.querySelector('#detail .spark-cap');
  return c ? c.textContent : "(no sparkline)";
})()`);
check("a composer whose typical month is zero does not print an infinite multiple",
      !/Infinity|NaN/.test(zeroMedianCap), zeroMedianCap);
const allZero = await ev(`(()=>{
  const name = document.querySelector('#detail h2').textContent;
  HIST.series[name] = window.__realSeries.map(() => 0);
  renderDetail(selected, false);
  return document.querySelectorAll('#detail .spark, #detail .spark-cap').length;
})()`);
// An all-zero series has no line to draw: every y is 0/0, so the path came out "MNaN,NaN…" and
// rendered as nothing at all under a caption reading "peak Mar 2019 — 0".
check("an all-zero series draws no sparkline rather than an invisible one", allZero === 0,
      "spark nodes = " + allZero);
await ev(`(()=>{ const name = document.querySelector('#detail h2').textContent;
  HIST.series[name] = window.__realSeries; renderDetail(selected, false); return true })()`);

// An article that did not exist in 2015 has nulls, and a null is a BREAK, not a zero — drawing it
// as zero would claim nobody read a page that was not there. John Verrall's article starts in 2025.
await goto(BASE + "#c=" + encodeURIComponent("John Verrall"));
await settle(sparkLine + " >= 1");
check("a composer whose article is younger than the axis starts partway across",
      await ev(`(()=>{const p=document.querySelector('#detail path.spark-line');
        return p && +p.getAttribute('d').slice(1).split(",")[0] > 100})()`),
      "line starts at x=" + await ev(`(()=>{const p=document.querySelector('#detail path.spark-line');
        return p ? p.getAttribute('d').slice(1).split(",")[0] : "no line"})()`));
// …and SAYS so, because nine tenths of an empty line chart reads as "nobody read this" rather
// than "the article did not exist yet".
check("the blank stretch before a young article is named, not left to read as zero",
      /^from [A-Z][a-z]{2} \d{4}$/.test(await ev(`[...document.querySelectorAll('#detail .spark-ax span')].pop().textContent`)),
      await ev(`[...document.querySelectorAll('#detail .spark-ax span')].pop().textContent`));

// The sparkline is the ONE drawn thing in this app whose colours are NOT baked into the SVG by
// JS — it is plain inline SVG in the document, so a CSS variable reaches it and Theme.subscribe
// has nothing to re-bake. That is a decision (see the note in styles.css), so it gets a check.
const sparkStroke = `getComputedStyle(document.querySelector('#detail path.spark-line')).stroke`;
const sparkLight = await ev(sparkStroke);
await ev(`Theme.set('dark')`);
await settle(`${sparkStroke} !== ${JSON.stringify(sparkLight)}`);
const sparkDark = await ev(sparkStroke);
check("the sparkline follows the theme with no colour baked into the SVG",
      sparkLight !== sparkDark
      && !(await ev(`document.querySelector('#detail path.spark-line').hasAttribute('stroke')`)),
      `${sparkLight} -> ${sparkDark}`);
await ev(`Theme.set('auto')`);
await settle(`${sparkStroke} === ${JSON.stringify(sparkLight)}`);

// --- 4. search filters both views --------------------------------------------
// The filters are synchronous — an input event has rebuilt the table by the time the dispatch
// returns — so the polls in this section settle on their first ask. They are polls anyway: the
// check reads the state it was written for, not a clock.
const rowCount = `document.querySelectorAll('tbody tr').length`;
await goto(BASE);
await ev(`(()=>{const q=document.getElementById('q'); q.value='haydn';
  q.dispatchEvent(new Event('input',{bubbles:true}));})()`);
await settle(rowCount + " === 2");
check("search filters the table", await ev(`document.querySelectorAll('tbody tr').length`) === 2,
      "rows=" + await ev(`document.querySelectorAll('tbody tr').length`));
check("search dims non-matching dots", await ev(`[...document.querySelectorAll('#plot svg circle.dot')]
  .filter(c=>+c.getAttribute('opacity')<0.2).length > 400`));
check("search is in the URL", (await ev(`location.hash`)).includes("q=haydn"));
check("filtered-out pin was dropped", !(await ev(`location.hash`)).includes("c="));

// --- 4b. the readership histogram filter -------------------------------------------------------
await goto(BASE);
const totalRows = await ev(`document.querySelectorAll('tbody tr').length`);
check("histogram drew its bars", await ev(`document.querySelectorAll('#hist svg g rect').length >= 20`),
      "bars=" + await ev(`document.querySelectorAll('#hist svg rect').length`));

// A REAL drag across the right-hand (high-readership) half, not a programmatic setRange: the
// point is to exercise the d3-brush wiring the user actually touches.
const hb = await ev(`(()=>{const r=document.querySelector('#hist svg').getBoundingClientRect();
  return {x:r.x,y:r.y,w:r.width,h:r.height}})()`);
await mouse("mousePressed", hb.x + hb.w * 0.62, hb.y + hb.h * 0.4);
await mouse("mouseMoved",   hb.x + hb.w * 0.85, hb.y + hb.h * 0.4);
await mouse("mouseReleased", hb.x + hb.w * 0.99, hb.y + hb.h * 0.4);
await settle(`${rowCount} < ${totalRows}`);
const filtered = await ev(`document.querySelectorAll('tbody tr').length`);
check("brushing filters the table to the readable tail", filtered > 0 && filtered < totalRows / 2,
      `${filtered} of ${totalRows}`);
check("brushing dims the rest of the chart",
      await ev(`[...document.querySelectorAll('#plot svg circle.dot')]
        .filter(c=>+c.getAttribute('opacity')<0.2).length > 100`));
check("the brushed range is in the URL", (await ev(`location.hash`)).includes("r="),
      await ev(`decodeURIComponent(location.hash)`));
check("a readout names the range", (await ev(`document.getElementById('hist-read').textContent`)).includes("views"),
      await ev(`document.getElementById('hist-read').textContent`));
// The range annotates the axis under its own handles instead of sitting inline among the controls.
check("the selected range is drawn on the axis, at its end points",
      await ev(`(()=>{const read=document.getElementById('hist-read').textContent;
        const ends=[...document.querySelectorAll('#hist svg g.ends text')];
        return ends.length === 2 && ends.every(t => read.includes(t.textContent))})()`),
      await ev(`[...document.querySelectorAll('#hist svg g.ends text')]
        .map(t=>t.textContent).join(" .. ")`));
check("no axis tick is printed under the range labels",
      await ev(`(()=>{const b=e=>e.getBoundingClientRect();
        const t=[...document.querySelectorAll('#hist svg g.axis text')].map(b);
        const e2=[...document.querySelectorAll('#hist svg g.ends text')].map(b);
        return !t.some(a=>e2.some(c=>a.left < c.right && a.right > c.left))})()`));
// THE REPORTED BUG: .seg is overflow:hidden, so when a Clear button appeared beside it the pill
// group gave up width and clipped its last pill — the filter lost the word "Men" while you were
// using the filter. That button has since left this row entirely (issue 35); the check stays,
// because what it is really asserting is that nothing in .filterbar may steal the pills' width.
check("the gender pills are not clipped",
      await ev(`(()=>{const g=document.getElementById('gender');
        return g.scrollWidth <= g.clientWidth + 1})()`),
      await ev(`(()=>{const g=document.getElementById('gender');
        return g.scrollWidth + " vs " + g.clientWidth})()`));
check("every gender pill is fully inside the filter row",
      await ev(`(()=>{const row=document.querySelector('.filterbar').getBoundingClientRect();
        return [...document.querySelectorAll('#gender button')].every(b=>{
          const r=b.getBoundingClientRect(); return r.right <= row.right + 0.5 && r.left >= row.left - 0.5})})()`));

// The two filters must INTERSECT, not replace one another.
await ev(`(()=>{const q=document.getElementById('q'); q.value='quartet';
  q.dispatchEvent(new Event('input',{bubbles:true}));})()`);
await settle(`${rowCount} <= ${filtered}`);
const both = await ev(`document.querySelectorAll('tbody tr').length`);
check("search and brush combine rather than override", both <= filtered, `${both} <= ${filtered}`);
await ev(`(()=>{const q=document.getElementById('q'); q.value='';
  q.dispatchEvent(new Event('input',{bubbles:true}));})()`);

await ev(`document.getElementById('reset-filters').click()`);
await settle(`${rowCount} === ${totalRows}`);
check("Reset filters restores every row",
      await ev(`document.querySelectorAll('tbody tr').length`) === totalRows);
check("...and drops the range from the URL", !(await ev(`location.hash`)).includes("r="));

// The handles are crossfilter's grips (issue 40). d3's own .handle is handleSize wide by the extent
// PLUS handleSize tall, so painting it drew a 20x62 accent slab through the tick labels — the hit
// area wearing the costume of the control. It is now the hit area only, and three things have to
// stay true together for that to be an improvement rather than a trade.
await mouse("mousePressed", hb.x + hb.w * 0.45, hb.y + hb.h * 0.4);
await mouse("mouseMoved",   hb.x + hb.w * 0.60, hb.y + hb.h * 0.4);
await mouse("mouseReleased", hb.x + hb.w * 0.72, hb.y + hb.h * 0.4);
await settle(`document.querySelectorAll('#hist .grips path').length === 2`);
// Identified by POSITION, not by DOM order. The join is keyed by side, so which node d3 creates
// first is not part of the contract — and a check that assumed it went red on a reorder that
// changed nothing on screen, which is a test failing for its own reasons rather than the code's.
check("a grip is drawn at each end of the selection, on the outside of it",
      await ev(`(()=>{const g=[...document.querySelectorAll('#hist .grips path')];
        if (g.length !== 2) return false;
        const s=document.querySelector('#hist .selection').getBoundingClientRect();
        const b=g.map(p=>p.getBoundingClientRect()).sort((a,c)=>a.left-c.left);
        return Math.abs(b[0].right - s.left) < 2 && b[0].left < s.left
            && Math.abs(b[1].left - s.right) < 2 && b[1].right > s.right})()`),
      await ev(`document.querySelectorAll('#hist .grips path').length + " grips"`));
// The grip is what is SEEN and the handle is what is FELT, the same split the chart's icon buttons
// use. Assert both numbers: shrinking the grip is only an improvement if the target survives it.
check("the grip is a small tab inside a 20px hit target",
      await ev(`(()=>{const p=document.querySelector('#hist .grips path').getBoundingClientRect();
        const h=document.querySelector('#hist .handle--e').getBoundingClientRect();
        return p.width < 10 && p.height > 20 && p.height < 34 && h.width >= 19})()`),
      await ev(`(()=>{const p=document.querySelector('#hist .grips path').getBoundingClientRect();
        const h=document.querySelector('#hist .handle--e').getBoundingClientRect();
        return `+"`grip ${p.width.toFixed(1)}x${p.height.toFixed(1)}, target ${h.width.toFixed(1)}`"+`})()`));
// The bug as REPORTED was the handle being visible at all, and none of the checks above would
// notice it coming back: a repainted handle draws its slab straight over an intact grip. Both
// values are d3's own, set on the brush <g> and inherited — what this asserts is that no rule in
// THIS stylesheet overrides either, which is the only way they have ever gone wrong.
check("...and the handle itself stays unpainted, so the slab cannot come back",
      await ev(`(()=>{const h=document.querySelector('#hist .handle--e');
        const c=getComputedStyle(h); return c.fill === 'none' && c.pointerEvents === 'all'})()`),
      await ev(`(()=>{const c=getComputedStyle(document.querySelector('#hist .handle--e'));
        return c.fill + ", pointer-events:" + c.pointerEvents})()`));
// THE REGRESSION THIS GUARDS is one line up in histogram.js, not in the stylesheet: the grips group
// is drawn ON TOP of the brush and OUTSIDE it, so without pointer-events:none on it a press lands on
// a path the brush never sees, and the drag does nothing at all. Ablating that attribute is what
// turns this check red; ablating anything in styles.css does not.
const r0 = await ev(`Histogram.getRange()`);
const eh = await ev(`(()=>{const r=document.querySelector('#hist .handle--e').getBoundingClientRect();
  return {cx:r.x+r.width/2, cy:r.y+r.height/2}})()`);
await mouse("mousePressed", eh.cx, eh.cy);
await mouse("mouseMoved",   eh.cx - 40, eh.cy);
await mouse("mouseReleased", eh.cx - 60, eh.cy);
await settle(`JSON.stringify(Histogram.getRange()) !== ${JSON.stringify(JSON.stringify(r0))}`);
const r1 = await ev(`Histogram.getRange()`);
// Both halves of the message are guarded. An unguarded r0[0] here throws a TypeError while BUILDING
// the failure text, which aborts the run and silently skips every check below — the same
// fails-by-vanishing shape goto()'s own comment calls worse than failing every time.
const span = r => (r ? r[0].toFixed(1) + "-" + r[1].toFixed(1) : "null");
check("dragging a grip resizes that end and leaves the other one alone",
      !!r0 && !!r1 && Math.abs(r1[0] - r0[0]) < r0[0] * 1e-6 && r1[1] < r0[1] * 0.9,
      `${span(r0)} -> ${span(r1)}`);
await ev(`document.getElementById('reset-filters').click()`);
await settle(`document.getElementById('reset-filters').disabled`);

// --- 4c. the frame holds: nothing escapes the plot rectangle under a zoom ----------------------
// Pinned to the timeline view: it is the one with the birth-year domain and the size legend these
// checks are about. The default view is now Fame (section 4e).
await goto(BASE + "#v=scatter");
const frame = await ev(`(()=>{const s=document.querySelector('#plot svg');
  const b=s.querySelector('rect.bg').getBoundingClientRect(); const r=s.getBoundingClientRect();
  return {bx:b.x,by:b.y,bw:b.width,bh:b.height,sx:r.x,sy:r.y,sw:r.width,sh:r.height}})()`);
// The empty band to the left of the first dot. It was a third of the width when the domain began
// at 1580: the three composers born before 1700 have no quartet count, so the chart cannot draw
// anything there — see X_DOMAIN in chart.js.
const lead = await ev(`(()=>{const s=document.querySelector('#plot svg');
  const b=s.querySelector('rect.bg').getBoundingClientRect();
  const xs=[...s.querySelectorAll('circle.dot')].map(c=>{const r=c.getBoundingClientRect();return r.x+r.width/2});
  return (Math.min(...xs)-b.x)/b.width})()`);
check("the x axis starts where the plottable data starts", lead < 0.08,
      (lead * 100).toFixed(1) + "% of the width is empty before the first dot");

// The clip must not touch the RESTING picture. Y_DOMAIN starts at 0.85, so a one-quartet dot's
// centre sits ~1.3% of the plot height above the bottom edge — a clip drawn on the frame sliced
// the most-read of them (Gershwin, Debussy, Ravel) flat, in the unzoomed view this file's header
// argues is the screenshot-able one. Asks the browser what is painted at the dot's lowest pixel.
const shaved = await ev(`(()=>{const s=document.querySelector('#plot svg');
  const low=[...s.querySelectorAll('circle.dot')]
    .filter(c=>+c.getAttribute('cy') > 0)
    .sort((a,b)=>(+b.getAttribute('cy')+ +b.getAttribute('r')) - (+a.getAttribute('cy')+ +a.getAttribute('r')))[0];
  const r=low.getBoundingClientRect();
  // elementsFROMPoint, plural: the axis labels are painted OVER the dots on purpose, so the
  // topmost element at that pixel is often a tick. A clipped dot is absent from the whole stack.
  const stack=document.elementsFromPoint(r.x+r.width/2, r.bottom-1.5);
  const b=s.querySelector('rect.bg').getBoundingClientRect();
  return {ok: stack.includes(low), r:+low.getAttribute('r'),
          over:+(r.bottom-b.bottom).toFixed(1),
          top: stack[0] ? stack[0].tagName : 'null'}})()`);
check("the bottom row of dots is not shaved by the frame", shaved.ok,
      `lowest dot r=${shaved.r.toFixed(1)}, overhangs the frame by ${shaved.over}px, `
      + `topmost element there is <${shaved.top}>`);

// Zoom in hard at the middle. d3-zoom clamps the PAN so the plot stays covered, which means dots
// outside the zoomed window are laid out past the frame — the clip is what keeps them from being
// painted over the axis labels and out past the card edge.
for (let i = 0; i < 6; i++) {
  await send("Input.dispatchMouseEvent", { type: "mouseWheel", x: frame.bx + frame.bw / 2,
    y: frame.by + frame.bh / 2, deltaX: 0, deltaY: -120, pointerType: "mouse" });
  await sleep(80);
}
await settle(`!document.getElementById('reset').disabled`);
const outside = await ev(`(()=>{const s=document.querySelector('#plot svg');
  const b=s.querySelector('rect.bg').getBoundingClientRect();
  return [...s.querySelectorAll('circle.dot')].filter(c=>{const r=c.getBoundingClientRect();
    return r.right < b.left-1 || r.left > b.right+1 || r.bottom < b.top-1 || r.top > b.bottom+1}).length})()`);
check("zooming really does push dots past the frame", outside > 50, outside + " dots laid out outside");
// A dot belongs on screen when its CENTRE is on screen; the half that hangs over the frame edge
// is normal scatter and is what the resting chart has always looked like.
const escaped = await ev(`(()=>{const s=document.querySelector('#plot svg');
  const b=s.querySelector('rect.bg').getBoundingClientRect();
  return [...s.querySelectorAll('circle.dot')].filter(c=>{
    if(getComputedStyle(c).display==='none') return false;
    const r=c.getBoundingClientRect(); const cx=r.x+r.width/2, cy=r.y+r.height/2;
    return cx < b.left-0.5 || cx > b.right+0.5 || cy < b.top-0.5 || cy > b.bottom+0.5}).length})()`);
check("a dot panned off the plot is not drawn at all", escaped === 0,
      escaped + " dots drawn with their centre outside the frame");
// Hit-testing honors clip-path, so this asks the browser what is actually PAINTED out in the
// margins — past anything an edge dot could legitimately overhang.
const stray = await ev(`(()=>{const s=document.querySelector('#plot svg');
  const b=s.querySelector('rect.bg').getBoundingClientRect(); const r=s.getBoundingClientRect();
  const over=Math.max(...[...s.querySelectorAll('circle.dot')].map(c=>+c.getAttribute('r')))+1;
  let n=0;
  for(let y=r.top+2; y<r.bottom-2; y+=6){
    for(const x of [r.left+2, b.left-over, b.right+over, r.right-2]){
      const e=document.elementFromPoint(x,y);
      if(e && e.tagName==='circle' && e.classList.contains('dot')) n++;
    }
  }
  return n})()`);
check("nothing is painted out in the margins", stray === 0, stray + " strays beyond the overhang");
check("the zoom is reversible from the toolbar",
      await ev(`!document.getElementById('reset').disabled`));
await shot("zoomed");

// --- 4d. the legend's size key ----------------------------------------------------------------
const legendOverlap = await ev(`(()=>{const t=[...document.querySelectorAll('#legend svg text')]
  .map(e=>e.getBoundingClientRect()).sort((a,b)=>a.x-b.x); let n=0;
  for(let i=1;i<t.length;i++) if(t[i].left < t[i-1].right + 2) n++;
  return n})()`);
check("size-legend labels do not run together", legendOverlap === 0, legendOverlap + " overlapping pairs");
check("size-legend labels sit under their circles",
      await ev(`(()=>{const s=document.querySelector('#legend svg');
        const c=[...s.querySelectorAll('circle')], t=[...s.querySelectorAll('text')];
        return c.length===t.length && c.every((e,i)=>Math.abs(
          e.getBoundingClientRect().x+e.getBoundingClientRect().width/2 -
          (t[i].getBoundingClientRect().x+t[i].getBoundingClientRect().width/2)) < 1.5)})()`));

// --- 4e. the Fame view: the one that makes the page's argument ------------------------------
await goto(BASE);
check("the Fame view is what a bare URL opens on",
      await ev(`Chart.getMode() === 'fame'`), await ev(`Chart.getMode()`));
// This view's mode key was "readers" until it was renamed. writeHash() omits v for the default
// mode, so nothing the app produced ever carried it -- but a link shared while the timeline was
// the default did, and an unmapped value is DROPPED rather than rejected, which would open an old
// link on the wrong chart with nothing to see. The alias is one line and this is what pins it.
await goto(BASE + "#v=readers");
check("an old #v=readers link still opens the Fame view",
      await ev(`Chart.getMode() === 'fame'`), await ev(`Chart.getMode()`));
await goto(BASE);
// The thirteen names are the ONLY hardcoded composer strings in the app, and they are canonical
// Wikipedia titles — which change spelling when the pipeline runs (invariant 4). A rename has to
// fail here rather than quietly drop a composer out of the argument the view is making.
check("every named composer still resolves in the data",
      (await ev(`Chart.missingNames()`)).length === 0,
      "missing: " + JSON.stringify(await ev(`Chart.missingNames()`)));
// Mozart sits 2.6% from the top of this view and Cambini hard against the right edge, so a
// labeller that only ever tries "above" drops exactly the two dots the argument is built on.
const named = await ev(`[...document.querySelectorAll('#plot svg text')]
  .filter(t => t.getAttribute('font-size') === '10.5').map(t => t.textContent)`);
// A label prints the SHORT name, not the canonical title -- and the short form is a function of
// the whole roster (a shared surname earns an initial), so this asks names.js rather than
// hardcoding "Mozart", which would go stale in exactly the way a second Mozart would cause.
for (const who of ["Wolfgang Amadeus Mozart", "Giuseppe Cambini", "Joseph Haydn"]) {
  const label = await ev(`Names.short(${JSON.stringify(who)})`);
  check(`${who} is labelled in the Fame view`, named.includes(label),
        `looking for ${JSON.stringify(label)} among ${named.length} labels placed`);
}
check("the labels are shortened, not the full Wikipedia titles",
      named.every(t => t.length < 20) && named.includes("Haydn"),
      JSON.stringify(named));
// The bare surname is not the shortening rule, it is the DOMINANCE rule on top of it: a surname
// only one composer is read for prints bare, and the initial stays on everyone else it would
// otherwise be ambiguous between. Asserted as a pair, because dropping the initial from BOTH
// Haydns is the failure mode -- two dots labelled the same thing -- and only checking the famous
// one would not see it. Michael is not labelled at rest, so this asks names.js directly.
check("a surname one composer owns prints bare; the others keep the initial",
      await ev(`Names.short("Joseph Haydn") === "Haydn"
             && Names.short("Michael Haydn") === "M. Haydn"
             && Names.short("Pyotr Ilyich Tchaikovsky") === "Tchaikovsky"
             && Names.short("Boris Tchaikovsky") === "B. Tchaikovsky"`),
      await ev(`[Names.short("Joseph Haydn"), Names.short("Michael Haydn"),
                 Names.short("Pyotr Ilyich Tchaikovsky"), Names.short("Boris Tchaikovsky")].join(" / ")`));
// No two composers may be handed the same chart label -- the whole point of the initial.
check("every short name is unique across the roster",
      await ev(`(()=>{const s = ROWS.map(d => Names.short(d.name));
        return new Set(s).size === s.length})()`),
      await ev(`(()=>{const s = ROWS.map(d => Names.short(d.name));
        return JSON.stringify(s.filter((x,i) => s.indexOf(x) !== i))})()`));
check("only the named composers are labelled", named.length <= 13, named.length + " labels");
check("the readers-per-quartet diagonals are drawn",
      await ev(`document.querySelectorAll('#plot svg line.dg').length >= 4`),
      "lines=" + await ev(`document.querySelectorAll('#plot svg line.dg').length`));
check("the diagonals are trimmed to the plot, not drawn past it",
      await ev(`(()=>{const s=document.querySelector('#plot svg');
        const b=s.querySelector('rect.bg'); const w=+b.getAttribute('width'), h=+b.getAttribute('height');
        return [...s.querySelectorAll('line.dg')].every(l=>['x1','x2'].every(a=>+l.getAttribute(a)>=-0.5 && +l.getAttribute(a)<=w+0.5)
          && ['y1','y2'].every(a=>+l.getAttribute(a)>=-0.5 && +l.getAttribute(a)<=h+0.5))})()`));
// Two pictures of one quantity, so they start in the same place (issue 38) — and two constants in
// two files, which is what makes it worth asserting.
const floors = await ev(`(()=>{
  const y=[...document.querySelectorAll('#plot svg text')]
    .filter(t=>t.getAttribute('text-anchor')==='end' && /^[\\d.]+k?$/.test(t.textContent));
  const h=[...document.querySelectorAll('#hist svg g.axis text')];
  const num=t=>t.endsWith('k')?parseFloat(t)*1000:parseFloat(t);
  const low=a=>a.length?Math.min(...a.map(t=>num(t.textContent))):-1;   // -1, not Infinity: CDP
  return {chart:low(y), hist:low(h)}})()`);                             // cannot return it by value
check("the chart and the filter agree where readership starts",
      floors.chart === 10 && floors.hist === 10,
      `chart axis from ${floors.chart}, histogram from ${floors.hist}`);

// Size is the y axis here, so a radius that repeated it would double-encode the one variable the
// view is about. Every unnamed dot is the same size.
const radii = await ev(`[...new Set([...document.querySelectorAll('#plot svg circle.dot')]
  .map(c => c.getAttribute('r')))].length`);
check("size is not double-encoded in the Fame view", radii <= 2, radii + " distinct radii");
// The control row is READ OFF seedNames() rather than named here: this check used to compare
// Mozart against Tchaikovsky, and when Tchaikovsky joined the repertoire both chips went --sel
// and the check failed for a change that was correct. A hardcoded "ordinary composer" is a
// second copy of the vocabulary, and it went stale the first time the vocabulary moved.
check("the table chip follows the view's encoding",
      await ev(`(()=>{const seeds=new Set(Chart.seedNames());
        const rows=[...document.querySelectorAll('tbody tr')];
        const named=rows.find(r=>r.querySelector('td').title==='Wolfgang Amadeus Mozart');
        const plain=rows.find(r=>!seeds.has(r.querySelector('td').title));
        return named && plain && named.querySelector('.chip').style.background
             !== plain.querySelector('.chip').style.background})()`));

// Pinning a composer puts it FIRST in the label list so it cannot lose its label to a rival --
// but in this view the list is only the 13 named, so a pin that is not one of them was hitting
// indexOf === -1, and splice(-1, 1) deletes the LAST entry: Ravel lost his label every time you
// clicked an unnamed dot.
//
// The pinned composer must therefore be one the view does NOT emphasise, or the check exercises
// the wrong branch entirely. It used to name Tchaikovsky, who has since joined the repertoire --
// so it is now picked from the table as the first row seedNames() does not contain.
const labelsBefore = await ev(`[...document.querySelectorAll('#plot svg text')]
  .filter(t => t.getAttribute('font-size') === '10.5').map(t => t.textContent)`);
const pinned = await ev(`(()=>{const seeds=new Set(Chart.seedNames());
  const r=[...document.querySelectorAll('tbody tr')]
    .find(r=>!seeds.has(r.querySelector('td').title));
  r.click(); return r.querySelector('td').title})()`);
await settle(`location.hash.includes('c=')`);
const labelsAfter = await ev(`[...document.querySelectorAll('#plot svg text')]
  .filter(t => t.getAttribute('font-size') === '10.5').map(t => t.textContent)`);
check("pinning an unnamed composer does not delete someone else's label",
      labelsBefore.every(n => labelsAfter.includes(n)),
      "lost: " + JSON.stringify(labelsBefore.filter(n => !labelsAfter.includes(n))));
check("the pinned composer gets a label of its own",
      labelsAfter.includes(await ev(`Names.short(${JSON.stringify(pinned)})`)),
      `pinned ${pinned}; labels ` + JSON.stringify(labelsAfter));
// --sel is the PINNED colour; tinting the repertoire with it elsewhere made ten composers look
// pinned with nothing pinned.
await goto(BASE + "#v=scatter");
check("the canon is not painted as pinned in the timeline view",
      await ev(`(()=>{const sel=getComputedStyle(document.documentElement)
        .getPropertyValue('--sel').trim();
        return ![...document.querySelectorAll('#plot svg text')]
          .filter(t => t.getAttribute('font-size') === '10.5')
          .some(t => t.getAttribute('fill') === sel)})()`));
check("the chart tells a screen reader which axes it is showing",
      (await ev(`document.querySelector('#plot svg').getAttribute('aria-label')`)).includes("birth year"),
      await ev(`document.querySelector('#plot svg').getAttribute('aria-label')`));
await goto(BASE);
check("and says something different in the Fame view",
      (await ev(`document.querySelector('#plot svg').getAttribute('aria-label')`)).includes("readers"),
      await ev(`document.querySelector('#plot svg').getAttribute('aria-label')`));

// Labels are a function of ZOOM, like a map. A fixed set answers a pinch with the same names
// larger, which makes the interaction decorative: it promises detail and delivers scale. At rest
// the Fame view still says exactly what it is about -- the thirteen -- and nothing else.
await goto(BASE);
const restLabels = await ev(`[...document.querySelectorAll('#plot svg text')]
  .filter(t=>new Set(ROWS.map(d=>Names.short(d.name))).has(t.textContent)).length`);
const pbox = await ev(`(()=>{const b=document.querySelector('#plot svg rect.bg').getBoundingClientRect();
  return {x:b.x,y:b.y,w:b.width,h:b.height}})()`);
for (let i = 0; i < 6; i++) {
  await send("Input.dispatchMouseEvent", { type: "mouseWheel", x: pbox.x + pbox.w / 2,
    y: pbox.y + pbox.h / 2, deltaX: 0, deltaY: -120, pointerType: "mouse" });
  await sleep(80);
}
await settle(`Chart.zoomK() > 1`);
const zoomLabels = await ev(`[...document.querySelectorAll('#plot svg text')]
  .filter(t=>new Set(ROWS.map(d=>Names.short(d.name))).has(t.textContent)).length`);
check("zooming the Fame view reveals more names", zoomLabels > restLabels,
      `${restLabels} at rest -> ${zoomLabels} zoomed in`);
check("the names it reveals are ones the seed never had",
      await ev(`(()=>{const seed=new Set(Chart.seedNames().map(Names.short));
        return [...document.querySelectorAll('#plot svg text')].map(t=>t.textContent)
          .filter(t=>new Set(ROWS.map(d=>Names.short(d.name))).has(t)).some(n=>!seed.has(n))})()`));
await ev(`document.getElementById('reset').click()`);
await idle();
check("and the resting picture is still just the seed",
      await ev(`(()=>{const seed=new Set(Chart.seedNames().map(Names.short));
        return [...document.querySelectorAll('#plot svg text')].map(t=>t.textContent)
          .filter(t=>new Set(ROWS.map(d=>Names.short(d.name))).has(t)).every(n=>seed.has(n))})()`),
      "a derived name is showing at rest, where the view should say only what it is about");

// --- 4e2. no two dots in one quartet stripe are drawn on top of each other ---------------------
// Fame has no y jitter, so the x offset separates same-count composers alone. It was a per-name
// hash, which separates ties on average and not in particular, and the pair it drew on top of each
// other owned half the hit area of the dot covering it — see spreadJq in chart.js, and #45.
//
// WITHIN A STRIPE, and to a FLOOR rather than to "never touching", because neither is what spreadJq
// guarantees: adjacent stripes overlap by construction, and inside a stripe the guarantee is about
// dots adjacent in readership, so a long run of near-ties degrades it. Both residuals are in
// TODO.md. Tightening this bar to "never touching" would assert something the fix does not do.
//
// The floor is a constant but the margin is not: the closest pair and the base radius are printed
// every run, so a change to dotRadius() or the aspect ratio shows up as a shrinking margin instead
// of quietly making the bar meaningless. Both viewports, because the phone is the worse case — the
// same jitter range is spent over a third of the width.
for (const [label, vw, vh, mob] of [["1280x900", 1280, 900, false], ["390x844", 390, 844, true]]) {
  await viewport(vw, vh, mob);
  await goto(BASE);
  // Only the dots actually DRAWN. plottable() is `quartets != null`, so a row with no readership
  // still joins a circle — parked off-frame at r=0 by layout(). Two of those share a quartet count
  // and this reads a 0px "overlap" between two dots nobody can see. validate.py permits up to 5% of
  // the roster to ship `views: null`; it is 0 today, which is exactly how this would arrive later
  // as a mystery FAIL naming two composers who are not on the chart.
  const worst = await ev(`(()=>{
    const ds=[...document.querySelectorAll('#plot svg circle.dot')]
      .filter(n=>+n.getAttribute('r')>0 && n.getAttribute('display')!=='none')
      .map(n=>({i:n.__data__.i, x:+n.getAttribute('cx'), y:+n.getAttribute('cy'), r:+n.getAttribute('r')}));
    let best=Infinity, pair=null;
    for(let a=0;a<ds.length;a++)for(let b=a+1;b<ds.length;b++){
      if(ROWS[ds[a].i].quartets!==ROWS[ds[b].i].quartets) continue;
      const d=Math.hypot(ds[a].x-ds[b].x, ds[a].y-ds[b].y);
      if(d<best){best=d;pair=[ds[a].i,ds[b].i];}}
    return {d:best, names:pair.map(i=>ROWS[i].name), r:Math.min(...ds.map(v=>v.r))};
  })()`);
  check(`same-count Fame dots stay a pixel apart at ${label}`, worst.d >= 1,
        `closest same-count pair ${worst.d.toFixed(2)}px (${worst.names.join(" / ")}) against a 1px floor, `
        + `base radius ${worst.r.toFixed(2)}px`);
}
await viewport(1280, 900, false);
await goto(BASE);

// --- 4f. one filter row, above everything it scopes -------------------------------------------
check("the filter row is not inside the chart or the table card",
      await ev(`(()=>{const f=document.getElementById('filters');
        return !document.getElementById('viz').contains(f)
            && f.parentElement.tagName === 'MAIN'})()`));
check("the filter row comes before the chart",
      await ev(`(()=>{const f=document.getElementById('filters'), g=document.querySelector('.grid');
        return f.compareDocumentPosition(g) & Node.DOCUMENT_POSITION_FOLLOWING})()`) > 0);
check("both filters still scope both views",
      await ev(`!!document.getElementById('filters').querySelector('#q')
             && !!document.getElementById('filters').querySelector('#hist')`));

// --- 4g. the table shows surnames --------------------------------------------------------------
// Full titles made the composer column the widest thing on a phone and sorted Joseph Haydn under
// J. Surname only, with a forename added ONLY where the surname is shared.
check("the table shows the surname, not the full title",
      await ev(`document.querySelector('tbody tr td').textContent.trim() === 'Mozart'`),
      await ev(`document.querySelector('tbody tr td').textContent.trim()`));
check("the full name is still reachable from the row",
      await ev(`document.querySelector('tbody tr td').title.includes('Wolfgang')`));
check("a shared surname is disambiguated, an unshared one is not",
      await ev(`(()=>{const t=[...document.querySelectorAll('tbody tr td:first-child')]
        .map(c=>c.textContent.trim());
        return t.includes('Haydn, Joseph') && t.includes('Haydn, Michael') && t.includes('Beethoven')})()`));
check("no Wikipedia disambiguator leaks into the column",
      await ev(`[...document.querySelectorAll('tbody tr td:first-child')]
        .every(c => !/[()\\d]/.test(c.textContent))`));
check("a compound surname is not split in half",
      await ev(`[...document.querySelectorAll('tbody tr td:first-child')]
        .some(c => c.textContent.trim() === 'Maxwell Davies')`),
      "Peter Maxwell Davies is filed under Maxwell Davies, not Davies");
check("every surname override still names a composer",
      (await ev(`Names.staleOverrides()`)).length === 0,
      "stale: " + JSON.stringify(await ev(`Names.staleOverrides()`)));
await ev(`[...document.querySelectorAll('thead th button')].find(b=>b.textContent==='Composer').click()`);
check("sorting by Composer sorts by surname",
      await ev(`(()=>{const t=[...document.querySelectorAll('tbody tr td:first-child')]
        .slice(0,3).map(c=>c.textContent.trim());
        return t.every((v,i)=>i===0||t[i-1].localeCompare(v)<=0)})()`),
      await ev(`[...document.querySelectorAll('tbody tr td:first-child')].slice(0,3)
        .map(c=>c.textContent.trim()).join(' | ')`));

// --- 4h. the footnote says true things about where the data came from --------------------------
// Both of these were wrong on the live site. The footer credited the 2014 EXPERIMENT to Mike
// Bostock, whose fisheye.js it merely used; and it said the composer list was "scraped from
// Wikipedia in May 2014" when the list here is a fresh scrape and 2014 is the original's date.
const footer = await ev(`document.querySelector('footer').textContent.replace(/\\s+/g,' ')`);
const flinks = await ev(`[...document.querySelectorAll('footer a')].map(a => a.getAttribute('href'))`);
check("the footnote links the original experiment",
      flinks.some(h => h.includes("viz.runningwithdata.com/quartet_composers")), flinks.join(", "));
check("it does not credit the experiment to the author of the fisheye plugin",
      !/Bostock/.test(footer) && !flinks.some(h => h.includes("d3-plugins")),
      "the fisheye code credit belongs in README.md and chart.js, where it is used");
check("it does not date this page's composer list to 2014",
      !/2014/.test(await ev(`document.getElementById('prov').textContent`)));
// The revision is a PERMALINK, not decoration. Every number in that sentence was counted from
// one document, and the live list has moved since — so naming the revision in text while linking
// today's page would be a citation that does not resolve to what was cited. Asserted against
// composers.json's own list_revid rather than a literal, because a pipeline run changes it.
const provRevid = await ev(`(async()=>(await (await fetch('composers.json')).json()).meta.list_revid)()`);
const provLink = await ev(`(()=>{const a=[...document.querySelectorAll('#prov a')]
  .find(a => /List of String Quartet Composers/i.test(a.textContent));
  return a ? a.textContent + ' -> ' + a.getAttribute('href') : '(no list link in the footnote)'})()`);
check("the provenance links the exact revision it was scraped from, not today's list",
      provLink.includes(`v${provRevid}`) && provLink.includes(`oldid=${provRevid}`), provLink);
// The lede frames what readership MEANS; the footnote says where it came from. Saying both twice
// is what "wordsmithing and consistency" was about.
// A property id is jargon until it is clickable: "Dates are Wikidata P569/P570" names a source
// the reader has no way to check from the page. Every id in the line links to its definition.
const props = await ev(`[...document.querySelectorAll('#prov a')]
  .map(a => a.textContent + ' ' + a.getAttribute('href'))`);
check("every Wikidata property id in the footnote is a link to its definition",
      ["P569", "P570", "P21"].every(p =>
        props.includes(`${p} https://www.wikidata.org/wiki/Property:${p}`)),
      props.join(" | "));
// Property anchors only: the footnote also links the source list, and counting THAT one here
// would make this check fail for the presence of a second kind of link rather than for a bare id.
check("no property id is left as bare text",
      await ev(`(()=>{const el=document.getElementById('prov');
        const linked=[...el.querySelectorAll('a')].map(a=>a.textContent)
          .filter(t=>/^P[1-9]\\d*$/.test(t));
        const all=el.textContent.match(/\\bP[1-9]\\d*\\b/g)||[];
        return all.every(p=>linked.includes(p)) && all.length===linked.length})()`),
      await ev(`(document.getElementById('prov').textContent.match(/\\bP[1-9]\\d*\\b/g)||[]).join()`));
check("linkifying did not disturb the sentence",
      /Dates are Wikidata P569\/P570\./.test(await ev(`document.getElementById('prov').textContent`)),
      await ev(`document.getElementById('prov').textContent.slice(120, 220)`));

check("the footnote does not restate the lede's framing",
      !/not as importance/.test(await ev(`document.getElementById('prov').textContent`)));

// --- 4h2. the empty detail panel describes the DOTS, not the roster ---------------------------
// It sits beside the chart and read "884 composers, born 1582–1989" — but the 94 rows the list
// page states no quartet count for are in the table only, and three of them are the earliest
// births on the roster, so the sentence dated a picture by composers it does not contain and
// began a century before the x axis does. Static: plottability is not a filter (issue 8).
await goto(BASE);
const plotStats = await ev(`(async()=>{const d=await (await fetch('composers.json')).json();
  const p=d.rows.filter(r=>r[3]!=null);
  return {n:p.length, all:d.rows.length, from:Math.min(...p.map(r=>r[1])),
          to:Math.max(...p.map(r=>r[1])), living:p.filter(r=>r[2]==null).length}})()`);
const emptyPanel = await ev(`document.querySelector('#detail .empty').textContent`);
check("the empty panel counts the composers the chart can place",
      emptyPanel.includes(`${plotStats.n} composers`)
      && !emptyPanel.includes(`${plotStats.all} composers`), emptyPanel);
check("it dates them by the plotted births, not the roster's",
      emptyPanel.includes(`${plotStats.from}–${plotStats.to}`),
      `plotted births are ${plotStats.from}–${plotStats.to}; the panel says: ${emptyPanel}`);
check("the living count is of those same rows",
      emptyPanel.includes(`${plotStats.living} are still living`), emptyPanel);
check("the count matches the dots actually drawn",
      await ev(`document.querySelectorAll('circle.dot').length`) === plotStats.n);

// --- 4i. the gender filter ---------------------------------------------------------------------
// A third filter in a row that composes by intersection. It is the only one with no module, so
// these checks are the only thing standing between it and a quiet divergence from the other two:
// the same "Set of indices or null" contract, the same URL round-trip, the same live chart.
await goto(BASE);
const allRows = await ev(`document.querySelectorAll('tbody tr').length`);
check("the gender filter lives in the one filter row, not in a card",
      await ev(`!!document.getElementById('filters').querySelector('#gender')`));
await ev(`document.querySelector('#gender button[data-g="female"]').click()`);
await idle();              // the frame closes in on the filter over 420ms; these read the settled state
const women = await ev(`document.querySelectorAll('tbody tr').length`);
check("filtering to women filters the table", women > 100 && women < allRows / 2,
      `${women} of ${allRows}`);
check("the pressed pill is the only pressed pill",
      await ev(`[...document.querySelectorAll('#gender button')]
        .map(b=>b.getAttribute('aria-pressed')).join()`) === "false,true,false");
check("it dims the rest of the chart rather than deleting it",
      await ev(`(()=>{const d=[...document.querySelectorAll('#plot svg circle.dot')];
        return d.length > 700 && d.filter(c=>+c.getAttribute('opacity')<0.2).length > 300})()`),
      await ev(`document.querySelectorAll('#plot svg circle.dot').length`) + " dots drawn");
// The point of option C: at the resting 0.22 the kept dots were barely separable from the 0.07
// ghosts, in the view whose whole job is showing where a group sits against the field.
check("the kept dots are emphasised, not merely less dim",
      await ev(`[...document.querySelectorAll('#plot svg circle.dot')]
        .filter(c=>+c.getAttribute('opacity')>0.5).length > 150`),
      "opacities: " + await ev(`[...new Set([...document.querySelectorAll('#plot svg circle.dot')]
        .map(c=>c.getAttribute('opacity')))].sort().join(' ')`));
// Every one of the thirteen names the Fame view argues about is a man, so a women filter used
// to leave the view with 219 emphasised dots and no labels at all: it showed where they are and
// refused to say who they are. A filtered field names its own most-read survivors.
const wlabels = await ev(`[...document.querySelectorAll('#plot svg text')].map(t=>t.textContent)`);
check("a filtered Fame view still names somebody",
      wlabels.includes("Price") && wlabels.length > 3,
      wlabels.filter(t => !/quartet|readers|written|month/.test(t)).join(" | "));
// Prominence, not readership: filtered to the women, readership names whoever has the biggest
// article (Beach, Monk — one quartet each, famous for other work) and never reaches the two who
// actually wrote the quartets. This is the difference the ranking exists to make.
check("the filtered view names the composers who stand out ON THIS CHART",
      wlabels.includes("Kats-Chernin") && wlabels.includes("Vrebalov"),
      wlabels.filter(t => /[A-Za-z]{4} /.test(t)).join(" | "));
check("it names only composers the filter kept",
      // Both sides in the chart's vocabulary: the label prints the SHORT name and the cell's
      // title carries the canonical one, so the row titles are shortened to compare them.
      await ev(`(()=>{const kept=new Set([...document.querySelectorAll('tbody tr td:first-child')]
          .map(c=>Names.short(c.title)));
        const everyone=new Set(ROWS.map(d=>Names.short(d.name)));
        const drawn=[...document.querySelectorAll('#plot svg text')].map(t=>t.textContent)
          .filter(t=>everyone.has(t));           // the rest of the <text> nodes are axis furniture
        return drawn.length > 0 && drawn.every(n=>kept.has(n))})()`),
      // Naming them: "a label is wrong" is a bug report you would otherwise reproduce by hand.
      "filtered out but still labelled: " + JSON.stringify(await ev(
        `(()=>{const kept=new Set([...document.querySelectorAll('tbody tr td:first-child')]
            .map(c=>Names.short(c.title)));
          const everyone=new Set(ROWS.map(d=>Names.short(d.name)));
          return [...document.querySelectorAll('#plot svg text')].map(t=>t.textContent)
            .filter(t=>everyone.has(t) && !kept.has(t))})()`)));

// The diagonal captions live in the grid layer, so they were never in the label collision map —
// invisible while the thirteen sat in open space, systematic once ten names crowd the left band.
check("no composer label is printed over a diagonal caption",
      await ev(`(()=>{const box=e=>e.getBoundingClientRect();
        const all=[...document.querySelectorAll('#plot svg text')];
        const dg=all.filter(t=>/per quartet|\\/quartet/.test(t.textContent)).map(box);
        const names=new Set(ROWS.map(d=>Names.short(d.name)));
        const nm=all.filter(t=>names.has(t.textContent)).map(box);
        return nm.length > 0 && !nm.some(a=>dg.some(b =>
          a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top))})()`),
      "a name is sitting on a readers-per-quartet caption");

check("the filter is in the URL", (await ev(`location.hash`)).includes("g=female"),
      await ev(`decodeURIComponent(location.hash)`));
// The pills wear the view switcher's `.seg` look. An unscoped ".seg button" handler bound the
// switcher over the filter, so a pill press called setMode(undefined) — the chart left every
// named mode, the legend emptied and the URL grew "#v=undefined". Two groups, one class.
check("filtering does not touch the chart view",
      await ev(`Chart.getMode() === 'fame'`), await ev(`String(Chart.getMode())`));

// fetch_wikidata.py can label eight P21 values and there are two pills, so the vocabularies can
// drift. A stated gender no pill reaches is a composer in neither filter, while the footnote still
// counts only the ones with no claim — silent in exactly the way the canon rename check exists for.
check("every stated gender is reachable by a pill",
      (await ev(`unfilterableGenders()`)).length === 0,
      "unreachable: " + JSON.stringify(await ev(`unfilterableGenders()`)));

// Unknown is in NEITHER set, so the three counts must PARTITION the roster. Asserting
// `women + men < allRows` instead goes vacuous the moment the data has no null claim; the
// partition holds at zero and still catches nulls filed under "male".
await ev(`document.querySelector('#gender button[data-g="male"]').click()`);
await settle(`${rowCount} !== ${women}`);
const men = await ev(`document.querySelectorAll('tbody tr').length`);
const noClaim = await ev(`ROWS.filter(d => d.gender == null).length`);
check("the gender pills partition the roster — a null claim is in neither",
      women + men + noClaim === allRows,
      `${women} women + ${men} men + ${noClaim} unstated = ${allRows}`);

// Intersection, not replacement — the same contract the search box and the brush hold to.
await ev(`(()=>{const q=document.getElementById('q'); q.value='haydn';
  q.dispatchEvent(new Event('input',{bubbles:true}));})()`);
await settle(`${rowCount} < 3`);
check("gender and search combine rather than override",
      await ev(`document.querySelectorAll('tbody tr').length`) < 3, "haydn ∩ men");
await ev(`(()=>{const q=document.getElementById('q'); q.value='';
  q.dispatchEvent(new Event('input',{bubbles:true}));})()`);
await ev(`document.querySelector('#gender button[data-g=""]').click()`);
await settle(`${rowCount} === ${allRows}`);
check("clearing to All restores every row",
      await ev(`document.querySelectorAll('tbody tr').length`) === allRows);
check("clearing drops the filter from the URL", !(await ev(`location.hash`)).includes("g="));

// A shared link has to arrive filtered, with the control showing it — a URL that filters the data
// but leaves three unpressed pills is a state the reader cannot undo because they cannot see it.
await goto(BASE + "#g=female");
check("a shared link arrives filtered, with the pill pressed",
      await ev(`document.querySelectorAll('tbody tr').length`) === women
   && await ev(`document.querySelector('#gender button[data-g="female"]').getAttribute('aria-pressed') === 'true'`));
// #g=nonsense must fall back to everyone rather than emptying the table with no visible cause.
await goto(BASE + "#g=chicken");
check("a junk gender in the URL falls back to everyone",
      await ev(`document.querySelectorAll('tbody tr').length`) === allRows,
      await ev(`document.querySelectorAll('tbody tr').length`) + " rows");
check("the footnote says whose statement the gender is",
      /P21/.test(await ev(`document.getElementById('prov').textContent`)),
      await ev(`document.getElementById('prov').textContent.slice(-220)`));

// --- 4j. the frame follows the filter ---------------------------------------------------------
// A filter used to leave the frame on the whole field: ask for the women and you got the same
// picture with 600 dots dimmed and the survivors still crammed into the corner they always
// occupied, which answers "where are they" at the resolution of the group you filtered AWAY. The
// frame now closes in on what the filter kept — against the ghost of the field, which is still
// drawn at 0.07, so it is a highlight and not a subtraction.
await goto(BASE);
check("nothing is fitted until something is filtered", await ev(`Chart.zoomK()`) === 1,
      "k=" + await ev(`Chart.zoomK()`));
await ev(`document.querySelector('#gender button[data-g="female"]').click()`);
await idle();
const fitK = await ev(`Chart.zoomK()`);
check("filtering closes the frame in on what it kept", fitK > 1.2, "k=" + fitK);
// One scale for both axes, so it is the TIGHTER one that ends up filling its side of the box and
// the other keeps whatever slack the aspect ratio leaves. Fitting the two independently would
// stretch the picture and make the readers-per-quartet diagonals lie.
check("and closes in until the kept dots fill the box",
      await ev(`(()=>{const b=document.querySelector('#plot svg rect.bg');
        const W=+b.getAttribute('width'), H=+b.getAttribute('height');
        const kept=[...document.querySelectorAll('#plot svg circle.dot')]
          .filter(c=>+c.getAttribute('opacity')>0.5 && c.getAttribute('display')!=='none');
        const xs=kept.map(c=>+c.getAttribute('cx')), ys=kept.map(c=>+c.getAttribute('cy'));
        return kept.length>50 && Math.max((Math.max(...xs)-Math.min(...xs))/W,
                                          (Math.max(...ys)-Math.min(...ys))/H) > 0.8})()`),
      "the fitted box does not fill the plot on either axis");
// "Exactly" cuts both ways: a frame that fits the survivors and then leaves one of them outside
// it is worse than no fit at all. cx below -1e6 is layout()'s park for a dot it cannot place at
// all (no view count), which is absence, not exclusion.
check("no composer the filter kept is left outside the frame",
      await ev(`[...document.querySelectorAll('#plot svg circle.dot')]
        .filter(c=>+c.getAttribute('opacity')>0.5 && c.getAttribute('display')==='none'
                && +c.getAttribute('cx') > -1e6).length`) === 0,
      "kept but off-frame");
// The fitted box IS the resting view while the filter is on, so the reset button must read as off
// — lighting it up says "you pinched" to a reader who only pressed a pill.
check("a fitted frame does not read as a pinch", await ev(`document.getElementById('reset').disabled`));
// ...and "reset" then means back to where this filter opens, not out to the whole field: dropping
// the reader to the full extent would undo the filter's answer rather than their gesture.
const fbox = await ev(`(()=>{const b=document.querySelector('#plot svg rect.bg').getBoundingClientRect();
  return {x:b.x,y:b.y,w:b.width,h:b.height}})()`);
for (let i = 0; i < 4; i++) {
  await send("Input.dispatchMouseEvent", { type: "mouseWheel", x: fbox.x + fbox.w / 2,
    y: fbox.y + fbox.h / 2, deltaX: 0, deltaY: -120, pointerType: "mouse" });
  await sleep(80);
}
await settle(`!document.getElementById('reset').disabled`);
check("pinching a filtered view still lights the reset button",
      !(await ev(`document.getElementById('reset').disabled`)),
      "k=" + await ev(`Chart.zoomK()`));
await ev(`document.getElementById('reset').click()`);
await idle();
check("reset returns to the filter's frame, not to the whole field",
      Math.abs(await ev(`Chart.zoomK()`) - fitK) < 0.01, "k=" + await ev(`Chart.zoomK()`));
await ev(`document.querySelector('#gender button[data-g=""]').click()`);
await idle();
check("clearing the filter opens the frame back out", await ev(`Chart.zoomK()`) === 1,
      "k=" + await ev(`Chart.zoomK()`));

// --- 4j. a handful of dots is not a box worth fitting ------------------------------------------
// A search that keeps ONE composer gave computeResting() a zero-width, zero-height box, so fit()
// returned Infinity on both axes and k landed on the 24x clamp: looking someone up threw the
// reader to maximum magnification, where the cloud the dot is being compared AGAINST is off
// screen entirely. Below MIN_FIT the frame does not move and the filter does its other job — the
// match comes up while the field stays drawn at 0.07 behind it.
const searchFor = q => ev(`(()=>{const el=document.getElementById('q'); el.value=${JSON.stringify(q)};
  el.dispatchEvent(new Event('input',{bubbles:true}));})()`);
await searchFor("mozart");
await idle();
check("searching one composer does not zoom the chart", await ev(`Chart.zoomK()`) === 1,
      "k=" + await ev(`Chart.zoomK()`));
const upDots = `[...document.querySelectorAll('#plot svg circle.dot')]
  .filter(c=>+c.getAttribute('opacity')>0.5 && c.getAttribute('display')!=='none').length`;
check("and the one match is still emphasised against the field",
      await ev(upDots) === 1, "emphasised dots=" + await ev(upDots));
// Two dots have a real box and still are not a picture; three Haydns would not be either.
await searchFor("haydn");
await idle();
check("nor does a two-composer search", await ev(`Chart.zoomK()`) === 1,
      "k=" + await ev(`Chart.zoomK()`));
// The threshold is a floor on a degenerate box, NOT a retreat from fitting filters: a search with
// a group behind it still gets the frame closed in on it.
await searchFor("anton");
await idle();
check("a search that keeps a group still fits the frame", await ev(`Chart.zoomK()`) > 1.2,
      "k=" + await ev(`Chart.zoomK()`));
await searchFor("");
await idle();
check("clearing the search opens the frame back out", await ev(`Chart.zoomK()`) === 1,
      "k=" + await ev(`Chart.zoomK()`));
// Skipping the fit means the FULL EXTENT, not wherever the reader had pinched to. It is the one
// consequence of this guard a reader can feel, so it is pinned rather than left to be rediscovered
// as a surprise: restingTransform() must stay a pure function of the filter, the mode and the box
// (its memo and resetZoom() both depend on that), and this is also exactly what clearing a filter
// does. Zoom in first, then search.
const zbox = await ev(`(()=>{const b=document.querySelector('#plot svg rect.bg').getBoundingClientRect();
  return {x:b.x,y:b.y,w:b.width,h:b.height}})()`);
for (let i = 0; i < 8; i++) {
  await send("Input.dispatchMouseEvent", { type: "mouseWheel", x: zbox.x + zbox.w / 2,
    y: zbox.y + zbox.h / 2, deltaX: 0, deltaY: -300, pointerType: "mouse" });
  await sleep(120);
}
await settle(`Chart.zoomK() > 2`);
const pinched = await ev(`Chart.zoomK()`);
await searchFor("mozart");
await idle();
check("a search from a pinched view returns to the full field, not to the pinch",
      pinched > 2 && await ev(`Chart.zoomK()`) === 1,
      `pinched to k=${pinched}, then k=${await ev(`Chart.zoomK()`)}`);
await searchFor("");
// Each view fits its own filter: the same composers occupy a different box in a timeline than in
// a log-log readership cloud, so a view switch recomputes the frame instead of carrying it over.
await goto(BASE + "#g=female&v=scatter");
await idle();
const scatterK = await ev(`Chart.zoomK()`);
// A modest fit, and that is the point: the women span nearly the whole birth-year range, so the
// timeline has little to close in on where the readership cloud had a great deal.
check("a filtered timeline fits its own box, not the Fame view's",
      scatterK > 1 && Math.abs(scatterK - fitK) > 0.05, `scatter k=${scatterK}, readers k=${fitK}`);

// --- 4k. the ring follows the filter -----------------------------------------------------------
// Every one of the curated thirteen is a man, so "Women" dimmed every accented dot to 0.07 and
// left the group with no emphasis of its own — in the one view whose whole job is picking a few
// names out of a field. The ring now says the same thing about whatever group is on screen.
await goto(BASE);
const ringsOf = `(()=>{const acc=getComputedStyle(document.documentElement)
    .getPropertyValue('--accent').trim();
  const shown=c=>c.getAttribute('display')!=='none' && +c.getAttribute('opacity')>0.5;
  return {dots:[...document.querySelectorAll('#plot svg circle.dot')]
            .filter(c=>c.getAttribute('stroke')===acc && shown(c)).length,
          labels:[...document.querySelectorAll('#plot svg text')]
            .filter(t=>t.getAttribute('font-size')==='10.5' && t.getAttribute('fill')===acc)
            .map(t=>t.textContent)}})()`;
const restRings = await ev(ringsOf);
check("the resting view rings the curated three and nothing else",
      await ev(`Chart.derivedRings()`) === 0 && restRings.dots === 3,
      `${restRings.dots} rings, ${await ev(`Chart.derivedRings()`)} derived`);
await ev(`document.querySelector('#gender button[data-g="female"]').click()`);
await idle();
const womenRings = await ev(ringsOf);
check("filtering to the women rings three of THEM", await ev(`Chart.derivedRings()`) === 3,
      "derived=" + await ev(`Chart.derivedRings()`));
// A ring with no name points at a composer the view refuses to identify — the exact complaint the
// rings were added to answer. They are seeds in pickLabels for that reason.
check("every derived ring is also named", womenRings.dots === 3 && womenRings.labels.length === 3,
      `${womenRings.dots} rings, ${womenRings.labels.length} accent labels: ${womenRings.labels.join(", ")}`);
check("and it rings composers the curated set never held",
      womenRings.labels.every(n => !restRings.labels.includes(n)),
      "overlap: " + womenRings.labels.filter(n => restRings.labels.includes(n)).join(", "));
// An outlier drawn on top of something already emphasised is not an outlier, it is clutter: the
// ring used to land on Meredith Monk, whose disc came within 4px of Amy Beach's — two 6.75px dots
// with a hairline between them. Prominence is distance from the CENTRE of the cloud, so a corner
// full of composers all scores high and the tie was broken by nothing visual at all.
//
// MEASURED, because the whole claim is about pixels. The bar is a whole dot's DIAMETER of clear
// space between the closest ring and the closest fill — "not touching" is too weak to catch what
// this fixes, since the old pick cleared touching by 4px and still read as one smudge.
// The measurement itself, reusable: the closest ring/fill pair, in the geometry on screen.
const closestOf = `(()=>{const cs=getComputedStyle(document.documentElement);
  const paint=v=>{const el=document.createElement('i'); el.style.color=cs.getPropertyValue(v).trim();
    document.body.appendChild(el); const c=getComputedStyle(el).color; el.remove(); return c};
  const acc=cs.getPropertyValue('--accent').trim(), sel=cs.getPropertyValue('--sel').trim();
  const accRgb=paint('--accent'), selRgb=paint('--sel');
  const shown=c=>c.getAttribute('display')!=='none' && +c.getAttribute('opacity')>0.5;
  const all=[...document.querySelectorAll('#plot svg circle.dot')].filter(shown);
  const at=c=>({x:+c.getAttribute('cx'), y:+c.getAttribute('cy'), r:+c.getAttribute('r')});
  const rings=all.filter(c=>[acc,accRgb].includes(c.getAttribute('stroke'))).map(at);
  const fills=all.filter(c=>[sel,selRgb].includes(c.getAttribute('fill'))).map(at);
  let best=Infinity, slack=Infinity;
  for(const a of rings) for(const b of fills){
    const d=Math.hypot(a.x-b.x,a.y-b.y);
    if(d<best){best=d; slack=d-(a.r+b.r);}}
  const r=rings.length&&fills.length?rings[0].r:0;
  return {rings:rings.length, fills:fills.length, r:+r.toFixed(2),
          gap:+best.toFixed(1), slack:+slack.toFixed(1)}})()`;
const closest = await ev(closestOf);
check("no derived ring is drawn on top of a filled composer",
      closest.rings === 3 && closest.fills === 9 && closest.slack > 2 * closest.r,
      `${closest.rings} rings vs ${closest.fills} fills; closest pair ${closest.gap}px apart, `
      + `${closest.slack}px clear of touching, needs ${(2 * closest.r).toFixed(1)}`);
// The promise the chip makes is that a row and its dot are the same thing, so it moves too.
// The subject is READ OFF the chart rather than named here. It used to be Elena Kats-Chernin,
// who was the top prominence pick until she joined the women's curated set -- at which point her
// chip correctly turned --sel and this check failed for the one reason it should not, that the
// composer it happened to name changed role. Whoever the view rings is who it tests.
const ringSubject = await ev(`(()=>{const acc=getComputedStyle(document.documentElement)
    .getPropertyValue('--accent').trim();
  const labels=[...document.querySelectorAll('#plot svg text')]
    .filter(t=>t.getAttribute('font-size')==='10.5' && t.getAttribute('fill')===acc)
    .map(t=>t.textContent);
  const r=ROWS.find(d=>labels.includes(Names.short(d.name)));
  return r ? r.name : null})()`);
check("the table chip follows the derived ring",
      ringSubject != null && await ev(`(()=>{const acc=getComputedStyle(document.documentElement)
          .getPropertyValue('--accent').trim();
        const r=[...document.querySelectorAll('tbody tr')]
          .find(r=>r.querySelector('td').title===${JSON.stringify(ringSubject)});
        if(!r) return false;
        const c=r.querySelector('.chip');
        const paint=c.style.background==='transparent' ? c.style.boxShadow : c.style.background;
        const el=document.createElement('i'); el.style.color=acc; document.body.appendChild(el);
        const rgb=getComputedStyle(el).color; el.remove();
        return paint.includes(rgb)})()`),
      "ringed composer tested: " + ringSubject);
// Filtering to the men keeps all three curated outliers, so there is nothing to derive — the
// ring budget is THREE, not three-plus-three, or a filter that changes almost nothing would
// double the ink.
await goto(BASE + "#g=male");
check("a filter that keeps the curated three derives none",
      await ev(`Chart.derivedRings()`) === 0 && (await ev(ringsOf)).dots === 3,
      "derived=" + await ev(`Chart.derivedRings()`));
// A ring means "stands out from the crowd it is drawn in", so it needs a crowd. Two Haydns are
// already the whole picture; ringing them would be pointing at everything.
await goto(BASE + "#q=haydn");
check("too small a group to have a crowd derives no rings",
      await ev(`Chart.derivedRings()`) === 0, "derived=" + await ev(`Chart.derivedRings()`));

// --- 4l. the FILL follows the filter too, but by taste, not by ranking -------------------------
// #7 asked whether the curated set should be computed. The ring: yes, it is a property of the
// crowd on screen. The fill: no, a canon is a claim about what gets played. So the women's group
// got a SECOND hand-written list rather than a derived one, and the two answers sit side by side
// here — three rings earned by prominence, nine dots filled by taste.
const filledOf = `(()=>{const sel=getComputedStyle(document.documentElement)
    .getPropertyValue('--sel').trim();
  const el=document.createElement('i'); el.style.color=sel; document.body.appendChild(el);
  const rgb=getComputedStyle(el).color; el.remove();
  const shown=c=>c.getAttribute('display')!=='none' && +c.getAttribute('opacity')>0.5;
  const hit=[...document.querySelectorAll('#plot svg circle.dot')].filter(c=>{
    const f=c.getAttribute('fill'); return (f===sel||f===rgb) && shown(c)});
  return hit.length})()`;
await goto(BASE);
const restFill = await ev(filledOf);
check("the resting view fills the default repertoire", restFill === 10, "filled=" + restFill);
// The gate is the whole design: not one of the nine clears 10,000 readers a month, so at rest
// they would be nine filled dots low in the densest part of the cloud under a key that says "the
// repertoire" — claiming to be the same set as Mozart. They are a different claim.
check("and none of the women's set is filled at rest",
      await ev(`Chart.seedNames().some(n => n === "Florence Price")`) === false,
      await ev(`JSON.stringify(Chart.seedNames())`));
await goto(BASE + "#g=female");
const womenFill = await ev(filledOf);
check("the Women filter swaps in a curated set of its own", womenFill === 9, "filled=" + womenFill);
check("and it is the hand-written one, not a ranking",
      await ev(`(()=>{const s=new Set(Chart.seedNames());
        return ["Fanny Hensel","Amy Beach","Rebecca Clarke","Florence Price","Elizabeth Maconchy",
                "Grażyna Bacewicz","Sofia Gubaidulina","Elena Kats-Chernin","Jennifer Higdon"]
          .every(n => s.has(n))})()`),
      await ev(`JSON.stringify(Chart.seedNames())`));
// "Men" keeps every name in the default list, so nothing about that view may move.
await goto(BASE + "#g=male");
check("filtering to the men changes neither the fill nor the key",
      await ev(filledOf) === 10
      && await ev(`document.getElementById('legend').textContent
                     .includes(Chart.repertoireLabel())`),
      "filled=" + await ev(filledOf));
// The separation is measured against the PICTURE, and every mode draws a different one in a
// differently shaped box — while fill, stroke, width, opacity and label colour are all Fame-only,
// so a filter applied in the timeline chose its rings from a geometry where none of them existed.
// Those picks were then drawn unchanged in Fame: this exact route put a ring 3.1px from a filled
// dot. Reachable from a shared link, which is why it is checked as one.
await goto(BASE + "#v=scatter&g=female");
await ev(`[...document.querySelectorAll('.controls .seg button')].find(b=>b.dataset.mode==='fame').click()`);
await settle(`Chart.getMode() === 'fame'`);
const afterSwitch = await ev(closestOf);
check("arriving in Fame from another view re-derives the rings for THIS geometry",
      afterSwitch.rings === 3 && afterSwitch.slack > 2 * afterSwitch.r,
      `closest pair ${afterSwitch.gap}px apart, ${afterSwitch.slack}px clear, `
      + `needs ${(2 * afterSwitch.r).toFixed(1)}`);
// The other half of the same bug, and the one that was actually caught in the wild: a ROTATION or
// a window drag changes the box without changing the filter, so resize() has to re-derive too.
// Shrunk AFTER loading on purpose — loading fresh at this size derives correctly and proves
// nothing. Pre-fix this measured 5.7px of clearance against a 10.6px bar.
await goto(BASE + "#g=female");
await viewport(360, 780, true);
await laidOut();
const onPhone = await ev(closestOf);
check("and resizing to a phone re-derives them for the smaller box",
      onPhone.rings >= 1 && onPhone.fills > 0 && onPhone.slack > 2 * onPhone.r,
      `${onPhone.rings} rings, r=${onPhone.r}; closest pair ${onPhone.gap}px apart, `
      + `${onPhone.slack}px clear, needs ${(2 * onPhone.r).toFixed(1)}`);
await viewport(1100, 1500);
// Same staleness contract as the composer names and the P21 values: a curated set keyed to a pill
// that does not exist can never be shown, and looks maintained while doing nothing.
await goto(BASE);
check("every curated set is reachable by a pill",
      await ev(`Chart.repertoireKeys().every(k =>
        [...document.querySelectorAll('#gender button')].some(b => b.dataset.g === k))`),
      await ev(`JSON.stringify(Chart.repertoireKeys())`));

// --- 4m. the lede says one static thing, and stays out of the layout's way ---------------------
// It used to carry a clause BUILT from the chart — which set is picked out, its birth span, a
// worked example — and three sections here checked it. That sentence is gone (issue 35): it could
// empty or change length under a filter, which moved everything below it, so it dragged
// reserveLede(), a ResizeObserver and a 20px page shift (issue 36) behind it. Nothing was lost by
// cutting it that the page still needs: the legend and the axes each still state their own, and
// the readership caveat was later cut from the footnote deliberately rather than moved, so nothing
// here pretends it survived somewhere else.
await goto(BASE);
// Defined here because the sections below still use it and its old home was one of the three this
// replaced. searchFor() lives up in section 4.
const pill = m => ev(`document.querySelector('.controls .seg button[data-mode="${m}"]').click()`);
const ledeText = () => ev(`document.querySelector('.lede').textContent.replace(/\\s+/g,' ').trim()`);
check("the lede is one static sentence", (await ledeText()) ===
      "Everyone on Wikipedia's List of String Quartet Composers, visualized.", await ledeText());
check("...that links the list it names",
      await ev(`!!document.querySelector('.lede a[href*="List_of_string_quartet_composers"]')`));
// The two of its claims the page still makes, each stated by the component that owns it. This is
// the rule in CLAUDE.md — build a claim only where the page states it nowhere else — checked
// rather than asserted, so cutting the sentence cannot quietly cut the information with it.
check("the legend still names the highlighted set",
      await ev(`document.getElementById('legend').textContent
                  .includes(Chart.repertoireLabel())`),
      await ev(`document.getElementById('legend').textContent.replace(/\\s+/g,' ').trim().slice(0,60)`));
check("the axes are still named by the chart itself",
      await ev(`[...document.querySelectorAll('#plot svg text')]
        .some(t=>t.textContent.includes("readers / month"))`)
      && (await ev(`document.getElementById('hint').textContent`)).length > 10,
      await ev(`document.getElementById('hint').textContent`));
// And it can no longer move: nothing writes to it, so no filter and no view can change its height.
const ledeH = () => ev(`document.querySelector('.lede').getBoundingClientRect().height`);
const ledeRest = await ledeH();
await goto(BASE + "#g=female&r=751-4501");
check("no filter changes the lede's height any more",
      Math.abs(await ledeH() - ledeRest) < 0.5,
      `${ledeRest.toFixed(1)} -> ${(await ledeH()).toFixed(1)} under the combination that moved it 20px`);
check("...and it reserves no height of its own to go stale",
      await ev(`!document.querySelector('.lede').style.minHeight`),
      await ev(`JSON.stringify(document.querySelector('.lede').style.minHeight)`));
await goto(BASE);

// --- 4m4. ...and neither does a view switch, because the switcher is no longer under the plot ---
// The residue of 4m3 (issue 29). Reserving the lede settled the plot's TOP; its HEIGHT still
// changes with the view, because measure() in chart.js picks an aspect ratio per mode — a
// square-ish Fame cloud, a naturally wide timeline, a swarm as tall as its collisions demand. With
// the controls under the plot, pressing Timeline on a phone lifted the pill you had just pressed
// 52px (61px for the swarm, 150px at 1280), so a quick second press landed on the wrong control:
// the same double-tap trap the full-screen strip's fixed height answers one component up.
//
// The fix is the ORDER, not the ratios — the picture is honestly a different shape per view, and
// one height for all four either squeezes the Fame cloud or leaves a blank band under the short
// ones. So the row moved above the plot and nothing a finger rests on is placed by a box the same
// press resizes. Driven IN PLACE by the pills, like 4m3: a boot lays the page out once and could
// never show the jump.
//
// The plot's height is asserted to CHANGE in the same breath, or this passes on a chart that had
// stopped resizing at all and the check would be measuring nothing.
const segTop = () => ev(`document.querySelector('.controls .seg').getBoundingClientRect().top`);
const plotHeight = () => ev(`document.getElementById('plot').getBoundingClientRect().height`);
for (const [w, h, mobile] of [[390, 844, true], [1280, 900, false]]) {
  await viewport(w, h, mobile);
  await goto(BASE);
  const restTop = await segTop(), restH = await plotHeight();
  let worstTop = 0, worstH = 0;
  for (const m of ["scatter", "swarm", "lens", "fame"]) {
    await pill(m);
    await laidOut();
    worstTop = Math.max(worstTop, Math.abs(await segTop() - restTop));
    worstH = Math.max(worstH, Math.abs(await plotHeight() - restH));
  }
  check(`a view switch does not move the switcher at ${w}px`, worstTop < 1.5,
        `switcher moved ${worstTop.toFixed(1)}px while the plot resized by up to ${worstH.toFixed(0)}px`);
  check(`...and there was a real shift to absorb at ${w}px`, worstH > 15,
        `plot height ${restH.toFixed(0)} changed by up to ${worstH.toFixed(0)}px across the four views`);
}
await viewport(1100, 1500);

// --- 4m5. ...and neither does a filter, because no control appears or disappears any more --------
// The rule 4m4 settled, one row up. Issue 31 fixed the readership brush's own Clear button in
// place — it appeared on the first frame of a drag, and it shared line one of `.filterbar` with the
// "Readership" label, so showing it took that line from a 17.4px label to a 40px button and dropped
// the brush, the pills and the plot 22.6px under the finger. Issue 35 removed the CATEGORY instead:
// there is no per-filter Clear at all now, one permanent `Reset filters` button in .controls clears
// all three, and a control that can never appear can never resize the row it is in.
//
// So this section no longer measures a step and hopes it is small. It asserts that going from no
// filter to all three filters, by every route a reader has, moves NOTHING. Under touch emulation,
// for the reason section 7 states: setDeviceMetricsOverride alone leaves (pointer:coarse) false, so
// a 390px box is a narrow desktop, buttons measure 28px instead of 40px, and the numbers are not
// the ones a phone gets.
await viewport(390, 844, true);
await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
await goto(BASE);
// Everything a filter control's box could push, and the plot under all of it. A check on one
// element passed a layout that moved the pills under a second tap.
const rowTops = () => ev(`JSON.stringify(['#hist','#gender','.controls .seg','#reset-filters','#plot']
  .map(s=>+document.querySelector(s).getBoundingClientRect().top.toFixed(1)))`);
const drift = (a, b) => Math.max(...JSON.parse(a).map((v, i) => Math.abs(v - JSON.parse(b)[i])));
const resetState = () => ev(`(()=>{const b=document.getElementById('reset-filters');
  return JSON.stringify({off:b.disabled, lit:b.classList.contains('on')})})()`);
const hb2 = await ev(`(()=>{const r=document.querySelector('#hist svg').getBoundingClientRect();
  return {x:r.x,y:r.y,w:r.width,h:r.height}})()`);
const rest5 = await rowTops();
check("nothing is filtered at rest, and the button says so",
      await resetState() === `{"off":true,"lit":false}`, await resetState());

// 1. the brush, mid-gesture and on release — the case issue 31 was reported for.
await mouse("mousePressed", hb2.x + hb2.w * 0.60, hb2.y + hb2.h * 0.4);
await mouse("mouseMoved",   hb2.x + hb2.w * 0.78, hb2.y + hb2.h * 0.4);
await settle(`!document.getElementById('reset-filters').disabled`);   // lit on the first frame
await laidOut();
const mid5 = await rowTops(), midState = await resetState();
await mouse("mouseMoved",   hb2.x + hb2.w * 0.92, hb2.y + hb2.h * 0.4);
await laidOut();
const mid5b = await rowTops();
await mouse("mouseReleased", hb2.x + hb2.w * 0.96, hb2.y + hb2.h * 0.4);
await settle(`${rowCount} < ${allRows}`);
await sleep(TWEEN);
check("a real touch device is what this section is measuring",
      await ev(`matchMedia('(pointer:coarse)').matches`) === true
      && await ev(`document.getElementById('reset-filters').getBoundingClientRect().height`) >= 40,
      `Reset filters is ${await ev(`document.getElementById('reset-filters').getBoundingClientRect().height`)}px tall`);
check("brushing moves nothing, mid-drag or on release",
      Math.max(drift(rest5, mid5), drift(rest5, mid5b), drift(rest5, await rowTops())) < 1.5,
      `tops ${rest5} -> ${mid5} mid-drag -> ${await rowTops()} released`);
// It lights up DURING the drag, which the old button could not do without moving the row. A colour
// and a disabled flag change no box, so live feedback is free here where it was not before.
check("...and the button lights up on the first frame of the drag",
      midState === `{"off":false,"lit":true}`, `mid-drag ${midState}`);

// The grip is drawn OUTWARD from the selection edge (issue 40), so a selection pushed to either
// end of the axis bleeds ~6.5px past the svg — histogram.js claims the card's padding absorbs it.
// A phone is where that padding is tightest and the brush is widest, so measure it here instead of
// taking the claim's word for it. Left in place afterwards: it moves no row top, which is what the
// checks below are about.
// max(1, …): the target is 30px left of the svg, which at 390px is x=1 — body padding 16 + border 1
// + card padding 14. A negative coordinate may never reach the renderer, and the check would then
// fail for a reason with nothing to do with the grip. Clamping keeps it past the axis end either way.
const past = Math.max(1, hb2.x - 30);
await mouse("mousePressed", hb2.x + hb2.w * 0.4, hb2.y + hb2.h * 0.4);
await mouse("mouseMoved",   past, hb2.y + hb2.h * 0.4);
await mouse("mouseReleased", past, hb2.y + hb2.h * 0.4);
await settle(`document.querySelectorAll('#hist .grips path').length === 2`);
check("a grip pushed to the end of the axis stays inside the card (390px, in the row's own card)",
      await ev(`(()=>{const g=[...document.querySelectorAll('#hist .grips path')]
          .map(p=>p.getBoundingClientRect()).sort((a,c)=>a.left-c.left)[0];
        const c=document.getElementById('filters').getBoundingClientRect();
        const s=document.querySelector('#hist svg').getBoundingClientRect();
        return g.left < s.left && g.left > c.left + 1})()`),
      await ev(`(()=>{const g=[...document.querySelectorAll('#hist .grips path')]
          .map(p=>p.getBoundingClientRect()).sort((a,c)=>a.left-c.left)[0];
        const c=document.getElementById('filters').getBoundingClientRect();
        const s=document.querySelector('#hist svg').getBoundingClientRect();
        return (s.left - g.left).toFixed(1) + "px past the svg, " +
               (g.left - c.left).toFixed(1) + "px still inside the card"})()`));

// 2. the other two filters, and all three at once — measured on ABSOLUTE tops again. This used to
// need an offset from #filters, because the lede's reserved box shrank 20px under Women plus a
// brush range and lifted the whole page (issue 36). That sentence is gone, so the page genuinely
// does not move and the check can say so directly.
await ev(`document.querySelector('#gender button[data-g="female"]').click()`);
await searchFor("a");
await sleep(TWEEN);
const all3 = await rowTops();
check("all three filters at once still move nothing", drift(rest5, all3) < 1.5,
      `tops ${rest5} -> ${all3} with search + brush + gender`);

// 3. and the button undoes all three, which is what its name promises.
await ev(`document.getElementById('reset-filters').click()`);
await settle(`document.getElementById('reset-filters').disabled`);
await sleep(TWEEN);
check("Reset filters clears the search, the brush and the pills together",
      await ev(`(()=>{const q=document.getElementById('q').value;
        const g=document.querySelector('#gender button[data-g=""]').getAttribute('aria-pressed');
        return q === '' && g === 'true' && !location.hash.includes('r=')
               && !location.hash.includes('g=') && !location.hash.includes('q=')})()`),
      await ev(`'q='+JSON.stringify(document.getElementById('q').value)
        +' hash='+JSON.stringify(decodeURIComponent(location.hash))`));
check("...and goes dark again once there is nothing to reset",
      await resetState() === `{"off":true,"lit":false}`, await resetState());
check("...and the page is back where it started", drift(rest5, await rowTops()) < 1.5,
      `tops ${rest5} -> ${await rowTops()}`);
// One applyFilters, not three: resetFilters() branches on whether the brush has a range, because
// d3-brush emits "end" for a programmatic move and would come back through onChange on its own.
// Rebuilding ~880 rows twice is the one thing in this app that visibly stutters.
check("...having rebuilt the table exactly once",
      await ev(`(()=>{const t=document.querySelector('tbody'); let n=0;
        const o=new MutationObserver(()=>n++); o.observe(t,{childList:true});
        document.querySelector('#gender button[data-g="male"]').click();
        Histogram.setRange([751,4501]); applyFilters(true);
        return new Promise(r=>setTimeout(()=>{ n=0;
          document.getElementById('reset-filters').click();
          setTimeout(()=>{ o.disconnect(); r(n) }, 700) }, 700))})()`) === 1,
      "table repaints on one reset");

// 4. the deep link that used to be the objection to all of this still boots filtered.
await goto(BASE + "#r=751-4501");
check("a #r= deep link boots with Reset filters lit",
      await resetState() === `{"off":false,"lit":true}`, await resetState());
await send("Emulation.setTouchEmulationEnabled", { enabled: false, maxTouchPoints: 0 });
await viewport(1100, 1500);

// --- 5. sorting ---------------------------------------------------------------
await goto(BASE);
await ev(`[...document.querySelectorAll('thead th button')].find(b=>b.textContent==='Quartets').click()`);
check("sort by Quartets desc puts Cambini first",
      (await ev(`document.querySelector('tbody tr td').textContent`)).includes("Cambini"),
      await ev(`document.querySelector('tbody tr td').textContent`));
await ev(`[...document.querySelectorAll('thead th button')].find(b=>b.textContent==='Died').click()`);
check("sort by Died keeps living composers off the top",
      (await ev(`document.querySelectorAll('tbody tr')[0].children[2].textContent`)) !== "—",
      "first Died cell = " + await ev(`document.querySelectorAll('tbody tr')[0].children[2].textContent`));

// --- 6. dark mode repaints the JS-baked colors --------------------------------
// The timeline view, because the lifespan ramp is the legend piece that is baked from the tokens.
await goto(BASE + "#v=scatter");
const dotFill = `document.querySelector('#plot svg circle.dot').getAttribute('fill')`;
const lightFill = await ev(dotFill);
await ev(`Theme.set('dark')`);
await settle(`${dotFill} !== ${JSON.stringify(lightFill)}`);
const darkFill = await ev(`document.querySelector('#plot svg circle.dot').getAttribute('fill')`);
check("theme flip re-bakes the dot colors", lightFill !== darkFill, `${lightFill} -> ${darkFill}`);
check("theme flip re-bakes the legend ramp",
      (await ev(`document.querySelector('#legend .ramp').style.background`)).includes("220, 236, 138"),
      await ev(`document.querySelector('#legend .ramp').style.background`));
await shot("dark");
await ev(`Theme.set('auto')`);

// --- 7. mobile + full screen ---------------------------------------------------
// Touch emulation, not just a 390px box: setDeviceMetricsOverride leaves (pointer:coarse) FALSE,
// so without this the "phone" checks were quietly exercising a narrow desktop — a different code
// path in chart.js (TOUCH) and a different one in styles.css (the compact panel).
await viewport(390, 844, true);
await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
await goto(BASE);
check("the phone viewport really reports a touch pointer",
      await ev(`matchMedia('(pointer:coarse)').matches && matchMedia('(hover:none)').matches`),
      "setDeviceMetricsOverride alone does NOT: chart.js's TOUCH and the compact panel both key off this");
check("no horizontal overflow at 390px",
      await ev(`document.documentElement.scrollWidth <= 390`),
      "scrollWidth=" + await ev(`document.documentElement.scrollWidth`));
// offsetParent is null while an element is `hidden`, so this scan only ever sees the controls that
// are on screen RIGHT NOW. It ran at BASE with no range applied, and the readership brush's own
// Clear button was the one control not on screen there — 28px for as long as this check existed,
// 8px under the assertion, because an ID selector outranks `.btn` whatever the order (the same
// specificity trap styles.css documents for `.seg.sm`). That button is gone (issue 35) and nothing
// on the page hides itself any more, but the scan still runs TWICE, once at rest and once filtered:
// it costs a second pass and it is the only thing standing between a future state-dependent control
// and the same blind spot. A third such state needs a third pass here.
const tapTargets = async () => ev(`JSON.stringify([...document.querySelectorAll('.seg button,.btn')]
  .filter(b=>b.offsetParent && b.getBoundingClientRect().height < 36)
  .map(b=>(b.id||b.textContent.trim())+'='+b.getBoundingClientRect().height.toFixed(1)))`);
const smallRest = await tapTargets();
check("control tap targets >= 36px tall", smallRest === "[]", `too small: ${smallRest}`);
// The `hidden` attribute is only display:none in the UA sheet, so any author `display` on the same
// element beats it — and the element goes on being hidden to a screen reader and to `.hidden` in JS
// while being drawn. Giving .btn a display for its icon did exactly that (issue 35): the search
// box's × came back at rest, wrapped the search row, and the page ran 50px tall until you filtered.
// styles.css answers it once with [hidden]{display:none!important}; this is what notices if that
// line is ever dropped or out-specified.
check("a hidden control is actually not drawn",
      await ev(`[...document.querySelectorAll('[hidden]')].every(e=>e.offsetParent === null
        && getComputedStyle(e).display === 'none')`),
      await ev(`[...document.querySelectorAll('[hidden]')]
        .map(e=>(e.id||e.tagName)+':'+getComputedStyle(e).display).join(', ') || 'nothing hidden'`));
await ev(`(()=>{ Histogram.setRange([751, 4501]); applyFilters(true) })()`);
await settle(`!document.getElementById('reset-filters').disabled`);
const smallFiltered = await tapTargets();
check("...including the ones only a filter puts on screen", smallFiltered === "[]",
      `with a range applied, too small: ${smallFiltered}`);
await ev(`Histogram.clear()`);
await settle(`document.getElementById('reset-filters').disabled`);
const cols = await ev(`document.querySelectorAll('tbody tr:first-child td:not(.wide-only)').length`);
check("phone table drops to 4 columns", cols === 4, "cols=" + cols);
check("table does not overflow its box at 390px",
      await ev(`(()=>{const b=document.querySelector('.scroll');return b.scrollWidth <= b.clientWidth+1})()`),
      await ev(`(()=>{const b=document.querySelector('.scroll');return b.scrollWidth+' vs '+b.clientWidth})()`));
check("y-axis tick labels are not clipped",
      await ev(`(()=>{const t=[...document.querySelectorAll('#plot svg text')].find(e=>e.textContent==='100');
        if(!t) return false; const s=document.querySelector('#plot svg').getBoundingClientRect();
        return t.getBoundingClientRect().left >= s.left - 0.5})()`));
check("the table box advertises that it scrolls",
      await ev(`(()=>{const b=document.querySelector('.scroll'), s=getComputedStyle(b);
        return b.scrollHeight > b.clientHeight + 50 && s.backgroundImage.split('gradient').length > 2})()`));
await shot("mobile");

// A phone has no room for a detail COLUMN, so app.js moves the panel into the chart card. The bug
// it fixes: the answer to a tap rendered a full screen-height below the dot you tapped.
const mdot = await ev(`(()=>{const s=document.querySelector('#plot svg');
  const c=[...s.querySelectorAll('circle.dot')].sort((a,b)=>+b.getAttribute('r')-+a.getAttribute('r'))[0];
  const b=c.getBoundingClientRect(); return {x:b.x+b.width/2, y:b.y+b.height/2}})()`);
check("the detail panel is hidden until something is pinned",
      await ev(`document.getElementById('detail').offsetParent === null`));
await mouse("mousePressed", mdot.x, mdot.y); await mouse("mouseReleased", mdot.x, mdot.y);
await settle(`location.hash.includes('c=')`);
check("tapping a dot on a phone answers inside the chart card",
      await ev(`document.getElementById('viz').contains(document.getElementById('detail'))`));
const drop = await ev(`(()=>{const d=document.getElementById('detail').getBoundingClientRect();
  const p=document.getElementById('plot').getBoundingClientRect(); return d.top - p.bottom})()`);
check("the answer lands within a finger's reach of the chart", drop >= 0 && drop < 60,
      drop.toFixed(0) + "px below the plot");
await shot("mobile-detail");

await ev(`document.getElementById('fs').click()`);
await laidOut();
check("full screen fills the viewport",
      await ev(`Math.abs(document.getElementById('viz').getBoundingClientRect().height - 844) < 2`),
      "h=" + await ev(`document.getElementById('viz').getBoundingClientRect().height`));
check("full screen still draws the chart",
      await ev(`document.querySelectorAll('#plot svg circle.dot').length > 400`));
// The controls sit ABOVE the plot everywhere else (issue 29: nothing a finger rests on may be
// placed by a box the same press resizes) — but here #plot is flex:1, sized by the viewport rather
// than by the view, so there is nothing to absorb and every pixel above the chart is a pixel of
// chart. styles.css orders #viz's children to put them back underneath.
check("full screen puts the controls back below the chart",
      await ev(`(()=>{const c=document.querySelector('.controls').getBoundingClientRect();
        const p=document.getElementById('plot').getBoundingClientRect();
        return c.top >= p.bottom - 1})()`),
      await ev(`(()=>{const c=document.querySelector('.controls').getBoundingClientRect();
        const p=document.getElementById('plot').getBoundingClientRect();
        return 'controls top '+c.top.toFixed(0)+' vs plot bottom '+p.bottom.toFixed(0)})()`));
// The pin survives into full screen — the grid column that normally holds it is display:none, so
// before this the chart answered a tap with nothing at all.
check("full screen keeps the pinned composer on screen",
      await ev(`(()=>{const d=document.getElementById('detail');
        if(d.offsetParent === null) return false; const r=d.getBoundingClientRect();
        return r.height > 40 && r.bottom <= 845 && r.top > 0
            && d.textContent.includes(${JSON.stringify(top)})})()`),
      await ev(`document.getElementById('detail').textContent.slice(0,60)`));
// Above the plot, not over it: floating at the bottom buried the x-axis, the "birth year" title
// and the whole legend for as long as anything was pinned.
check("the full-screen strip sits above the chart, covering nothing",
      await ev(`(()=>{const d=document.getElementById('detail').getBoundingClientRect();
        const p=document.getElementById('plot').getBoundingClientRect();
        return d.bottom <= p.top + 1})()`),
      await ev(`(()=>{const d=document.getElementById('detail').getBoundingClientRect();
        const p=document.getElementById('plot').getBoundingClientRect();
        return 'strip bottom '+d.bottom.toFixed(0)+' vs plot top '+p.top.toFixed(0)})()`));
// The anti-churn contract: #plot is flex:1 in full screen, so a strip that changed height would
// re-lay out the chart — moving the dot out from under the finger that just tapped it.
const plotH = await ev(`document.getElementById('plot').getBoundingClientRect().height`);
// The strip's height is FIXED because #plot is flex:1 there — anything that grows on select
// re-lays out the chart under the finger that just tapped it, which is why tight() returns before
// the sparkline is ever built.
check("the full-screen strip draws no sparkline",
      await ev(`document.querySelectorAll('#detail .spark, #detail .spark-cap').length === 0`),
      "spark nodes in strip=" + await ev(`document.querySelectorAll('#detail .spark, #detail .spark-cap').length`));
await shot("mobile-fs");
await ev(`[...document.querySelectorAll('#detail .detail-nav button')].find(b=>b.textContent==='Clear').click()`);
await settle(`!location.hash.includes('c=')`);
await laidOut();
check("clearing the pin does not resize the full-screen chart",
      Math.abs(await ev(`document.getElementById('plot').getBoundingClientRect().height`) - plotH) < 1,
      "plot h " + plotH + " -> " + await ev(`document.getElementById('plot').getBoundingClientRect().height`));
check("the strip is still drawn with nothing pinned",
      await ev(`(()=>{const d=document.getElementById('detail');
        return d.offsetParent !== null && d.getBoundingClientRect().height > 40})()`));
// THE TIGHTEST BOX THE GRIP EVER BLEEDS INTO. Section 4m5 measures the same 6.5px overhang inside
// the filters card, which pads 14px; here `body.fs #filters` pads nothing at all and #viz pads 10,
// so this is the case a padding change breaks first, and 4m5 would not notice.
const fh = await ev(`(()=>{const r=document.querySelector('#hist svg').getBoundingClientRect();
  return {x:r.x,y:r.y,w:r.width,h:r.height}})()`);
await mouse("mousePressed", fh.x + fh.w * 0.4, fh.y + fh.h * 0.4);
await mouse("mouseMoved",   Math.max(1, fh.x - 30), fh.y + fh.h * 0.4);
await mouse("mouseReleased", Math.max(1, fh.x - 30), fh.y + fh.h * 0.4);
await settle(`document.querySelectorAll('#hist .grips path').length === 2`);
check("...and a grip at the end of the axis still clears the full-screen edge",
      await ev(`(()=>{const g=[...document.querySelectorAll('#hist .grips path')]
          .map(p=>p.getBoundingClientRect()).sort((a,c)=>a.left-c.left)[0];
        const s=document.querySelector('#hist svg').getBoundingClientRect();
        return g.left < s.left && g.left > 1})()`),
      await ev(`(()=>{const g=[...document.querySelectorAll('#hist .grips path')]
          .map(p=>p.getBoundingClientRect()).sort((a,c)=>a.left-c.left)[0];
        const s=document.querySelector('#hist svg').getBoundingClientRect();
        return (s.left - g.left).toFixed(1) + "px past the svg, " +
               g.left.toFixed(1) + "px from the screen edge"})()`));
await ev(`document.getElementById('reset-filters').click()`);
await settle(`document.getElementById('reset-filters').disabled`);
await send("Emulation.setTouchEmulationEnabled", { enabled: false });

// --- 7c2. Share and Full screen become icons ON the chart, and stay usable there ---------------
// Issue 35. They leave .controls on a phone because that is what pays for the Reset filters button
// beside Reset zoom — the row is already two lines at 390, and a third word button takes it to
// three. The risks of putting a control over a zoom surface are what this checks: that they still
// receive taps (d3-zoom binds to the SVG, not to #plot, so they should), that chart.js's rebuild
// does not delete them (it removes its own svg by reference, and a descendant query there took
// these glyphs with it), that they clear the touch floor, and that an icon-only button still has a
// NAME — the words are visually hidden, not display:none'd, precisely so it does.
//
// It sets its own device state and its own URL. The checks above leave the page in full screen and
// turn touch emulation back OFF, and everything here up to the narrow-window check is about a phone:
// without the emulation a 390px box is a narrow desktop, the touch floor does not apply, and the
// button heights this checks are the wrong ones. The two states at the END are deliberate — a
// narrow window WITH a pointer, then a wide one — because each has a rule the phone cannot reach.
await viewport(390, 844, true);
await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
await goto(BASE);
check("...and it really is a phone this time",
      await ev(`matchMedia('(pointer:coarse)').matches && matchMedia('(hover:none)').matches`));
check("the chart tools sit on the plot at 390px",
      await ev(`document.getElementById('chart-tools').parentNode.id === 'plot'`),
      "parent = " + await ev(`document.getElementById('chart-tools').parentNode.id`));
check("...showing a glyph instead of a word",
      await ev(`(()=>{const s=document.querySelector('#share .ico');
        return s && getComputedStyle(s).display !== 'none'
          && getComputedStyle(document.querySelector('#share .btn-t')).clipPath !== 'none'})()`));
check("...but still naming themselves to a screen reader",
      await ev(`(()=>{const t=n=>document.querySelector('#'+n+' .btn-t').textContent.trim();
        return t('share') === 'Share' && t('fs') === 'Full screen'})()`),
      await ev(`document.querySelector('#fs .btn-t').textContent`));
check("...at the touch floor, and inside the plot",
      await ev(`(()=>{const p=document.getElementById('plot').getBoundingClientRect();
        return [...document.querySelectorAll('#chart-tools .btn')].every(b=>{const r=b.getBoundingClientRect();
          return r.height >= 40 && r.width >= 40
            && r.top >= p.top - 0.5 && r.right <= p.right + 0.5})})()`),
      await ev(`[...document.querySelectorAll('#chart-tools .btn')].map(b=>{const r=b.getBoundingClientRect();
        return b.id+' '+r.width.toFixed(0)+'x'+r.height.toFixed(0)}).join(', ')`));
// Exactly ONE glyph, or the 40px box holds two 18px icons side by side. `#chart-tools .btn .ico` is
// (1,2,0) and out-specifies a bare `#fs .ico-out` (1,1,0), so the state rules have to carry the
// group's id too — the same specificity trap that left #hist-clear under the touch floor in #31,
// one selector along.
// The glyph's SIZE, not just its presence. `#plot svg{width:100%}` means THE CHART, and moving
// these buttons into #plot made it a descendant selector over their icons too: an 18px glyph
// rendered at 38x38 — 95% of the button — with a 3.2px stroke, and `body.fs #plot svg{height:100%}`
// did it again in full screen. Desktop could never show it, because there the buttons are still in
// the controls row and the rule does not reach them. Measured against the BUTTON, so this stays
// meaningful if either size is retuned.
check("the glyphs are icon-sized, not stretched to fill the button",
      await ev(`[...document.querySelectorAll('#chart-tools .ico')]
        .filter(i=>getComputedStyle(i).display !== 'none')
        .every(i=>{const g=i.getBoundingClientRect(),
                         b=i.closest('.btn').getBoundingClientRect();
          return g.width >= 13 && g.width <= 20 && g.width / b.width < 0.5})`),
      await ev(`[...document.querySelectorAll('#chart-tools .ico')]
        .filter(i=>getComputedStyle(i).display !== 'none')
        .map(i=>{const g=i.getBoundingClientRect(), b=i.closest('.btn').getBoundingClientRect();
          return i.closest('.btn').id+' '+g.width.toFixed(0)+'px ('
            + (g.width/b.width*100).toFixed(0)+'% of button)'}).join(', ')`));
// Centred on the axis title's line. Measured against the title's own box rather than against the
// 3.5px in styles.css, so this fails if the font, the size or chart.js's `y:-8` ever moves the text
// — the constant is derived from those and a check that repeated it would only confirm arithmetic.
// Checked in the views that HAVE a title; the swarm has none.
let worstCentre = 0;
for (const m of ["fame", "scatter", "lens"]) {
  await ev(`document.querySelector('.controls .seg button[data-mode="${m}"]').click()`);
  await laidOut();
  worstCentre = Math.max(worstCentre, Math.abs(await ev(`(()=>{
    const t=document.querySelector('#plot svg text.ttl').getBoundingClientRect();
    const g=document.querySelector('#share .ico').getBoundingClientRect();
    return (g.top+g.bottom)/2 - (t.top+t.bottom)/2})()`)));
}
await ev(`document.querySelector('.controls .seg button[data-mode="fame"]').click()`);
await laidOut();
check("the glyphs are centred on the axis title's line", worstCentre <= 1.5,
      `worst offset ${worstCentre.toFixed(1)}px between glyph centre and title centre`);
check("...drawn as a bare glyph, not a pill moved onto the chart",
      await ev(`[...document.querySelectorAll('#chart-tools .btn')].every(b=>{
        const c=getComputedStyle(b);
        return parseFloat(c.borderTopWidth) === 0
          && (c.backgroundColor === 'rgba(0, 0, 0, 0)' || c.backgroundColor === 'transparent')})`),
      await ev(`(()=>{const c=getComputedStyle(document.getElementById('share'));
        return 'border '+c.borderTopWidth+', bg '+c.backgroundColor})()`));
// The copy confirmation, in the half that is visible here. navigator.share is absent in this
// browser and the clipboard write is refused without a permission, so BOTH fallback branches land
// on copied() — which is the point: the label they used to swap is `clip-path:inset(50%)` in this
// layout, so the button acknowledged a copy nowhere a reader could see it.
await ev(`document.getElementById('share').click()`);
await settle(`document.getElementById('share').classList.contains('copied')`);
check("Share acknowledges a copy with the glyph, not just the clipped label",
      await ev(`(()=>{const b=document.getElementById('share');
        const vis=[...b.querySelectorAll('.ico')].filter(i=>getComputedStyle(i).display !== 'none');
        return vis.length === 1 && vis[0].classList.contains('ico-ok')
          && b.querySelector('.btn-t').textContent.trim() === 'Link copied'})()`),
      await ev(`[...document.querySelectorAll('#share .ico')]
        .map(i=>i.getAttribute('class')+':'+getComputedStyle(i).display).join(' | ')`));
await settle(`!document.getElementById('share').classList.contains('copied')`);   // app.js reverts it after 1600ms
check("...and goes back to the share glyph afterwards",
      await ev(`(()=>{const b=document.getElementById('share');
        return !b.classList.contains('copied')
          && b.querySelector('.btn-t').textContent.trim() === 'Share'})()`));
check("...and #fs shows one glyph, not both",
      await ev(`(()=>{const vis=[...document.querySelectorAll('#fs .ico')]
        .filter(i=>getComputedStyle(i).display !== 'none'); return vis.length === 1
          && vis[0].classList.contains('ico-in')})()`),
      await ev(`[...document.querySelectorAll('#fs .ico')]
        .map(i=>i.getAttribute('class')+':'+getComputedStyle(i).display).join(' | ')`));
// It covers NOTHING, in any view — which is the whole reason it sits in the axis-title band rather
// than in a corner. Checked in all four, because the corners were judged from Fame and Fame is the
// one view where the top right looks empty: the swarm piles 90 dots and the "Rachmaninoff" label
// exactly there. Bottom left was the best corner at 3 dots and still ate the axis origin ("1700").
// Zero is the assertion because the band makes zero achievable; anything above it means the band
// stopped being tall enough (Chart.setTopReserve) or the title grew into the group's 86px.
const covered = () => ev(`(()=>{const t=document.getElementById('chart-tools').getBoundingClientRect();
  const hit=r=>r.left<t.right&&r.right>t.left&&r.top<t.bottom&&r.bottom>t.top;
  const dots=[...document.querySelectorAll('#plot svg circle.dot')].filter(c=>hit(c.getBoundingClientRect()));
  const names=[...document.querySelectorAll('#plot svg text.label, #plot svg text')]
    .filter(t2=>hit(t2.getBoundingClientRect())).map(t2=>t2.textContent.trim())
    .filter(s=>s && !/^[0-9.,k]+$/.test(s) && !/quartet|year|→|↑|readers/i.test(s));
  return JSON.stringify({dots:dots.length, names})})()`);
let worstDots = 0, coveredNames = [];
for (const m of ["fame", "scatter", "swarm", "lens"]) {
  await ev(`document.querySelector('.controls .seg button[data-mode="${m}"]').click()`);
  await laidOut();
  const c = JSON.parse(await covered());
  worstDots = Math.max(worstDots, c.dots);
  coveredNames.push(...c.names.map(n => `${m}:${n}`));
}
await ev(`document.querySelector('.controls .seg button[data-mode="fame"]').click()`);
await laidOut();
// Counted against the whole BUTTON, not the glyph: the target is invisible, so a dot it overlaps is
// not covered — it silently stops being tappable, which is worse than being hidden because nothing
// on screen explains it. That is what sets the band's height (see TOOLS_BAND in app.js).
check("the overlay covers and shadows nothing, in any view",
      worstDots === 0 && coveredNames.length === 0,
      `worst view covers ${worstDots} dots; labels: ${coveredNames.join(", ") || "none"}`);

// At rest is not the only state. The dot clip is inset OUTWARD by one maximum radius (chart.js's
// `over`), so a dot whose centre sits just inside the top edge draws a sliver up into the band —
// under a pinch, under the invisible target. The target cannot be shortened to miss it without
// going under the 40px floor, so the guarantee is one step weaker and it is this: no dot's CENTRE
// is ever under the target, because the frame test only draws a dot whose centre is inside the plot
// rect and that rect starts 4.5px below the target's bottom. A finger aiming at a dot lands on the
// dot.
const underTools = () => ev(`(()=>{const t=document.getElementById('chart-tools').getBoundingClientRect();
  const mid=r=>[(r.left+r.right)/2,(r.top+r.bottom)/2];
  const box=[...document.querySelectorAll('#plot svg circle.dot')].filter(c=>{const r=c.getBoundingClientRect();
    return r.left<t.right&&r.right>t.left&&r.top<t.bottom&&r.bottom>t.top});
  const ctr=box.filter(c=>{const [x,y]=mid(c.getBoundingClientRect());
    return x>t.left&&x<t.right&&y>t.top&&y<t.bottom});
  return JSON.stringify({box:box.length, ctr:ctr.length})})()`);
// The GUARANTEE, not a sample of it. A state-by-state hunt for the bad case is a check that passes
// by not finding one — zooming the top right pushes dots away from the anchor, zooming the bottom
// lifted none into that column at k=5.3, and the swarm's y is not under the zoom at all. What holds
// in every state instead is arithmetic: the frame test only draws a dot whose CENTRE is inside the
// plot rect, so a target whose bottom is above that rect can never have one under it, at any zoom.
// One measurement, and it is the one the band exists to make true.
check("...and its bottom stays above the plot area, so no dot's CENTRE can fall under it at any zoom",
      await ev(`(()=>{const t=document.getElementById('chart-tools').getBoundingClientRect();
        return document.querySelector('#plot svg rect.bg').getBoundingClientRect().top - t.bottom >= 0})()`),
      await ev(`(()=>{const t=document.getElementById('chart-tools').getBoundingClientRect();
        return (document.querySelector('#plot svg rect.bg').getBoundingClientRect().top - t.bottom)
          .toFixed(1)+'px of clearance'})()`));
const zbx = await ev(`(()=>{const b=document.querySelector('#plot svg rect.bg').getBoundingClientRect();
  return {x:b.x,y:b.y,w:b.width,h:b.height}})()`);
for (let i = 0; i < 8; i++) {
  await send("Input.dispatchMouseEvent", { type: "mouseWheel", x: zbx.x + zbx.w * 0.8,
    y: zbx.y + zbx.h * 0.92, deltaX: 0, deltaY: -300, pointerType: "mouse" });
  await sleep(120);
}
await settle(`Chart.zoomK() > 1.5`);
const uz = JSON.parse(await underTools());
check("...and a real pinch agrees",
      uz.ctr === 0 && await ev(`Chart.zoomK()`) > 1.5,
      `k=${(await ev(`Chart.zoomK()`)).toFixed(1)}, ${uz.box} dots reach the band, ${uz.ctr} centres under it`);
await ev(`Chart.resetZoom()`);
await idle();
// And it fits INSIDE the reservation rather than merely happening to miss the dots: the band is the
// plot group's own translate, read off the DOM, so this goes red the moment Chart.setTopReserve is
// dropped or the buttons grow — before anything is visibly covered. Zero coverage above is the
// symptom; this is the cause, and the cause is what a reader needs when it breaks.
// Read off the SVG transform MATRIX, not by parsing the attribute: a `\d` inside a template
// literal is consumed before the browser ever sees it, which is a good way to write a regex that
// silently matches nothing and a check that silently passes.
const band = await ev(`(()=>{const tops=[...document.querySelectorAll('#plot svg > g')]
    .map(g=>{const c=g.transform.baseVal.consolidate(); return c ? c.matrix.f : 0});
  const tools=document.getElementById('chart-tools').getBoundingClientRect();
  const plot=document.getElementById('plot').getBoundingClientRect();
  return JSON.stringify({top:Math.max(0, ...tops), used:+(tools.bottom-plot.top).toFixed(1)})})()`);
const b = JSON.parse(band);
check("...because the chart reserved the band for it", b.top >= 40 && b.used <= b.top + 0.5,
      `band ${b.top}px, buttons reach ${b.used}px`);

// A REAL tap through the CDP, not .click(): the whole question is whether a press over the zoom
// surface reaches the button or is swallowed by the pan gesture.
// Deliberately NOT the centre: the affordance here is a 40px target around a 16px glyph, so the
// tap that proves it is one that lands on empty space inside the button — 3px in from the corner,
// about 12px clear of the mark that is actually drawn. A centre tap would pass on a 16px button.
const fsBox = await ev(`(()=>{const r=document.getElementById('fs').getBoundingClientRect();
  const g=document.querySelector('#fs .ico').getBoundingClientRect();
  return {x:r.left+3, y:r.top+3,
          clear:+Math.hypot(g.left-(r.left+3), g.top-(r.top+3)).toFixed(1)}})()`);
await mouse("mousePressed", fsBox.x, fsBox.y);
await mouse("mouseReleased", fsBox.x, fsBox.y);
await settle(`document.body.classList.contains('fs')`);
check("a tap in the empty part of the hit target fires, not just on the glyph",
      await ev(`document.body.classList.contains('fs')`),
      `tapped ${fsBox.clear}px clear of the glyph`);
check("...and the icon swaps to the exit glyph rather than losing it",
      await ev(`(()=>{const b=document.getElementById('fs');
        return b.getAttribute('aria-pressed') === 'true'
          && getComputedStyle(b.querySelector('.ico-out')).display !== 'none'
          && getComputedStyle(b.querySelector('.ico-in')).display === 'none'
          && b.querySelector('.btn-t').textContent.trim() === 'Exit full screen'})()`),
      await ev(`document.querySelector('#fs .btn-t').textContent`));
check("...and they are still on the plot in full screen",
      await ev(`document.getElementById('chart-tools').parentNode.id === 'plot'`));
await ev(`document.getElementById('fs').click()`);
await settle(`!document.body.classList.contains('fs')`);
// setData/setMode rebuild the SVG inside #plot. An overlay that a re-render deletes is the way this
// breaks silently: the buttons are simply gone the first time the reader changes the view.
await ev(`document.querySelector('.controls .seg button[data-mode="swarm"]').click()`);
await ev(`document.querySelector('.controls .seg button[data-mode="fame"]').click()`);
await settle(`Chart.getMode() === 'fame'`);
check("a chart re-render does not delete the overlay",
      await ev(`document.getElementById('chart-tools').parentNode.id === 'plot'
        && !!document.querySelector('#plot > #chart-tools #share .ico')`));
// A WINDOW under 640px with a real pointer — the layout neither of the two above can see. This
// block is `(max-width:640px)`, width only, but the 40px touch floor is
// `(hover:none) and (pointer:coarse) and (max-width:800px)`: a desktop dragged narrow matches the
// first and not the second, so the buttons took .btn's base min-height of 36 and dropped the glyph
// ~4px below the title's line — the derivation in styles.css describing a box the browser was not
// drawing. Every check above runs under touch emulation, where the button is 40px and this is
// invisible. Same shape of blind spot as the icon-inflation bug: a state the suite never entered.
await send("Emulation.setTouchEmulationEnabled", { enabled: false });
await viewport(600, 900, false);
await goto(BASE);
check("a narrow window with a mouse gets the same geometry, not a 36px button",
      await ev(`(()=>{const t=document.querySelector('#plot svg text.ttl').getBoundingClientRect();
        return [...document.querySelectorAll('#chart-tools .btn')].every(b=>{
          const r=b.getBoundingClientRect(), g=b.querySelector('.ico').getBoundingClientRect();
          return Math.abs(r.height - 40) < 0.5
            && Math.abs((g.top+g.bottom)/2 - (t.top+t.bottom)/2) <= 1.5})})()`),
      await ev(`(()=>{const t=document.querySelector('#plot svg text.ttl').getBoundingClientRect(),
        b=document.getElementById('share'), r=b.getBoundingClientRect(),
        g=b.querySelector('.ico').getBoundingClientRect();
        return r.height.toFixed(1)+'px tall, glyph '
          + ((g.top+g.bottom)/2 - (t.top+t.bottom)/2).toFixed(1)+'px off the title'})()`));

// And on a desktop they go back to being words in the row, one element moved rather than two drawn.
await viewport(1280, 900, false);
await settle(`document.getElementById('chart-tools').parentNode.classList.contains('controls')`);
check("on a desktop they are words in the controls row again",
      await ev(`(()=>{const t=document.getElementById('chart-tools');
        return t.parentNode.classList.contains('controls')
          && getComputedStyle(document.querySelector('#share .ico')).display === 'none'
          && document.querySelector('#share .btn-t').offsetParent !== null})()`),
      "parent = " + await ev(`document.getElementById('chart-tools').parentNode.className`));
await send("Emulation.setTouchEmulationEnabled", { enabled: false });
await viewport(390, 844, true);
await goto(BASE);

// --- 7d. full screen on a real pointer: hover previews into the strip, and nothing moves --------
await viewport(1280, 900);
await goto(BASE);
await ev(`document.getElementById('fs').click()`);
await laidOut();
const fsPlotH = await ev(`document.getElementById('plot').getBoundingClientRect().height`);
const fsDot = await ev(`(()=>{const s=document.querySelector('#plot svg');
  const c=[...s.querySelectorAll('circle.dot')].sort((a,b)=>+b.getAttribute('r')-+a.getAttribute('r'))[0];
  const b=c.getBoundingClientRect(); return {x:b.x+b.width/2, y:b.y+b.height/2}})()`);
await mouse("mouseMoved", fsDot.x, fsDot.y);
await settle(`document.getElementById('detail').textContent.includes(${JSON.stringify(top)})`);
await sleep(TWEEN);
check("hovering in full screen previews into the strip",
      (await ev(`document.getElementById('detail').textContent`)).includes(top),
      "expected " + top);
check("hovering in full screen does not move the chart",
      Math.abs(await ev(`document.getElementById('plot').getBoundingClientRect().height`) - fsPlotH) < 1);
check("a hover in full screen still does not pin", await ev(`!location.hash.includes('c=')`));
await shot("desktop-fs-hover");
await ev(`document.getElementById('fs').click()`);

// --- 7e. narrow window on a real pointer: the compact panel previews without moving the page ---
// The one layout where hover and the in-flow compact panel meet. Its box is reserved (styles.css)
// so a preview fills it instead of appearing out of nowhere and shoving the legend down.
await viewport(760, 900);
await goto(BASE);
const beforeTop = await ev(`document.querySelector('#viz .legend').getBoundingClientRect().top`);
const ndot = await ev(`(()=>{const s=document.querySelector('#plot svg');
  const c=[...s.querySelectorAll('circle.dot')].sort((a,b)=>+b.getAttribute('r')-+a.getAttribute('r'))[0];
  const b=c.getBoundingClientRect(); return {x:b.x+b.width/2, y:b.y+b.height/2}})()`);
await mouse("mouseMoved", ndot.x, ndot.y);
await settle(`document.getElementById('detail').textContent.includes(${JSON.stringify(top)})`);
await sleep(TWEEN);
check("a narrow window previews into the compact panel",
      (await ev(`document.getElementById('detail').textContent`)).includes(top), "expected " + top);
const afterTop = await ev(`document.querySelector('#viz .legend').getBoundingClientRect().top`);
check("previewing does not shove the rest of the card down", Math.abs(afterTop - beforeTop) < 2,
      `legend top ${beforeTop.toFixed(0)} -> ${afterTop.toFixed(0)}`);
// Pinning adds the Prev/Next/Clear row, which is the tallest the panel ever gets — the reserved
// box has to cover THAT, or the page still jumps at the moment you click.
await mouse("mousePressed", ndot.x, ndot.y); await mouse("mouseReleased", ndot.x, ndot.y);
await settle(`location.hash.includes('c=')`);
await sleep(TWEEN);
const pinnedTop = await ev(`document.querySelector('#viz .legend').getBoundingClientRect().top`);
check("pinning does not shove it either", Math.abs(pinnedTop - beforeTop) < 2,
      `legend top ${beforeTop.toFixed(0)} -> ${pinnedTop.toFixed(0)}`
      + " (panel " + await ev(`document.getElementById('detail').getBoundingClientRect().height.toFixed(0)`) + "px)");
// The dot above is whichever is largest, and its caption is a short trend line. The WORST case for
// the reservation is a spike caption — "peak Jun 2023 — 42,195, 18× typical" is half again as long
// and is what would wrap first — so the box has to cover that one too.
await goto(BASE + "#c=" + encodeURIComponent("Kaija Saariaho"));
await settle(`!!document.querySelector('#detail .spark-cap')`);
const spikeTop = await ev(`document.querySelector('#viz .legend').getBoundingClientRect().top`);
await goto(BASE);
check("the reservation covers the LONGEST caption, not just the first one tested",
      Math.abs(spikeTop - (await ev(`document.querySelector('#viz .legend').getBoundingClientRect().top`))) < 2,
      `legend top with a spike caption ${spikeTop.toFixed(0)} vs empty `
      + (await ev(`document.querySelector('#viz .legend').getBoundingClientRect().top`)).toFixed(0));

// --- 7f. landscape full screen: the strip must not eat the chart ------------------------------
// A phone on its side is 390px TALL. The strip takes its height out of #plot rather than floating
// over it, so this is where that choice costs the most.
await viewport(844, 390, true);
await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
await goto(BASE);
await ev(`document.getElementById('fs').click()`);
await laidOut();
const land = await ev(`(()=>{const p=document.getElementById('plot').getBoundingClientRect();
  const d=document.getElementById('detail').getBoundingClientRect();
  return {plot:p.height, strip:d.height, vp:innerHeight}})()`);
check("landscape full screen still gives the chart most of the height",
      land.plot / land.vp > 0.5,
      `plot ${land.plot.toFixed(0)} of ${land.vp} (strip ${land.strip.toFixed(0)})`);
// The SVG must FILL its box, not letterbox inside it: measure() floors the full-screen height,
// and a viewBox taller than the box scales the whole chart down and centres it in empty card.
check("the landscape chart fills its box instead of letterboxing",
      await ev(`(()=>{const s=document.querySelector('#plot svg');
        const b=s.getBoundingClientRect(); const vb=s.viewBox.baseVal;
        return Math.abs((vb.width/vb.height) - (b.width/b.height)) < 0.25})()`),
      await ev(`(()=>{const s=document.querySelector('#plot svg'); const b=s.getBoundingClientRect();
        const vb=s.viewBox.baseVal;
        return 'viewBox '+vb.width.toFixed(0)+'x'+vb.height.toFixed(0)+' in box '
             + b.width.toFixed(0)+'x'+b.height.toFixed(0)})()`));
await shot("landscape-fs");
await send("Emulation.setTouchEmulationEnabled", { enabled: false });

// --- 8. offline: load once online to prime the precache, then kill the network ---------------
await viewport(1280, 900);
await goto(BASE);
// The SW precaches per-file on install; wait for it to take control AND finish the shell.
let cached = 0;
for (let i = 0; i < 60; i++) {
  cached = await ev(`(async()=>{const k=(await caches.keys()).filter(n=>n.startsWith('quartets-v'));
    if(!k.length) return 0; return (await (await caches.open(k[0])).keys()).length})()`);
  if (cached >= 12) break;
  await sleep(100);
}
check("service worker precached the whole shell", cached >= 12, cached + " entries");
check("sw.js took control", await ev(`!!navigator.serviceWorker.controller`));

await send("Network.enable");
await send("Network.emulateNetworkConditions",
  { offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0 });
await goto(BASE);
check("offline reload still paints the chart",
      await ev(`document.querySelectorAll('#plot svg circle.dot').length > 400`),
      "dots=" + await ev(`document.querySelectorAll('#plot svg circle.dot').length`));
check("offline reload still fills the table",
      await ev(`document.querySelectorAll('tbody tr').length > 400`));
await shot("offline");
await send("Network.emulateNetworkConditions",
  { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });

// --- 9. print stylesheet -----------------------------------------------------------------------
await goto(BASE);
await send("Emulation.setEmulatedMedia", { media: "print" });
await settle(`getComputedStyle(document.querySelector('.controls')).display === 'none'`);
check("print hides the interactive chrome",
      await ev(`getComputedStyle(document.querySelector('.controls')).display === 'none'`));
check("print un-scrolls the table so every row is on the page",
      await ev(`getComputedStyle(document.querySelector('.scroll')).overflow === 'visible'`));
await shot("print", { clip: await printClip() });
await send("Emulation.setEmulatedMedia", { media: "" });

// --- 9b. AND THE SCREENSHOTS' OWN RESOLUTION --------------------------------------------------
// Nothing asserts on the PNGs and the directory is deleted unless KEEP=1, so what they are FOR is
// the one look at the page a failure gets — read, increasingly, by a model rather than by eyes.
// An image handed to one is resampled to fit a long-edge cap AND a visual-token budget, at the
// largest size satisfying both, so height spends width: the full-page print shot this issue began
// with is 1280x34,936 and arrives 94px wide, 368 tokens of a page nothing can read, at any capture
// scale. That is why "make it fewer megapixels" was the wrong fix and clipping the height was the
// right one, and this is the property the clip bought, pinned so it cannot drift back.
// It does NOT catch #50's hang — that shot never returns to be measured. It catches the same
// mistake where the capture SUCCEEDS and only the picture is lost, which is every other machine.
{
  const PATCH = 28, LONG = 2576, TOKENS = 4784;   // the high-resolution tier's two limits
  const at = ({ w, h }) => DSF * Math.min(1, LONG / Math.max(w, h), Math.sqrt(TOKENS * PATCH ** 2 / (w * h)));
  const worst = shots.reduce((a, b) => at(b) < at(a) ? b : a);
  check("every screenshot survives an image resize at 1:1 or better", at(worst) >= 1,
        `${worst.name} is ${worst.w}x${worst.h} and resolves at ${at(worst).toFixed(2)} image pixels `
        + `per CSS pixel, against a floor of 1 — ${shots.length} shots measured`);
}

// --- 8. THE SUITE'S OWN STATED SIZE ---------------------------------------------------------
// The docs quote this total, and it is the one count in the repo that cannot be taken offline:
// some checks are registered in loops, so the literal `check(` count is not what this reports.
// So `scripts/prose-lint.py` deliberately does not pin it and this does, where the real total is
// known — the same pin-it-where-the-file-settles-it rule og-lint.py uses for manifest.json.
// README carried a stale size for months before this check existed; the drift was spotted during
// #23, deferred to a follow-up, and never done. Quoting the literal count here went stale inside
// the branch that added this check, which is why neither number is written down any more.
{
  const total = results.length + 1;   // +1: this check is about to be pushed
  const stated = [];
  for (const f of ["README.md", "CLAUDE.md"]) {
    const src = readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
    for (const m of src.matchAll(/(\d+)\s+behaviou?ral checks/g)) stated.push([f, +m[1]]);
  }
  const wrong = stated.filter(([, n]) => n !== total);
  // The other diagnosis: on a pass `wrong` is empty, so this text was `"" + " — it is 242"` and
  // every green run printed "the docs state this suite's real size —  — it is 242".
  check("the docs state this suite's real size",
        stated.length >= 2 && wrong.length === 0, "",
        stated.length < 2
          ? `only ${stated.length} doc(s) state it — a claim that stops matching proves nothing`
          : wrong.map(([f, n]) => `${f} says ${n}`).join(", ") + ` — it is ${total}`);
}

report(null);
