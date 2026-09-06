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

import { writeFileSync } from "node:fs";

const [,, PORT, OUTDIR, ORIGIN] = process.argv;

const targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
const page = targets.find(t => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener("open", r));

let id = 0; const pending = new Map(); const logs = [];
ws.addEventListener("message", e => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error")
    logs.push("console.error: " + m.params.args.map(a => a.value ?? a.description).join(" "));
  if (m.method === "Runtime.exceptionThrown")
    logs.push("EXCEPTION: " + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
});
const send = (method, params = {}) => new Promise(res => {
  const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params }));
});
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function ev(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.result?.exceptionDetails) throw new Error(r.result.exceptionDetails.text + " :: " + expr);
  return r.result.result.value;
}
async function shot(name) {
  const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
  writeFileSync(`${OUTDIR}/${name}.png`, Buffer.from(r.result.data, "base64"));
}
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
  for (let i = 0; i < 100; i++) { if (await ev("document.readyState === 'complete'")) break; await sleep(60); }
  await sleep(700);
  // Cheap proof the navigation actually happened. Nothing asserts the fragment SURVIVED, because
  // the app is allowed to rewrite it — it strips a value it rejects — and the sections that care
  // check the state it produced instead.
  if (await ev(`location.href`) === "about:blank") throw new Error("goto never left about:blank: " + url);
}
async function mouse(type, x, y) {
  await send("Input.dispatchMouseEvent", { type, x, y, button: type === "mouseMoved" ? "none" : "left",
    buttons: 0, clickCount: type === "mouseMoved" ? 0 : 1, pointerType: "mouse" });
}
async function viewport(w, h, mobile = false) {
  await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 2, mobile });
}

await send("Page.enable"); await send("Runtime.enable"); await send("Log.enable");

const BASE = (ORIGIN || "http://127.0.0.1:8765") + "/";
const results = [];
const check = (name, cond, extra = "") => results.push(`${cond ? "ok  " : "FAIL"} ${name}${extra ? " — " + extra : ""}`);

// --- 1. lens mode: aim the magnifier at the crowded low bands -----------------
await viewport(1280, 900);
await goto(BASE + "#v=lens");
const box = await ev(`(()=>{const r=document.querySelector('#plot svg').getBoundingClientRect();
  return {x:r.x,y:r.y,w:r.width,h:r.height}})()`);
// Radii of every dot BEFORE the lens exists, keyed by the label d3 bound to them.
const before = await ev(`(()=>{const o={};document.querySelectorAll('#plot svg circle.dot')
  .forEach((e,i)=>o[i]=+e.getAttribute('r'));return o})()`);
await mouse("mouseMoved", box.x + box.w * 0.55, box.y + box.h * 0.72);
await sleep(400);
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
await sleep(300);
check("hover shows the name flag", await ev(`document.getElementById('flag').classList.contains('on')`),
      await ev(`document.getElementById('flag').textContent`));
check("hover previews into the detail panel",
      (await ev(`document.getElementById('detail').textContent`)).includes(top), "expected " + top);
check("hover does NOT pin (no ring yet)", await ev(`!location.hash.includes('c=')`));

// --- 3. click pins ------------------------------------------------------------
await mouse("mousePressed", dot.x, dot.y); await mouse("mouseReleased", dot.x, dot.y);
await sleep(400);
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

// --- 4. search filters both views --------------------------------------------
await ev(`(()=>{const q=document.getElementById('q'); q.value='haydn';
  q.dispatchEvent(new Event('input',{bubbles:true}));})()`);
await sleep(300);
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
await sleep(500);
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
// THE REPORTED BUG: .seg is overflow:hidden, so when Clear appeared the pill group gave up width
// and clipped its last pill — the filter lost the word "Men" while you were using the filter.
check("the gender pills are not clipped when Clear appears",
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
await sleep(300);
const both = await ev(`document.querySelectorAll('tbody tr').length`);
check("search and brush combine rather than override", both <= filtered, `${both} <= ${filtered}`);
await ev(`(()=>{const q=document.getElementById('q'); q.value='';
  q.dispatchEvent(new Event('input',{bubbles:true}));})()`);
await sleep(200);

await ev(`document.getElementById('hist-clear').click()`);
await sleep(400);
check("clearing the brush restores every row",
      await ev(`document.querySelectorAll('tbody tr').length`) === totalRows);
check("clearing drops the range from the URL", !(await ev(`location.hash`)).includes("r="));

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
await sleep(300);
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
      named.every(t => t.length < 20) && named.includes("J. Haydn"),
      JSON.stringify(named));
check("only the named composers are labelled", named.length <= 13, named.length + " labels");
check("the readers-per-quartet diagonals are drawn",
      await ev(`document.querySelectorAll('#plot svg line.dg').length >= 4`),
      "lines=" + await ev(`document.querySelectorAll('#plot svg line.dg').length`));
check("the diagonals are trimmed to the plot, not drawn past it",
      await ev(`(()=>{const s=document.querySelector('#plot svg');
        const b=s.querySelector('rect.bg'); const w=+b.getAttribute('width'), h=+b.getAttribute('height');
        return [...s.querySelectorAll('line.dg')].every(l=>['x1','x2'].every(a=>+l.getAttribute(a)>=-0.5 && +l.getAttribute(a)<=w+0.5)
          && ['y1','y2'].every(a=>+l.getAttribute(a)>=-0.5 && +l.getAttribute(a)<=h+0.5))})()`));
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
await sleep(400);
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
await sleep(400);
const zoomLabels = await ev(`[...document.querySelectorAll('#plot svg text')]
  .filter(t=>new Set(ROWS.map(d=>Names.short(d.name))).has(t.textContent)).length`);
check("zooming the Fame view reveals more names", zoomLabels > restLabels,
      `${restLabels} at rest -> ${zoomLabels} zoomed in`);
check("the names it reveals are ones the seed never had",
      await ev(`(()=>{const seed=new Set(Chart.seedNames().map(Names.short));
        return [...document.querySelectorAll('#plot svg text')].map(t=>t.textContent)
          .filter(t=>new Set(ROWS.map(d=>Names.short(d.name))).has(t)).some(n=>!seed.has(n))})()`));
await ev(`document.getElementById('reset').click()`);
await sleep(600);
check("and the resting picture is still just the seed",
      await ev(`(()=>{const seed=new Set(Chart.seedNames().map(Names.short));
        return [...document.querySelectorAll('#plot svg text')].map(t=>t.textContent)
          .filter(t=>new Set(ROWS.map(d=>Names.short(d.name))).has(t)).every(n=>seed.has(n))})()`),
      "a derived name is showing at rest, where the view should say only what it is about");

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
await sleep(200);
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
check("the provenance names the revision it was scraped from",
      (await ev(`document.getElementById('prov').textContent`)).includes("revision "),
      await ev(`document.getElementById('prov').textContent.slice(0, 70)`));
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
check("no property id is left as bare text",
      await ev(`(()=>{const el=document.getElementById('prov');
        const linked=[...el.querySelectorAll('a')].map(a=>a.textContent);
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
await sleep(700);          // the frame closes in on the filter over 420ms; these read the settled state
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

// Unknown is in NEITHER set: Women + Men must not add up to the whole roster, or the null rule
// has quietly been replaced by "everyone we didn't call a man".
await ev(`document.querySelector('#gender button[data-g="male"]').click()`);
await sleep(300);
const men = await ev(`document.querySelectorAll('tbody tr').length`);
check("a composer with no P21 claim is in neither filter", women + men < allRows,
      `${women} + ${men} < ${allRows}`);

// Intersection, not replacement — the same contract the search box and the brush hold to.
await ev(`(()=>{const q=document.getElementById('q'); q.value='haydn';
  q.dispatchEvent(new Event('input',{bubbles:true}));})()`);
await sleep(300);
check("gender and search combine rather than override",
      await ev(`document.querySelectorAll('tbody tr').length`) < 3, "haydn ∩ men");
await ev(`(()=>{const q=document.getElementById('q'); q.value='';
  q.dispatchEvent(new Event('input',{bubbles:true}));})()`);
await sleep(200);
await ev(`document.querySelector('#gender button[data-g=""]').click()`);
await sleep(300);
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
      /P21/.test(await ev(`document.getElementById('prov').textContent`))
   && /neither filter/.test(await ev(`document.getElementById('prov').textContent`)),
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
await sleep(700);
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
await sleep(300);
check("pinching a filtered view still lights the reset button",
      !(await ev(`document.getElementById('reset').disabled`)),
      "k=" + await ev(`Chart.zoomK()`));
await ev(`document.getElementById('reset').click()`);
await sleep(700);
check("reset returns to the filter's frame, not to the whole field",
      Math.abs(await ev(`Chart.zoomK()`) - fitK) < 0.01, "k=" + await ev(`Chart.zoomK()`));
await ev(`document.querySelector('#gender button[data-g=""]').click()`);
await sleep(700);
check("clearing the filter opens the frame back out", await ev(`Chart.zoomK()`) === 1,
      "k=" + await ev(`Chart.zoomK()`));
// Each view fits its own filter: the same composers occupy a different box in a timeline than in
// a log-log readership cloud, so a view switch recomputes the frame instead of carrying it over.
await goto(BASE + "#g=female&v=scatter");
await sleep(700);
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
await sleep(700);
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
// The key has to say which crowd it is talking about, or it labels the wrong channel.
check("the legend says the ring changed crowds",
      /stand out in this group/.test(await ev(`document.getElementById('legend').textContent`)),
      await ev(`document.getElementById('legend').textContent.slice(0, 120)`));
// The promise the chip makes is that a row and its dot are the same thing, so it moves too.
check("the table chip follows the derived ring",
      await ev(`(()=>{const acc=getComputedStyle(document.documentElement)
          .getPropertyValue('--accent').trim();
        const r=[...document.querySelectorAll('tbody tr')]
          .find(r=>r.querySelector('td').title==='Elena Kats-Chernin');
        if(!r) return false;
        const c=r.querySelector('.chip');
        const paint=c.style.background==='transparent' ? c.style.boxShadow : c.style.background;
        const el=document.createElement('i'); el.style.color=acc; document.body.appendChild(el);
        const rgb=getComputedStyle(el).color; el.remove();
        return paint.includes(rgb)})()`));
// Filtering to the men keeps all three curated outliers, so there is nothing to derive — the
// ring budget is THREE, not three-plus-three, or a filter that changes almost nothing would
// double the ink.
await goto(BASE + "#g=male");
await sleep(700);
check("a filter that keeps the curated three derives none",
      await ev(`Chart.derivedRings()`) === 0 && (await ev(ringsOf)).dots === 3,
      "derived=" + await ev(`Chart.derivedRings()`));
// A ring means "stands out from the crowd it is drawn in", so it needs a crowd. Two Haydns are
// already the whole picture; ringing them would be pointing at everything.
await goto(BASE + "#q=haydn");
await sleep(700);
check("too small a group to have a crowd derives no rings",
      await ev(`Chart.derivedRings()`) === 0, "derived=" + await ev(`Chart.derivedRings()`));

// --- 5. sorting ---------------------------------------------------------------
await goto(BASE);
await ev(`[...document.querySelectorAll('thead th button')].find(b=>b.textContent==='Quartets').click()`);
await sleep(200);
check("sort by Quartets desc puts Cambini first",
      (await ev(`document.querySelector('tbody tr td').textContent`)).includes("Cambini"),
      await ev(`document.querySelector('tbody tr td').textContent`));
await ev(`[...document.querySelectorAll('thead th button')].find(b=>b.textContent==='Died').click()`);
await sleep(200);
check("sort by Died keeps living composers off the top",
      (await ev(`document.querySelectorAll('tbody tr')[0].children[2].textContent`)) !== "—",
      "first Died cell = " + await ev(`document.querySelectorAll('tbody tr')[0].children[2].textContent`));

// --- 6. dark mode repaints the JS-baked colors --------------------------------
// The timeline view, because the lifespan ramp is the legend piece that is baked from the tokens.
await goto(BASE + "#v=scatter");
const lightFill = await ev(`document.querySelector('#plot svg circle.dot').getAttribute('fill')`);
await ev(`Theme.set('dark')`); await sleep(400);
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
await sleep(500);
check("the phone viewport really reports a touch pointer",
      await ev(`matchMedia('(pointer:coarse)').matches && matchMedia('(hover:none)').matches`),
      "setDeviceMetricsOverride alone does NOT: chart.js's TOUCH and the compact panel both key off this");
check("no horizontal overflow at 390px",
      await ev(`document.documentElement.scrollWidth <= 390`),
      "scrollWidth=" + await ev(`document.documentElement.scrollWidth`));
const small = await ev(`[...document.querySelectorAll('.seg button,.btn')]
  .filter(b=>b.offsetParent && b.getBoundingClientRect().height < 36).length`);
check("control tap targets >= 36px tall", small === 0, `${small} too small`);
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
await sleep(400);
check("tapping a dot on a phone answers inside the chart card",
      await ev(`document.getElementById('viz').contains(document.getElementById('detail'))`));
const drop = await ev(`(()=>{const d=document.getElementById('detail').getBoundingClientRect();
  const p=document.getElementById('plot').getBoundingClientRect(); return d.top - p.bottom})()`);
check("the answer lands within a finger's reach of the chart", drop >= 0 && drop < 60,
      drop.toFixed(0) + "px below the plot");
await shot("mobile-detail");

await ev(`document.getElementById('fs').click()`);
await sleep(600);
check("full screen fills the viewport",
      await ev(`Math.abs(document.getElementById('viz').getBoundingClientRect().height - 844) < 2`),
      "h=" + await ev(`document.getElementById('viz').getBoundingClientRect().height`));
check("full screen still draws the chart",
      await ev(`document.querySelectorAll('#plot svg circle.dot').length > 400`));
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
await shot("mobile-fs");
await ev(`[...document.querySelectorAll('#detail .detail-nav button')].find(b=>b.textContent==='Clear').click()`);
await sleep(400);
check("clearing the pin does not resize the full-screen chart",
      Math.abs(await ev(`document.getElementById('plot').getBoundingClientRect().height`) - plotH) < 1,
      "plot h " + plotH + " -> " + await ev(`document.getElementById('plot').getBoundingClientRect().height`));
check("the strip is still drawn with nothing pinned",
      await ev(`(()=>{const d=document.getElementById('detail');
        return d.offsetParent !== null && d.getBoundingClientRect().height > 40})()`));
await send("Emulation.setTouchEmulationEnabled", { enabled: false });

// --- 7d. full screen on a real pointer: hover previews into the strip, and nothing moves --------
await viewport(1280, 900);
await goto(BASE);
await ev(`document.getElementById('fs').click()`);
await sleep(600);
const fsPlotH = await ev(`document.getElementById('plot').getBoundingClientRect().height`);
const fsDot = await ev(`(()=>{const s=document.querySelector('#plot svg');
  const c=[...s.querySelectorAll('circle.dot')].sort((a,b)=>+b.getAttribute('r')-+a.getAttribute('r'))[0];
  const b=c.getBoundingClientRect(); return {x:b.x+b.width/2, y:b.y+b.height/2}})()`);
await mouse("mouseMoved", fsDot.x, fsDot.y);
await sleep(300);
check("hovering in full screen previews into the strip",
      (await ev(`document.getElementById('detail').textContent`)).includes(top),
      "expected " + top);
check("hovering in full screen does not move the chart",
      Math.abs(await ev(`document.getElementById('plot').getBoundingClientRect().height`) - fsPlotH) < 1);
check("a hover in full screen still does not pin", await ev(`!location.hash.includes('c=')`));
await shot("desktop-fs-hover");
await ev(`document.getElementById('fs').click()`);
await sleep(400);

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
await sleep(300);
check("a narrow window previews into the compact panel",
      (await ev(`document.getElementById('detail').textContent`)).includes(top), "expected " + top);
const afterTop = await ev(`document.querySelector('#viz .legend').getBoundingClientRect().top`);
check("previewing does not shove the rest of the card down", Math.abs(afterTop - beforeTop) < 2,
      `legend top ${beforeTop.toFixed(0)} -> ${afterTop.toFixed(0)}`);
// Pinning adds the Prev/Next/Clear row, which is the tallest the panel ever gets — the reserved
// box has to cover THAT, or the page still jumps at the moment you click.
await mouse("mousePressed", ndot.x, ndot.y); await mouse("mouseReleased", ndot.x, ndot.y);
await sleep(400);
const pinnedTop = await ev(`document.querySelector('#viz .legend').getBoundingClientRect().top`);
check("pinning does not shove it either", Math.abs(pinnedTop - beforeTop) < 2,
      `legend top ${beforeTop.toFixed(0)} -> ${pinnedTop.toFixed(0)}`
      + " (panel " + await ev(`document.getElementById('detail').getBoundingClientRect().height.toFixed(0)`) + "px)");

// --- 7f. landscape full screen: the strip must not eat the chart ------------------------------
// A phone on its side is 390px TALL. The strip takes its height out of #plot rather than floating
// over it, so this is where that choice costs the most.
await viewport(844, 390, true);
await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
await goto(BASE);
await ev(`document.getElementById('fs').click()`);
await sleep(600);
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
  await sleep(300);
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
await sleep(400);
check("print hides the interactive chrome",
      await ev(`getComputedStyle(document.querySelector('.controls')).display === 'none'`));
check("print un-scrolls the table so every row is on the page",
      await ev(`getComputedStyle(document.querySelector('.scroll')).overflow === 'visible'`));
await shot("print");
await send("Emulation.setEmulatedMedia", { media: "" });

console.log(results.join("\n"));
console.log(logs.length ? "\nPAGE ERRORS:\n" + logs.join("\n") : "\nno page errors");
process.exit(results.some(r => r.startsWith("FAIL")) || logs.length ? 1 : 0);
