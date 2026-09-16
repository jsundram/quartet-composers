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
   Nothing about this needs a human: `sw-lint.py --fix`, which the pre-commit hook runs, bumps the
   tail and re-stages `sw.js` in the same commit, and declines only where writing would have been
   wrong (its header says which three states). `--bump` is the same increment with no git in it and is
   what `refresh.py` calls, so one piece of code knows how to move `V`. That covers one commit;
   `--base REF` in CI covers the branch, because two PRs off one base can bump identically and merge
   to a net delta of zero (#32), which looks correct from either side alone.

2. **`sw.js`'s `BOOT` must list every script the page dies without.** Every pixel here is drawn by
   JS, so a cached `index.html` without `d3.v7.min.js` or `composers.json` is a headline over an
   empty box; the offline page is strictly better, and one online launch repairs the precache. A
   new load-bearing script goes into `SHELL`, into `BOOT`, and bumps `V`. `readership.json` and
   `imslp-works.json` are the deliberate exceptions — SHELL but not BOOT — because what they feed
   is what nothing waits for: the sparkline arrives after the first paint, and the IMSLP work pages
   are the detail behind a column whose number and link are already in `composers.json`. Gating a
   navigation on either would trade a working page for an offline notice over a decoration.

3. **Colors read into JS can't be reached by a CSS variable swap.** `chart.js` bakes `--c-*` into
   SVG fills and `app.js` into the legend. Both re-read through `Theme.getCssColor` inside
   `rerender()`, which `Theme.subscribe` fires on every theme change — never `getComputedStyle`
   directly. A fourth component that bakes a colour needs a fourth `rerender()` wired in there.

4. **`composers.json`, `readership.json` and `imslp-works.json` are generated; never hand-edit
   them.** `scrape_list.py` -> `fetch_wikidata.py` -> `fetch_views.py` -> `fetch_imslp.py` ->
   `build_imslp.py` -> `build_data.py`, each caching into `data/`. Only the fetches touch the
   network, so a rebuild is offline and reproducible. **`build_rows()` in `build_data.py` is the
   one place the roster is decided**, and `build_imslp.py` CALLS it rather than reading
   `composers.json`, which it cannot — it is upstream of a file that now carries an IMSLP column.
   Breaking the cycle is only half of why: a second reduction of the same caches would be a second
   opinion about who is on this list, and the join would file counts under names nothing looks up.
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
   The last stage writes ALL THREE shipped files from one set of caches and they must stay in
   lockstep: `validate.py`'s `check_history()` recomputes each row's median, min and max from that
   composer's own sparkline and fails when they disagree, and `check_imslp()` requires
   `imslp-works.json` to carry the same `generated` date and every composer's total to sit between
   the largest of their pages and the sum of them — NOT equality, because the de-duplication exists
   precisely because pages overlap. Files that are each internally consistent but built
   from different fetches are a drift nothing in the app can see — the panel would print one
   readership and draw another. `build_data.py` carries the canonical title in a list PARALLEL to the rows and reorders
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
   median of `STAT_MONTHS` monthly page-view counts (`build_data.py`), and at most that: a null is
   dropped, and a composer whose article moved inside the window has one fewer (invariant 15). Not
   however many months
   `data/pageviews.json` happens to cache. Widening that window would resize every dot on the chart
   and bake a 2016 readership into a 2026 picture — and it rebuilds CLEANLY, both files internally
   consistent, so `validate.py`'s `STAT_WINDOW` pins it in all three places that state it: the
   `views_months` axis, `readership.json`'s `stat_months`, and the `views_stat` prose the provenance
   line prints to a reader. Typed there rather than imported from `build_data.py`, or the check could
   only agree with the code it is checking.
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
   Of the articles in this roster that moved, only Fanny's moved inside the statistic window — the
   rest changed a sparkline and not one dot.
   **Do not sum redirects generally.** That is a different policy, measured and rejected:
   `audit_redirects.py` priced every redirect into every article and the median correction was 1.02x,
  invisible on
   a five-decade log axis, in exchange for a count that depends on how many aliases an article
   happened to accumulate. A move is not an alias; the article LIVED there.

16. **The IMSLP columns are TWO fields carrying THREE answers, and `imslp_cat` is the one that can
   tell them apart.** `imslp` is a work count and it is `0` both for a composer IMSLP holds with no
   quartets and for one nothing could place — deliberately not distinguished in the digit, because
   the reader's next move is the same either way. `imslp_cat` is `null` for the second (nowhere to
   link), `""` for a composer whose category reduces to `Surname, Forename`, and the category
   VERBATIM for the ones whose does not (`Shostakovich, Dmitry`, `Beach, Amy Marcy`). Shipping only
   the exceptions costs ~280 bytes against 13 KB for all of them, and it is safe **because the
   build verifies it, not because the rule is trustworthy**: `build_data.py` emits `""` only where
   its own reduction reproduces the category the scrape found, `validate.py` re-derives every one
   of them against `data/imslp-join.json` with an independent copy of the line, and `app.js`
   restates it a third time in JS with `ui.test.mjs` reading the `href` the browser ends up with
   for one derived composer and one override. What is COUNTED is distinct **works, not pages** —
   one page can hold a whole cycle — and invariant 11's rule applies to that parse, which is what
   `scripts/imslp-audit.py` grades against the page. What the UI CALLS them is "quartets", which is
   looser than the parse and deliberately so: it is IMSLP's own category and what the reader came
   for. **The thing that must never happen is subtracting it from `quartets`**, which is how many
   the composer WROTE, from Wikipedia prose. The two columns sit one apart, routinely disagree,
   and answer different questions from different sources. Copy about the absences is the other
   half: "no quartets **found**" for a composer IMSLP holds none for, and "no
   IMSLP page found", never "not on IMSLP" — what we know is that no P839 claim, no page linking
   their article and no name guess reached them, which is evidence and is not the same as having
   asked.

## Testing

**The ethos, measured.** A mutation run in Sep 2026 — 39 plausible one-line bugs injected into
source, suites run, tree restored — caught 25. The data gate caught 6 of 7, five of them failure
modes this repo has never had; the browser suite caught 13 of 22; `sw.test.mjs` caught 1 of 5.
Every miss was a pure function or an untested entry point, and not one was a layout or interaction
bug. Four rules come out of that, and they decide what gets written here from now on:

**Budget checks by how silent the failure is, not by how much code there is.** A chart bug is
visible the moment you open the page; a precache bug is visible only on somebody else's installed
client, a month later. Coverage should run the other way round from file size, and today it does
not: `sw.js`, the largest file here, is exercised through one of five entry points.

**A check may not read its expectation out of the code under test.** `fetch_views.test.py` derived
its window from `months_back()` — to stop a copy drifting, and unfalsifiable for exactly the value
it was named after: a `months_back()` ending ON the month in progress answered the question, the
case refused the month after that, and it passed (measured). It runs against a FROZEN clock now, and
the months are the calendar's. `sw.test.mjs` reads `BOOT` out of `sw.js` the same way and is left
alone on purpose — it is vendored pwa-starter, so the fix belongs upstream. Where anti-drift pushes
you there, cross-check two independent artifacts instead (a date function against a frozen clock,
`BOOT` against `index.html`'s script tags).

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
- `python3 scripts/record-lint.py` — **did a number reach a comment or a docstring?** The rule
  above says prose states a RECORD or no number at all, and that rule was in force while forty-nine
  claims went stale under it, thirty of them in one feature. **What it asks is not "record or
  not"** — that is a binary, and it sends a reader straight to a vaguer rewrite. It names three
  branches in the order the built-or-cut rule gives them, and the first is DELETE: take the number
  out and read what is left, because a clause that then says nothing was hosting the count rather
  than making a point. The pass that produced this tool under-applied that on itself — "there are
  884 links on this page whose text is a number" became "this column is hundreds of them", and one
  such link is exactly as wrong as hundreds. Nothing asked, because both gates
  import `codehash.unchanged()` and stop asking a comments-only hunk for a test — correctly, since
  a comment cannot be tested, and the side effect is that prose is the one unguarded surface here.
  It is HOOK-ONLY and WARN-ONLY: whether a number is a record is a judgement, so a nonzero exit is
  a prompt and never a verdict, and putting it in CI would block a PR on one. **It is not
  `prose-lint.py` reborn**, and the difference is the whole design — that one stored each claim's
  VALUE and re-checked it, so it could not tell a reflowed paragraph from a stale fact. This stores
  nothing: it asks only whether a number is NEW to a file's prose, comparing multisets over the
  whole file, so a re-wrap moves every number and reports none. The prose comes from
  `codehash.code_of()` rather than a second scanner — a file's prose is its source minus its code —
  which also means DOCSTRINGS are covered by construction, and they are 44% of the Python prose
  here. It reads the DOCS too — they are where `prose-lint.py`'s seventeen numbers lived, so a
  scan of source alone would leave the files that motivated the rule unwatched — and a fenced block
  there is code. It also reads SPELLED counts from eleven up, because "the shipped twelve chains"
  and "in thirteen cases" went stale this pass and a digit scanner sees neither; the floor is where
  it is because below it the word is ordinary English rather than a claim.
  `scripts/record-lint.test.py` pins every half; `reflow_is_silent` is the case it exists for, and
  ablating the tool found three defects in it — a four-figure count the regex could not see at all,
  a finding dropped when its line could not be located, and markdown handled by a reader that was
  never offered a markdown file.
- `python3 scripts/volume.py` — **how much of this repo is prose, and is this change adding more of
  it?** Hook-only and warn-only, for the reason `record-lint.py` is: the classifying is exact but
  the judgement is not, and CI blocking a large feature for being large is the wrong trade. It
  exists because the rule says a number the repo recomputes is read off the thing that holds it,
  and nothing held these — so every measurement was written fresh and they disagreed, once
  reporting `scripts/` at 83% against a real 35%. The disagreement is never in the counting; it is
  in four judgements an ad-hoc script re-decides each time, and `scripts/volume.test.py` pins all
  four: vendored by its STAMP rather than by a path list, a suite against the runner that launches
  it, what is excluded outright, and a docstring against a comment. A fifth has the teeth — a file
  `codehash` cannot classify is REPORTED, never skipped, because a bucket that omits what it could
  not read is a ratio that improves by failing, on exactly the files something is wrong with.
  **`--check` judges the CHANGE, not the total.** Both ceilinged buckets are well over today, so a
  check against the total would be red on every commit and unanswerable besides — nothing a reader
  can do to the file in front of them clears a ratio the whole repo owns. The commit's own ratio
  against the same ceiling is answerable, converges from wherever history sits, and says nothing to
  a change whose comments are proportionate to its code. Below a floor of added prose lines it says
  nothing at all, because a one-line fix to a comment is 100% prose and means nothing by it.
  **It bounds prose against the code it explains and says nothing about CLAUDE.md.** Measured over
  this repo's history the two do not move together: the app source held flat while this file grew by
  a third, so a doc-to-code ratio would license the briefing to grow on any commit that adds code.
  This file's ceiling is attention, and it is stated where the ceiling belongs rather than as a
  number here.
- `python3 scripts/validate.py` — **the data gate**, and the most important thing here. Every
  serious defect this dataset has had was a plausible-looking wrong number no test caught, so this
  compares `composers.json` against its schema, the other caches, `readership.json` and the
  previous commit. Run it after every pipeline run. `scripts/validate.test.py` proves it still
  catches each past incident; weaken a check and it goes red.
- `node scripts/names.test.mjs` — the display-name rules, offline, in the module loaded under a
  one-line `window` stub. It is the one app module with a suite of its own because it is the one
  that is PURE — a roster in, two strings out — and the most heuristic thing here: the last-word
  rule, the five kinds of name it is wrong about, and the floor-AND-margin that awards a bare
  surname. Three of its cases run against the shipped roster rather than a fixture, and they are
  what the shared-surname map is for: no two composers may get the same chart label, nor the same
  filed name, and sorting the filed column must keep every surname group contiguous. The counts
  this file used to state in prose — how many names the rule is wrong about, which groups qualify
  today — are gone; they moved every time the pipeline ran.
- `scripts/ui-test.sh` — the behavioural suite, against a real Chrome over CDP. **Its size is not
  stated here: run it and read the total it prints.** Some of its checks are registered in loops,
  so the literal `check(` count is not that total and no offline count is exact. A figure written here
  could only be re-typed by hand every time somebody adds a check, which is churn in exchange for a
  number the suite already reports. It starts
  its own server and browser and skips cleanly (exit 0) if no Chromium is installed — right for a
  laptop and wrong for a runner, where a job that quietly lost its Chrome would go green having
  tested nothing, so `REQUIRE_BROWSER=1` turns that skip and both pointer warnings into a failure
  and `checks.yml` sets it in both jobs that reach here. Every check
  in it exists because something was actually broken; read the header before deleting one.
  **Every wait in it is a poll, not a budget** (#48): `settle()` re-asks the page for the state the
  next check reads, `goto()` polls for a drawn page, and `idle()` asks d3 whether the zoom tween
  is still running. The suite used to spend ~100 of its ~110 seconds asleep in fixed waits, most
  of them following synchronous DOM work, and a fixed wait is wrong in the other direction too — a
  cold runner can miss it. The only fixed wait left is `TWEEN`, one frame past chart.js's 420ms
  transition, and it is used ONLY before a non-event assertion ("nothing moved"), which has no
  signal to poll for. A new check that waits should say what it is waiting for.
  **A POINTER is a platform fact and cannot be emulated** (#50). The lens, every hover preview and
  the panel's reserved height all need `(hover:hover) and (pointer:fine)`, which chart.js reads
  once into `TOUCH` and styles.css reserves the panel behind. macOS reports it unconditionally and
  a headless Linux Chrome reports no pointing device at all, so all of them failed on every runner
  that was not a Mac. `Emulation.setEmulatedMedia`'s `features` list is NOT
  the fix TODO prescribed: it accepts `hover` and `pointer`, returns success, and ignores them.
  `--blink-settings` is worse — it works until the first `setTouchEmulationEnabled`, whose restore
  then clobbers the pointer type for every page in the browser, so a suite that interleaves phone
  and desktop sections cannot use it. `ui-test.sh` runs Chrome on an **Xvfb** display where there
  is one, which gives it a real pointer that a touch toggle restores TO, and section 2 asserts
  which of the two it got rather than leaving eight later checks to imply it.
  **And every CDP call has a watchdog.** `send()` rejects after 60s, the socket closing rejects
  everything pending, and both print the checks that had already run — a dropped reply used to end
  the run as node's bare "unsettled top-level await" with zero lines of output, which is how one
  oversized screenshot read as a random hang. That screenshot is the other half, and its lesson is
  **height spends width**. Print un-scrolls the table, so the page is 884 rows and ~35,000px tall,
  and asking for it at deviceScaleFactor 2 made this Chromium drop the page target. The first fix
  halved the SCALE, which was wrong: the screenshots are deleted unless `KEEP=1`, so what they are
  for is the one look a failure gets, and whoever takes it reads a copy resized to fit a long-edge
  cap and a visual-token budget. That resize is driven by the LONG EDGE, so the full-page shot
  lands 94px wide at either scale — fewer megapixels bought nothing. `shot()` takes a `clip` now
  and the print one clips its HEIGHT, to the 30th row: everything print changes is above the fold
  and the rest is the same row 850 more times. `ui.test.mjs` 9b pins the property that bought —
  every PNG the run wrote still resolves at 1:1 or better after that resize, measured off the
  IHDR — because a comment claiming it could never go red.
  **No check reads a PIXEL, deliberately.** The DOM is the better oracle and every check here
  asserts against it; a screenshot hash or baseline would go red for two reasons that are not
  bugs — `system-ui` resolves to a different face per platform (which is what #53 was, arriving
  through the one check that DID read a measurement) and `refresh.py` tops the data up monthly by
  design, moving every dot. So the PNGs
  are evidence for whoever reads a failure, and what they needed was to still EXIST then:
  `ui-test.sh` deleted `$OUT` unless `KEEP=1`, which is a guess made before a run about a need
  that arises after it, so a failing run destroyed its own evidence. It now keeps the directory
  whenever the suite fails — including when Chrome never opened, so `chrome.log` outlives the
  scrollback — and prints the path either way. A clean run still cleans up.
  **And a boot is a claim, not a reset** (#48 again): most of the 53 navigations it made were a
  way back to a known state, a full boot to clear a pill or press one. `rest()` gets there through
  the app's own controls, then reads every piece of state a boot would have cleared and boots
  after all if any is out of place — recording where, which the second-to-last check reports, so a
  reset that quietly reboots cannot hide the app failing to reset. The boots left each test a URL
  (a bare one opens on Fame, `#v=readers` still resolves, a `#g=`, `#r=` or `#c=` link arrives
  applied, an offline reload paints), straddle a change of touch emulation, because chart.js
  reads `TOUCH` once at boot, or follow a full-screen round trip, after which this Chromium
  forwards no wheel event to the page until something registers a listener afresh. A
  section that only needs another viewport asks for it and waits for the re-layout (`relaid()`);
  a view switch goes through its pill (`view()`). One wheel event now carries a whole zoom, and
  it is checked for rather than assumed: this Chromium drops a synthetic wheel now and then under
  emulation, so `wheel()` re-sends one that moved nothing and the run prints how often it had to.
- `python3 scripts/ui-test.test.py` — the RUNNER rather than the app: the two ports
  `ui-test.sh` derives from the checkout's own path, in cases that need no browser. They
  were fixed at 8765/9333 and are cleared with a `pkill -f` that matches every process on the
  machine, so a second checkout starting up killed the first one's browser and server mid-run —
  and the victim was the run that had done nothing wrong (#49). Deriving the default gives every
  worktree its own pair while keeping it the SAME on every run here, which is what lets that clear
  go on reaping a browser left over from an INTERRUPTED run, the failure it was written for. The
  hash has 200 slots, so two worktrees can still land on one: the runner prints the pair, says so
  when it is clearing a port somebody else may be holding, and takes `PORT=` and `CDP=` to pin
  one. `--ports` answers out of the path and starts nothing, which is how the cases ask. It is
  a suite because the defect is invisible in the run in front of you and in CI, which never runs
  two at once — and because the way back to it is a one-line edit that looks like tidying.
  **The cases that are not about the sibling are about the stranger.** A 200-wide band covers ports
  people use — 8888 is Jupyter's, 9515 is chromedriver's — and a run that finds one held used to
  proceed: the server exits on "Address already in use" into a `/dev/null`, or the new Chrome
  fails to bind, and the suite then drives somebody ELSE's origin or debug endpoint and reports it
  as a suiteful of failures of this app. So the runner stops and says which port and why, `kill -0` on its
  own server being the oracle that needs no marker in the page, and every probe is bounded
  (`answers()`), because a process that accepts a connection and never replies hangs a bare
  `curl` for as long as it likes — which would be the same silence one step earlier.
  **The clear waits on the PROCESS, not on the port** — `pgrep` over the pattern the kill just
  used. What it waits for is OUR leftover dying, and a port probe cannot tell that from a
  stranger's live socket, so it spent the whole budget to report something the first `pgrep`
  already knew: 4s on every run that meets a squatter, and 8 of the 11 seconds this suite took to
  prove it. That is issue 48's rule — a wait says what it is waiting for — reaching the one loop
  that had kept a budget. The cases that start a full run pin PORT/CDP to **ephemeral** ports
  rather than deriving them: a run clears its pair machine-wide, and pointed at a derived slot the
  suite proving #49 would commit #49 against a sibling worktree.
  **And the runner is SOURCE to the gates now**, not a test file beside the suite it launches:
  `ablate.py`'s `COVERS` maps `scripts/ui-test.sh` to these cases, so a change to it has to be
  proved by one of them. Filed as a test — which it was, back when it only started a server and a
  browser — the port derivation was logic nothing ablated, and the branch that wrote it was
  ablated on one unrelated file alone.
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
- `python3 scripts/fetch_views.test.py` — the page-view cache's invariants, `fetch` stubbed, the
  cache in a temp file and the clock FROZEN at a mid-month date, so "the month in progress" is the
  calendar's fact and not `months_back()`'s opinion of it. It exists because the flat array has only two values and **every bug in
  that file has been a null no request justified** — invisible afterwards, because the array is the
  right length and every number in it is plausible, and the only symptom is that `todo` quietly
  stops asking. Some of its cases stub the move log and cover invariant 15: that a move is stitched and
  its month nulled, that the stitch is re-applied on every refetch, that a chain on record is not
  re-judged, that a logged move the traffic does not support is recorded and NOT stitched, that a
  source which does not answer leaves both series and record alone, that a log which could not be
  READ is not written down as "no move", and that a record collapsing to nothing is not written
  down either.
- `python3 scripts/imslp.test.py` — the IMSLP join's judgements, offline: the wikitext readers, the
  catalogue parse, the work counting and the date confirmation all read strings. It exists because
  every defect that join has had was a wrong PARSE presenting as a missing row, and a missing row
  here is invisible — nothing says how many rows there should be. A line-anchored field reader
  turned every IMSLP date into `None`, because the person template packs three fields onto one line;
  a pattern that stopped at the first `|` read the article title out of `[[wikipedia:{{#iflang:…}}]]`
  as the literal `{{`, which took out the six biggest quartet catalogues on the site while the long
  tail joined fine and the totals looked healthy. Neither crashed. Since #61 it also covers
  `catalogue()`, which returns the per-page work counts and the composer's total from ONE parse —
  derived twice, `imslp-works.json` could state one number on a row under a heading counting
  another and neither would look wrong — and `compress()`, which moved here from `imslp-audit.py`
  so the shipped rows and the audit page collapse a range of opus numbers the same way.
- `python3 scripts/fetch_imslp.test.py` — the crawl's REQUEST SEQUENCE, `get` stubbed against a
  dict-shaped wiki and the cache in a temp file. Separate from the suite above because it answers a
  question no reader of the cache can: that one asks whether a string parsed correctly, this asks
  whether a warm run asked the site anything at all. `fetch_works()` returned early on a cached
  listing, and the category crawl is the only place a work page or a composer can ENTER this
  pipeline — every other pass is keyed by a title it would never have been told — so a monthly run
  would have discovered nothing forever and exited 0 doing it (#62). No symptom: nothing says how
  many quartet pages IMSLP holds, every number in the cache stays plausible, and the file simply
  stops growing. So the cases assert what a run ASKS FOR — the categories listed again, a page
  that appeared between two runs reaching the markers and the work info, a composer page naming no
  identifier re-read and a `{{wp}}` link added since followed all the way to a resolved QID — and,
  just as hard, what it declines to ask for, because "re-ask everything" is `--refresh` and costs
  megabytes of unchanged wikitext against a volunteer-funded server.
- `scripts/refresh.py` — not a test but the same discipline: it decides whether a top-up is DUE
  (does `composers.json` already cover the last complete month?), runs the three pipeline stages,
  refuses to bump `V` if `validate.py` fails, and is a pure no-op otherwise.
  `.github/workflows/refresh.yml` runs it monthly and opens a PR. A PR opened with the built-in
  `GITHUB_TOKEN` does not trigger `checks.yml`, which is why refresh.py runs the gate itself — the
  gate must not be skippable because a robot opened the PR.
- `python3 scripts/codehash.py` — **is this change comments-only, or did code go with them?**
  A comment-compression pass through `chart.js` deleted `function hash()` and `const MIN_SEP` from
  inside the blocks it was rewriting, and the audit that missed it was a human reading a long diff
  for an ABSENCE. This isolates the code and hashes it: the AST for Python, where comments and
  formatting are absent by construction, and a scanner for JS and CSS that knows strings, template
  literals and regex literals, so `"http://x"` is code. The scanner is **verified by re-parsing**
  both the source and the stripped text with `node --check`, which is what makes its imperfection
  affordable — a misclassification leaves something that does not parse, so it degrades to "cannot
  tell" rather than to a false pass, and cannot-tell is a third exit code rather than a pass.
  Newlines survive the strip deliberately: collapsing them would hide a reflow of code too, and in
  JS it would change meaning (`return` and its value on two lines). A template literal is copied
  whole, so a comment inside `${…}` reads as code — the conservative direction, because recursing
  would mean deleting inside a string. `ablate.py` and `fix-lint.py` both import `unchanged()` and
  stop asking a comments-only hunk for a test, which is the only place the claim is acted on rather
  than reported. `scripts/codehash.test.py` is where the awkward cases live, and two of them are
  defects it found in the tool.
- `python3 scripts/fix-lint.py --base REF` and `python3 scripts/ablate.py --base REF` — **the two
  branch gates**, and the answer to why simple changes were taking six rounds of review. Both read
  TWO commits, so like `sw-lint.py --base` they run on pull requests only and CI is the one place
  with both sides of the merge. `fix-lint` notices that a branch changed source and touched no
  test. `ablate` is the one with teeth: it reverts the branch's SOURCE hunks to the base, keeps its
  TEST hunks, runs the suites that cover what changed, and requires a NAMED check to go red. A test
  that still passes without the code it is meant to prove does not prove it — which is exactly how
  PR #23 ran six rounds, four of them fixing a defect in the previous round's fix, every one
  shipped on a green suite. It is the reviewer's ablation of `pointer-events="none"` (#42), run
  automatically. Three details are load-bearing: a new named `FAIL` rather than a nonzero exit,
  because an ablated tree is this branch's tests over the base's code and can die on import while
  proving nothing (reported as INCONCLUSIVE, which also fails); only the suites `COVERS` maps to
  the changed files, so a chart.js branch is never asked to redden `validate.test.py`; and it
  refuses a dirty tree, because restoring means `git checkout HEAD --` and that would take
  uncommitted work with it. `--with-ui` adds the browser suite, and the `gates` job passes it — a
  UI branch is ablated by CI rather than told its ablation is owed locally, which is what this
  sentence used to say and the whole point of #56. On a machine with no browser the suite still
  skips, and the report says so rather than passing quietly. A `No-test: <reason>` trailer skips BOTH, so an
  untested source change is a sentence somebody wrote on purpose and a reviewer can read, not a
  silence — and it is scoped PER FILE, to the ones its own commit touched. Read anywhere in the range
  it was two holes at once: a docs-only "No-test: TODO.md only" disarmed both gates for every source
  change on the branch, and one legitimately excused file excused every file beside it. A file edited
  again with no trailer is back in the gate, because the second edit is the unexplained one.
  `scripts/fix-lint.test.py` covers both, in cases that each build a throwaway repo with real
  branches.
- `scripts/audit_counts.py` — not automated: it prints parsed quartet counts beside the sentence
  they came from so a human can grade them. Run it after touching `scrape_list.py`.
- `scripts/audit_redirects.py` — not automated either, and for the same reason: it answers a POLICY
  question. It prices every redirect into every article and reports what summing them would change,
  which is the evidence behind invariant 15's refusal to. `--limit N` audits the N most-read
  instead of all 884, which is the difference between two minutes and ten.

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
  it goes.** This is the built-or-cut rule applied one level down, and it is the rule the steady
  trickle of low-severity review findings has been about: `histogram.js`'s "Keyed by side" over a
  `.data([-1, 1])` that joins by INDEX (#42), invariant 13's six folded characters where `FOLD` has
  nine, "58 names carry such characters" where eight do. Each was correct when written and none
  could fail — a comment cannot go red. The repo already had the answer and was applying it
  everywhere except to its own prose: `Chart.missingNames()`, `Names.staleOverrides()`,
  `unfilterableGenders()` and `unreachableRepertoires()` all turn a claim into something a suite
  asserts. For the DOCS the answer is not a lint — that was tried and deleted, because a check
  cannot tell a reflowed paragraph from a stale fact — it is not writing the number. So a comment
  that states a join key, a count, a list or a threshold either gets pinned by a check or gets
  written loosely enough to stay true. A comment about WHY is never in this category, which is
  most of them, and none of this is an argument for fewer comments.
- **A fix ships with the test that goes red without it — not with the next review.** `ablate.py`
  enforces it on a branch, but the discipline is the point: run the fix's test against the tree
  WITHOUT the fix and watch it fail, before proposing it. PR #23 ran six rounds and four of them
  fixed a defect in the previous round's fix, every one shipped on a green suite; the test that
  would have caught each arrived one round late, every time. `validate.test.py` has embodied this
  from the start — it proves the gate still catches each past incident — and round 4 of that PR had
  to invent `case(name, expect=None)` to test a deliberate LOOSENING, which is the same idea
  inverted. When there is genuinely nothing to assert, say so in a `No-test:` trailer rather than
  leaving it silent.
- **One filter row, above everything it scopes.** `#filters` is a sibling of `.grid`, not a child
  of the chart card or the table card — all THREE filters (search, readership brush, gender pills)
  scope both views, and a filter drawn inside one card says otherwise. `placeFilters()` moves it into `#viz` in full screen (where the chart
  is everything) and CSS drops its search half there to keep the chart's height.
- **The lens is an OVERLAY, not a view — a checkbox in the controls row, over all three modes.**
  It was a fourth pill, and as a view it differed from Timeline in exactly two things: it drew a
  circular fisheye, and it had no zoom. Neither is a way of reading the DATA, which is what the
  other three pills each are, so the switcher claimed four pictures where there are three — and the
  crowd the magnifier could not reach was the Fame cloud, ~600 dots in one corner and the densest
  thing the app draws. `layout()` in `chart.js` lays the picture out per mode and `warp()` applies
  the fisheye LAST, in screen space, which is what lets one lens serve three modes with no per-mode
  case at all: what it moves is pixels, so what you click is still what you see (the Delaunay is
  built over the warped positions like everything else).
  **What it takes away is one gesture, on a touch screen only.** The first answer was that it took
  the zoom entirely — `applyZoomBehavior()` bound nothing while the box was checked, on the 2014
  chart's lesson that a magnified view of a MOVING picture cannot be read. That is one rule too
  blunt by half, and it shipped: the conflict is between the AIM and the PAN, which are the same
  one-finger drag on a phone and two different inputs on a mouse, so a reader who framed a decade
  and then reached for the magnifier found the chart had silently stopped zooming, with nothing on
  the page saying why. The conflict is therefore resolved where it actually lives, in a
  `zoom.filter` keyed on `event.type`: a touch gesture is refused while the lens is on and
  everything else goes through, so a wheel still zooms the picture under the glass and a HYBRID
  machine gets both answers — its mouse zooms while its finger aims. Two consequences worth
  knowing. The filter must restate d3's own default (`(!ctrlKey || wheel) && !button`), because
  passing one REPLACES it rather than adding to it. And the hint says two different things now
  (`LENS_POINTER` adds a sentence to the drive half, `LENS_TOUCH` replaces it), because on a phone
  "drag to pan" is an instruction the chart has stopped obeying and on a desktop it has not.
  The transform is LEFT where it was either way rather than reset, so the lens magnifies whatever
  the reader had framed and unchecking hands the frame back unchanged; `zoomed()` and `resetZoom()`
  therefore ask nothing about the lens, and neither does `setLens()` in `app.js` — a line re-reading
  Reset zoom there would be answering a question nothing had changed the answer to. What the
  vanished branch does NOT excuse is telling d3 the box, because the gestures are not the only
  thing that reads it: d3 reads `extent` again when it SCHEDULES A TRANSITION, for the centroid and
  the width its interpolation travels through — and `goTo()` animates. So `zoom.extent()` is called
  ahead of everything else in `applyZoomBehavior()`; while it sat inside the bound branch, a filter
  fitted after a resize under the lens tweened along a path computed for a box that was gone.
  **Only the path**: `zoom.transform` does not constrain
  (probed — a transform applied against an extent ten times too small survives intact), so the
  frame it lands on was right either way, which is why fourteen resize-and-filter pairs were probed
  for a wrong frame and none of them found one. `Chart.zoomBox()` exists so the suite can assert
  the invariant at the cause rather than chase an artefact that only shows while it moves.
  **What `zoom.transform` DOES do is interrupt**, which is its contract and not an accident — so
  the `__zoom` sync beside those setters runs only when it would change something. `setMode()` and
  `resize()` assign a new transform before they get there and still sync; `setLens()` comes
  through changing nothing about the frame, so its sync was a no-op whose only effect was to cancel
  a transition — check the box inside a filter's 420ms fit and the chart stopped dead at k=1 with
  Reset zoom lit
  over a frame nobody asked for. A no-op that interrupts is not a no-op.
  Two things it does keep from the view it replaced, both about the AIM rather than the frame.
  **`baseLayout()` un-aims it**, because the
  filter fit and the ring separation are claims about the chart that outlive a pointer move.
  **And `resize()` drops the aim outright**, for the reason `setMode()` does: it is a point in a box
  that is going away. A pointer re-aims on its next move and a rotation even synthesises one — which
  is why the desktop check for this passed without the fix and the real one lives in the phone
  section. A FINGER cannot: `pointerleave` is `!TOUCH`, so a rotation or a tap on Full screen left
  the fisheye magnifying a spot nobody had pointed at, its boundary circle clipped away by a box
  that had shrunk under it.
  **What the lens does NOT do is earn labels, and that was tried.** Unpinning `pickLabels()`'s
  resting-Fame budget for an aimed lens named nothing extra — 13 before, 13 after — because a ZOOM
  earns names by culling the frame while the lens moves pixels and culls nothing, so `prom` goes on
  ranking the whole roster and the budget goes to the same far-flung dots that were already losing
  their place to a collision. Ranking by nearness to the focus would name the crowd and would churn
  every label on every pointer move, against a flag and a detail panel that already name the dot
  under the glass continuously. The suite asserts both halves — the pin holds, and the flag names
  what the glass is over — because the first is only defensible while the second is true.
  And **`#v=lens` still resolves** — to the timeline with `l=1`, which is the picture that link
  named — the same shape of alias as `#v=readers`, one vocabulary over.
  Two costs, both paid in the row rather than in the chart. It is 28px wider than the pill it
  replaced, which moved both edges of the icons-on-plot measurement (see that entry); and it is a
  CHECKBOX rather than a pressed `.btn` or a fourth pill because it is a thing you leave on, not a
  picture you switch to — the box says so with no copy, and carries the state to the accessibility
  tree without anything here keeping it in sync. Switching it re-lays out nothing (the plot's box
  is a function of the MODE), which is what makes it safe in a row above the plot at all: see the
  next entry for the rule it would otherwise break, and `ui.test.mjs` 4m4 for the check.
  One detail the eye finds before any of that, and it is a lesson about constants rather than about
  checkboxes: the box is centred on the WORD and not on the word's line box. `align-items:center`
  centres boxes, and "Lens" has no descender, so the line box runs past the ink it draws and the
  checkbox hung 1px low. **The first fix was a -1px nudge, and it was wrong** — HOW low is a fact
  about the FACE, and `system-ui` is a different one per platform (#53 again): measured at 13px,
  DejaVu and FreeSans hang it 1.0px low, Liberation Sans 0.5px HIGH, and SF's metrics put it within
  a tenth of centred — so the constant fixed the machine it was measured on and would have doubled
  the error on the Mac it was written on, with the suite going red there. `text-box-trim`/
  `text-box-edge: cap alphabetic` asks the font instead and lands within 0.3px in every face
  measured; a browser without it centres line boxes exactly as before.
  It is applied to EVERY label in `.controls`, not to this one, because trimming moves a word down
  onto the band it draws (1.23px in DejaVu, nothing in the faces that were already symmetric) and
  one label doing that alone breaks the baseline it shares with the pills beside it — `ui.test.mjs`
  asserts both halves, the box against its own cap band and the five labels against each other.
  That rule is also why `#reset` and `#reset-filters` keep their labels in a `span`: bare text in an
  inline-flex button lands in an anonymous flex item, which no selector reaches and which
  `text-box-trim` does not inherit into, so those two stayed put while the pills moved.
  One more thing that has to fail in the safe direction: the keyboard ring is drawn round the PILL
  through `:has(input:focus-visible)`, and the rule that takes the input's own ring away is scoped
  the same way. An engine that cannot parse `:has()` drops both and the input keeps the global ring;
  unscoped, it dropped the pill's ring and kept the removal, leaving a control with no visible focus
  at all. `ui.test.mjs` deletes every `:has()` rule on the page and looks again, which is what such
  an engine does.

- **The chart's controls sit ABOVE the plot, because the plot's height is a function of the VIEW.**
  `measure()` gives each mode its own aspect ratio — the swarm the widest of them, Fame the most
  nearly square, and every one of them taller on a phone — so a row underneath moves when you press it — 61px on a phone, 150px at 1280,
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
  member takes it only if they also lead by `DOMINANT_MARGIN`, because a floor alone hands the bare
  surname to whoever leads by one view once both clear it, and readership is refetched monthly, so
  that is drift rather than hypothesis. `names.test.mjs` asserts the margin and, over the real
  roster, that no two composers end up with the same label. Not in
  `filed()`: the table sorts on what it prints, and a bare "Haydn" beside "Haydn, Michael" is
  inconsistent about who gets a forename. This is why `Names.setData()` takes readership alongside
  the names, as a PARALLEL array for the reason `build_data.py` carries canonical titles in one.
- **The phone table has to fit in a font you do not choose.** `system-ui` is SF on a Mac, Segoe on
  Windows and DejaVu on most Linux — and DejaVu is wide enough that the four phone columns
  overflowed 390px outright (#53), which is how the suite came to fail on a Linux runner and
  nowhere else. Two things were paying width for nothing and now do not: a header WORD wider than
  any value beneath it (`short` in `table.js`'s `COLS` — "Qts" is drawn below 640px) and the cell
  gutters. **An abbreviation is not free to a reader who can SEE it**: the accessible name has to
  contain the drawn label (WCAG 2.5.3), or a voice-control user says "click Qts" against a name
  that reads "Quartets" and the column cannot be sorted at all. So both spans stay in the name, the
  drawn one first, and the word is moved off screen rather than `display:none`d. This is NOT the
  `#chart-tools` split, where the drawn thing is a GLYPH and there is no visible word to mismatch.
  `ui.test.mjs` asserts the name the browser COMPUTES, over CDP, because an `aria-label` added
  later overrides the markup while a check written against the two spans stays green.
  The other lesson is in what the measurement found on the way: at 360px, the common Android
  width, the old table overflowed in EVERY face including SF, so the 390px check was passing on the
  one width where the narrowest font happened to clear. `ui.test.mjs` asserts BOTH widths for that
  reason — a fit measured in the runner's own font is measuring the font — and the document-level
  overflow guard runs at both too, since declaring a width supported means the whole page fits it.
  A new column, or a longer header, has to be measured the same way rather than eyeballed on a Mac.
- **A number printed beside the chart counts the PLOTTABLE rows.** The empty detail panel said
  "884 composers, born 1582–1989" next to an x axis starting at 1709 — the 94 rows with no stated
  quartet count are in the table only, and three of them are the roster's earliest births.
  `Chart.plottedStats()` is the one place that answers "what can the chart place", so the count,
  the birth span and the living count can't disagree with each other or with `plottable()`. The
  roster's own total belongs to the table and the provenance line, which state the difference.
  The same split governs the app's stated CLAIMS: `manifest.json` and the link preview describe
  what the page draws and say 790, while the `#count` readout, the search placeholder and the
  provenance line count the 884 rows the table actually holds. They are not inconsistent — they
  are answering different questions, and the provenance line is where the difference is named.
  README's 884s describe the dataset and the pipeline, not the plot, and stay.
- **Prose the app can FALSIFY is built or cut; only prose it cannot is typed — and CUT is the
  first branch to try.** The rule was "states a number or a range" until issue #24 found the third
  case: a claim with no number in it that the app falsifies anyway, about the VIEW rather than the
  data. "Across is how many quartets they wrote, up is how much their article is read" was typed,
  and true in Fame only — across is birth year in Timeline and Swarm, up means nothing at all in
  Swarm. It was cut rather than derived per mode, because the axes are already stated twice on
  screen by whichever view is drawn (the axis titles in `chart.js` and the per-mode hint it builds
  from `SHOWS`/`DRIVE`), so a
  third statement could only ever be the copy that goes stale.
  **Issue #35 applied the same test to the built half and it failed too.** The lede carried a
  sentence generated from `Chart.emphasisStats()` — which set is picked out, its birth span, a
  worked example — and it was correct at every instant. What it cost was the machinery a claim that
  can change LENGTH needs: it emptied outside Fame and under any filter no curated composer
  survived, so the paragraph collapsed and everything below it rose 40px, lifting the pill you had
  just pressed (#27). That bought `reserveLede()`, a width-guarded `ResizeObserver`, a `ledeClause()`
  split so the measured string was the printed one, three sections of `ui.test.mjs` — and a
  residual 20px shift it never did fix (#36), because the gender pill changes which sentence
  "resting" means. All of it is gone. The lede is now one static line. Two of the claims it made
  are still on the page in the component that owns it — the legend names the highlighted set, the
  axis titles and the hint name the axes — and `ui.test.mjs` 4m checks those two rather than the
  sentence, so cutting the prose cannot quietly cut the information. The third, `setProv()`'s
  English-only caveat, was later cut outright: the footnote had grown into an essay, and a caveat
  nobody reads is not a caveat. That is the same judgement one level down, and it is why 4m checks
  two things now and not three — a check kept alive over deleted prose is the vacuous kind.
  **The lesson is the ordering.** Before building a mechanism to make prose behave, ask whether the
  prose should exist — a page that states a thing twice does not need the second one to be clever,
  it needs it deleted. `#count`, the search placeholder and `setProv()` stay built because each is
  the ONLY statement of what it says, and none of them can empty.
- **The provenance line is built, not assigned.** `setProv()` in `app.js` linkifies every Wikidata
  property id it prints (`P569` -> its definition page), because an id is jargon a reader cannot
  check from the page. It links the TEXT rather than storing anchors in `composers.json`: that file
  is data and carries no markup, so a new property named by the pipeline is linked the moment it is
  printed. Setting `$("prov").textContent` directly again would silently drop every link.
- **`.seg` is a look, not a behaviour.** Two pill groups wear it — the chart view switcher and the
  gender filter — so anything binding `.seg button` must scope itself (`.controls .seg button`).
  Unscoped, the switcher's handler landed on the filter's buttons and a pill press called
  `setMode(undefined)`: the chart left every named mode at once and the URL grew `#v=undefined`.
- **`names.js` loads before `chart.js` and `table.js`, and `Names.setData()` runs before either
  gets data.** The short form of a name is a function of the WHOLE roster (a shared surname earns
  an initial), so neither module can display a name until the roster has been counted. It is a
  SHELL and a BOOT dep like every other load-bearing script — see invariants 1 and 2.
- `index.html` owns structure, `styles.css` owns looks, `app.js` owns boot and the shared state
  (which composer is selected, which filters are active). `chart.js`, `table.js` and
  `histogram.js` never talk to each other (they share `names.js` and `Chart.colorOf`, which are
  read-only lookups, not state) — the filters compose in `applyFilters()`, where each
  source returns "a Set of indices, or null for everything" and they are intersected. The gender
  filter is the one with no module of its own (`genderMatches()` in `app.js`): three buttons and a
  string, nothing to render and no data to hold. A fourth filter that DOES draw something belongs
  in its own file, on the same contract.
- Anything that BAKES a color into JS (SVG fills in `chart.js` and `histogram.js`, the legend in
  `app.js`) needs a `rerender()` wired into `Theme.subscribe`. Adding a fourth such component
  means adding a fourth call there.
- **Share and Full screen are icons ON the chart wherever the controls row will not hold them on
  one line, and that is what PAYS for the third button in the row.** `.controls` is already two
  lines at 390, and a third word button takes it to three — 48px of a phone's first screen, half of
  what issue 29 spent 94px winning back. Shrinking those two to icons IN the row is not enough on
  its own: at 360 it still wraps. So
  `placeChartTools()` reparents `#chart-tools` into `#plot`, on the same one-element-moved contract
  as `placeFilters()` and `placeDetail()` — never a second copy, because `#fs` holds the pressed
  state and `share()` holds a timeout on its own label. Everything that makes the overlay safe is
  already true of `#plot`: it is `position:relative` and already hosts `#flag`, d3-zoom binds to the
  `svg` rather than to `#plot` so the buttons take taps without eating a pan, and `chart.js`'s
  rebuild removes the one svg it made BY REFERENCE. That last one was a claim before it was true:
  `selectAll("svg")` is a DESCENDANT query and matched the three `.ico` glyphs as well, and nothing
  showed it because `build()` only runs from `init()`, which runs before the move.
  **The condition is a MEASUREMENT of that row rather than a device, and it is TWO intervals.** It
  was `(max-width:640px)` while this was read as a phone fix, but the row is two lines well past a
  phone. What decides it is the CARD, not the viewport, and the two are not monotonic in each other:
  the `(min-width:900px)` two-column grid takes 194px off the card. Measured with the words in the
  row and `share()`'s "Link copied" showing — the widest state the row ever has — stepping 2px:
  641-807 wraps (card 609-775), **808-899 fits** (776-867), 900-1121 wraps (554-775), 1122+ fits
  (776+). One card width decides both bands, 776px. So the words belong in two bands and the icons
  in the other two, and `iconsOnPlot()` in `app.js` is `NARROW` (`max-width:819px`) or `SQUEEZED`
  (`min-width:900px and max-width:1139px`). A single
  `(max-width:1139px)` would be wrong in a 92px band: 808-899 would spend 26px of DATA height to
  buy no page height at all, which is the exact trade this rule refuses at the top end. The two
  numbers sit clear of the measured edges on the ICON side, because the two errors are not equal —
  words where they do not fit means a PRESS on Share wraps the row and drops the plot
  44px under the cursor that just pressed it, while icons where words would have fitted costs the
  26px and nothing else. Those widths are one machine's font metrics, so they are defended by checks
  rather than by arithmetic: `ui.test.mjs` presses Share at 820 and at 1140 — the first width in each
  band that draws the words — and fails if the row grows. **It has, once, and that is the entry
  worth reading**: the lens stopped being a fourth pill and became a checkbox in this row (see the
  lens entry below), 28px wider than the pill it replaced, and both edges moved with it — 778 to
  808 and 1092 to 1122, re-measured the same way. Nothing in the arithmetic above could have
  noticed; the two Share presses did, on the branch that made the change.
  **They are two QUERIES and not one list, because only the second one is about the grid.**
  `body.fs .grid{ display:block }` — full screen has no two-column grid, so the card is the window
  and the row has its 1122+ geometry back. Measured the same way, full screen fits both words from
  794px, where the two-column card does not until 1122. So `SQUEEZED` is skipped under `.fs`, or a
  1000px window in full screen spends the 48px band on a row that would have held them — and that
  costs MORE there than at rest, because `#plot` is `flex:1` and the band comes off a chart that is
  already the whole viewport. `NARROW` still applies in full screen, conservatively: it fits from
  794 and this draws icons to 819, erring 25px toward the side that cannot wrap a row under a
  cursor. The suite enters full screen at 1000px and asserts the words stayed and no band was spent.
  **A wheel over the glyphs is a wheel over the CHART, and that needs saying in code.** d3-zoom is
  bound to the svg and `#chart-tools` is a SIBLING of it, so a wheel starting over a glyph reached
  no zoom listener at all: the corner was dead and the page scrolled instead, two pixels from a spot
  in the same band that zooms. It cost nothing while the icons were a phone layout — a phone has no
  wheel, and the trade measured for that layout was all about dots COVERED — and became reachable
  the moment the layout reached a laptop. `Chart.wheelInto()` re-dispatches into the CURRENT svg
  (`build()` makes a new one on every `setData`/`setMode`, so a captured node is the `selectAll("svg")`
  trap again) and `app.js` forwards only while the group is on the plot, since in the row a wheel
  should move the page. The DRAG is deliberately NOT forwarded: `pointerdown` into the zoom would
  start a gesture on every press of these two buttons, which is the conflict binding to the svg
  rather than `#plot` avoids. A control swallowing a drag is the platform convention; swallowing a
  wheel is not, because a wheel was never aimed at the control. The check measures the glyph AND the
  band beside it — "the corner is dead" only means something against a corner that works.
  **`app.js` holds the only copy of it.** `styles.css` scopes the icon look to `#plot > #chart-tools`,
  so the looks follow the DOM rather than re-deciding the width, and the two cannot disagree. They
  could when that look lived in a width query: the CSS answered on width alone, so every state where
  `placeChartTools()` had not run yet drew the icon look in the controls row — a cold boot before
  `app.js`, and permanently on `start()`'s error path, which bails before the move and left two bare
  glyphs with clipped labels and no click handlers sitting in the row. `chart.js` reads neither — it
  is TOLD, via `Chart.setTopReserve()`, which is why moving the breakpoint changed nothing in that
  file.
  Four things a change here must keep. The words stay in the DOM, visually hidden rather than `display:none`, because they are
  still the buttons' accessible NAMES. The label is written into that `.btn-t` span and never onto
  the button — `share()` and `setFull()` used to set `textContent` directly, which now deletes the
  icon beside it. The print rule names `#chart-tools` separately from `.controls`, because on a
  phone it is no longer inside it. And they sit in the AXIS-TITLE BAND, over no dot in any view:
  `placeChartTools()` asks `Chart.setTopReserve(48)` and `measure()` widens `m.top` from 22 to fit a
  touch target. Every corner was measured first and every one covers something — dots the group
  would sit on, summed over Fame, Timeline, Swarm and the lens at 390: top-left 11, top-right 90,
  bottom-right 239, bottom-left 3 (the lens was a view of its own when that was measured; as a
  toggle it warps nothing until it is aimed, so it adds no layout to the sum). **Top right is the trap**: it reads as empty in Fame and is exactly where the SWARM
  piles up, 90 dots and the "Rachmaninoff" label, which is what judging a shared overlay from one
  view gets you. The band costs 26px of DATA height and no page height — the plot's outer box is a
  function of the aspect ratio, so the dots' area gives up the pixels and the card is the size it
  was. `ui.test.mjs` 7c2 asserts zero coverage across all three views AND that the buttons fit inside
  the reservation, because the second is the cause and the first only the symptom.
  They are drawn as BARE GLYPHS — 16px in an invisible 40px hit target, no border, no background,
  `var(--muted)` like every other `.btn` label and like the axis title beside them. That is the
  platform shape for a control sitting on content, and a `.btn` pill moved onto the chart is not:
  40px of visible chrome around a 16px mark reads as furniture next to an 11px axis title. The hit
  target is felt and not seen, so the suite taps 3px in from a CORNER — 22.8px clear of the glyph —
  rather than at the centre, which would pass on a 16px button.
  **They are CENTRED on the axis title's line**, not sitting on its baseline: bottom-aligned read a
  touch high, because a 16px glyph beside 11px text carries more visual mass below its own middle
  than the letters do. The offsets follow from that and are not nudges — the title's box centre is
  4.47px above its baseline and the baseline is 8px above the plot area (chart.js draws `text.ttl`
  at `y:-8`), so the glyph's centre lands at `BAND - 12.47` and the 40px target, whose bottom is the
  glyph's bottom, starts 3.5px down — spanning 3.5 to 43.5, and clearing the plot area by 4.5px.
  The band is 48 because the target must stay CLEAR of that area: it is invisible, so a dot it
  overlaps silently stops being TAPPABLE, which is worse than being hidden because nothing on screen
  explains it — at 46 it shadowed 12 dots in the swarm. **Clearing the plot area is not clearing
  every pixel a dot can occupy**, and the 4.5px is the whole margin: `chart.js` insets the dot clip
  OUTWARD by one maximum radius (~11px on a phone), so under a pinch the sliver of a dot at the very
  top edge reaches under the target. Its CENTRE cannot — the frame test only draws a dot whose
  centre is inside the plot rect — so the dot is still tappable where a finger aims, and that is the
  guarantee, one step weaker than the resting one. Shortening the target to miss the sliver would
  put it under the 40px floor issue 31 was fought over. The suite counts coverage against the whole
  button for that reason, asserts the centre rule at a NON-IDENTITY transform, and measures the
  alignment against the title's own box rather than against the constants here, so a change of font,
  size or that `y:-8` fails instead of drifting. The corner was re-measured at 700, 900 and 1024
  when the breakpoint moved, because zero coverage on a 390px box does not imply zero on a laptop —
  the dots are laid out again on a card twice as wide, and the swarm spreads to fill it. It is
  still zero in every view, and the suite now asserts it at 1024 as well as at 390. The 40px height
  is stated with the overlay rather than inherited from the touch-target rule, which asks a
  different question (`(hover:none) and (pointer:coarse)`): a desktop window dragged narrow matched
  one and not the other, took `.btn`'s 36px, and the derivation above stopped describing the box
  being drawn. Most of the windows that draw this layout answer no to that query, so stating it is
  what makes the geometry a property of the overlay rather than of the input device.
  One more thing moving them INTO `#plot` broke: `#plot svg{ width:100% }` means THE CHART, and as a
  descendant selector it caught the icons too and stretched an 18px glyph to 38px — 95% of its
  button — with a 3.2px stroke, `body.fs #plot svg{ height:100% }` doing it again in full screen.
  Both are `> svg` now, `.ico` carries its own `width`/`flex:none` (a width ATTRIBUTE loses to any
  stylesheet), and a check measures the glyph against its button. Note the shape of it: it shipped
  because a desktop could not show it, the buttons being words in the row there — the same reason
  the tap-target scan could not see a control that hides itself. Widening the breakpoint shrinks
  that blind spot rather than moving it: the layout every bug in this group hid in is now the one
  the machine it was written on draws. The suite enters the states the phone hides — a narrow
  window with a real pointer, a laptop, a wide window, and the boundary itself.
  One consequence of the icon layout reaches `app.js`: under the breakpoint `.btn-t` is the
  accessible NAME and not the face, so `share()`'s "Link copied" swap wrote the confirmation where
  nobody could see it. The glyph acknowledges too (`.copied` swaps the arrow for a check), off the
  same one call, so the two halves cannot disagree. Both are raced against `STALL`, because a
  clipboard write that never SETTLES is not a rejection and the catch beside it can never fire —
  Chrome under a bare X server leaves `writeText` pending indefinitely, which is a Share button that
  promises nothing and delivers nothing. The suite stubs that promise rather than waiting for a
  platform that does it, since on macOS the real write rejects and a check written around the Linux
  behaviour would leave the fix unproven on every machine it is developed on. It is not phone-only:
  `navigator.share` returns before either fallback on a real phone, so the branches that reach the
  swap are exactly the ones that run where it is missing — which, at 1139px, is most of the desktops
  that see this layout.
  The other consequence is the TOOLTIP. A clipped label is a name a screen reader can read and a
  pointer cannot, and up to 1139px that pointer is usually a mouse — so both buttons carry a
  `title`, and `label()` writes it with the span in one call rather than the markup carrying it
  alone. `#fs`'s name changes with its state, and a tooltip still reading "Full screen" over the
  exit glyph would be worse than none. It is written at every width, including where the word beside
  it is visible and the tooltip only repeats it: scoping it would mean asking `app.js` which layout
  it is in, which is a second copy of a breakpoint that now lives in exactly one place.
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
  filtered. `styles.css` answers it once with `[hidden]{ display:none !important }` and
  `ui.test.mjs` has a check that notices if that line is ever dropped or out-specified.
- **There is ONE detail panel, and `app.js`'s `placeDetail()` moves it.** Beside the chart above
  900px; inside `#viz` (`.compact`) on a phone and in full screen at any width, because the grid
  column is a screen-height away there and `display:none` in full screen. Never render a second
  compact copy — the selection, the nav buttons and the `.on` state all assume one element.
  The two in-card positions differ on purpose: BELOW the plot on a phone (free to grow; nothing
  above it moves), ABOVE the plot in full screen as a fixed-height strip that is drawn even when
  empty. **Its height must stay constant**: `#plot` is `flex:1` in full screen, so a box that grew
  on select would trip the ResizeObserver and re-lay out the chart under the finger that just
  tapped it. `tight()` in `app.js` is what trims the content to fit that box.
- **Anything that handles its own arrow keys marks itself `[data-keys]`.** `app.js`'s document
  keydown listener steps the SELECTION on left/right, and its old guard was
  `matches("input, textarea")` — so the first focusable thing that was neither had its keys stolen:
  arrowing along the sparkline changed the composer instead of the month, and the readout answered
  about someone else. The guard has since failed the other way round too, which is the same
  mistake inverted: `input` is a proxy for "this control handles the key", and a CHECKBOX matches
  it while answering to Space alone — so the lens toggle, a pill until it became an input, ate both
  arrows for as long as focus sat on it. It is `input:not([type="checkbox"])` now, which still
  covers the search box and anything that really does step with the arrows (a range, a radio
  group), and `ui.test.mjs` presses a key with the box focused rather than trusting the selector. Escape is handled before the guard, because it means "back out of this"
  wherever focus is. The readership brush still owes a keyboard path (TODO); when it gets one it
  needs the attribute and no edit to the listener.
- **A hover previews into the detail panel, so its box is reserved wherever a pointer exists.**
  `@media (hover:hover) and (pointer:fine)` gives `.compact` a `min-height` covering its TALLEST
  state (pinned, with the nav row) and ellipsizes the name; without it, moving the mouse across the
  chart pumps the legend up and down. Touch screens get neither rule — no hover to churn, and the
  space is the chart's. The reservation is MEASURED: the suite prints the pinned panel's real height
  beside the "pinning does not shove it either" check and fails when `min-height` falls short, which
  is how adding the sparkline was caught — the pinned panel measured 267px against a reservation
  that was then a few pixels short. It pins the composer with the LONGEST
  caption, because the reservation has to cover the worst case and the dot an earlier check happens
  to hover is not it.
- **The sparkline's caption names the spike if there is one and the trend otherwise.** A fixed "peak
  N× typical" was the wrong sentence for most of the roster: when the caption was written the median
  composer's biggest month was 3.1× their typical one, because a composer read thirty times a month hits ninety by chance, so it
  cried spike about noise on half the list — and it buried the real story for the steady ones, where
  Haydn's meaningless 1.7× peak displaced a line that had slid 42% since 2015. `SPIKE` tests the
  peak against the 95th PERCENTILE of that composer's own months, which is scale-free and judges a
  small noisy article against its own noise; at 3× it fired on 18% of that roster and selects almost
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
  orders of magnitude, but within one composer the question is proportion, and a log baseline
  flattens exactly the spike the line exists to show.
- **Every sparkline shares one month axis, so the blank left of a young article has to be named.** A
  shared axis is what makes two composers comparable, and it means the articles created after
  2015 draw over the right-hand end and leave the rest empty — which under a line chart reads as
  "nobody read this" rather than "not written yet". The label row prints `from Jul 2025` instead of
  the axis span in that case. A null month is a BREAK in the path for the same reason (invariant
  10); joining across it would draw a line down to zero and back.
- **A chart label prints the short name, not the canonical title.** Half the characters, and because `pickLabels()` is first-come-first-served on space, halving every box is what
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
  the two halves are deliberately different mechanisms. `refreshEmphasis()` keeps a ring budget
  DERIVED from `OUTLIERS` (`RINGS = OUTLIERS.length`, so the two cannot drift), filled first by the
  curated outliers the filter kept and then by `prom`, the same seed-then-rank shape the labels have.
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
  plot AND a floor of `GAP_DOTS` named radii, because the dot radius is FLOORED while the diagonal
  keeps shrinking; the fraction is not delicate (2.5%–5% picks the same dots) and the floor is a
  guard, not a fix. Deriving FEWER than the budget is the honest outcome when nothing
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
