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
   the numeric TAIL is ever incremented. `sw-lint.py --fix` (pre-commit) bumps and re-stages
   `sw.js`; `--bump` is the same increment with no git in it, for `refresh.py`; `--base REF` in CI
   covers the branch, because two PRs off one base can bump identically and merge to a net delta of
   zero (#32).

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
   network, so a rebuild is offline and reproducible.
   **`build_rows()` in `build_data.py` is the one place the roster is decided**, and
   `build_imslp.py` CALLS it rather than reading `composers.json` — a second reduction of the same
   caches would be a second opinion about who is on this list, and the join would file counts under
   names nothing looks up. `data/pageviews.json` stores each series as a FLAT ARRAY aligned to its
   `months` axis. Alignment is load-bearing: an array one element short shifts every month by one
   and the numbers stay plausible, so `build_data.py` and `validate.py` both refuse a ragged one.
   Three distinct states: `null` is "asked, nothing there" (or, at a move, invariant 15); a MISSING
   month is "never asked"; a title that did not ANSWER is DROPPED rather than written, since writing
   it would null-pad the months it never answered for and read as complete forever. One failure
   never aborts a run.
   **Every title is fetched over the whole AXIS, never over `--months`**, because a flat array holds
   exactly one asked window — `--months 24` on a new composer would bury nine years permanently.
   `--months` narrows what counts as STALE, never what gets asked for. And a month IN PROGRESS is
   not a month, so `months_back()` ends at the last COMPLETE month and `--end` is refused past it.
   The last stage writes ALL THREE shipped files from one set of caches and they must stay in
   lockstep — files each internally consistent but built from different fetches are a drift nothing
   in the app can see. `validate.py` is what holds them together, recomputing each row's statistics
   from that composer's own sparkline and each IMSLP total against the pages it came from.
   `build_data.py` carries the canonical title in a list PARALLEL to the rows rather than a {name:
   canonical} map: `QUALIFIER` strips the disambiguator, so "John Adams (composer)" and a bare "John
   Adams" collapse to one key and the second silently wins. It also refuses to write when two rows
   print the same name, which `readership.json` is keyed by. Composer NAMES are canonical Wikipedia
   titles and change spelling when the pipeline runs, so anything hardcoding one (`make-og-svg.py`'s
   `LABELS`, a test assertion) must use that form.

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
   when the pipeline runs. `Chart.missingNames()` reports any that stop resolving and the UI suite
   asserts it empty, checking EVERY list — a rename inside `WOMEN_CANON` would otherwise sit
   unreported until somebody pressed the pill. `names.js`'s `SURNAME` map carries the same contract
   through `Names.staleOverrides()`. The gender pills are a third such vocabulary: `index.html`
   names the values the UI can filter, `app.js` reads its URL whitelist off the pills, and a stated
   P21 label no pill reaches fails both `validate.py` and `unfilterableGenders()`. `REPERTOIRES` is
   keyed by those same pill values, so `unreachableRepertoires()` fails on a curated list keyed to a
   pill that does not exist.

8. **Each view encodes different things, so each needs its own key.** In Fame, size is the y AXIS
   and hue is emphasis, so the lifespan ramp and the size key would label channels carrying nothing:
   `renderLegend()` branches on the mode, and `setMode()` re-renders the legend and the table (row
   chips come from `Chart.colorOf`, which follows the view). The ring's meaning also changes under a
   filter and the key no longer captions it — the wrong-channel failure is prevented by having no
   words to get wrong rather than by keeping two of them correct.

9. **Readership is a measure, not a tally — round it everywhere except the table.** It is the median
   of `STAT_MONTHS` monthly page-view counts, and at most that: nulls are dropped. Not however many
   months `data/pageviews.json` happens to cache. Widening that window would resize every dot and
   bake a 2016 readership into a 2026 picture — and it rebuilds CLEANLY, so `validate.py`'s
   `STAT_WINDOW` pins it in all three places that state it: the `views_months` axis,
   `readership.json`'s `stat_months`, and the `views_stat` prose. Typed there rather than imported
   from `build_data.py`, or the check could only agree with the code it is checking. Any one month
   runs well off typical, so the detail panel states two significant figures floored plus a "+"
   (`twoSig`/`atLeast` in `app.js`), formatted through `Histogram.fmt` so the brush readout and the
   panel agree. A new place that prints a view count almost certainly wants `atLeast()`. Two
   deliberate exceptions: the table keeps the exact number because it sorts on that column, and the
   SPARKLINE prints exact counts because a month there is a raw tally and rounding the figure
   somebody hovered to read defeats the hovering.

10. **`null` means unknown and must stay null.** `quartets: null` (the page states no count),
    `death: null` (living) and `gender: null` (no P21 claim) are facts, not gaps. Null quartets are
    in the table and excluded from the chart by `plottable()`; null death means the lifespan ramp
    does not apply and the dot is drawn open; null gender is in NEITHER the Women nor the Men
    filter, because "Women" means Wikidata says female, not "everyone we didn't call a man". A
    default puts a fabricated dot on the chart. Gender is the one field where the tempting default
    is a guess about a PERSON — never infer it from a name or a pronoun; an unmapped P21 value ships
    as its raw QID and `validate.py` fails on it.

11. **Grade the parser against the PAGE, not against 2014.** `scripts/audit_counts.py` samples
    parsed counts beside their source sentence for a human to grade; that is the real measure.
    `compare_2014.py` is useful for row matching but its count column is misleading — the page has
    been rewritten over twelve years, so disagreement is usually the parser being right.

12. **The 2014 page views are not comparable to modern ones** and must never be plotted alongside
    them: the API has no per-article data before 2015-07, so they came from a different measurement
    system. Archived for provenance only.

13. **Search folds the characters NFD cannot decompose, before NFD** — `ł`, `ø`, `ß` and the rest of
    `FOLD` in `table.js`. They have no Unicode decomposition, so NFD alone leaves them intact and
    "lutoslawski" misses "Lutosławski". A name that needs a new one means a new `FOLD` entry, and
    the suite types a folded query so the RULE is checked rather than the table.

14. **`scripts/make-og-svg.py` duplicates chart.js's scales on purpose.** Same log domains, same
    jitter (`spread_jq()` / `spreadJq()`), same emphasis, the same two uniform radii, the same
    short-name rule from `names.js`. It renders the Fame view AT REST, which is what a bare URL
    opens on, so no derived ring and no second repertoire ever reaches it. Change an encoding in
    `chart.js` and change it there too, or the share card stops matching the page. Duplicated rather
    than shared because the app must not ship a build step and the card must not ship a JS runtime.

15. **A canonical title is only canonical TODAY, so a page MOVE is a hole in the series.** The API
    counts the string requested, so months before a move were counted under the name the article
    held then and asking the current one returns the redirect traffic nobody followed. Fanny
    Hensel's article sat at "Fanny Mendelssohn" until March 2026 and shipped a median of **500**
    against a real **5,217** — and the app NARRATED the artefact, firing `SPIKE` and captioning a
    rename as an obituary. Those two figures live here and nowhere else; `pagemoves.py` points at
    them rather than restating them, because two files stating one measurement is how they drifted
    apart once already. `scripts/pagemoves.py` is the one place this rule lives, in three
    deliberately separate parts. `step()`/`suspects()` are offline and only generate suspects,
    because the shape has no clean threshold. `find_moves()` reads the MediaWiki move log, which
    STATES the old title and the date. `confirm()` throws out the hops the numbers do not support,
    because **the log records events, not tenures**: a move reverted twenty minutes later leaves the
    same two entries a permanent one does. The test is that traffic CHANGES HANDS across the move.
    **The month of the move itself is null.** A move happens on a day, so either title alone is a
    partial month and the sum quietly adds the redirect share every other month excludes — enough to
    invent a peak, which invariant 9 makes visible because the sparkline prints exact counts on
    hover. `null` already means "no answer to give", already breaks the path, and is already dropped
    from the median.
    **The repair is not a migration that happens once.** A refetch overwrites the stitched series
    with the API's per-title answer, so `fetch_views.py` re-applies every recorded move on every run
    that touches the title, and `data/pageviews.json`'s `moves` block records what it did — an EMPTY
    list meaning "the log was asked and said none", which stops a no-op run re-investigating the
    same noisy articles and is how `validate.py` tells genuine growth from an unchecked rename. **A
    chain on record is trusted, never re-derived**, and nothing records an answer it does not have:
    a log that could not be READ and a source that did not ANSWER both leave the series and the
    record exactly as they were, and the gate then fails on a recorded move whose stitch is missing.
    Re-confirming gave a good record a way back out, so a chain only ever goes from non-empty to
    empty by a human editing the file.
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
    verifies it, not because the rule is trustworthy**: `build_data.py` emits `""` only where its
    own reduction reproduces the scraped category, `validate.py` re-derives every one against
    `data/imslp-join.json` with an independent copy of the line, and `app.js` restates it a third
    time in JS with `ui.test.mjs` reading the `href` the browser ends up with. What is COUNTED is
    distinct **works, not pages** — one page can hold a whole cycle — and invariant 11's rule
    applies to that parse (`scripts/imslp-audit.py`). What the UI CALLS them is "quartets", looser
    and deliberately so: it is IMSLP's own category and what the reader came for. **The thing that
    must never happen is subtracting it from `quartets`**, which is how many the composer WROTE,
    from Wikipedia prose; the two columns sit one apart, routinely disagree, and answer different
    questions from different sources. Copy about absences is the other half: "no quartets **found**"
    and "no IMSLP page found", never "not on IMSLP" — no P839 claim, no page linking their article
    and no name guess reaching them is evidence, not the same as having asked.

## Testing

**The ethos, measured.** A mutation run in Sep 2026 — 39 plausible one-line bugs injected, suites
run, tree restored — caught 25. The data gate caught 6 of 7, the browser suite 13 of 22,
`sw.test.mjs` 1 of 5. Every miss was a pure function or an untested entry point, and not one was a
layout or interaction bug. Four rules come out of that:

**Budget checks by how silent the failure is, not by how much code there is.** A chart bug is
visible the moment you open the page; a precache bug is visible only on somebody else's installed
client a month later. Coverage should run the other way round from file size, and today it does not.

**A check may not read its expectation out of the code under test.** A check that derives its
expectation from the function it is checking is unfalsifiable for exactly that value —
`fetch_views.test.py` did, and runs against a FROZEN clock now. `sw.test.mjs` reads `BOOT` out of
`sw.js` the same way and is left alone on purpose: it is vendored pwa-starter, so the fix belongs
upstream. Where anti-drift pushes you there, cross-check two independent artifacts instead.

**Prefer a positive assertion.** `!panel.includes(exact)` passes when the formatting differs, not
only when the rounding is right.

**A number the repo can compute does not belong in prose at all.** Pinning one with a lint is the
wrong branch of the built-or-cut rule, and it was taken and reverted (#67, #74): a check cannot tell
a reflowed paragraph from a stale fact. When a claim is about behaviour, test the behaviour; when it
is a count, read it off the thing that holds it.

And the growth rule: **a check earns its place by failing without the code it covers, and keeps it
by being the only one that does.** `ablate.py` enforces the first half. The second half is why
deletions are welcome — re-run the suite without a check, and if nothing else noticed, it was never
holding that property up.

No test framework, and nothing to install. Each of these states its own rules in its header; what
follows is the directory and the few rules that reach outside the file.

| run | asks |
|---|---|
| `python3 scripts/validate.py` | **the data gate** — `composers.json` against its schema, the other caches, `readership.json` and the previous commit. Run it after every pipeline run. |
| `scripts/ui-test.sh` | the behavioural suite, against a real Chrome over CDP. |
| `python3 scripts/ui-test.test.py` | the runner's own port derivation, no browser needed (#49). |
| `node scripts/names.test.mjs` | the display-name rules, three cases against the shipped roster. |
| `node scripts/sw.test.mjs` | the SW fetch handler under mocked globals. |
| `python3 scripts/sw-lint.py` | the precache contract (invariant 1); `--base REF` is the branch half. |
| `python3 scripts/og-lint.py` | the link preview: card size, meta length, and the counts that SHIP to readers. |
| `python3 scripts/pagemoves.test.py` | invariant 15's pure parts, against a stubbed move log. |
| `python3 scripts/fetch_views.test.py` | the page-view cache, `fetch` stubbed and the clock frozen mid-month. |
| `python3 scripts/imslp.test.py` | the IMSLP join's parses and judgements, all offline. |
| `python3 scripts/fetch_imslp.test.py` | what a warm crawl ASKS FOR, and what it declines to (#62). |
| `python3 scripts/codehash.py` | is a change comments-only, or did code go with them? |
| `python3 scripts/fix-lint.py --base REF` | a branch changed source and touched no test. |
| `python3 scripts/ablate.py --base REF` | the branch's tests over the base's code — do they still pass? |
| `python3 scripts/record-lint.py` | did a number reach a comment or a docstring? Hook-only, warn-only. |
| `python3 scripts/volume.py` | how much of this repo is prose, and is this change adding more? Hook-only, warn-only. |
| `scripts/audit_counts.py`, `audit_redirects.py` | not automated: evidence printed for a human to grade. |

Everything that needs neither a browser nor a network runs in CI, and since #56 so does the browser
suite — `checks.yml` has a `ui` job with `xvfb-run` and node 22 (the CDP client is the global
`WebSocket`). `ui-test.sh` skips cleanly where no Chromium is installed, which is right for a laptop
and wrong for a runner, so `REQUIRE_BROWSER=1` turns that skip and both pointer warnings into a
failure. Still run it by hand after touching `chart.js`, `table.js` or `styles.css`: it is faster
than a push, and a UI change is one you want to LOOK at. The bigger prize of a browser on the runner
is that `ablate.py --with-ui` runs there too.

**The two branch gates read TWO commits**, so `fix-lint.py`, `ablate.py` and `sw-lint.py --base` run
on pull requests only. A `No-test: <reason>` trailer skips both gates, scoped PER FILE to the ones
its own commit touched — so an untested source change is a sentence somebody wrote on purpose and a
reviewer can read, not a silence. A file edited again with no trailer is back in the gate.

**Four rules hold inside the browser suite**, and a new check answers to all four. **Every wait is a
poll, not a budget** (#48): the one fixed wait left is `TWEEN`, used only before a "nothing moved"
assertion, which has no signal to poll for. **A POINTER is a platform fact and cannot be emulated**
(#50) — CDP accepts `hover`/`pointer` and ignores them — so the suite needs a real Xvfb display and
section 2 asserts which pointer it got. **No check reads a PIXEL**: `system-ui` resolves to a
different face per platform (#53) and the monthly top-up moves every dot, so the DOM is the oracle
and the PNGs are evidence for whoever reads a failure. **A boot is a claim, not a reset** (#48):
`rest()` returns through the app's own controls and reboots only when some state is out of place,
recording where, so a reset that quietly reboots cannot hide the app failing to reset.

`scripts/refresh.py` is not a test but the same discipline: it decides whether a top-up is DUE, runs
the three pipeline stages, refuses to bump `V` if `validate.py` fails, and is a pure no-op
otherwise. `.github/workflows/refresh.yml` runs it monthly and opens a PR — with the built-in
`GITHUB_TOKEN`, which does not trigger `checks.yml`, which is why refresh.py runs the gate itself.
The gate must not be skippable because a robot opened the PR.

## Design artifacts

`mocks/` holds the artboards a design decision was made from — currently the canvas that chose the
Fame view, drawn from `composers.json` by `mocks/gen.py`, which duplicates chart.js's scales for the
reason `make-og-svg.py` does. Nothing there ships and nothing there follows a change to `chart.js`:
it is a record of a decision, not a second implementation of one.

## Conventions

Each rule below is the part a session needs BEFORE opening a file. Where the reasoning is local to
one function it stays in the comment at the site, and this names the site rather than repeating it.

- Vendored pwa-starter files carry `pwa-starter: <file> @ <sha>` near the top. Keep the stamp when
  editing them; it is how `check-downstream.py` upstream finds this repo.
- Comments explain *why*, and especially what breaks otherwise. Don't narrate the next line, and
  don't recount how a bug was found — that is the commit message's job.
- **A comment may not assert a mechanical fact about the code beside it — that becomes a check, or
  it goes.** A comment cannot go red, so a stated join key, count, list or threshold is correct when
  written and silently wrong later (#42). `Chart.missingNames()`, `Names.staleOverrides()`,
  `unfilterableGenders()` and `unreachableRepertoires()` are the pattern: turn the claim into
  something a suite asserts, or write it loosely enough to stay true. For the DOCS the answer is not
  a lint (#67) — it is not writing the number. A comment about WHY is never in this category, which
  is most of them, and none of this is an argument for fewer comments.
- **A fix ships with the test that goes red without it — not with the next review.** Run the fix's
  test against the tree WITHOUT the fix and watch it fail, before proposing it; `ablate.py` enforces
  it on a branch, but the discipline is the point. PR #23 ran six rounds and four of them fixed a
  defect in the previous round's fix, every one shipped on a green suite. When there is genuinely
  nothing to assert, say so in a `No-test:` trailer rather than leaving it silent.
- **Prose the app can FALSIFY is built or cut; only prose it cannot is typed — and CUT is the first
  branch to try.** It catches claims with no number in them: a sentence naming the axes was true in
  Fame only, and was cut rather than derived per mode, because the axes are already stated twice on
  screen (#24). The built half fails the same test when a claim can change LENGTH — a generated lede
  emptied under some filters, collapsing the paragraph and lifting the pill you had just pressed
  (#27, #35). **The lesson is the ordering**: before building a mechanism to make prose behave, ask
  whether the prose should exist. `#count`, the search placeholder and `setProv()` stay built
  because each is the ONLY statement of what it says, and none of them can empty.
- **The provenance line is built, not assigned.** `setProv()` linkifies every Wikidata property id
  it prints, because an id is jargon a reader cannot check from the page. It links the TEXT rather
  than storing anchors in `composers.json`, which is data and carries no markup. Setting
  `$("prov").textContent` directly again would silently drop every link.
- **A number printed beside the chart counts the PLOTTABLE rows.** Rows with no stated quartet count
  are in the table only, and three of them are the roster's earliest births, so the empty panel once
  said "born 1582–1989" beside an x axis starting at 1709. `Chart.plottedStats()` is the one place
  that answers "what can the chart place". The same split governs the app's stated CLAIMS:
  `manifest.json` and the link preview describe what the page DRAWS, while `#count`, the search
  placeholder and the provenance line count the rows the table holds. The provenance line is where
  the difference is named.
- `index.html` owns structure, `styles.css` owns looks, `app.js` owns boot and the shared state
  (which composer is selected, which filters are active). `chart.js`, `table.js` and `histogram.js`
  never talk to each other — they share `names.js` and `Chart.colorOf`, which are read-only lookups,
  not state. The filters compose in `applyFilters()`, where each source returns "a Set of indices,
  or null for everything" and they are intersected. The gender filter is the one with no module of
  its own (`genderMatches()` in `app.js`): three buttons and a string, nothing to render and no data
  to hold. A fourth filter that DOES draw something belongs in its own file, on the same contract.
- **`names.js` loads before `chart.js` and `table.js`, and `Names.setData()` runs before either gets
  data.** The short form of a name is a function of the WHOLE roster, so neither module can display
  a name until the roster has been counted. It is a SHELL and a BOOT dep like every other
  load-bearing script.
- **The table and the chart show short names; the detail panel shows the full title.** `names.js` is
  the only place that takes a canonical name apart, and it is a heuristic. BOTH forms come from one
  shared-surname map, so the two can never disagree about who needs more than a surname: `filed()`
  gives the table "Haydn, Joseph", `short()` gives the chart "M. Haydn", and a shared surname whose
  initials also match falls through to the full name. The panel, the hover flag and the row's
  `title` keep the canonical title, where recognising the person is the job. **One exception, in the
  chart form only: a surname only one composer is READ for prints bare** — and the test has to stay
  decisive, because readership is refetched monthly, so a floor without a MARGIN is drift rather
  than hypothesis. Not in `filed()`, which sorts on what it prints. This is why `Names.setData()`
  takes readership alongside the names, as a PARALLEL array for the reason `build_data.py` carries
  canonical titles in one.
- **A chart label prints the short name, not the canonical title.** Because `pickLabels()` is
  first-come-first-served on space, halving every box is what lets the names behind it find room at
  all. The label text and the width estimate must come from the same string.
- **Labels are a function of zoom, not a list.** `pickLabels()` spends a budget that grows with the
  zoom on frame-culled candidates, so pinching in names what is in the frame. In Fame the curated
  names are the SEED and fill the budget first; beyond them the ranking is `prom`, recomputed in
  `setFilter()`/`setData()` because a filter must rank its own group. The one special case is the
  resting unfiltered Fame view, where the budget is pinned to the seed so the view says exactly what
  it is about — also the state `make-og-svg.py` draws.
- **The ring follows the filter by RANKING; the fill follows it by TASTE** (#7). `refreshEmphasis()`
  fills a budget DERIVED from `OUTLIERS` with the curated outliers the filter kept and then by
  `prom`, the same seed-then-rank shape the labels have. Every channel that follows emphasis reads
  `named()`, which reads the DERIVED set, so adding a channel needs no further wiring; `namedSet`
  stays the curated set where that is what is meant. Derived rings are seeds in `pickLabels()`,
  because a dot the view rings and then declines to name points at a composer it refuses to
  identify. The FILL is never derived — it is an editorial claim no ranking reproduces — so the
  women's group got a SECOND hand-written list, and because that fill and the sentence naming it are
  ONE claim, `REPERTOIRES` carries both and `renderLegend()` prints `Chart.repertoireLabel()`. Both
  lists answer to the same neutral noun, which is the other way out of invariant 8's wrong-channel
  trap. `chart.js` states the rest: the `MIN_FIELD` floor, and why `MIN_SEP` is measured in SCREEN
  space and re-derived by `setMode()` and `resize()` as well as `setFilter()`.
- **A filter fits the frame, and the fit is the RESTING view.** `computeResting()` is the one answer
  to "where should this chart be sitting right now": identity with no filter, the box containing the
  kept dots with one. `setFilter()` transitions there when the gesture settles, never mid-drag;
  `resetZoom()` returns there rather than to the full extent; `zoomed()` is measured against it, so
  a filter that fits at 4x does not light the reset button. It is measured from a `layout()` at
  `zoomIdentity` rather than from the scales, so a fourth encoding cannot forget to update it, and
  it must stay a pure function of the filter, the mode and the box or the memo is meaningless and
  "reset" has nothing to return to. This works because a filter here is a HIGHLIGHT: the rest of the
  cloud is still drawn faintly, so closing in shows the group against the ghost of its field.
- **Anything the zoom moves must be clipped.** `chart.js` clips the dots, labels, selection ring and
  lens to `#plot-clip`; a new zoom-transformed group needs the same `clip-path`, or a pinch lays it
  out over the axes and past the card edge.
- **One filter row, above everything it scopes.** `#filters` is a sibling of `.grid`, not a child of
  either card — all three filters scope both views, and a filter drawn inside one card says
  otherwise. `placeFilters()` moves it into `#viz` in full screen and CSS drops its search half
  there to keep the chart's height.
- **The chart's controls sit ABOVE the plot, because the plot's height is a function of the VIEW.**
  `measure()` gives each mode its own aspect ratio, so a row underneath moves when you press it,
  lifting the pill out from under a second tap at the same spot. **Nothing a finger rests on may be
  placed by a box the same press resizes.** Full screen is the exception and stays underneath:
  `#plot` is `flex:1` there, sized by the viewport rather than the view. Above the plot costs a
  phone's first screen (#29), and `placeDetail()`'s phone anchor moved with the row — it inserts
  before `.legend`, or the panel lands above the chart.
- **No filter control appears or disappears at all**, which is the rule above satisfied by
  construction: #31 fixed the brush's own Clear button in place twice, #35 deleted the category
  instead. One permanent `Reset filters` clears all three filters and is `disabled` at rest and
  accent-filled when live — a state change that moves no box, which is why `applyFilters()` may
  light it on the drag's first frame, above the `settled` guard. Being the page's one answer to "is
  anything filtered?" is why `anyFilter()` reads the query TRIMMED, the way `Table.matches()` does.
  It does not focus the search box, though `#clear` does: this one is a card below the row, where
  `focus()` scrolls the viewport back up over a box the reader had left. For the next layout fix
  here, note that an ID selector out-specifies `.btn` — that is how this button sat under the touch
  floor unseen.
- **The lens is an OVERLAY, not a view — a checkbox in the controls row, over all three modes.** As
  a fourth pill it differed from Timeline in a fisheye and no zoom, neither of which is a way of
  reading the DATA, so the switcher claimed four pictures where there are three. `warp()` applies
  the fisheye LAST, in screen space, which is what lets one lens serve three modes with no per-mode
  case: what it moves is pixels, so what you click is still what you see. `#v=lens` still resolves,
  to the timeline with `l=1`. It is a CHECKBOX because it is a thing you leave on, not a picture you
  switch to, and it re-lays out nothing, which is what makes it safe in a row above the plot. Four
  of its rules reach past `chart.js`, which states the rest. **It takes away one gesture, on a touch
  screen only** — the AIM and the PAN are the same one-finger drag on a phone and two different
  inputs on a mouse, so it lives in a `zoom.filter` on `event.type` rather than in unbinding the
  zoom, which silently stopped a reader's framing from working. **The frame is LEFT where it was and
  the AIM is dropped**, so `zoomed()`, `resetZoom()` and `setLens()` ask nothing about the lens
  while `baseLayout()` and `resize()` un-aim it. **d3 still has to be told the box** even where no
  gesture reads it, because it re-reads `extent` when it SCHEDULES A TRANSITION — and the `__zoom`
  sync beside those setters must run only when it would change something, since `zoom.transform`
  interrupts and a no-op sync cancels a transition mid-fit. **It does not earn labels**, which was
  tried: a ZOOM earns names by culling the frame, and the lens culls nothing.
- **Share and Full screen are icons ON the chart wherever the controls row will not hold them on one
  line**, which is what PAYS for the third button in the row. `placeChartTools()` reparents
  `#chart-tools` into `#plot`, on the same one-element-moved contract as `placeFilters()` and
  `placeDetail()` — never a second copy, because `#fs` holds the pressed state and `share()` a
  timeout on its own label. **The condition is a MEASUREMENT of that row rather than a device, and
  it is TWO intervals**, because what decides it is the CARD and the two are not monotonic in each
  other. `app.js` holds the only copy of the breakpoint and the measurement behind it, `styles.css`
  scopes the icon look to `#plot > #chart-tools` so the look follows the DOM rather than re-deciding
  the width, and `ui.test.mjs` defends the two edges by pressing Share at the first width in each
  band — which is what caught them moving when the lens became a checkbox 28px wider than the pill.
  Five things a change here must keep. The words stay in the DOM, visually hidden rather than
  `display:none`, because they are still the buttons' accessible NAMES. The label goes into the
  `.btn-t` span and never onto the button, which would delete the icon beside it — and under the
  breakpoint that span is the name and not the face, so `share()` also acknowledges in the glyph,
  raced against `STALL` because a clipboard write that never SETTLES is not a rejection the catch
  can see. Both buttons carry a `title`, because a clipped label is a name a screen reader can read
  and a pointer cannot. The print rule names `#chart-tools` separately from `.controls`, since on a
  phone it is no longer inside it. **A wheel over the glyphs is a wheel over the CHART**: d3-zoom
  binds to the `svg` and `#chart-tools` is a SIBLING of it, so `Chart.wheelInto()` re-dispatches
  into the CURRENT svg — `build()` makes a new one on every `setData`/`setMode` — while the DRAG is
  deliberately not forwarded, because a control swallowing a drag is the platform convention and
  swallowing a wheel is not. And they sit in the AXIS-TITLE BAND, over no dot in any view, on a
  touch target that is felt and not seen, so a dot it overlapped would silently stop being TAPPABLE.
  **Top right is the trap** — it reads as empty in Fame and is exactly where the SWARM piles up,
  which is what judging a shared overlay from one view gets you.
- **A specificity trap runs through this stylesheet**, and it has shipped three times: a
  `pointer-events="none"` ATTRIBUTE on the brush grips that any later `#hist .grips path` rule would
  outrank, `#hist-clear` sitting under the touch floor because an ID out-specifies `.btn` (#31), and
  the chart-tools glyphs, where a bare `#fs .ico-out` loses to the group's full `#plot >
  #chart-tools` prefix and drew both glyphs at once. Carrying the full prefix is not tidiness.
  `#plot > svg` is the same shape: it means THE CHART, and as a descendant selector it stretched an
  18px glyph to fill its button.
- **The readership brush's handles are crossfilter's grips, and the rect underneath is the hit
  area** (#40). d3-brush sets `fill:none` and `pointer-events:all` on the brush `<g>` and both
  inherit, so painting `.handle` drew the hit area wearing the costume of the control;
  `histogram.js` draws the visible tab instead. The load-bearing line is `pointer-events="none"` on
  the grips group, which sits on top of the brush and outside it, so a hittable grip swallows the
  press and the drag does nothing.
- **The `hidden` ATTRIBUTE is only `display:none` in the UA sheet**, so ANY author `display` on the
  same element beats it — silently, since the element stays hidden to a screen reader and to
  `.hidden` in JS while being drawn. `styles.css` answers it once with `[hidden]{ display:none
  !important }` and `ui.test.mjs` notices if that line is dropped or out-specified.
- **There is ONE detail panel, and `app.js`'s `placeDetail()` moves it.** Beside the chart above
  900px; inside `#viz` (`.compact`) on a phone and in full screen at any width. Never render a
  second compact copy — the selection, the nav buttons and the `.on` state all assume one element.
  The two in-card positions differ on purpose: BELOW the plot on a phone (free to grow; nothing
  above it moves), ABOVE the plot in full screen as a fixed-height strip drawn even when empty.
  **Its height must stay constant** there: `#plot` is `flex:1` in full screen, so a box that grew on
  select would trip the ResizeObserver and re-lay out the chart under the finger that just tapped
  it. `tight()` trims the content to fit.
- **A hover previews into the detail panel, so its box is reserved wherever a pointer exists.**
  `@media (hover:hover) and (pointer:fine)` gives `.compact` a `min-height` covering its TALLEST
  state; without it, moving the mouse across the chart pumps the legend up and down. Touch screens
  get neither rule — no hover to churn, and the space is the chart's. The reservation is MEASURED:
  the suite prints the pinned panel's real height and fails when `min-height` falls short, pinning
  the composer with the LONGEST caption, because the dot an earlier check happens to hover is not
  the worst case.
- **Anything that handles its own arrow keys marks itself `[data-keys]`.** `app.js`'s document
  keydown listener steps the SELECTION on left/right, and its guard has failed both ways: as
  `matches("input, textarea")` it stole the sparkline's arrows, and `input` alone matches a CHECKBOX
  that answers to Space, so the lens toggle ate them. It is `input:not([type="checkbox"])` now, and
  the suite presses a key with the box focused rather than trusting the selector. Escape is handled
  before the guard, because it means "back out of this" wherever focus is. The readership brush
  still owes a keyboard path (#81); when it gets one it needs the attribute and no edit to the
  listener.
- **The phone table has to fit in a font you do not choose.** `system-ui` is SF on a Mac, Segoe on
  Windows and DejaVu on most Linux, and DejaVu overflowed the four phone columns at 390px outright
  (#53) — which is how the suite came to fail on a Linux runner and nowhere else. **An abbreviation
  is not free to a reader who can SEE it**: the accessible name has to contain the drawn label, per
  WCAG 2.5.3, or a voice-control user says "click Qts" against a name that reads "Quartets" and the
  column cannot be sorted at all. So both spans stay in the name, the drawn one first, and the word
  is moved off screen rather than `display:none`d. `ui.test.mjs` asserts the name the browser
  COMPUTES, because an `aria-label` added later overrides the markup while a check written against
  the two spans stays green — and it asserts 360px as well as 390px, since the old table cleared
  390px in the narrowest font while overflowing 360px in every face. A new column, or a longer
  header, has to be measured the same way rather than eyeballed on a Mac.
- **`.seg` is a look, not a behaviour.** Two pill groups wear it — the chart view switcher and the
  gender filter — so anything binding `.seg button` must scope itself (`.controls .seg button`).
  Unscoped, the switcher's handler landed on the filter's buttons and a pill press called
  `setMode(undefined)`: the chart left every named mode at once and the URL grew `#v=undefined`.
- **The sparkline's caption names the spike if there is one and the trend otherwise.** A fixed "peak
  N× typical" cried spike about noise on half the roster, because a composer read thirty times a
  month hits ninety by chance, and buried the real story for the steady ones. `SPIKE` tests the peak
  against the 95th PERCENTILE of that composer's own months, which is scale-free and judges a small
  noisy article against its own noise. The peak hairline is drawn ONLY in the spike branch — an
  annotation pointing at a month nothing mentions has no referent.
- **The sparkline is the app's one optional part, in both halves.** Its data is precached but not a
  BOOT dep and is fetched after the paint; `sparkline()` returns null when it has not arrived, when
  a composer has fewer than two months of data, and in the full-screen strip, whose height must not
  change. Its colours are the one drawn thing here NOT baked into the SVG by JS: it is plain inline
  SVG, so `var(--accent)` reaches it and `Theme.subscribe` has nothing to re-bake (invariant 3 does
  not apply, and a check keeps the `stroke` attribute absent so nobody "fixes" that). Linear y and
  zero-based, unlike the chart's log readership axis: log is there because the ROSTER spans orders
  of magnitude, but within one composer the question is proportion, and a log baseline flattens
  exactly the spike the line exists to show.
- **Every sparkline shares one month axis, so the blank left of a young article has to be named.** A
  shared axis is what makes two composers comparable, and it means articles created after 2015 draw
  over the right-hand end and leave the rest empty — which under a line chart reads as "nobody read
  this" rather than "not written yet". The label row prints `from Jul 2025` instead of the axis span
  in that case. A null month is a BREAK in the path for the same reason (invariant 10); joining
  across it would draw a line down to zero and back.
