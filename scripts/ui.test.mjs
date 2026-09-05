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
  await send("Page.navigate", { url });
  // A navigation that changes only the FRAGMENT is same-document: the app never re-runs, so
  // goto(BASE + "#v=scatter") from BASE quietly left the previous section's view in place and the
  // checks that followed tested the wrong chart. Force the load.
  if (url.includes("#")) await send("Page.reload", { ignoreCache: false });
  for (let i = 0; i < 100; i++) { if (await ev("document.readyState === 'complete'")) break; await sleep(60); }
  await sleep(700);
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
// checks are about. The default view is now Readers (section 4e).
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

// --- 4e. the readers view: the one that makes the page's argument ------------------------------
await goto(BASE);
check("the readers view is what a bare URL opens on",
      await ev(`Chart.getMode() === 'readers'`), await ev(`Chart.getMode()`));
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
for (const who of ["Wolfgang Amadeus Mozart", "Giuseppe Cambini", "Joseph Haydn"])
  check(`${who} is labelled in the readers view`, named.includes(who), named.length + " labels placed");
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
check("size is not double-encoded in the readers view", radii <= 2, radii + " distinct radii");
check("the table chip follows the view's encoding",
      await ev(`(()=>{const rows=[...document.querySelectorAll('tbody tr')];
        const moz=rows.find(r=>r.textContent.includes('Mozart'));
        const tch=rows.find(r=>r.textContent.includes('Tchaikovsky'));
        return moz && tch && moz.querySelector('.chip').style.background
             !== tch.querySelector('.chip').style.background})()`));

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
check("every surname override still names a composer",
      (await ev(`Table.staleOverrides()`)).length === 0,
      "stale: " + JSON.stringify(await ev(`Table.staleOverrides()`)));
await ev(`[...document.querySelectorAll('thead th button')].find(b=>b.textContent==='Composer').click()`);
await sleep(200);
check("sorting by Composer sorts by surname",
      await ev(`(()=>{const t=[...document.querySelectorAll('tbody tr td:first-child')]
        .slice(0,3).map(c=>c.textContent.trim());
        return t.every((v,i)=>i===0||t[i-1].localeCompare(v)<=0)})()`),
      await ev(`[...document.querySelectorAll('tbody tr td:first-child')].slice(0,3)
        .map(c=>c.textContent.trim()).join(' | ')`));

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
      (await ev(`document.querySelector('#legend .ramp').style.background`)).includes("240, 164, 74"),
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
