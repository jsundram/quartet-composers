# String Quartet Composers

**[jsundram.github.io/quartet-composers](https://jsundram.github.io/quartet-composers/)**

884 composers from Wikipedia's [List of String Quartet
Composers](https://en.wikipedia.org/wiki/List_of_string_quartet_composers), plotted by birth year
and number of quartets written, sized by how much their article is read and coloured by lifespan —
with a searchable, sortable table of the same data underneath.

A remake of a 2014 experiment that used a *cartesian* fisheye: both axes warped continuously under
the cursor. It magnified beautifully and read terribly — with the axes always moving there was no
stable picture, hovering was the only way to learn anything, and a screenshot of it was nonsense.

## What changed

| 2014 | now |
|---|---|
| One view: cartesian fisheye, always on | Three: **scatter** (fixed axes, ordinary pan/zoom), **swarm** (force-collided, nothing overlaps), **lens** (a *circular* fisheye over a fixed chart) |
| Linear y, 0–200 | **Log y** — most composers here wrote three quartets or fewer, and a linear axis crushed them into one line |
| Tap target = the dot (2.5px for most) | **Voronoi hit-testing** — a Delaunay over current screen positions, so the target is the dot's whole cell |
| Hover-only tooltip | **A persistent detail panel.** Hover previews it, click/tap pins it — which is also why there's no hover bubble to double-fire on touch |
| No labels | **Collision-avoided labels**, so the static view says something with no interaction at all |
| Fixed 960px, desktop only | Responsive, dark mode, print stylesheet, and a CSS-driven full-screen chart |
| Colour = lifespan on RdYlBu-9 | Diverging ramp pivoting on the **median** lifespan, with living composers off the ramp entirely |
| 477 composers, frozen 2014 scrape | **884**, re-scraped, with a repeatable pipeline (below) |
| Dot size = one month of page views | **Median of 12 months** — a single month is 12% off typical, 29% at worst |
| — | **Readership histogram with a drag-to-filter brush**, to get the long tail out of the way |
| — | Shareable URLs (`#v=swarm&c=Joseph+Haydn&r=1500-200000`), a share card generated from the real data, installable + offline |

## The pipeline

Four cached stages. Nothing in the build touches the network, so the dataset is reproducible
offline and the exact bytes behind a deploy stay in git.

```sh
python3 scripts/scrape_list.py      # the wiki page  -> data/list.json + data/list.wiki
python3 scripts/fetch_wikidata.py   # canonical titles + P569/P570 -> data/people.json
python3 scripts/fetch_views.py      # 12 monthly counts each -> data/pageviews.json
python3 scripts/build_data.py       # combine the three -> composers.json
```

Then run the data gate and **bump `V` in `sw.js`** — `composers.json` is precached, so without a bump the new numbers
reach the repo and nobody's phone. `scripts/sw-lint.py` guards it; enable the hook with
`git config core.hooksPath .githooks`.

Two review tools that are not part of the build:

```sh
python3 scripts/audit_counts.py     # sample parsed counts beside their source sentence, to grade
python3 scripts/compare_2014.py     # diff against the archived 2014 snapshot, with reasons
```

## Four data elements, four different problems

**(a) The roster** and **(b) quartet counts** come from the list page, which is *prose, not a
table*: `*[[Joseph Haydn]] (1732–1809): Wrote sixty-eight string quartets…`. Seven rules read 791
of 885 entries; the rest return **null** and appear in the table but not the chart, because a wrong
count ships as a confident dot while a null is merely honest. Graded by hand on a random sample:
25 exactly right, 4 correctly null, 1 arguable. *Wikidata is not an alternative here* — Beethoven's
quartets are typed as generic "musical work/composition" with nothing linking them to the genre, so
a SPARQL count over the whole corpus returns four composers.

**(c) Birth and death dates** come from **Wikidata** (P569/P570), not the page prose, so a composer
who died last year isn't still shown as living. Rank matters: Wikidata marks known-wrong values
`deprecated` rather than deleting them, and reading claims without checking rank reported Tania
León — alive, Pulitzer 2021 — as having died in 1996.

**(d) Page views** are the noisiest input and the loudest channel, since they drive dot area. Three
traps, all of which this repo fell into first:

- *A redirect is its own title.* Asking the API for "Bela Bartok" returns **41** views, not Béla
  Bartók's **14,330** — with a 200 and no error. Titles are resolved through the MediaWiki API
  before any view is requested.
- *A disambiguator is load-bearing.* A bare "John Adams" resolves correctly and unambiguously to
  the second President of the United States, whose 144,948 views briefly outranked Beethoven here.
- *One month is weather.* Measured against a 12-month window, a single month is 12% off the median
  typically and 29% at worst; August is a seasonal trough; one composer has a month at 2.13× his
  own median. `monthly` granularity returns the whole range in **one request**, so twelve months
  costs exactly what one did. The stored series makes the statistic recomputable offline.

The honest name for (d) is **English Wikipedia readership**, not popularity — a Czech or Russian
composer's readers are largely on their own language's Wikipedia, which this does not count. The
UI says so in the legend ("EN Wikipedia readers / mo"), the lede, and the provenance line, rather
than letting "views" imply importance. A per-language fan-out via Wikidata sitelinks would trade
one bias for a messier one and is deliberately not attempted.

Readership spans 1 to 186,772 monthly views with a **median of 233**: half the roster is composers
essentially nobody reads, and at 884 dots they are most of the ink. Hence `histogram.js` — a
log-scale histogram of the distribution with a drag-to-select brush, which is the control and the
context in one 56px strip. It intersects with the search box; neither knows the other exists.

## The 2014 data

Archived in `data/composers-2014.json` and `data/views-2014.json`, **not plotted**. The pageviews
API has no per-article data before 2015-07, so the 2014 numbers came from a different measurement
system entirely and cannot be compared to a modern figure — "down 30% since 2014" is not a claim
this data can support. Counts and dates *are* comparable (same page, twelve years apart), which is
what `compare_2014.py` is for: birth years agree 98.2%, which is the check that proves rows are
matched to the same human.

## Checks

```sh
python3 scripts/validate.py       # THE DATA GATE — see below; run it after every rebuild
python3 scripts/validate.test.py  # proves the gate catches each bug it claims to (11 cases)
scripts/ui-test.sh           # 39 behavioural checks in a real headless Chrome (lens, tap-to-pin,
                             #   brush filter, theme repaint, 390px layout, offline, print) — no deps
node scripts/sw.test.mjs     # 24 tests of the service worker's fetch handler
python3 scripts/sw-lint.py   # precache contract: V bumped, SHELL paths exist, no cross-origin
python3 scripts/og-lint.py   # share card size (a card over ~250 KB previews as a grey box)
```

`validate.py`, `validate.test.py`, `sw.test.mjs` and `sw-lint.py` all run in CI; `ui-test.sh` needs
a browser, so it's a local check and skips with exit 0 rather than failing if there isn't one.

### Why there's a data gate

Every serious bug this dataset has had was a **data** bug, and not one was caught by a test — they
were caught by a human noticing a number looked off, twice only after it was already live. A
redirect returning 41 views instead of 14,330. The second President of the United States outranking
Beethoven. A living composer reported dead because Wikidata marks known-wrong values `deprecated`
rather than deleting them. Every one produced *plausible-looking output*, which is precisely what
unit tests and code review are worst at catching.

`validate.py` compares `composers.json` against three things — its schema, the other cached files,
and the previous commit — and fails the build. Drift against the last commit is the only check that
can see a wrong-article join, because 144,948 views is implausible only *next to* what the same row
said last time. `validate.test.py` reproduces each historical defect in a throwaway copy and asserts
the gate rejects it, so a weakened check goes red instead of quietly green.

## Layout

```
index.html        structure          styles.css   design system (light/dark/print)
app.js            boot + selection   chart.js     the three views
table.js          the data table     histogram.js the readership filter (log histogram + brush)
theme.js          three-state theme + the JS-baked-color contract
sw.js             offline shell + the V cache-busting constant
composers.json    the dataset (generated — edit data/ and rebuild)
d3.v7.min.js      vendored, not a CDN
data/             cached pipeline inputs + the 2014 archive (not shipped)
scripts/          pipeline, review tools, lints, the data gate (never shipped)
TODO.md           open work, with the reasoning — read before picking something up
```

Built on [pwa-starter](https://github.com/jsundram/pwa-starter); vendored files carry a
`pwa-starter: <file> @ <sha>` stamp so a fix upstream can be traced downstream.

## Credit

Based on [fisheye.js](https://github.com/d3/d3-plugins/tree/master/fisheye) by
[Mike Bostock](https://bost.ocks.org/mike/) — the circular lens in `chart.js` is his, inlined
because the plugin is d3 v3-only.
