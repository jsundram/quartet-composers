#!/usr/bin/env node
// pwa-starter: sw.test.mjs @ d2fad01  (fixtures retargeted from usage/ to this app's BOOT_DEPS,
//                                       which are now READ OUT of sw.js rather than copied)
// Behavioral tests for sw.js's fetch handler — the offline / "lie-fi" contract that this file
// exists to hold. sw.js is dense with invariant-carrying prose; this is the executable half.
//
// It loads sw.js UNMODIFIED under mocked Service Worker globals (self, caches, fetch, Response,
// URL) and a FAKE clock, so the network-timeout bounds (NET_TIMEOUT_MS / NET_TIMEOUT_COLD_MS) are
// exercised deterministically and instantly instead of by real waiting. No dependencies.
//
//     node scripts/sw.test.mjs
//
// Exits non-zero on any failed assertion, so it drops straight into CI (see .github/workflows).
import { readFileSync } from "node:fs";

// ---- fake clock ------------------------------------------------------------
// sw.js's withTimeout() is the only timer user; the rest of the code is microtask-driven. A "slow"
// fetch simply never settles, so advancing this clock past a bound is what fires the timeout.
let now = 0;
let nextTimer = 1;
const timers = new Map();
const fakeSetTimeout = (fn, ms) => { const id = nextTimer++; timers.set(id, { at: now + (ms || 0), fn }); return id; };
const fakeClearTimeout = (id) => { timers.delete(id); };
const flush = async (n = 60) => { for (let i = 0; i < n; i++) await Promise.resolve(); };
async function tick(ms) {
  const target = now + ms;
  await flush();
  for (;;) {
    let dueId = null, dueAt = Infinity;
    for (const [id, t] of timers) if (t.at <= target && t.at < dueAt) { dueId = id; dueAt = t.at; }
    if (dueId === null) break;
    const t = timers.get(dueId);
    timers.delete(dueId);
    now = t.at;
    t.fn();
    await flush();
  }
  now = target;
  await flush();
}

// ---- mocked SW environment -------------------------------------------------
// Project-page scope (user.github.io/repo/), so docKey()'s scope-stripping is exercised.
const ORIGIN = "https://ex.test";
const BASE = ORIGIN + "/pwa-starter/";
const b = (p) => BASE + p;

let fetchMode = "ok";        // "ok" | "slow" | "offline" | "offline-heal" | "redirect"
let fetchStatus = 200;       // status for "ok" mode
let fetchCalls = 0;
let healEntry = null;        // [url, response] inserted by "offline-heal" before it rejects
const CACHE = new Map();     // url -> response

const makeResponse = (body, { status = 200, redirected = false, type = "basic" } = {}) => ({
  _body: body, status, ok: status >= 200 && status < 300, redirected, type,
  clone() { return makeResponse(body, { status, redirected, type }); },
});
const href = (r) => (typeof r === "string" ? new URL(r, self.location).href : r.url);
const req = (url, mode = "no-cors") => ({ url, method: "GET", mode });

const self = {
  location: new URL(BASE + "sw.js"),
  registration: {},
  clients: { claim: async () => {} },
  skipWaiting: async () => {},
  _listeners: {},
  addEventListener(t, fn) { (this._listeners[t] ||= []).push(fn); },
};
const location = self.location;
const ResponseCtor = function (body, init = {}) { return makeResponse(body, { status: init.status || 200 }); };

const cacheApi = {
  async match(r) { return CACHE.get(href(r)); },
  async put(r, resp) { CACHE.set(href(r), resp); },
  async keys() { return [...CACHE.keys()].map((url) => ({ url })); },
};
const caches = {
  async open() { return cacheApi; },
  async match(r) { return CACHE.get(href(r)); },
  async keys() { return ["app-v7"]; },
  async delete() { return true; },
};
const fetchImpl = async (r) => {
  fetchCalls++;
  if (fetchMode === "offline") throw new Error("offline");
  if (fetchMode === "offline-heal") { if (healEntry) CACHE.set(href(healEntry[0]), healEntry[1]); throw new Error("offline"); }
  if (fetchMode === "slow") return new Promise(() => {});   // never settles → only a timeout ends it
  // A navigation's redirect mode is "manual": the browser hands the SW an opaqueredirect
  // (status 0, ok false) that respondWith must pass back for the browser to follow.
  if (fetchMode === "redirect") return makeResponse("", { status: 0, type: "opaqueredirect" });
  return makeResponse("NET:" + href(r), { status: fetchStatus });
};

// ---- load sw.js under those globals ----------------------------------------
const src = readFileSync(new URL("../sw.js", import.meta.url), "utf8");
new Function("self", "location", "caches", "fetch", "Response", "URL", "setTimeout", "clearTimeout", src)(
  self, location, caches, fetchImpl, ResponseCtor, URL, fakeSetTimeout, fakeClearTimeout,
);
const fetchHandler = self._listeners.fetch[0];

// Drive one request through the handler; returns a promise for whatever respondWith() settles to.
function start(request) {
  let settle;
  const done = new Promise((res) => (settle = res));
  fetchHandler({ request, respondWith: (p) => Promise.resolve(p).then(settle), waitUntil() {} });
  return done;
}
// Fire the handler and report whether it claimed the request at all (respondWith called).
async function intercepts(request) {
  let called = false;
  fetchHandler({ request, respondWith: () => { called = true; }, waitUntil() {} });
  await flush();
  return called;
}
const bodyOf = (r) => (r ? (r._body ?? "(generated page)") : "(undefined!)");
const isPending = async (p) => (await Promise.race([p.then(() => false), flush().then(() => true)]));

// ---- assertions ------------------------------------------------------------
// Seed a FAILING exit code up front. The suite runs inside an async IIFE; if the fetch handler
// ever HANGS (e.g. a regression back to unbounded network-first), that IIFE never settles, and with
// only the fake clock there's no real timer keeping the process alive — node would drain the event
// loop and exit 0, staying green on the exact hang this suite exists to catch. The explicit
// process.exit() at the very end is the ONLY sanctioned way to reach a clean exit; any earlier exit
// (a hung await, a handler that rejects instead of settling respondWith) now surfaces as a red 1.
//
// Its signature is exit 1 with NO OUTPUT — the run stops mid-suite, so there is no failure line and
// no summary. Silence here means "something never settled", not "the runner is broken"; the ok
// lines printed before it stopped are where to look.
process.exitCode = 1;

let pass = 0, fail = 0;
const ok = (name, cond, detail = "") => { if (cond) { pass++; console.log("  ok   -", name); } else { fail++; console.log("  FAIL -", name, detail); } };
function reset(mode = "ok", status = 200) { CACHE.clear(); fetchMode = mode; fetchStatus = status; fetchCalls = 0; healEntry = null; now = 0; timers.clear(); }
// This app's shell as the tests need it. Unlike pwa-starter's skeleton — whose root page renders
// scriptless markup and so has an EMPTY BOOT_DEPS — every pixel here is drawn by script, so the
// ROOT document is the bootability case: cached but missing d3 (or the dataset) it is a headline
// and a blank box, which is worse than the honest offline page.
//
// READ OUT OF sw.js, not typed here, because a copy of this list DRIFTS AND FAILS ILLEGIBLY. Add
// a script to BOOT (invariant 2) and forget the copy, and every seeded shell below is missing a
// boot dep: the root nav is judged unbootable, falls through to a network that never settles under
// the fake clock, and the IIFE never reaches its process.exit(). The suite then exits 1 having
// printed NOTHING AT ALL — no failure name, no summary, no stack — which reads as a broken test
// runner rather than as the one line you forgot. (That is the seeded exitCode below doing its job;
// it just cannot tell you why.) Derived, the copy cannot drift.
const BOOT_FILES = (() => {
  const m = src.match(/const BOOT\s*=\s*\[([\s\S]*?)\]/);
  const list = m ? [...m[1].matchAll(/"\.\/([^"]+)"/g)].map(x => x[1]) : [];
  // A regex over source is only as good as the shape it assumes, so fail loudly if sw.js is
  // reformatted out from under it rather than silently seeding an empty shell — which would look
  // exactly like the drift this exists to prevent.
  if (list.length < 4 || !list.includes("composers.json")) {
    console.log("  FAIL - could not read BOOT out of sw.js: " + JSON.stringify(list));
    process.exit(1);
  }
  return list;
})();
const seedBootableShell = () => {
  CACHE.set(BASE, makeResponse("CACHED_ROOT"));
  CACHE.set(b("index.html"), makeResponse("CACHED_INDEX"));
  CACHE.set(b("styles.css"), makeResponse("CACHED_CSS"));
  for (const f of BOOT_FILES) CACHE.set(b(f), makeResponse("CACHED_" + f.replace(/\W/g, "_").toUpperCase()));
};

(async () => {
  // --- cache-first happy path: instant, zero network -----------------------
  reset("slow"); seedBootableShell();
  let r = await start(req(BASE, "navigate"));
  ok("cached+bootable nav → cache, 0 fetches", bodyOf(r) === "CACHED_ROOT" && fetchCalls === 0, `body=${bodyOf(r)} fetches=${fetchCalls}`);

  reset("slow"); seedBootableShell();
  r = await start(req(b("app.js")));
  ok("cached subresource → cache, 0 fetches", bodyOf(r) === "CACHED_APP_JS" && fetchCalls === 0, `fetches=${fetchCalls}`);

  // A second page would have no BOOT_DEPS entry (deps default to []), so it is bootable on its
  // own and must be served as ITSELF — the root-document fallback is gated to the root precisely
  // so a future page can't be answered with the wrong document.
  reset("slow"); seedBootableShell();
  CACHE.set(b("about/"), makeResponse("CACHED_ABOUT"));
  r = await start(req(b("about/"), "navigate"));
  ok("second-page nav → its OWN page (not index)", bodyOf(r) === "CACHED_ABOUT" && fetchCalls === 0);

  // THE BOOT_DEPS CONTRACT, stated directly: the root doc is cached and the network is gone, but
  // d3 is missing, so the page would paint a title over an empty box. The offline page wins.
  reset("offline"); seedBootableShell();
  CACHE.delete(b("d3.v7.min.js"));
  r = await start(req(BASE, "navigate"));
  ok("cached root minus d3 → offline page, not a chartless page", r && r.status === 503, `status=${r && r.status} body=${bodyOf(r)}`);

  reset("offline"); seedBootableShell();
  CACHE.delete(b("composers.json"));
  r = await start(req(BASE, "navigate"));
  ok("cached root minus the dataset → offline page", r && r.status === 503, `status=${r && r.status}`);

  // --- first run ------------------------------------------------------------
  reset("ok");
  r = await start(req(BASE, "navigate"));
  ok("first-run online nav → network response", bodyOf(r) === "NET:" + BASE && fetchCalls === 1);

  reset("offline");
  r = await start(req(BASE, "navigate"));
  ok("first-run offline nav → real fallback page", r && r.status === 503, `status=${r && r.status}`);

  reset("offline");
  r = await start(req(b("assets/icon-192.png")));
  ok("uncached image offline → real 504", r && r.status === 504, `status=${r && r.status}`);

  reset("offline");
  r = await start(req(b("theme.js")));
  ok("uncached script offline → real 504, not HTML", r && r.status === 504, `status=${r && r.status}`);

  // --- ISSUE 1: the COLD (no-cache) path must be BOUNDED, not infinite ------
  reset("slow");   // nothing cached + lie-fi: the previously-unbounded path
  let p = start(req(BASE, "navigate"));
  await tick(3001);
  ok("cold lie-fi nav still pending at 3s (WARM bound must not apply)", await isPending(p));
  await tick(14000);   // now ~17s total, past the 15s COLD bound
  r = await p;
  ok("cold lie-fi nav → bounded, honest fallback (issue 1)", r && r.status === 503, `status=${r && r.status}`);

  // --- WARM bound: cached-but-unbootable + lie-fi resolves at 3s ------------
  reset("slow");
  CACHE.set(BASE, makeResponse("CACHED_ROOT"));   // doc cached, every boot dep absent → not bootable
  p = start(req(BASE, "navigate"));
  await tick(2999);
  ok("warm lie-fi nav still pending just before 3s", await isPending(p));
  await tick(3);
  r = await p;
  ok("warm lie-fi nav → fallback at ~3s (does NOT wait 15s)", r && r.status === 503, `status=${r && r.status}`);

  // --- ISSUE 2: a navigation 5xx must NOT serve the unbootable cached doc ---
  reset("ok", 500);
  CACHE.set(BASE, makeResponse("CACHED_UNBOOTABLE_ROOT"));   // cached but boot deps absent
  r = await start(req(BASE, "navigate"));
  ok("nav + server 500 → honest fallback, not bare doc (issue 2)", r && r.status === 503 && bodyOf(r) !== "CACHED_UNBOOTABLE_ROOT", `status=${r && r.status} body=${bodyOf(r)}`);

  // knock-on: a first-run nav hitting a transient 5xx gets the "try again" page, not the raw error
  reset("ok", 500);
  r = await start(req(BASE, "navigate"));
  ok("first-run nav + server 500 → try-again page, not raw 500", r && r.status === 503, `status=${r && r.status}`);

  // subresource 5xx keeps the old behavior (a real response, not a fallback page)
  reset("ok", 500);
  r = await start(req(b("app.js")));
  ok("subresource + server 500 → returns the response (unchanged)", r && r.status === 500, `status=${r && r.status}`);
  

  // ...but a PERMANENT 4xx is the server's honest answer: an online nav to a typo'd path must get
  // the real 404, not an offline page lying "open it once with a connection" to an online user.
  reset("ok", 404);
  r = await start(req(b("typo.html"), "navigate"));
  ok("online nav + 404 → server's 404, not the offline lie", r && r.status === 404, `status=${r && r.status}`);

  // ...and an OPAQUEREDIRECT (nav redirect mode is "manual": status 0, ok false — e.g. GitHub
  // Pages 301ing slashless /repo/usage) is a healthy answer the browser must get back to follow.
  reset("redirect");
  r = await start(req(b("about"), "navigate"));
  ok("online nav + 301 → opaqueredirect passed back, not offline page", r && r.type === "opaqueredirect", `type=${r && r.type} status=${r && r.status}`);

  // --- ISSUE 3: the catch re-reads the cache, catching a mid-window repair --
  reset("offline-heal");
  for (const f of BOOT_FILES) CACHE.set(b(f), makeResponse("DEP"));   // so bootable() passes in the catch
  healEntry = [BASE, makeResponse("REPAIRED_ROOT")];   // "ensure-shell" repairs during the fetch
  r = await start(req(BASE, "navigate"));
  ok("catch re-reads cache → serves mid-window repair (issue 3)", bodyOf(r) === "REPAIRED_ROOT", `body=${bodyOf(r)}`);

  // --- app-specific branches -------------------------------------------------
  // Precached JSON (manifest.json AND composers.json are in SHELL) is served without revalidation: the refresh would
  // be discarded by cachePut()'s SHELL refusal, so fetching it is pure cellular waste.
  reset("slow");
  CACHE.set(b("manifest.json"), makeResponse("CACHED_MANIFEST"));
  r = await start(req(b("manifest.json")));
  ok("precached json → cache, 0 fetches (no discarded revalidate)", bodyOf(r) === "CACHED_MANIFEST" && fetchCalls === 0, `fetches=${fetchCalls}`);

  // Non-shell JSON is stale-while-revalidate: cached copy now, one background refresh.
  reset("ok");
  CACHE.set(b("stats.json"), makeResponse("CACHED_STATS"));
  r = await start(req(b("stats.json")));
  ok("non-shell json → cached copy + background refresh", bodyOf(r) === "CACHED_STATS" && fetchCalls === 1, `body=${bodyOf(r)} fetches=${fetchCalls}`);

  // pwa-starter's Google Fonts branch was REMOVED here (system fonts only), so the contract
  // flips: a cross-origin request must fall through untouched rather than be cached.
  reset("ok");
  ok("cross-origin request → not intercepted", !(await intercepts(req("https://fonts.gstatic.com/s/font.woff2"))));

  // The SW must never intercept its own script (checkVer()'s ./sw.js?_=<ts> probe) or non-GETs.
  reset("ok");
  ok("sw.js version probe → not intercepted", !(await intercepts(req(b("sw.js?_=123"), "no-cors"))));
  reset("ok");
  ok("POST → not intercepted", !(await intercepts({ url: BASE, method: "POST", mode: "navigate" })));

  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})();
