# String Quartet Composers

**[jsundram.github.io/quartet-composers](https://jsundram.github.io/quartet-composers/)**

466 composers from Wikipedia's [List of String Quartet
Composers](https://en.wikipedia.org/wiki/List_of_string_quartet_composers), plotted by birth year
and number of quartets written, sized by Wikipedia readership and colored by lifespan — with a
searchable, sortable table of the same data underneath.

A remake of a [2014
experiment](https://github.com/jsundram/viz.runningwithdata.com) that used a *cartesian* fisheye:
both axes warped continuously under the cursor. It magnified beautifully and read terribly — with
the axes always moving there was no stable picture, hovering was the only way to learn anything,
and a screenshot of it was nonsense.

## What changed

| 2014 | now |
|---|---|
| One view: cartesian fisheye, always on | Three: **scatter** (fixed axes, ordinary pan/zoom), **swarm** (force-collided, nothing overlaps), **lens** (a *circular* fisheye over a fixed chart) |
| Linear y, 0–200 | **Log y** — 268 of 466 composers wrote 3 quartets or fewer, and a linear axis crushed them into one line |
| Tap target = the dot (2.5px for most) | **Voronoi hit-testing** — a Delaunay over current screen positions, so the target is the dot's whole cell |
| Hover-only tooltip | **A persistent detail panel.** Hover previews it, click/tap pins it — which is also why there's no hover bubble to double-fire on touch |
| No labels | **Collision-avoided labels**, so the static view says something with no interaction at all |
| Fixed 960px, desktop only | Responsive, dark mode, print stylesheet, and a CSS-driven full-screen chart |
| Color = lifespan on RdYlBu-9 | Diverging ramp with its midpoint at the **median** lifespan (72), and living composers pulled off the ramp entirely (see below) |
| — | Shareable URLs (`#v=swarm&c=Joseph+Haydn`), a share card generated from the real data, installable + offline |

## The data gotcha worth knowing about

The 2014 scrape stored `died - born` for dead composers and `2014 - born` for living ones **in the
same field**. 139 of 466 rows are the second kind, so coloring naively paints every living composer
as tragically short-lived — Mohammed Fairouz (b. 1985) reads as "died at 29."

`scripts/build_data.py` flags those rows, and the app draws them as **open circles** with no color
at all — a shape difference, so it survives color-blindness and black-and-white printing. The table
writes their lifespan as `29+`, and the UI says "living in 2014", never "living", because the flag
can't tell someone alive that year from someone who died in it.

## Build

Deployed files are static, with **zero runtime dependencies** — d3 is vendored, not CDN-loaded.
The scripts are build-time only and need nothing from pip.

```sh
python3 scripts/build_data.py    # data/*.json          -> composers.json
python3 scripts/make-og-svg.py   # composers.json       -> assets/og.svg   (a real render of the data)
scripts/make-og.sh               # assets/og.svg        -> assets/og.png   (needs rsvg-convert + pngquant)
scripts/make-icons.sh            # assets/icon.svg      -> the PWA PNGs
python3 -m http.server 8000      # then open http://localhost:8000/
```

Refresh the page views (Wikimedia API, stdlib only, a couple of minutes):

```sh
python3 scripts/fetch_views.py               # the last complete month
python3 scripts/fetch_views.py --month 2026-01 --dry-run
```

**Then bump `V` in `sw.js`.** `composers.json` is precached, so without a bump the new numbers reach
the repo and nobody's phone. `scripts/sw-lint.py` catches it; enable the hook with
`git config core.hooksPath .githooks`.

## Checks

```sh
scripts/ui-test.sh           # 31 behavioral checks in a real headless Chrome (lens, tap-to-pin,
                             #   theme repaint, 390px layout, offline reload, print) — no deps
node scripts/sw.test.mjs     # 24 tests of the service worker's fetch handler
python3 scripts/sw-lint.py   # precache contract: V bumped, SHELL paths exist, no cross-origin
python3 scripts/og-lint.py   # share card size (a card over ~250 KB previews as a grey box)
```

`sw.test.mjs` and `sw-lint.py` also run in CI (`.github/workflows/checks.yml`); `ui-test.sh` needs a
browser, so it's a local check — and it skips with exit 0 rather than failing if there isn't one.

## Layout

```
index.html        structure          styles.css   design system (light/dark/print)
app.js            boot + selection   chart.js     the three views
table.js          the data table     theme.js     three-state theme + JS-baked-color contract
sw.js             offline shell + the V cache-busting constant
composers.json    the dataset (generated — edit data/ and rebuild)
d3.v7.min.js      vendored, not a CDN
data/             raw scrape inputs (not shipped)
scripts/          build + lint tooling (never shipped)
```

Built on [pwa-starter](https://github.com/jsundram/pwa-starter); vendored files carry a
`pwa-starter: <file> @ <sha>` stamp so a fix upstream can be traced downstream.

## Credit

Based on [fisheye.js](https://github.com/d3/d3-plugins/tree/master/fisheye) by
[Mike Bostock](https://bost.ocks.org/mike/) — the circular lens in `chart.js` is his, inlined
because the plugin is d3 v3-only.
