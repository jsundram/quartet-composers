# String Quartet Composers

**[jsundram.github.io/quartet-composers](https://jsundram.github.io/quartet-composers/)**

884 composers from Wikipedia's [List of String Quartet
Composers](https://en.wikipedia.org/wiki/List_of_string_quartet_composers), plotted by birth year
and number of quartets written, sized by how much their article is read and coloured by lifespan —
with a searchable, sortable table of the same data underneath.

A remake of a [2014 experiment](http://viz.runningwithdata.com/quartet_composers/index.html) that
used a *cartesian* fisheye: both axes warped continuously under
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
| — | **A readership sparkline** in the detail panel — every month since 2015-07, hover or arrow-key any month to read it, and a caption that names the spike (Saariaho's obituary, 18× typical) or the trend (Haydn, down 42% since 2015) |
| — | **Readership histogram with a drag-to-filter brush**, to get the long tail out of the way |
| — | **Gender filter** from Wikidata [P21](https://www.wikidata.org/wiki/Property:P21) — 276 of the 884 are women, and the Fame view shows the band they occupy |
| — | Shareable URLs (`#v=swarm&c=Joseph+Haydn&r=1500-200000`), a share card generated from the real data, installable + offline |

## The pipeline

Four cached stages. Nothing in the build touches the network, so the dataset is reproducible
offline and the exact bytes behind a deploy stay in git.

```sh
python3 scripts/scrape_list.py      # the wiki page  -> data/list.json + data/list.wiki
python3 scripts/fetch_wikidata.py   # canonical titles + P569/P570 + P21 -> data/people.json
python3 scripts/fetch_views.py      # every month since 2015-07 -> data/pageviews.json
python3 scripts/build_data.py       # combine the three -> composers.json + readership.json
```

`build_data.py` writes **two** files, because they are wanted at different moments.
`composers.json` (46 KB) is the roster and carries one view number per composer — the page cannot
paint without it. `readership.json` (487 KB) is the monthly history behind the sparkline: nothing
waits for it, so it is fetched after the first paint and the panel simply grows a line when it
arrives. Both are precached; only the first is a boot dependency.

Then run the data gate and **bump `V` in `sw.js`** — both files are precached, so without a bump the new numbers
reach the repo and nobody's phone. `scripts/sw-lint.py` guards it; enable the hook with
`git config core.hooksPath .githooks`.

### Keeping it current

Readership is the one input that goes stale purely because time passed, so it is the one on a
schedule:

```sh
python3 scripts/refresh.py            # top up if a month has completed since the last build
python3 scripts/refresh.py --check    # is one due? exit 1 if so, touch nothing
```

It is a **no-op unless a month has completed** — the test is whether `composers.json` already
covers the last complete month, not a timestamp — and when one has, it runs the three stages,
fails the run if the data gate fails, and bumps `V` only after it passes.
`.github/workflows/refresh.yml` runs it on the 3rd of each month (the API needs a day or two to
settle a finished month) and opens a PR. A PR rather than a push because every dataset bug this
repo has had looked entirely plausible in the file and needed a human to read a two-line diff.

The roster and the Wikidata reads are deliberately **not** on the schedule: those change for
editorial reasons, and a roster that grows by three composers overnight with nobody looking is how
a bad parse ships.

Two review tools that are not part of the build:

```sh
python3 scripts/audit_counts.py     # sample parsed counts beside their source sentence, to grade
python3 scripts/compare_2014.py     # diff against the archived 2014 snapshot, with reasons
```

## Five data elements, five different problems

**(a) The roster** and **(b) quartet counts** come from the list page, which is *prose, not a
table*: `*[[Joseph Haydn]] (1732–1809): Wrote sixty-eight string quartets…`. Seven rules read 791
of 885 entries; the rest return **null** and appear in the table but not the chart, because a wrong
count ships as a confident dot while a null is merely honest. Graded by hand on a random sample:
25 exactly right, 4 correctly null, 1 arguable. *Wikidata is not an alternative here* — Beethoven's
quartets are typed as generic "musical work/composition" with nothing linking them to the genre, so
a SPARQL count over the whole corpus returns four composers.

**(c) Birth and death dates** come from **Wikidata** ([P569](https://www.wikidata.org/wiki/Property:P569) born, [P570](https://www.wikidata.org/wiki/Property:P570) died), not the page prose, so a composer
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

The cache now holds **every month the API has** — 2015-07 onward, 134 months — for the same
one-request reason, and the detail panel draws it as a sparkline.
Each series is stored as a **flat array aligned to a shared `months` axis**, null where the API had
nothing: the obvious `{month: count}` object repeats the key 884 times per month and cost 1.9 MB
against 0.5 MB for the same numbers, and had to be rewritten whole every month. A null is *asked,
and there was nothing there* — distinct from a **missing** month, which is *never asked*, and
recording it is what makes a top-up cheap: without it the 62 articles created after 2015 look
permanently incomplete and are refetched in full on every run. The corollary is that a title that
needs fetching is fetched over the **whole axis**, never over `--months`: a flat array has no third
value between a count and a null, so the file holds exactly one asked window, and writing a
narrower fetch onto the wider axis would record un-asked months as nulls that then read as
complete forever. A month **in progress** is refused outright — the API does not withhold the
current month, it returns the days so far as though they were the month. And a title that does not
**answer** — a 404, or five exhausted retries — is dropped from the cache rather than written,
because the flatten would otherwise null-pad it into looking complete forever; dropping it makes
the next run ask again in full, which is what "rerun to pick them up" promises.
`scripts/fetch_views.test.py` holds all of that as six stubbed, offline cases. The headline number did **not**
move with it: the median is still over the last **twelve** cached months, because "how much read
is this composer" is a question about now. The rest is history, which is a different question, and
`validate.py` recomputes one from the other so the two files cannot drift apart. What a decade
buys is the thing twelve months structurally cannot show: Kaija Saariaho runs at ~2,000 readers a
month for eight years and touches 42,195 in June 2023, the month she died. 61 of the 884 articles
did not exist in 2015, and their sparklines start partway across the box and say so — a blank
stretch under a line chart otherwise reads as "nobody read this" rather than "not written yet".

**(e) Sex or gender** is **Wikidata [P21](https://www.wikidata.org/wiki/Property:P21)**, and it is the one element that is not a measurement but
a statement about a person — so it is reported, never derived. Same rank discipline as the dates
(the two share one `best_value()`), Wikidata's own labels kept as the values, and **no inference
from names or pronouns** for the composers who have no claim: `null` is a fact here exactly as it
is for an unstated quartet count. A value outside the label map ships as its raw QID rather than
as a null — a stated fact filed under "not stated" is the one outcome that is wrong about someone
rather than merely incomplete — and `validate.py` fails on it, so the fix is a label, not a
mystery. 276 of the 884 are women, 219 of them plottable; one composer (Fernand de la Tombelle,
the single row with no Wikidata item at all) has no claim and is in neither filter, which the
provenance line says out loud.

The honest name for (d) is **English Wikipedia readership**, not popularity — a Czech or Russian
composer's readers are largely on their own language's Wikipedia, which this does not count. The
UI says so in the legend ("EN Wikipedia readers / mo"), the lede, and the provenance line, rather
than letting "views" imply importance. A per-language fan-out via Wikidata sitelinks would trade
one bias for a messier one and is deliberately not attempted.

Readership spans 1 to 186,772 monthly views with a **median of 233**: half the roster is composers
essentially nobody reads, and at 884 dots they are most of the ink. Hence `histogram.js` — a
log-scale histogram of the distribution with a drag-to-select brush, which is the control and the
context in one 56px strip. It intersects with the search box and the gender pills; none of the three knows the others exist —
each returns "a Set of row indices, or null for everything" and `applyFilters()` intersects them.

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
python3 scripts/validate.test.py  # proves the gate catches each bug it claims to (20 cases)
python3 scripts/fetch_views.test.py  # the page-view cache's invariants, network stubbed (7 cases)
scripts/ui-test.sh           # 170 behavioural checks in a real headless Chrome (lens, tap-to-pin,
                             #   the three filters, theme repaint, 390px layout, offline, print) — no deps
node scripts/sw.test.mjs     # 24 tests of the service worker's fetch handler
python3 scripts/sw-lint.py   # precache contract: V bumped, SHELL paths exist, no cross-origin
python3 scripts/og-lint.py   # share card size (a card over ~250 KB previews as a grey box)
```

`validate.py`, `validate.test.py`, `fetch_views.test.py`, `sw.test.mjs` and `sw-lint.py` all run in CI; `ui-test.sh` needs
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
names.js          canonical Wikipedia title -> the short name the chart and the table print
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
