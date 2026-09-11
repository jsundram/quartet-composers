# CLAUDE.md — quartet-composers

A static d3 visualization + data table on [pwa-starter](https://github.com/jsundram/pwa-starter).
No build step; the deployed files are the repo's files. README.md says what the app is.

Three places to put a thing, and keeping them apart is what keeps this file short. **Here: rules** —
what to do, and what breaks otherwise. **TODO.md: history** — open work, decisions already made, and
the incident behind each. **A check: anything mechanical** — a count, a list, a threshold, a measured
offset — because a check can go red and a sentence cannot. So where a rule below is enforced, it
names the enforcement instead of repeating the arithmetic.

**Which means a number in here is a RECORD or it is absent.** A record is a measurement that
happened — a run, an audit, an experiment — and cannot go stale, so it is safe to type. Anything the
repo recomputes is not: a roster total, a list size, a suite's case count, a constant, a live
statistic. Those are read from the thing that holds them, and writing one here buys a reader nothing
while costing an edit every time the thing moves. `chart.js` had this right about `CANON` from the
start — "deliberately NOT a count… every place that printed the number went stale in the same
commit" — and the docs spent a 300-line lint keeping such numbers honest instead of not writing them.

## Invariants — break these and it fails silently

1. **`V` in `sw.js` moves on every change to a `SHELL` file — and the hook moves it for you.** The
   shell is precached and served cache-first, so without a bump the fix reaches the repo and
   nobody's installed copy. `app.js`'s `VER_PREFIX` must keep matching `V`'s stem, which is why only
   the numeric TAIL is ever incremented.
   Nothing about this needs a human: `sw-lint.py --fix`, which the pre-commit hook runs, knows which
   files are `SHELL` and which of them this commit stages, so it bumps the tail and re-stages
   `sw.js` in the same commit. It declines and falls back to nagging in exactly three cases — a
   merge in progress, an `sw.js` carrying unstaged edits, or a `V` with no numeric tail — so a
   decline is always a state where writing would have been wrong rather than a state where it gave
   up. `--bump` is the same increment with no git in it, and is what `refresh.py` calls, so only one
   piece of code knows how to move `V`.
   That covers one commit. `--base REF` in CI covers the branch, because one commit is not enough
   information: two PRs off one base each bumped `v32` -> `v33` byte-identically and merged to a net
   delta of zero (#32), which looks correct from either side alone.

2. **`sw.js`'s `BOOT` must list every script the page dies without.** Every pixel here is drawn by
   JS, so a cached `index.html` without `d3.v7.min.js` or `composers.json` is a headline over an
   empty box; the offline page is strictly better, and one online launch repairs the precache. A
   new load-bearing script goes into `SHELL`, into `BOOT`, and bumps `V`. `readership.json` is the
   one deliberate exception — SHELL but not BOOT — because the sparkline is the only thing here
   nothing waits for: gating a navigation on it would trade a working page for an offline notice
   over a decoration.

3. **Colors read into JS can't be reached by a CSS variable swap.** `chart.js` bakes `--c-*` into
   SVG fills and `app.js` into the legend. Both re-read through `Theme.getCssColor` inside
   `rerender()`, which `Theme.subscribe` fires on every theme change — never `getComputedStyle`
   directly. A fourth component that bakes a colour needs a fourth `rerender()` wired in there.

4. **`composers.json` and `readership.json` are generated; never hand-edit them.**
   `scrape_list.py` -> `fetch_wikidata.py` -> `fetch_views.py` -> `build_data.py`, each caching
   into `data/`. Only the first three touch the network, so a rebuild is offline and reproducible.
   `data/pageviews.json` stores each series as a FLAT ARRAY aligned to its `months` axis — a
   quarter of the bytes of `{month: count}` and one changed line per composer per top-up. Alignment
   is load-bearing: an array one element short shifts every month by one and the numbers stay
   plausible, so `build_data.py` and `validate.py` both refuse a ragged one.
   The three states are distinct. `null` means "asked, nothing there" — or, at the month of a move,
   "asked, and the answer belongs to neither title" (invariant 15). A MISSING month means "never
   asked". A title that did not ANSWER is DROPPED rather than written, because the flatten fills
   every month on the axis and writing it would null-pad the months it never answered for and read
   as complete forever. One failure never aborts the run: that would discard the other eight
   hundred-odd good fetches.
   **Every title is fetched over the whole AXIS, never over `--months`.** A flat array has no third
   value, so the file holds exactly one asked window; a narrower fetch writes nulls for months
   nobody asked about, and `--months 24` on a newly added composer would bury nine years of history
   permanently. `--months` narrows what counts as STALE, never what gets asked for. And a month IN
   PROGRESS is not a month — the API returns the days so far with nothing to say so — so
   `months_back()` ends at the last COMPLETE month and `--end` is refused past it.
   The last stage writes BOTH shipped files from one set of caches and they must stay in lockstep:
   `validate.py`'s `check_history()` recomputes each row's median, min and max from that composer's
   own sparkline and fails when they disagree. Two internally consistent files built from different
   fetches is a drift nothing in the app can see — the panel would print one readership and draw
   another. `build_data.py` carries the canonical title in a list PARALLEL to the rows and reorders
   both together rather than in a {name: canonical} map: `QUALIFIER` strips the disambiguator, so
   "John Adams (composer)" and a bare "John Adams" collapse to one key and the second silently
   wins, handing one composer the other's decade of history. It also refuses to write either file
   when two rows print the same name, which `readership.json` is keyed by.
   Composer NAMES are canonical Wikipedia titles and change spelling when the pipeline runs, so
   anything hardcoding one (`make-og-svg.py`'s `LABELS`, a test assertion) must use the canonical
   form.

5. **Never ask the pageviews API for an unresolved title.** Views are counted per title, a redirect
   is its own title with its own tiny count, and the request succeeds either way — Bartók returned
   41 instead of 14,330. Resolve the DISAMBIGUATED title too: a bare "John Adams" resolves to the
   second President of the United States, whose views outranked Beethoven here. Asking the right
   title is half of it; invariant 15 is the other half.

6. **Wikidata claim RANK is not metadata.** A known-wrong value is marked `deprecated` rather than
   deleted, so reading `claims[0]` reported Tania León — alive, Pulitzer 2021 — as dead since 1996.
   `year_of()` drops deprecated, prefers `preferred`, and ignores novalue/somevalue snaks.

7. **The Fame view is the default, and the only place the app hardcodes composer NAMES.**
   `CANON` (the REPERTOIRE — the composers a quartet actually plays, in birth order),
   `OUTLIERS` and `WOMEN_CANON` (shown only under the Women filter) in `chart.js` hold canonical
   Wikipedia titles, which change spelling when the pipeline runs (invariant 4). `Chart.missingNames()` reports any that stop resolving and the UI suite asserts
   it empty, so a rename fails loudly instead of dropping a composer out of the argument the view
   is making — and it checks EVERY list, or a rename inside `WOMEN_CANON` would sit unreported
   until somebody pressed the pill. `names.js`'s `SURNAME` map carries the same contract through
   `Names.staleOverrides()`. Adding a name means adding it to the list, not to a comment.
   The gender pills are a third such vocabulary: `index.html` names the values the UI can filter,
   `app.js` reads its URL whitelist off the pills, and a stated P21 label no pill reaches fails
   both `validate.py` and `unfilterableGenders()` — that composer is in NEITHER filter while the
   footnote counts only the ones with no claim at all. `REPERTOIRES` is keyed by those same pill
   values, so a curated list keyed to a pill that does not exist can never be shown while looking
   maintained; `unreachableRepertoires()` fails on it.

8. **Each view encodes different things, so each needs its own key.** In Fame, size is the y AXIS
   and hue is emphasis, so the lifespan ramp and the size key would label channels that carry
   nothing: `renderLegend()` branches on the mode and `setMode()` re-renders the legend and the
   table (row chips are painted from `Chart.colorOf`, which follows the view). The ring's meaning
   also changes under a filter, and the key no longer captions it — the wrong-channel failure is
   prevented by having no words to get wrong rather than by keeping two of them correct.

9. **Readership is a measure, not a tally — round it everywhere except the table.** It is the
   median of the last TWELVE monthly page-view counts (`STAT_MONTHS` in `build_data.py`): up to
   twelve strictly, since a null is dropped and a composer whose article moved inside the window
   has one fewer (invariant 15). Not however many months
   `data/pageviews.json` happens to cache. Widening that window would resize every dot on the chart
   and bake a 2016 readership into a 2026 picture.
   Any one month runs ~12% off typical, so the detail panel states two significant figures floored
   plus a "+" (`twoSig`/`atLeast` in `app.js`), formatted through `Histogram.fmt` so the brush
   readout and the panel agree. A new place that prints a view count almost certainly wants
   `atLeast()`. Two exceptions, both deliberate: the table keeps the exact number because it sorts
   on that column, and the SPARKLINE prints exact counts because a month on that line is a raw
   tally and rounding the figure somebody hovered to read defeats the hovering.

10. **`null` means unknown and must stay null.** `quartets: null` (the page's prose states no
   count), `death: null` (living) and `gender: null` (no P21 claim) are facts, not gaps. Null
   quartets are in the table and excluded from the chart by `plottable()`; null death means the
   lifespan ramp does not apply and the dot is drawn open; null gender is in NEITHER the Women nor
   the Men filter, because "Women" means Wikidata says female, not "everyone we didn't call a man".
   A default puts a fabricated dot on the chart. Gender is the one field where the tempting default
   is a guess about a PERSON — never infer it from a name or a pronoun; an unmapped P21 value ships
   as its raw QID and `validate.py` fails on it.

11. **Grade the parser against the PAGE, not against 2014.** `scripts/audit_counts.py` samples
   parsed counts beside their source sentence for a human to grade; that is the real measure.
   `compare_2014.py` is useful for row matching (birth years agree 98.2%) but its count column is
   misleading — the page has been rewritten over twelve years, so disagreement is usually the
   parser being right.

12. **The 2014 page views are not comparable to modern ones** and must never be plotted alongside
   them: the API has no per-article data before 2015-07, so they came from a different measurement
   system. Archived for provenance only.

13. **Search folds the characters NFD cannot decompose, before NFD** — `ł`, `ø`, `ß` and the rest
   of `FOLD` in `table.js`. They have no Unicode decomposition, so NFD alone leaves them intact and
   "lutoslawski" misses "Lutosławski". A name that needs a new one means a new `FOLD` entry, and the
   suite types a folded query so the RULE is what is checked rather than the table: a transcription
   of `FOLD` in here was pinned three ways while the call site that uses it was pinned nowhere, and
   deleting the `.replace()` left every check green.

14. **`scripts/make-og-svg.py` duplicates chart.js's scales on purpose.** Same log domains, same
   jitter (`spread_jq()` there, `spreadJq()` here — ranked by readership within a quartet count, so
   a top-up can move it), same emphasis, the same two uniform radii (readership is the y AXIS here,
   so there is no radius scale), and the same short-name rule from `names.js`. It renders the Fame
   view AT REST, which is what a bare URL opens on, so no derived ring and no second repertoire
   ever reaches it. Change an encoding in `chart.js` and change it there too, or the share card
   stops matching the page. Duplicated rather than shared because the app must not ship a build
   step and the card must not ship a JS runtime.

15. **A canonical title is only canonical TODAY, so a page MOVE is a hole in the series.** The API
   counts the string requested, so every month before a move was counted under the name the article
   held then and asking the current one returns the redirect traffic nobody followed. Fanny
   Hensel's article sat at "Fanny Mendelssohn" until March 2026 and shipped a median of **500**
   against a real 5,217 — and the app NARRATED the artefact, because 5,198 against a 95th
   percentile of 149 fires `SPIKE` at 34.9x and captions a rename as an obituary.
   `scripts/pagemoves.py` is the one place that rule lives, in three deliberately separate parts.
   `step()`/`suspects()` are offline and only generate suspects, because the shape has no clean
   threshold — real moves here run 9x to 1163x and genuine growth reaches 8x. `find_moves()` reads
   the MediaWiki move log, which STATES the old title and the date. `confirm()` throws out the hops
   the numbers do not support, because **the log records events, not tenures**: a move reverted
   twenty minutes later leaves the same two entries a permanent one does, and a chain walked from
   the log alone put Roberto Gerhard at a title he never occupied. The test is that traffic CHANGES
   HANDS across the move — old-against-new before, over old-against-new after.
   **The month of the move itself is null.** A move happens on a day, so either title alone is a
   partial month and the sum quietly adds the redirect share every other month excludes — for an
   ASCII-to-diacritic rename that share is large enough to invent a peak (Takemitsu's 2020-10 came
   out 53% over its neighbours), and invariant 9 is why that matters: the sparkline prints exact
   counts on hover. `null` already means "no answer to give", already breaks the path, and is
   already dropped from the median.
   **The repair is not a migration that happens once.** A refetch overwrites the stitched series
   with the API's per-title answer, so `fetch_views.py` re-applies every recorded move on every run
   that touches the title, and `data/pageviews.json`'s `moves` block records what it did — an EMPTY
   list meaning "the log was asked and said none", which is what stops a no-op run re-investigating
   the same noisy articles and how `validate.py` tells genuine growth from a rename nobody has
   checked. **A chain on record is trusted, never re-derived**, and nothing records an answer it
   does not have: a log that could not be READ and a source that did not ANSWER both leave the
   series and the record exactly as they were, and the gate then fails on a recorded move whose
   stitch is missing. Re-confirming gave a good record a way back out — one 404 on a redirect and
   Fanny reads 500 again with `moves` agreeing nothing is wrong — so a chain only ever goes from
   non-empty to empty by a human editing the file.
   Twelve articles in this roster moved; only Fanny's moved inside the twelve-month statistic
   window, so the other eleven changed the sparkline and not one dot.
   **Do not sum redirects generally.** That is a different policy, measured and rejected:
   `audit_redirects.py` priced every redirect into every article and the median correction was 1.02x,
  invisible on
   a five-decade log axis, in exchange for a count that depends on how many aliases an article
   happened to accumulate. A move is not an alias; the article LIVED there.

## Testing

**The ethos, measured.** A mutation run in Sep 2026 — 39 plausible one-line bugs injected into
source, suites run, tree restored — caught 25. The data gate caught 6 of 7, five of them failure
modes this repo has never had; the browser suite caught 13 of 22; `sw.test.mjs` caught 1 of 5.
Every miss was a pure function or an untested entry point, and not one was a layout or interaction
bug. Four rules come out of that, and they decide what gets written here from now on:

**Budget checks by how silent the failure is, not by how much code there is.** A chart bug is
visible the moment you open the page; a precache bug is visible only on somebody else's installed
client, a month later. Coverage should run the other way round from file size, and today it does
not: the 588 lines of `sw.js` are exercised through one of five entry points.

**A check may not read its expectation out of the code under test.** `sw.test.mjs` reads `BOOT`
from `sw.js` and `fetch_views.test.py` derives its window from `months_back()` — both to stop a
copy drifting, and both unfalsifiable for exactly the value they are named after. Where anti-drift
pushes you there, cross-check two independent artifacts instead (`BOOT` against `index.html`'s
script tags, a date function against a frozen clock).

**Prefer a positive assertion.** `!panel.includes(exact)` passes when the formatting differs, not
only when the rounding is right. Assert the shape you want, not the absence of one you don't.

**A number the repo can compute does not belong in prose at all.** Pinning one with a lint is the
wrong branch of the built-or-cut rule, and it was taken: thirteen claims across two docs, eleven of
which bought a reader nothing, kept honest by 300 lines that could not tell a reflowed paragraph
from a stale fact. The same mistake as `reserveLede()`, which built a `ResizeObserver` to manage a
sentence that should not have existed. When a claim is about behaviour, test the behaviour; when it
is a count, read it off the thing that holds it.

And the growth rule: **a check earns its place by failing without the code it covers, and keeps it
by being the only one that does.** `ablate.py` enforces the first half on every branch. The second
half is why deletions are welcome — re-run the suite without a check, and if nothing else noticed,
it was never the thing holding that property up.

One entry per bullet below: the checks that run offline, the one that needs a browser, the pair of
branch gates only CI can run, the monthly top-up, and the two audits a human grades. No test
framework, and nothing to install:

- `node scripts/sw.test.mjs` — the fetch handler under mocked SW globals: cache-first, lie-fi
  bounds, offline fallbacks. It drives the `fetch` listener only; install, activate, `cachePut`'s
  SHELL refusal and `cacheLookup`'s version scoping are unexercised, which is where its 1-of-5
  came from.
- `python3 scripts/sw-lint.py` — the precache contract (invariant 1). Five of its six checks read
  one commit; the sixth, `--base REF`, reads two and takes the other as an argument, so CI runs it
  on pull requests against the base sha. `python3 scripts/sw-lint.test.py` covers the two halves a
  reader cannot check by eye, in cases that each build a throwaway repo with real branches: the `--base` failure (#32), which looks correct from either side alone, and `--fix`,
  which WRITES — so its cases assert the staged result, and five of them also pin the three
  declines, the states where writing would be wrong. It is a vendored pwa-starter file; keep the
  stamp current.
- `python3 scripts/validate.py` — **the data gate**, and the most important thing here. Every
  serious defect this dataset has had was a plausible-looking wrong number no test caught, so this
  compares `composers.json` against its schema, the other caches, `readership.json` and the
  previous commit. Run it after every pipeline run. `scripts/validate.test.py` proves it still
  catches each past incident; weaken a check and it goes red.
- `scripts/ui-test.sh` — the behavioural suite, against a real Chrome over CDP. **Its size is not
  stated here: run it and read the total it prints.** Its own header documents the harness; three
  rules matter before you add to it. **Every wait is a poll, not a budget** (#48) — `settle()`
  re-asks the page for the state the next check reads, and the only fixed wait is `TWEEN`, used
  solely before a "nothing moved" assertion, which has no signal to poll for. **A POINTER is a
  platform fact and cannot be emulated** (#50): `Emulation.setEmulatedMedia` accepts `hover` and
  `pointer` and silently ignores them, so the suite runs the full Chrome under **Xvfb** — never
  `chrome-headless-shell`, which reports no pointer even under a display — and section 2 asserts
  which pointer it got rather than leaving eight later checks to imply it. **No check reads a PIXEL,
  deliberately**: the DOM is the better oracle, and a baseline would go red for two reasons that are
  not bugs — `system-ui` resolves to a different face per platform (#53) and `refresh.py` moves
  every dot monthly by design. The PNGs are evidence for whoever reads a failure, which is why a
  failing run keeps them. `REQUIRE_BROWSER=1` turns the no-Chromium skip and both pointer warnings
  into failures, because a runner that quietly lost its Chrome would otherwise go green having
  tested nothing.
- `python3 scripts/og-lint.py` — the link preview. The card-SIZE half is hook-only (it reads
  `git diff --cached`); the meta-length and stated-count halves read the working tree and run in
  CI, so "og:description is too long" is caught before a deploy rather than by pasting the live URL
  into a validator afterwards. `check_counts()` knows both live totals and requires a stated count
  to be one of them, because "884 quartet composers" and "790 quartet composers" are both
  grammatical — and this is the one place a count is worth holding, because these strings SHIP to
  readers. It pins per FILE where the file settles the question: `manifest.json` holds exactly one
  description and describes what the app DRAWS, so it may state only the plottable total. The two descriptions
  in `index.html` are deliberately different lengths — a SERP snippet wants 120-160, a phone link
  preview truncates near 125 — and re-unifying them fails the lint. `check_card_axis()` refuses a
  card labelling a readership its own axis does not contain: `logscale()` clamps, so a tick under
  the floor is painted on the bottom edge with the wrong number beside it rather than dropped.
- `python3 scripts/pagemoves.test.py` — the page-move rule (invariant 15), offline: `step`,
  `tenures`, `confirm` and `stitch` are pure and `find_moves`'s walk runs against a stubbed log. It
  exists because every defect that module has had is one the pipeline cannot show you — a dropped
  middle hop double-counting a month, a complete chain thrown away as truncated, a reverted move
  read as permanent. None crashes, none moves a number by an order of magnitude, and
  the chains this roster ships happen to miss all three.
- `python3 scripts/fetch_views.test.py` — the page-view cache's invariants, `fetch` stubbed and the
  cache in a temp file. It exists because the flat array has only two values and **every bug in
  that file has been a null no request justified** — invisible afterwards, because the array is the
  right length and every number in it is plausible, and the only symptom is that `todo` quietly
  stops asking. Some of its cases stub the move log and cover invariant 15: that a move is stitched and
  its month nulled, that the stitch is re-applied on every refetch, that a chain on record is not
  re-judged, that a logged move the traffic does not support is recorded and NOT stitched, that a
  source which does not answer leaves both series and record alone, that a log which could not be
  READ is not written down as "no move", and that a record collapsing to nothing is not written
  down either.
- `scripts/refresh.py` — not a test but the same discipline: it decides whether a top-up is DUE
  (does `composers.json` already cover the last complete month?), runs the three pipeline stages,
  refuses to bump `V` if `validate.py` fails, and is a pure no-op otherwise.
  `.github/workflows/refresh.yml` runs it monthly and opens a PR. A PR opened with the built-in
  `GITHUB_TOKEN` does not trigger `checks.yml`, which is why refresh.py runs the gate itself — the
  gate must not be skippable because a robot opened the PR.
- `python3 scripts/fix-lint.py --base REF` and `python3 scripts/ablate.py --base REF` — **the two
  branch gates**, and the answer to why simple changes were taking six rounds of review. Both read
  two commits, so like `sw-lint.py --base` they are pull-request only. `fix-lint` notices a branch
  that changed source and touched no test. `ablate` has the teeth: it reverts the branch's SOURCE
  hunks to the base, keeps its TEST hunks, runs the suites `COVERS` maps to the changed files, and
  requires a NAMED check to go red — a test that still passes without the code it is meant to prove
  does not prove it, which is how PR #23 ran six rounds, four of them fixing a defect in the
  previous round's fix, every one shipped on a green suite. A named `FAIL` rather than a nonzero
  exit, because an ablated tree can die on import while proving nothing (INCONCLUSIVE, which also
  fails). It refuses a dirty tree, because restoring means `git checkout HEAD --`. `--with-ui` adds
  the browser suite and the `gates` job passes it, so a UI branch is ablated by CI rather than told
  its ablation is owed locally. One `No-test: <reason>` trailer on any commit in the range skips
  both, so an untested source change is a sentence somebody wrote on purpose and a reviewer can
  read, not a silence. `scripts/fix-lint.test.py` covers both in throwaway repos with real
  branches.
- `scripts/audit_counts.py` and `scripts/audit_redirects.py` — not automated, and not automatable:
  the first prints parsed quartet counts beside the sentence they came from so a human can grade
  them (run it after touching `scrape_list.py`), and the second answers a POLICY question by
  pricing every redirect into every article to report what summing them would change — the evidence
  behind invariant 15's refusal to. `--limit N` audits the N most-read instead of all 884.

Everything that needs neither a browser nor a network runs in CI, and since #56 so does the browser
suite — `checks.yml` has a `ui` job, with `xvfb-run` and node 22 (the whole CDP client is the global
`WebSocket`). Still run `ui-test.sh` by hand after touching `chart.js`, `table.js` or `styles.css`:
it is faster than a push, and a UI change is one you want to LOOK at. The prize of a browser on the
runner is bigger than the suite, because `ablate.py --with-ui` runs there too — a branch whose
source is the page is finally ablated by something other than a human remembering to.

## Design artifacts

`mocks/` holds the artboards a design decision was made from — currently the canvas that chose the
Fame view over two alternatives, drawn from `composers.json` by `mocks/gen.py`, which duplicates
chart.js's scales for the reason `make-og-svg.py` does. Nothing there ships and nothing there
follows a change to `chart.js`: it is a record of a decision, not a second implementation of one.

## Conventions

- Vendored pwa-starter files carry `pwa-starter: <file> @ <sha>` near the top. Keep the stamp when
  editing them; it is how `check-downstream.py` upstream finds this repo.
- Comments explain *why*, and especially what breaks otherwise. Don't narrate the next line, and
  don't recount how a bug was found — that is TODO.md's job.
- **A comment may not assert a mechanical fact about the code beside it — that becomes a check, or
  it goes.** A comment cannot go red, so "Keyed by side" over a `.data([-1, 1])` that joins by index
  (#42) was correct when written and wrong for a year. `Chart.missingNames()`,
  `Names.staleOverrides()`, `unfilterableGenders()` and `unreachableRepertoires()` each turn such a
  claim into something a suite asserts, and `prose-lint.py` does it for the docs. A claim about a
  join key, a count, a list or a threshold gets pinned or gets written loosely enough to stay true.
  A comment about WHY is never in this category, which is most of them.
- **A fix ships with the test that goes red without it.** Run it against the tree WITHOUT the fix
  and watch it fail before proposing it; `ablate.py` enforces this, but the discipline is the point.
  PR #23 ran six rounds, four of them fixing a defect in the previous round's fix, every one on a
  green suite. When there is genuinely nothing to assert, say so in a `No-test:` trailer.
- **One filter row, above everything it scopes.** `#filters` is a sibling of `.grid`, not a child of
  either card: all three filters scope both views, and a filter drawn inside one card says
  otherwise. `placeFilters()` moves it into `#viz` in full screen, where the chart is everything.
- **The chart's controls sit ABOVE the plot, because the plot's height is a function of the VIEW.**
  `measure()` gives each mode its own aspect ratio (0.98 for Fame, 0.82 for the timeline on a phone,
  0.44 for the swarm), so a row underneath moves when you press it — 61px on a phone, 150px at 1280,
  lifting the pill out from under a second tap at the same spot. **Nothing a finger rests on may be
  placed by a box the same press resizes.** Full screen is the exception and stays underneath:
  `#plot` is `flex:1` there, sized by the viewport rather than the view, so there is nothing to
  absorb. Above the plot costs 94px of a phone's first screen (#29), and `placeDetail()`'s phone
  anchor moved with the row — it inserts before `.legend`, or the panel lands above the chart.
- **No filter control appears or disappears at all.** The rule above, satisfied by construction one
  row up: #31 fixed the brush's own Clear button in place twice, #35 deleted the category instead.
  One permanent `Reset filters` sits in `.controls` beside `Reset zoom`, clears all three filters,
  and is `disabled` at rest and accent-filled when live — a state change that moves no box, which is
  why `applyFilters()` may light it on the drag's first frame, above the `settled` guard. Being the
  page's one answer to "is anything filtered?" is why `anyFilter()` reads the query TRIMMED, the way
  `Table.matches()` does: a lone space filters nothing, and the button lit over an unchanged
  `#count` answers its own question wrong. It does not focus the search box, though `#clear` does —
  this one is a card below the row, where `focus()` scrolls the viewport back up and opens the
  keyboard over a box the reader had left. Note for the next layout fix here: the row never wrapped
  (below 640px `#hist` is `flex:1 0 100%`, so the lines are pinned by `order`, not width), and an ID
  selector out-specifies `.btn`, which is how that button sat 12px under the touch floor unseen.
- **The table and the chart show short names; the detail panel shows the full title.** `names.js` is
  the only place that takes a canonical Wikipedia name apart, and it is a heuristic — see `SURNAME`
  there. BOTH forms come from one shared-surname map, so the two can never disagree about who needs
  more than a surname: `filed()` gives the table "Haydn, Joseph" (a column that sorts on the string
  it prints), `short()` gives the chart "M. Haydn" (a label that has to fit beside its dot), and a
  surname shared by two people whose initials also match falls through to the full name — Ferdinand
  and Félicien David. The panel, the hover flag and the row's `title` keep the canonical title,
  where recognising the person is the job.
  **One exception, in the chart form only: a surname only one composer is READ for prints bare.**
  "Haydn" is Joseph and "Tchaikovsky" is Pyotr Ilyich on any programme; the initial is what Michael
  and Boris need. `DOMINANT_VIEWS` in `names.js` is the test and it has to stay decisive — the most-read
  member takes it only if nobody in the group ties them, or two dots get the same label. Not in
  `filed()`: the table sorts on what it prints, and a bare "Haydn" beside "Haydn, Michael" is
  inconsistent about who gets a forename. This is why `Names.setData()` takes readership alongside
  the names, as a PARALLEL array for the reason `build_data.py` carries canonical titles in one.
- **The phone table has to fit in a font you do not choose.** `system-ui` is SF on a Mac, Segoe on
  Windows, DejaVu on most Linux — wide enough that the four phone columns overflowed 390px outright
  (#53). Two things were paying width for nothing: a header WORD wider than any value beneath it
  (`short` in `COLS`) and the cell gutters. **An abbreviation is not free to a reader who can SEE
  it**: the accessible name must contain the drawn label (WCAG 2.5.3), or a voice-control user says
  "click Qts" against a name that reads "Quartets" and cannot sort the column at all. So both spans
  stay in the name, the drawn one first, and the word moves off screen rather than `display:none`.
  The suite asserts the name the browser COMPUTES, because an `aria-label` added later would
  override the markup while a check written against the two spans stayed green. Measure a new column
  at 390 AND 360 — at 360, the common Android width, the old table overflowed in every face
  including SF, so the 390 check was passing on the one width where the narrowest font clears.
- **A number printed beside the chart counts the PLOTTABLE rows.** The empty panel said "884
  composers, born 1582–1989" next to an x axis starting at 1709: the rows with no stated quartet
  count are in the table only, and the roster's three earliest births are among them. `Chart.plottedStats()` is
  the one place that answers "what can the chart place", so the count, the birth span and the living
  count cannot disagree with each other or with `plottable()`. The same split governs the app's
  stated claims — `manifest.json` and the link preview describe what the page DRAWS, while
  `#count`, the search placeholder and the provenance line count every row the table holds, which is
  more. `og-lint.py` holds those shipped strings to a total the data supports.
  They answer different questions, and the provenance line is where the difference is named.
- **Prose the app can FALSIFY is built or cut; only prose it cannot is typed — and CUT is the first
  branch to try.** #24 found the case with no number in it: "across is how many quartets they wrote,
  up is how much their article is read" was true in Fame only, and was cut rather than derived per
  mode, because the axis titles and the per-mode `HINTS` already say it.
  #35 applied the same test to the BUILT half and it failed too. A lede generated from
  `Chart.emphasisStats()` was correct at every instant, and what it cost was the machinery a claim
  that can change LENGTH needs: it emptied outside Fame, so the paragraph collapsed and everything
  below it rose 40px, lifting the pill you had just pressed (#27). All of that machinery is gone and
  the lede is one static line. Two of its claims survive in the components that own them, the legend
  and the axis titles, and `ui.test.mjs` 4m checks those rather than the sentence, so cutting prose
  cannot quietly cut information.
  **The lesson is the ordering**: before building a mechanism to make prose behave, ask whether the
  prose should exist. `#count`, the search placeholder and `setProv()` stay built because each is
  the only statement of what it says, and none of them can empty.
- **The provenance line is built, not assigned.** `setProv()` linkifies every Wikidata property id
  it prints (`P569` -> its definition page), because an id is jargon a reader cannot check from the
  page. It links the TEXT rather than storing anchors in `composers.json`, which is data and carries
  no markup, so a new property is linked the moment it is printed. Setting `textContent` directly
  again would silently drop every link.
- **`.seg` is a look, not a behaviour.** Two pill groups wear it, so anything binding `.seg button`
  must scope itself (`.controls .seg button`). Unscoped, the view switcher's handler landed on the
  gender pills and a press called `setMode(undefined)`.
- **`names.js` loads before `chart.js` and `table.js`, and `Names.setData()` runs before either gets
  data.** The short form of a name is a function of the WHOLE roster, so no module can display a
  name until the roster has been counted. SHELL and BOOT dep like every other load-bearing script.
- `index.html` owns structure, `styles.css` owns looks, `app.js` owns boot and shared state (which
  composer is selected, which filters are active). `chart.js`, `table.js` and `histogram.js` never
  talk to each other — they share `names.js` and `Chart.colorOf`, read-only lookups, not state. The
  filters compose in `applyFilters()`, where each source returns "a Set of indices, or null for
  everything" and they are intersected. The gender filter has no module of its own
  (`genderMatches()`): three buttons and a string, nothing to render and no data to hold. A fourth
  filter that DOES draw something belongs in its own file, on the same contract.
- **Share and Full screen are icons ON the chart wherever the controls row will not hold them on
  one line, and that is what PAYS for the third button in the row.** `.controls` is already two
  lines at 390 and a third word button takes it to three; icons in the row still wrap at 360. So
  `placeChartTools()` reparents `#chart-tools` into `#plot` — one element moved, like
  `placeFilters()` and `placeDetail()`, never a second copy, because `#fs` holds the pressed state
  and `share()` a timeout on its own label. `#plot` is already `position:relative`, already hosts
  `#flag`, and d3-zoom binds to the `svg` rather than to `#plot`, so the buttons take taps without
  eating a pan. chart.js's rebuild must remove the svg it made BY REFERENCE — `selectAll("svg")` is
  a descendant query and matched the `.ico` glyphs too.
  **The condition is a MEASUREMENT of the row rather than a device, and it is TWO intervals**,
  because the card is not monotonic in the viewport: the `(min-width:900px)` grid takes 194px off
  it, so the row fits the words in two bands and not in the two between them. Hence `NARROW` and
  `SQUEEZED` in `iconsOnPlot()`, where a single `max-width:1100px` spent DATA height for no page
  height across a 120px band — and both edges err toward ICONS, because the mistakes are not equal:
  words that do not fit means a PRESS wraps the row and drops the plot 44px under the cursor that
  just pressed it, while icons where words would have fitted costs 26px and nothing else.
  `SQUEEZED` is skipped under `.fs`, where `body.fs .grid` is `display:block` and the row has its
  widest geometry back; the band costs more there, off a `flex:1` chart that is the whole viewport.
  Those widths are one machine's font metrics, so they are defended by checks rather than by
  arithmetic — the suite presses Share at the first width in each band and fails if the row grows.
  **`app.js` holds the only copy of the breakpoint**: `styles.css` scopes the icon look to
  `#plot > #chart-tools` so the look follows the DOM, and `chart.js` is TOLD through
  `Chart.setTopReserve()`. In a width query the two could disagree, and every state where
  `placeChartTools()` had not run drew the icon look in the row — a cold boot, and permanently on
  `start()`'s error path, which bails before the move.
  **A wheel over the glyphs is a wheel over the CHART, and that needs saying in code**, because the
  group is a SIBLING of the svg the zoom is bound to: the corner was dead and the page scrolled, two
  pixels from a spot in the same band that zooms. `Chart.wheelInto()` re-dispatches into the CURRENT
  svg (a captured node is the `selectAll("svg")` trap again) and `app.js` forwards only while the
  group is on the plot, since in the row a wheel should move the page. The DRAG is deliberately not
  forwarded — `pointerdown` into the zoom would start a gesture on every press, and a control
  swallowing a drag is the platform convention while swallowing a wheel is not.
  Four things a change here must keep: the words stay in the DOM, visually hidden rather than
  `display:none`, because they are the accessible NAMES; the label is written into that `.btn-t` span
  and never onto the button, which would delete the icon; the print rule names `#chart-tools`
  separately from `.controls`, since on a phone it is not inside it; and they sit in the AXIS-TITLE
  BAND, over no dot in any view.
  That band is measured, not chosen. Every corner covers something — the least bad was 3 dots, and
  **top right is the trap**: it reads as empty in Fame and is exactly where the swarm piles up, 90
  dots and the "Rachmaninoff" label. The band costs DATA height and no page height, because the
  plot's outer box follows the aspect ratio. Its height is set so the invisible 40px target stays
  CLEAR of the plot area, or a dot it overlaps silently stops being TAPPABLE — one pixel short of
  that it shadowed 12 dots in the swarm. The glyphs are centred on the axis title's LINE rather than
  its baseline, because a glyph beside smaller text carries more visual mass below its own middle;
  the offsets are derived from the title's own box and the suite measures them against that box, so a
  change of font, size or of chart.js's `y:-8` fails instead of drifting. **Clearing the plot area is
  not clearing every pixel a dot can occupy**: the dot clip is inset OUTWARD by one maximum radius,
  so under a pinch the sliver of an edge dot reaches under the target. Its CENTRE cannot, because the
  frame test only draws a dot whose centre is inside the plot rect — so a finger aiming at a dot
  still lands on it, which is the guarantee, one step weaker than the resting one. Shortening the
  target would put it under the 40px floor #31 was fought over.
  They are BARE GLYPHS — a small mark in an invisible 40px target, no border, no background,
  `var(--muted)` like the axis title beside them: the platform shape for a control sitting on
  content, where a pill's worth of chrome around a small mark reads as furniture. The target is felt
  and not seen, so the suite taps in from a CORNER rather than at the centre, which would pass on a
  button the size of the glyph. The 40px is stated with the overlay rather than inherited from the
  touch-target rule, which asks a different question (`(hover:none) and (pointer:coarse)`) that a
  narrow desktop window answers no to, taking `.btn`'s 36px. And `#plot svg{ width:100% }` means THE
  CHART: as a descendant selector it caught the icons and stretched the glyph to nearly fill its
  button, so both rules are `> svg` now and `.ico` carries its own `width`/`flex:none` — a width
  ATTRIBUTE loses to any stylesheet. Every bug in this group hid in a layout the developer's machine
  could not draw, which is why the suite enters all of them: a narrow window with a real pointer, a
  laptop, a wide window, and the boundary.
  Two consequences reach `app.js`. Under the breakpoint `.btn-t` is the accessible NAME and not the
  face, so `share()`'s "Link copied" swap wrote the confirmation where nobody could see it; the glyph
  acknowledges too (`.copied`) off the same one call, and both are raced against `STALL`, because a
  clipboard write that never SETTLES is not a rejection and the catch beside it can never fire. And a
  clipped label is a name a screen reader can read and a pointer cannot, so both buttons carry a
  `title` written by `label()` with the span in one call — `#fs`'s name changes with its state, and a
  tooltip still reading "Full screen" over the exit glyph would be worse than none.
- **The readership brush's handles are crossfilter's grips, and the rect underneath is the hit
  area.** d3-brush's `.handle` is `handleSize` wide by the extent PLUS `handleSize` tall, so
  painting it drew a 20x62 slab of accent above the bars and down through the tick labels — the hit
  area wearing the costume of the control (#40). The fix was a DELETION: d3-brush sets `fill:none`
  and `pointer-events:all` on the brush `<g>` and both inherit, so this stylesheet was the only
  thing painting it. `histogram.js` draws the visible tab instead, the same felt-not-seen split the
  chart's icons use. The load-bearing line is `pointer-events="none"` on the grips group: it sits on
  top of the brush and outside it, so a hittable grip swallows the press and the drag does nothing.
  That is an ATTRIBUTE, so a later `#hist .grips path{ pointer-events: … }` would silently outrank
  it — the same specificity trap as `#hist-clear` and the chart-tools glyphs.
- **The `hidden` ATTRIBUTE is only `display:none` in the UA sheet**, so ANY author `display` on the
  same element beats it — silently, since the element stays hidden to a screen reader and to
  `.hidden` in JS while being drawn. Giving `.btn` a `display` for its icon did exactly that: the
  search box's × came back at rest, wrapped the search row, and the page ran 50px tall until you
  filtered. `styles.css` answers it once with `[hidden]{ display:none !important }`, and the suite
  notices if that line is dropped or out-specified.
- **There is ONE detail panel, and `placeDetail()` moves it.** Beside the chart above 900px; inside
  `#viz` (`.compact`) on a phone and in full screen at any width, because the grid column is a
  screen-height away there and `display:none` in full screen. Never render a second compact copy —
  the selection, the nav buttons and the `.on` state all assume one element. The two in-card
  positions differ on purpose: BELOW the plot on a phone, free to grow because nothing above it
  moves, and ABOVE the plot in full screen as a fixed-height strip drawn even when empty. **Its
  height must stay constant** there, because `#plot` is `flex:1` and a box that grew on select would
  trip the ResizeObserver and re-lay out the chart under the finger that just tapped it. `tight()`
  trims the content to fit.
- **A hover previews into the detail panel, so its box is reserved wherever a pointer exists.**
  `@media (hover:hover) and (pointer:fine)` gives `.compact` a `min-height` covering its TALLEST
  state (pinned, with the nav row) and ellipsizes the name; without it, moving the mouse across the
  chart pumps the legend up and down. Touch screens get neither rule — no hover to churn, and the
  space is the chart's. The reservation is MEASURED: the suite prints the pinned panel's real height
  beside the "pinning does not shove it either" check and fails when `min-height` falls short, which
  is how adding the sparkline was caught at 267px against 262. It pins the composer with the LONGEST
  caption, because the reservation has to cover the worst case and the dot an earlier check happens
  to hover is not it.
- **The sparkline's caption names the spike if there is one and the trend otherwise.** A fixed "peak
  N× typical" was the wrong sentence for most of the roster: the median composer's biggest month is
  3.1× their typical one, because a composer read thirty times a month hits ninety by chance, so it
  cried spike about noise on half the list — and it buried the real story for the steady ones, where
  Haydn's meaningless 1.7× peak displaced a line that has slid 42% since 2015. `SPIKE` tests the
  peak against the 95th PERCENTILE of that composer's own months, which is scale-free and judges a
  small noisy article against its own noise; at 3× it fires on 18% of the roster and selects almost
  entirely obituaries. The peak hairline is drawn ONLY in the spike branch — an annotation pointing
  at a month nothing mentions has no referent.
- **The sparkline is the app's one optional part, in both halves.** Its data (`readership.json`,
  an order of magnitude larger than the roster) is precached but not a BOOT dep and is fetched after the
  paint; `sparkline()` returns null when it has not arrived, when a composer has fewer than two
  months of data, and — via `tight()`'s early return — in the full-screen strip, whose height must
  not change. Its colours are the one drawn thing here NOT baked into the SVG by JS: it is plain
  inline SVG, so `var(--accent)` reaches it and `Theme.subscribe` has nothing to re-bake (invariant
  3 does not apply, and a check keeps the `stroke` attribute absent so nobody "fixes" that). Linear
  y and zero-based, unlike the chart's log readership axis: log is there because the ROSTER spans
  five orders of magnitude, but within one composer the question is proportion, and a log baseline
  flattens exactly the spike the line exists to show.
- **Every sparkline shares one month axis, so the blank left of a young article has to be named.** A
  shared axis is what makes two composers comparable, and it means the articles created after
  2015 draw over the right-hand end and leave the rest empty — which under a line chart reads as
  "nobody read this" rather than "not written yet". The label row prints `from Jul 2025` instead of
  the axis span in that case. A null month is a BREAK in the path for the same reason (invariant
  10); joining across it would draw a line down to zero and back.
- **Anything that handles its own arrow keys marks itself `[data-keys]`.** `app.js`'s document
  keydown listener steps the SELECTION on left/right, and its old guard was
  `matches("input, textarea")`, so the first focusable thing that was neither had its keys stolen:
  arrowing along the sparkline changed the composer instead of the month. Escape is handled before
  the guard, because it means "back out of this" wherever focus is. The brush still owes a keyboard
  path (TODO); when it gets one it needs the attribute and no edit to the listener.
- **A chart label prints the short name, not the canonical title.** 7 characters on average instead
  of 15, and because `pickLabels()` is first-come-first-served on space, halving every box is what
  lets the names behind it find room at all. The label text and the width estimate must come from
  the same string — `pickLabels()` computes it once and carries it on the placement.
- **Labels are a function of zoom, not a list.** `pickLabels()` spends a budget that grows with the
  zoom (`base × (1 + log₂ k)`) on frame-culled candidates, so pinching in names what is in the
  frame. In Fame the curated names are the SEED and fill the budget first; beyond them the
  ranking is `prom`, z-scored distance from the centre of the visible cloud, recomputed in
  `setFilter()`/`setData()` because a filter must rank its own group. The one special case is the
  resting unfiltered Fame view, where the budget is pinned to the seed so the view says exactly what
  it is about — also the state `make-og-svg.py` draws (invariant 14).
- **The ring follows the filter by RANKING; the fill follows it by TASTE.** That is #7's answer, and
  the two halves are deliberately different mechanisms. `refreshEmphasis()` keeps a ring budget of
  THREE — the size of `OUTLIERS`, and they must stay the same size — filled first by the curated
  outliers the filter kept and then by `prom`, the same seed-then-rank shape the label budget has.
  So the resting view and the share card are what they were, "Men" changes nothing, and "Women"
  derives all three. Below `MIN_FIELD` visible dots nothing is derived: a ring means "stands out
  from the crowd it is drawn in", and two Haydns are not a crowd. Every channel that follows
  emphasis — fill, stroke, radius, opacity, label colour, the table chip — reads `named()`, which
  reads the DERIVED set, so adding a channel needs no further wiring; `namedSet` stays the curated
  set where that is what is meant. Derived rings are seeds in `pickLabels()` too, because a dot
  the view rings and then declines to name points at a composer it refuses to identify.
  The FILL is never derived: it is an editorial claim about which quartets are played, which no
  ranking recomputes — Prokofiev is on it for two quartets and Debussy for one, and TODO records
  that no single scalar reproduces that set. So the women's group got a SECOND hand-written
  list (`WOMEN_CANON`), swapped in by `Chart.setRepertoire()`. The `--sel` fill and the sentence
  naming it are ONE claim, so `REPERTOIRES` carries both and `renderLegend()` prints
  `Chart.repertoireLabel()` — the suite reads the label off that function rather than quoting it, so
  rewording is free and printing a different noun than the chart is using is not. Both lists answer
  to the same neutral noun, which is the other way out of invariant 8's wrong-channel trap: "the
  repertoire" over nine women the repertoire never held was the failure. The gate is the point — not
  one of them clears `DOMINANT_VIEWS`-scale readership — the best is an order of magnitude under
  `CANON`'s median — so at rest they would be filled dots low in the densest part of the cloud,
  captioned as the set that holds Mozart. Filling a curated set also FEEDS the ring, since
  `refreshEmphasis` ranks over a pool that excludes `namedSet`.
  **A derived ring must also stand APART — `MIN_SEP`, a fraction of the plot diagonal, from every dot
  already emphasised and every ring derived before it.** Prominence is distance from the CENTRE of
  the cloud, so a corner full of composers all scores high and the tie was broken by nothing visual:
  the ring landed on Monk, whose disc came within 4px of Beach's. Measured in SCREEN space from
  `baseLayout()`, because "on top of" is a claim about pixels and the three modes lay the same dots
  out three ways — and only x and y are read, never the radius, which `layout()` derives from
  `named()` while this function is in the middle of changing it. **Measuring against the picture
  means re-deriving whenever the picture changes shape**, so `setMode()` and `resize()` call it too:
  reached only from `setFilter()`, it chose rings in a geometry where nothing is ringed and those
  picks were drawn unchanged in Fame, 3.1px from a filled dot. The threshold is a fraction of the
  plot AND a floor of `GAP_DOTS` named radii, because the dot radius is clamped at 3.2 while the
  diagonal keeps shrinking; the fraction is not delicate (2.5%–5% picks the same three) and the
  floor is a guard, not a fix. Deriving FEWER than the budget is the honest outcome when nothing
  stands clear.
- **A filter fits the frame, and the fit is the RESTING view.** `computeResting()` is the one answer
  to "where should this chart be sitting right now": identity with no filter, the box containing the
  kept dots with one. `setFilter()` transitions there when the gesture settles, never mid-drag;
  `resetZoom()` returns there rather than to the full extent; `zoomed()` is measured against it, so
  a filter that fits at 4x does not light the reset button as though the reader had pinched. It is
  memoized because `zoomed()` is asked on every frame of a pinch, and invalidated by the only three
  things it depends on: the filter, the mode, the box. The fit is measured from a `layout()` at
  `zoomIdentity` rather than from the scales, so a fourth encoding cannot forget to update it — and
  the swarm fits x ONLY, because its y is solved once at k=1 and is not under the zoom. This works
  because a filter here is a HIGHLIGHT: the rest of the cloud is still drawn at 0.07, so closing in
  shows the group against the ghost of its field.
  **Below `MIN_FIT` placeable dots it does not fit at all.** One match is a zero-width box, so
  `fit()` returns Infinity on both axes and `k` lands on the 24x clamp — searching a composer threw
  the reader to maximum magnification, where the cloud that dot is being compared AGAINST is off
  screen. The count is of dots the chart can PLACE, not `visible.size`: a filter can keep rows the
  Fame view has no y for. Skipping the fit means the FULL EXTENT, not the reader's current
  transform, because `restingTransform()` has to stay a pure function of the filter, the mode and
  the box or the memo is meaningless and "reset" has nothing to return to.
- **Anything the zoom moves must be clipped.** `chart.js` clips the dots, labels, selection ring and
  lens to `#plot-clip`; a new zoom-transformed group needs the same `clip-path`, or a pinch lays it
  out over the axes and past the card edge.
## Where to pick up

`TODO.md` holds the open work, one known defect (the readership brush has no keyboard path) and the
things deliberately not being done, with why. Read it before starting something: it exists so a
cold session doesn't re-derive a decision already made on evidence, or re-derive one badly.
