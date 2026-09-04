#!/usr/bin/env node
// UI tests: drives a real headless Chrome over the DevTools Protocol and asserts what the app
// actually DOES — the lens magnifies, a tap pins, a theme flip re-bakes the SVG fills, the table
// fits a 390px phone, an offline reload still paints 466 dots.
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
await mouse("mouseMoved", dot.x, dot.y);
await sleep(300);
check("hover shows the name flag", await ev(`document.getElementById('flag').classList.contains('on')`),
      await ev(`document.getElementById('flag').textContent`));
check("hover previews into the detail panel", await ev(`/Beethoven/.test(document.getElementById('detail').textContent)`));
check("hover does NOT pin (no ring yet)", await ev(`!location.hash.includes('c=')`));

// --- 3. click pins ------------------------------------------------------------
await mouse("mousePressed", dot.x, dot.y); await mouse("mouseReleased", dot.x, dot.y);
await sleep(400);
check("click pins to the URL", await ev(`decodeURIComponent(location.hash)`).then(h => h.includes("c=Ludwig")),
      await ev(`decodeURIComponent(location.hash)`));
check("click rings the dot", await ev(`document.querySelectorAll('#plot svg circle.sel-ring').length === 1`));
check("selected row is marked in the table", await ev(`!!document.querySelector('tbody tr[aria-selected="true"]')`));
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
await goto(BASE);
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
await viewport(390, 844, true);
await goto(BASE);
await sleep(500);
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
await shot("mobile");
await ev(`document.getElementById('fs').click()`);
await sleep(600);
check("full screen fills the viewport",
      await ev(`Math.abs(document.getElementById('viz').getBoundingClientRect().height - 844) < 2`),
      "h=" + await ev(`document.getElementById('viz').getBoundingClientRect().height`));
check("full screen still draws the chart",
      await ev(`document.querySelectorAll('#plot svg circle.dot').length > 400`));
await shot("mobile-fs");

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
