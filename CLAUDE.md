# CLAUDE.md — quartet-composers

A static d3 visualization + data table on [pwa-starter](https://github.com/jsundram/pwa-starter). No
build step; the deployed files are the repo's files. README.md says what the app is.

## Where a thing goes

Three destinations, and keeping them apart is what keeps this file short.

**Here: rules.** What to do, and what breaks otherwise.

**The commit and the issue: history.** What happened and why, attached to the diff that did it. A
commit message describes a moment, so it cannot go stale; a file describing the same thing can. `git
log -S`, `git blame` and `git log --grep` retrieve it. Where a rule needs its incident to be
understood, an issue number is the pointer.

**A check: anything mechanical.** A count, a list, a threshold, a measured offset — a check can go
red and a sentence cannot. Where a rule here is enforced, name the enforcement rather than repeat
the arithmetic.

**So a number in this file is a RECORD or it is absent.** A record is a measurement that happened
and cannot go stale. Anything the repo recomputes can, and is read off the thing that holds it.

**And this file has a ceiling.** It is read in full before every session's first change, so its
length is charged to all of them: keep it readable in one sitting by someone who has never seen the
repo. The prose inside the code answers to a ratio instead — `scripts/volume.py --check`.

## Invariants — break these and it fails silently

1. **`V` in `sw.js` moves on every change to a `SHELL` file — and the hook moves it for you.** The
   shell is precached and served cache-first, so without a bump the fix reaches the repo and
   nobody's installed copy. `app.js`'s `VER_PREFIX` must keep matching `V`'s stem, which is why only
   the numeric TAIL is ever incremented. `sw-lint.py --fix` does the bump in the pre-commit hook and
   `--base REF` covers the branch in CI, because two PRs off one base can bump identically and merge
   to a net delta of zero (#32); `sw-lint.py` states its checks.
   **The hook only exists in a clone that ran `scripts/setup.sh`**, git having no way to enable it
   on clone, so the branch check is what has to hold. What that clone alone gets is the BUMP and
   og-lint's staged card-size check; the rest of the lints report in CI either way.
   `.claude/hooks/session-start.sh` runs the setup step per session.

2. **`sw.js`'s `BOOT` must list every script the page dies without.** Every pixel is drawn by JS, so
   a cached `index.html` without `d3.v7.min.js` or `composers.json` is a headline over an empty box;
   the offline page is strictly better. A new load-bearing script goes into `SHELL`, into `BOOT`,
   and bumps `V`. `readership.json` and `imslp-works.json` are SHELL but not BOOT, because nothing
   waits for them — the sparkline arrives after first paint, and the IMSLP work pages are detail
   behind a column already in `composers.json`.

3. **Colors read into JS can't be reached by a CSS variable swap.** `chart.js` bakes `--c-*` into
   SVG fills and `app.js` into the legend. Both re-read through `Theme.getCssColor` inside
   `rerender()`, which `Theme.subscribe` fires on every theme change — never `getComputedStyle`
   directly. A fourth component that bakes a colour needs a fourth `rerender()` wired in there.

4. **`composers.json`, `readership.json` and `imslp-works.json` are generated; never hand-edit
   them.** `scrape_list.py` -> `fetch_wikidata.py` -> `fetch_views.py` -> `fetch_imslp.py` ->
   `build_imslp.py` -> `build_data.py`, each caching into `data/`. Only the fetches touch the
   network, so a rebuild is offline and reproducible. The last stage writes ALL THREE from one set
   of caches and they must stay in lockstep — files each internally consistent but built from
   different fetches are a drift nothing in the app can see, and `validate.py` is what holds them
   together, recomputing every shipped statistic from the cache it came from.
   **`build_rows()` in `build_data.py` is the one place the roster is decided**, and
   `build_imslp.py` CALLS it rather than reading `composers.json`: a second reduction of the same
   caches would be a second opinion about who is on this list.
   `data/pageviews.json` stores each series as a FLAT ARRAY aligned to its `months` axis, and the
   alignment is load-bearing — one element short shifts every month by one and the numbers stay
   plausible, so `build_data.py` and `validate.py` both refuse a ragged one. It carries three
   distinct states, which `fetch_views.py` states in full, and every title is fetched over the whole
   AXIS rather than over `--months`.
   Composer NAMES are canonical Wikipedia titles and change spelling when the pipeline runs, so
   anything hardcoding one (`make-og-svg.py`'s `LABELS`, a test assertion) must use that form.

5. **Never ask the pageviews API for an unresolved title.** Views are counted per title, a redirect
   is its own title with its own tiny count, and the request succeeds either way — Bartók returned
   41 instead of 14,330. Resolve the DISAMBIGUATED title too: a bare "John Adams" is the second
   President of the United States, who outranked Beethoven here. Invariant 15 is the other half.

6. **Wikidata claim RANK is not metadata.** A known-wrong value is marked `deprecated` rather than
   deleted, so reading `claims[0]` reported Tania León — alive — as dead since 1996. `year_of()`
   drops deprecated, prefers `preferred`, and ignores novalue/somevalue snaks.

7. **The Fame view is the default, and the only place the app hardcodes composer NAMES.** `CANON`
   (the repertoire a quartet actually plays, in birth order), `OUTLIERS` and `WOMEN_CANON` (shown
   only under the Women filter) in `chart.js` hold canonical Wikipedia titles, which change spelling
   when the pipeline runs. Every such vocabulary answers to a check that goes red when it stops
   resolving, and a new one needs its own: `Chart.missingNames()` covers all three lists — a rename
   inside `WOMEN_CANON` would otherwise sit unreported until somebody pressed the pill — `names.js`
   has `Names.staleOverrides()` for `SURNAME`, the gender pills have `unfilterableGenders()` and
   `validate.py` for a P21 label no pill reaches, and `REPERTOIRES`, keyed by those same pill
   values, has `unreachableRepertoires()`.

8. **Each view encodes different things, so each needs its own key.** In Fame, size is the y AXIS
   and hue is emphasis, so the lifespan ramp and the size key would label channels carrying nothing:
   `renderLegend()` branches on the mode, and `setMode()` re-renders the legend and the table (row
   chips come from `Chart.colorOf`, which follows the view). Under a filter the ring's meaning
   changes and the key stops captioning it — the wrong-channel failure prevented by having no words
   to get wrong rather than by keeping two of them correct.

   **The two non-Fame views ramp DIFFERENT variables, and that is the point.** The timeline keeps
   LIFESPAN, because the count is already its y axis and a hue repeating it would spend the last
   free channel restating what the scale says — the same refusal `layout()` makes when it declines
   to put readership into the Fame radius. The SWARM ramps the COUNT (`QUARTET_CLASSES` in
   `chart.js`): its x is birth year, its radius is readership and its y is a packing that carries
   nothing, so the count was in no channel of that view at all and only the hint said so (#94). The
   open circle goes on meaning LIVING in both, so the swarm rings a living composer in their own
   count's colour rather than the timeline's flat grey.

   **The swarm's ramp is CLASSED and the timeline's continuous, which is measured rather than
   taste.** It shipped continuous and was precise and unreadable at once: most adjacent counts came
   out under a just-noticeable difference. One hue carries about seven decodable levels however many
   stops anchor it, which is why ColorBrewer's sequential schemes are classed and stop at nine. The
   bounds are FIXED and not computed from the data — Jenks was rejected twice, once on `LIFE_DOMAIN`'s
   own lesson that a break derived from the roster repaints a composer when somebody ELSE joins the
   list, and once on this distribution, where all the variance sits in the dozen composers above
   forty, so minimising within-class variance spends its classes on the tail and hands the majority
   one colour. The top class is OPEN and has to stay clear of the mid-range: a five-class version put
   Schubert and Cambini in one bucket, a tenfold range of output in one colour, in the view whose
   point is who wrote a lot. The KEY is painted and captioned out of one array
   (`Chart.quartetClasses()`), so an edge cannot be drawn in one place and stated in another, and the
   `--c-q*` steps are a SINGLE hue running dim-to-bright in dark mode — "more" has to mean more ink.
   `ui.test.mjs` asserts the rise in both themes, that adjacent classes clear a JND in Lab, that the
   top classes stay resolved, and that the timeline did not quietly follow.

9. **Readership is a measure, not a tally — round it everywhere except the table.** It is the median
   of `STAT_MONTHS` monthly page-view counts, and at most that: nulls are dropped. Not however many
   months `data/pageviews.json` happens to cache. Widening that window would resize every dot and
   bake a 2016 readership into a 2026 picture — and it rebuilds CLEANLY, so `validate.py`'s
   `STAT_WINDOW` pins it in all three places that state it, TYPED there rather than imported from
   `build_data.py`, or the check could only agree with the code it is checking. Any one month runs
   well off typical, so a printed count is two significant figures floored plus a "+" (`atLeast()`
   in `app.js`, through `Histogram.fmt` so the brush readout and the panel agree), and a new place
   that prints one almost certainly wants it. Two deliberate exceptions: the table keeps the exact
   number because it SORTS on that column, and the sparkline prints exact counts because a month
   there is a raw tally and rounding the figure somebody hovered to read defeats the hovering.

10. **`null` means unknown and must stay null**, because a default puts a fabricated dot on the
    chart. `quartets: null` (the page states no count), `death: null` (living) and `gender: null`
    (no P21 claim) are facts, not gaps: null quartets are in the table and excluded from the chart
    by `plottable()`, null death means the lifespan ramp does not apply and the dot is drawn open,
    and null gender is in NEITHER the Women nor the Men filter, because "Women" means Wikidata says
    female, not "everyone we didn't call a man". Gender is the one field where the tempting default
    is a guess about a PERSON — never infer it from a name or a pronoun; an unmapped P21 value ships
    as its raw QID and `validate.py` fails on it.

11. **Grade the parser against the PAGE, not against 2014.** `scripts/audit_counts.py` samples
    parsed counts beside their source sentence for a human to grade; that is the real measure.
    `compare_2014.py` is useful for row matching, but the page has been rewritten over twelve years,
    so a disagreeing count is usually the parser being right.

12. **The 2014 page views are not comparable to modern ones** and must never be plotted alongside
    them: the API has no per-article data before 2015-07, so they came from a different measurement
    system. Archived for provenance only.

13. **Search folds the characters NFD cannot decompose, before NFD** — `ł`, `ø`, `ß` and the rest of
    `FOLD` in `table.js`, which have no Unicode decomposition, so NFD alone leaves "lutoslawski"
    missing "Lutosławski". A name that needs a new one means a new `FOLD` entry, and the suite types
    a folded query so the RULE is checked rather than the table.

14. **`scripts/make-og-svg.py` duplicates chart.js's scales on purpose** — the app must not ship a
    build step and the card must not ship a JS runtime. Same log domains, same jitter, same
    emphasis, the same two uniform radii, the same short-name rule from `names.js`. It renders the
    Fame view AT REST, which is what a bare URL opens on, so no derived ring and no second
    repertoire ever reaches it. Change an encoding in `chart.js` and change it there too, or the
    share card stops matching the page.

15. **A canonical title is only canonical TODAY, so a page MOVE is a hole in the series.** The API
    counts the string requested, so months before a move were counted under the name the article
    held then and asking the current one returns the redirect traffic nobody followed. Fanny
    Hensel's article sat at "Fanny Mendelssohn" until March 2026 and shipped a median of **500**
    against a real **5,217** — and the app NARRATED the artefact, firing `SPIKE` and captioning a
    rename as an obituary. Those two figures live here and nowhere else; `scripts/pagemoves.py`
    points at them rather than restating them, because two files stating one measurement is how they
    drifted apart once already.
    `pagemoves.py` is the one place the rule lives, in three deliberately separate parts it names
    itself: a shape detector that only ever GENERATES suspects, the MediaWiki move log as the
    arbiter of whether a move happened, and a traffic test for whether it STUCK. **The month of the
    move itself is null**, since either title alone is a partial month and the sum adds the redirect
    share every other month excludes.
    **The repair is not a migration that happens once.** A refetch overwrites the stitched series
    with the API's per-title answer, so `fetch_views.py` re-applies every recorded move on every run
    that touches the title, and `data/pageviews.json`'s `moves` block records what it did — an EMPTY
    list meaning "asked, and the log said none", which is how `validate.py` tells genuine growth
    from an unchecked rename. **A chain on record is trusted, never re-derived**, and nothing
    records an answer it does not have.
    **Do not sum redirects generally.** A different policy, measured and rejected: the median
    correction was 1.02x, invisible on a log axis four decades tall, in exchange for a count that
    depends on how many aliases an article happened to accumulate. A move is not an alias; the
    article LIVED there.

16. **The IMSLP columns are TWO fields carrying THREE answers, and `imslp_cat` is the one that can
    tell them apart.** `imslp` is a work count and is `0` both for a composer IMSLP holds with no
    quartets and for one nothing could place — deliberately not distinguished, because the reader's
    next move is the same either way. `imslp_cat` is `null` for the second (nowhere to link), `""`
    for a composer whose category reduces to `Surname, Forename`, and the category VERBATIM
    otherwise (`Shostakovich, Dmitry`). Shipping only the exceptions is safe **because the build
    verifies it, not because the rule is trustworthy** — the reduction is written three times, in
    `build_data.py`, `validate.py` and `app.js`, each checked against a different artifact. What is
    COUNTED is distinct **works, not pages**, and invariant 11's rule applies to that parse
    (`scripts/imslp-audit.py`). **The thing that must never happen is subtracting it from
    `quartets`**, which is how many the composer WROTE, from Wikipedia prose; the two columns sit
    one apart, routinely disagree, and answer different questions from different sources. Copy about
    absences is the other half: "no quartets **found**" and "no IMSLP page found", never "not on
    IMSLP" — having found no evidence is not the same as having asked.

## Testing

**The ethos, measured.** A mutation run in Sep 2026 — 39 plausible one-line bugs injected, suites
run, tree restored — caught 25: the data gate 6 of 7, the browser suite 13 of 22, `sw.test.mjs` 1 of
5. Every miss was a pure function or an untested entry point, and not one was a layout or
interaction bug. The rules that come out of it:

- **Budget checks by how SILENT the failure is, not by how much code there is.** A chart bug is
  visible the moment you open the page; a precache bug is visible only on somebody else's installed
  client a month later. Coverage runs the other way round from that today.
- **A check may not read its expectation out of the code under test** — that is unfalsifiable for
  exactly that value; cross-check two independent artifacts instead. `sw.test.mjs` reads `BOOT` out
  of `sw.js` this way and is left alone on purpose: it is vendored pwa-starter.
- **Prefer a POSITIVE assertion.** `!panel.includes(exact)` passes when the formatting differs, not
  only when the rounding is right.
- **A number the repo can compute does not belong in prose at all.** Pinning one with a lint is the
  wrong branch of the built-or-cut rule, and it was taken and reverted (#67, #74): a check cannot
  tell a reflowed paragraph from a stale fact. When a claim is about behaviour, test the behaviour;
  when it is a count, read it off the thing that holds it.
- **A check earns its place by failing without the code it covers, and keeps it by being the only
  one that does.** `ablate.py` enforces the first half; the second is why deletions are welcome —
  re-run the suite without a check, and if nothing else noticed, it was never holding anything up.

No test framework, and nothing to install. Each of these states its own rules in its header.

| run | asks |
|---|---|
| `python3 scripts/validate.py` | **the data gate** — the three shipped files against their schemas, the caches and the previous commit. Run it after every pipeline run. |
| `scripts/ui-test.sh` | the behavioural suite, against a real Chrome over CDP. |
| `python3 scripts/ui-test.test.py` | the runner's own port derivation, no browser needed (#49). |
| `node scripts/names.test.mjs` | the display-name rules, against the shipped roster. |
| `node scripts/sw.test.mjs` | the SW fetch handler under mocked globals. |
| `python3 scripts/sw-lint.py` | the precache contract (invariant 1); `--base REF` is the branch half. |
| `python3 scripts/og-lint.py` | the link preview: card size, meta length, and the counts that SHIP. |
| `python3 scripts/pagemoves.test.py` | invariant 15's pure parts, against a stubbed move log. |
| `python3 scripts/fetch_views.test.py` | the page-view cache, `fetch` stubbed and the clock frozen. |
| `python3 scripts/imslp.test.py` | the IMSLP join's parses and judgements, all offline. |
| `python3 scripts/fetch_imslp.test.py` | what a warm crawl ASKS FOR, and what it declines to (#62). |
| `python3 scripts/codehash.py` | is a change comments-only, or did code go with them? |
| `python3 scripts/fix-lint.py --base REF` | a branch changed source and touched no test. |
| `python3 scripts/ablate.py --base REF` | the branch's tests over the base's code — do they still pass? |
| `python3 scripts/setup.test.py` | `setup.sh` enables the hook, survives a second run, and never takes over a `core.hooksPath` somebody set. |
| `python3 scripts/record-lint.py` | did a number reach a comment or a docstring? `--base REF` for the branch. |
| `python3 scripts/volume.py` | how much of this repo is prose, and is this change adding more? `--base REF` for the branch. |
| `scripts/audit_counts.py`, `audit_redirects.py` | not automated: evidence printed for a human to grade. |

Everything that needs neither a browser nor a network runs in CI, and since #56 so does the browser
suite — the bigger prize there being that `ablate.py --with-ui` runs on the runner too. `ui-test.sh`
skips cleanly where no Chromium is installed, which is right for a laptop and wrong for a runner, so
`REQUIRE_BROWSER=1` turns that skip and both pointer warnings into a failure. Still run it by hand
after touching `chart.js`, `table.js` or `styles.css`: a UI change is one you want to LOOK at.

**The two branch gates read TWO commits**, so `fix-lint.py`, `ablate.py` and `sw-lint.py --base` run
on pull requests only, and a `No-test: <reason>` trailer skips both — scoped PER FILE to the ones
its own commit touched, so an untested source change is a sentence a reviewer can read rather than a
silence. `record-lint.py --base` and `volume.py --base` are the same shape and deliberately NOT
gates: each asks a judgement, and a lint that pinned one was reverted (#67, #74), so CI prints them
to the run summary and never fails on them.

**Four rules hold inside the browser suite**, each stated in `ui.test.mjs` beside the code that
keeps it, and a new check answers to all four: every wait is a POLL and not a budget (#48); a
POINTER is a platform fact that cannot be emulated (#50), so the suite needs a real Xvfb display and
section 2 asserts which one it got; no check reads a PIXEL, so the DOM is the oracle and the PNGs
are evidence for whoever reads a failure; and a boot is a CLAIM, not a reset (#48).

`scripts/refresh.py` is not a test but the same discipline, and `refresh.yml` runs it monthly with
the built-in `GITHUB_TOKEN` — which does not trigger `checks.yml`, which is why refresh.py runs the
data gate itself. The gate must not be skippable because a robot opened the PR.

## Conventions

Each rule below is the part a session needs BEFORE opening a file. Where the reasoning is local to
one function it stays in the comment at the site, and this names the site rather than repeating it.

- Vendored pwa-starter files carry `pwa-starter: <file> @ <sha>` near the top. Keep the stamp when
  editing them; it is how `check-downstream.py` upstream finds this repo.
- `mocks/` is a RECORD of a design decision, not a second implementation of one. Nothing there ships
  and nothing there follows a change to `chart.js`.
- Comments explain *why*, and especially what breaks otherwise. Don't narrate the next line, and
  don't recount how a bug was found — that is the commit message's job.
- **A comment may not assert a mechanical fact about the code beside it — that becomes a check, or
  it goes.** A comment cannot go red, so a stated join key, count, list or threshold is correct when
  written and silently wrong later (#42); invariant 7's four checks are the pattern. For the DOCS
  the answer is not a lint (#67) — it is not writing the number. A comment about WHY is never in
  this category, which is most of them, and none of this is an argument for fewer comments.
- **A fix ships with the test that goes red without it — not with the next review.** Run that test
  against the tree WITHOUT the fix and watch it fail, before proposing it; `ablate.py` enforces it
  on a branch, but the discipline is the point. Where there is genuinely nothing to assert, say so
  in a `No-test:` trailer rather than leaving it silent.
- **Prose the app can FALSIFY is built or cut; only prose it cannot is typed — and CUT is the first
  branch to try.** A sentence naming the axes was true in Fame only and went, rather than being
  derived per mode (#24); a built lede emptied under some filters and collapsed the paragraph under
  the pill you had just pressed (#27, #35). `#count`, the search placeholder and `setProv()` stay
  built because each is the ONLY statement of what it says, and none of them can empty.
- **A number printed beside the chart counts the PLOTTABLE rows**, and `Chart.plottedStats()` is the
  one place that answers what the chart can place — rows with no stated quartet count are in the
  table only, and three of them are the roster's earliest births. The same split governs the app's
  CLAIMS: `manifest.json` and the link preview describe what the page DRAWS, while `#count`, the
  search placeholder and the provenance line count the rows the TABLE holds.
- `index.html` owns structure, `styles.css` owns looks, `app.js` owns boot and the shared state
  (which composer is selected, which filters are active). `chart.js`, `table.js` and `histogram.js`
  never talk to each other — they share `names.js` and `Chart.colorOf`, which are read-only lookups,
  not state. The filters compose in `applyFilters()`, where each source returns "a Set of indices,
  or null for everything" and they are intersected. The gender filter is the one with no module of
  its own (`genderMatches()` in `app.js`): nothing to render and no data to hold. A fourth filter
  that DOES draw something belongs in its own file, on the same contract.
- **`names.js` loads before `chart.js` and `table.js`, and `Names.setData()` runs before either gets
  data**, because the short form of a name is a function of the WHOLE roster. It is a SHELL and a
  BOOT dep like every other load-bearing script.
- **The table and the chart show short names; the detail panel shows the full title.** `names.js` is
  the only place that takes a canonical name apart, and it is a heuristic. BOTH forms come from one
  shared-surname map, so the two can never disagree about who needs more than a surname: `filed()`
  gives the table "Haydn, Joseph", `short()` gives the chart "M. Haydn". The panel, the hover flag
  and the row's `title` keep the canonical title, where recognising the person is the job. One
  exception, in the chart form only: a surname only one composer is READ for prints bare — which is
  why `Names.setData()` takes readership too. A chart LABEL prints that short form, because
  `pickLabels()` is first-come-first-served on space, and the label text and the width estimate it
  is picked by must be the same string.
- **Labels are a function of zoom, not a list.** `pickLabels()` spends a budget that grows with the
  zoom on frame-culled candidates, so pinching in names what is in the frame. In Fame the curated
  names SEED it; beyond them the ranking is `prom`, recomputed in `setFilter()`/`setData()` because
  a filter must rank its own group. The resting unfiltered Fame view pins the budget to the seed —
  also the state `make-og-svg.py` draws.
- **The ring follows the filter by RANKING; the fill follows it by TASTE** (#7). `refreshEmphasis()`
  fills a budget derived from `OUTLIERS` by taste then by `prom`, the seed-then-rank shape the
  labels have, and every channel that follows emphasis reads `named()`, so adding one needs no
  further wiring. The FILL is never derived — it is an editorial claim no ranking reproduces — so
  the women's group got a SECOND hand-written list, and because that fill and the sentence naming it
  are ONE claim, `REPERTOIRES` carries both. `chart.js` states the rest.
- **A filter fits the frame, and the fit is the RESTING view.** `computeResting()` is the one answer
  to "where should this chart be sitting right now", and `setFilter()`, `resetZoom()` and `zoomed()`
  all measure against it, so it must stay a pure function of the filter, the mode and the box — or
  the memo is meaningless and "reset" has nothing to return to. It works because a filter here is a
  HIGHLIGHT: the rest of the cloud is still drawn faintly.
- **Anything the zoom moves must be clipped.** `chart.js` clips the dots, labels, selection ring and
  lens to `#plot-clip`; a new zoom-transformed group needs the same `clip-path`, or a pinch lays it
  out over the axes and past the card edge.
- **One filter row, above everything it scopes.** `#filters` is a sibling of `.grid`, not a child of
  either card — all three filters scope both views, and a filter drawn inside one card says
  otherwise. `placeFilters()` moves it into `#viz` in full screen.
- **The chart's controls sit ABOVE the plot, because the plot's height is a function of the VIEW.**
  `measure()` gives each mode its own aspect ratio, so a row underneath moves when you press it,
  lifting the pill out from under a second tap at the same spot. **Nothing a finger rests on may be
  placed by a box the same press resizes.** Full screen is the exception and stays underneath, where
  `#plot` is sized by the viewport rather than by the view. It costs a phone's first screen (#29).
- **No filter control appears or disappears at all**, which is the rule above satisfied by
  construction (#31, #35). One permanent `Reset filters` clears all three and is `disabled` at rest
  and accent-filled when live — a state change that moves no box, which is why `applyFilters()` may
  light it on the drag's first frame, above the `settled` guard. Being the page's one answer to "is
  anything filtered?" is why `anyFilter()` reads the query TRIMMED, like `Table.matches()`.
- **The lens is an OVERLAY, not a view — a checkbox in the controls row, over all three modes.**
  `warp()` applies the fisheye LAST, in screen space, which is what lets one lens serve three modes
  with no per-mode case: what it moves is pixels, so what you click is still what you see. It
  re-lays out nothing, which is what makes it safe in a row above the plot, and `#v=lens` still
  resolves, to the timeline with `l=1`. Everything else — the one gesture it takes away on touch,
  what it leaves the frame doing, the `__zoom` sync, why it earns no labels — is in `chart.js`.
- **Share and Full screen are icons ON the chart wherever the controls row will not hold them on one
  line**, which is what PAYS for the third button in the row. `placeChartTools()` reparents
  `#chart-tools` into `#plot`, on the same one-element-moved contract as `placeFilters()` and
  `placeDetail()` — never a second copy. **The condition is a MEASUREMENT of that row rather than a
  device, and it is TWO intervals**: `iconsOnPlot` in `app.js` holds the only copy, `styles.css`
  scopes the look to `#plot > #chart-tools` so it follows the DOM rather than re-deciding the width,
  and `ui.test.mjs` presses Share at the first width in each band. They sit in the AXIS-TITLE BAND,
  over no dot in any view, on a touch target that is felt and not seen, so a dot they overlapped
  would silently stop being TAPPABLE — and top right is the trap, reading as empty in Fame and
  piled with dots in the swarm, which is what judging a shared overlay from one view gets you.
- **A specificity trap runs through this stylesheet**, and it has shipped three times: the brush
  grips, `#hist-clear` sitting under the touch floor because an ID out-specifies `.btn` (#31), and
  the chart-tools glyphs, where a bare `#fs .ico-out` loses to the group's full `#plot >
  #chart-tools` prefix and drew both glyphs at once. Carrying the full prefix is not tidiness.
  `#plot > svg` is the same shape: it means THE CHART, and as a descendant selector it stretched an
  18px glyph to fill its button. The grips are the one to read first (`histogram.js`, #40): d3-brush
  sets `fill:none` and `pointer-events:all` on the brush `<g>` and both INHERIT, so painting
  `.handle` dresses the hit area as the control.
- **The `hidden` ATTRIBUTE is only `display:none` in the UA sheet**, so ANY author `display` on the
  same element beats it — silently, since the element stays hidden to a screen reader and to
  `.hidden` in JS while being drawn. `styles.css` answers it once, `!important`.
- **There is ONE detail panel, and `app.js`'s `placeDetail()` moves it.** Beside the chart above
  900px; inside `#viz` (`.compact`) on a phone and in full screen at any width. Never render a
  second compact copy — the selection, the nav buttons and the `.on` state all assume one element.
  BELOW the plot on a phone, free to grow because nothing above it moves; ABOVE it in full screen as
  a fixed-height strip drawn even when empty, where a box that grew on select would trip the
  ResizeObserver and re-lay out the chart under the finger that just tapped it (`tight()` trims it).
- **A hover previews into the detail panel, so its box is reserved wherever a pointer exists.**
  `@media (hover:hover) and (pointer:fine)` gives `.compact` a `min-height` covering its TALLEST
  state; without it, moving the mouse across the chart pumps the legend up and down. Touch screens
  get neither rule — no hover to churn, and the space is the chart's. The reservation is MEASURED
  against the composer with the LONGEST caption, because the dot an earlier check happens to hover
  is not the worst case.
- **Anything that handles its own arrow keys marks itself `[data-keys]`.** `app.js`'s document
  keydown listener steps the SELECTION on left/right, and its guard has failed both ways — it is
  `input:not([type="checkbox"]), textarea, [data-keys]` now, and the suite presses a key with the
  box focused rather than trusting the selector. Escape is handled BEFORE the guard: it means "back
  out of this" wherever focus is. The readership brush still owes a keyboard path (#81); when it
  gets one it needs the attribute and no edit to the listener.
- **The phone table has to fit in a font you do not choose.** `system-ui` is SF on a Mac, Segoe on
  Windows and DejaVu on most Linux, and DejaVu overflowed the four phone columns outright (#53).
  **An abbreviation is not free to a reader who can SEE it**: WCAG 2.5.3 asks the accessible name to
  contain the drawn label, or a voice-control user says "click Qts" at a name reading "Quartets" and
  the column cannot be sorted at all. A new column, or a longer header, has to be MEASURED — at
  360px as well as 390px, and in a font that is not a Mac's.
- **`.seg` is a look, not a behaviour.** Two pill groups wear it — the chart view switcher and the
  gender filter — so anything binding `.seg button` must scope itself (`.controls .seg button`).
  Unscoped, the switcher's handler landed on the filter's buttons and a pill press called
  `setMode(undefined)`: the chart left every named mode at once and the URL grew `#v=undefined`.
- **The sparkline is the app's one optional part, in both halves.** Its data is precached but not a
  BOOT dep and is fetched after the paint, and `sparkline()` returns null when it has not arrived,
  when a composer has fewer than two months of data, and in the full-screen strip, whose height must
  not change. Its colours are the one drawn thing here NOT baked into the SVG by JS: it is plain
  inline SVG, so `var(--accent)` reaches it, invariant 3 does not apply, and a check keeps the
  `stroke` attribute absent so nobody "fixes" that. Linear y and zero-based, unlike the chart's log
  readership axis: the log is for a ROSTER spanning orders of magnitude, but within one composer the
  question is proportion, and a log baseline flattens exactly the spike the line exists to show.
- **Its caption names the spike if there is one and the trend otherwise**, so `SPIKE` tests the peak
  against the 95th PERCENTILE of that composer's own months — a fixed "peak N× typical" cried spike
  about noise on half the roster and buried the real story for the steady ones. The peak hairline is
  drawn ONLY in the spike branch; an annotation pointing at a month nothing mentions has no
  referent. Every sparkline shares one month AXIS, which is what makes two composers comparable and
  which leaves an article created after 2015 drawing over the right-hand end only — read under a
  line chart as "nobody read this" rather than "not written yet", so the label row prints the
  RECORD's span rather than the axis's. A null month is a BREAK in the path for the same reason
  (invariant 10); joining across it would draw a line down to zero and back.
