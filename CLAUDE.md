# CLAUDE.md — quartet-composers

A static d3 visualization + data table, built on
[pwa-starter](https://github.com/jsundram/pwa-starter). No build step ships; the deployed files are
plain static assets. Read README.md first for what the app is.

## Invariants — break these and it fails silently

1. **Bump `V` in `sw.js` on every change to a `SHELL` file.** `composers.json`, `chart.js`,
   `table.js`, `app.js`, `styles.css`, `index.html`, `theme.js`, `d3.v7.min.js` are all precached
   and served cache-first. Without a bump the fix reaches the repo and nobody's installed copy.
   `scripts/sw-lint.py` guards it; `app.js`'s `VER_PREFIX` must keep matching `V`'s stem.
   *This bit during development*: a headless-Chrome profile kept running the previous edit's
   `chart.js` for two test rounds. That was the feature working.

2. **`sw.js`'s `BOOT_DEPS` must list every script the page dies without.** Unlike the skeleton's
   root page, every pixel here is drawn by JS, so a cached `index.html` without `d3.v7.min.js` or
   `composers.json` is a headline over an empty box. Adding a new load-bearing script means adding
   it to `SHELL`, to `BOOT`, and bumping `V`.

3. **Colors read into JS can't be reached by a CSS variable swap.** `chart.js` bakes `--c-*` into
   SVG fills and `app.js` bakes them into the legend. Both re-read via `Theme.getCssColor` inside
   `rerender()`, which `Theme.subscribe` fires on every theme change. A new baked color must go
   through `getCssColor`, never `getComputedStyle` directly.

4. **`composers.json` is generated.** Edit `data/composers_raw.json` / `data/views.json` and rerun
   `scripts/build_data.py`; never hand-edit the output.

5. **The `lifespan` field is a lifespan only when `living` is 0.** For the other 139 rows it is
   age-in-2014. Anything that ramps, sorts, or averages it has to branch on `living` — see the long
   note in `scripts/build_data.py`.

6. **`meta.scrape_year` and `meta.views_month` are different dates and must stay that way.** The
   composer list is frozen at 2014; page views are refreshable. The `living` flag, the legend, and
   the detail panel all key off `scrape_year`; only the provenance line uses `views_month`. Reading
   the year off `views_month` was a real bug: the first refresh would have marked every living
   composer dead. `build_data.py` now aborts if fewer than 10% of rows read as living.

7. **Search folds `ł ø đ ß æ œ` before NFD** (`table.js`). Those have no Unicode decomposition, so
   NFD alone leaves them intact and "lutoslawski" misses "Lutosławski". Adding a name with a new
   such character means adding it to `FOLD`.

6. **`scripts/make-og-svg.py` duplicates chart.js's scales on purpose.** Same domains, same 0.35
   radius exponent, same ramp. Changing an encoding in `chart.js` means changing it there too, or
   the share card stops matching the page. They are duplicated rather than shared because the app
   must not ship a build step and the card must not ship a JS runtime.

## Testing

Three suites, all dependency-free:

- `node scripts/sw.test.mjs` — the service worker's fetch handler under mocked SW globals.
- `python3 scripts/sw-lint.py` — the precache contract (invariant 1).
- `scripts/ui-test.sh` — 31 behavioral checks against a real headless Chrome over CDP. It starts
  its own server and browser and skips cleanly (exit 0) if no Chromium is installed. Every check
  in it exists because something was actually broken; read the header before deleting one.

The first two run in CI. `ui-test.sh` does not (it needs a browser) — run it by hand after touching
`chart.js`, `table.js`, or `styles.css`.

## Conventions

- Vendored pwa-starter files carry `pwa-starter: <file> @ <sha>` near the top. Keep the stamp when
  editing them; it is how `check-downstream.py` upstream finds this repo.
- Comments explain *why*, and especially what breaks otherwise. Match that; don't narrate what the
  next line does.
- `index.html` owns structure, `styles.css` owns looks, `app.js` owns boot and the one piece of
  shared state (which composer is selected). `chart.js` and `table.js` never talk to each other.
