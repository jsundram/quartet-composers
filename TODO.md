# Open work

Written down so a session that starts cold can pick any item up without reconstructing the
reasoning. Roughly in the order I'd do them. **known defect** means the current build gets it wrong
today, not an enhancement.

Closed entries are kept SHORT and only to stop a decision being re-derived: what was decided, and
the measurement that decided it. The narrative of how each was found is in the issue it links to.

---

## Accessibility

### The readership brush has no keyboard path — **known defect**
`histogram.js` is drag-only, so a keyboard-only user cannot reach the readership filter at all. It
regresses the pwa-starter checklist's "semantic controls" row and was introduced knowingly under
time pressure.

Cheapest honest fix: a visually-hidden pair of `<input type="number">` (min/max views) bound to the
same `setRange()` the brush uses, inside the existing `role="group"`. A `<input type="range">` pair
is tempting but two thumbs on one axis is worse for screen readers than two labelled numbers. Do
NOT make the SVG focusable and hand-roll arrow keys — that reinvents a form control badly. It will
need `[data-keys]`; see the Conventions rule.

### Chart is `role="img"` with a text alternative that isn't equivalent
The `aria-label` says "the table below carries the same data", true only for the plotted rows — the
94 with no quartet count are in the table and not the chart, and nothing says so to a screen
reader. Either state the count in the label or drop the claim.

---

## Data quality

### Readership is displayed to two significant figures; the data has one meaningful one
`twoSig()` quantizes the median and floors it, so Mozart reads "180k+" rather than "186,772". Two is
a guess, not a derivation: the honest input is the 12-month spread, which for Mozart runs 140k–390k
— a factor of 2.8, i.e. barely one significant figure. A defensible rule would pick the number of
figures from each composer's OWN spread. The table deliberately keeps the exact value: it sorts on
that column.

### 94 of 885 entries (11%) have no quartet count
Listed in the table, excluded from the chart; `audit_counts.py --null` shows them. Most enumerate
works without ever using the word "quartet" ("VSTO (1993)."), where counting dated titles would
usually be right — but the same rule would count "(1907–1949)" as a work, which is why it is off.
Worth another pass with a tighter enumeration test. It costs real composers: Caroline Shaw, Jessie
Montgomery, Tania León, Joan Tower and Chen Yi cannot be plotted at all.

### Ranges are read as whichever bound the regex reaches first
Czerny's entry says "at least 20 and as many as 40 string quartets" and the parser returns 40. It
should take the lower bound consistently, or store a range and let the UI show it. Right now the
choice is an accident of regex ordering, which is the worst of the three options.

### Semantic mismatches need a human, and only one has had one
`OVERRIDE` in `scrape_list.py` holds exactly one entry (Paganini — his "fifteen string quartets"
are for guitar quartet; the honest count is three). There are almost certainly more. Finding them
means reading the ~460 entries the "N string quartets" rule fires on and looking for a qualifier
the regex can't see; `audit_counts.py --rule "N string quartets"` samples them.

### What counts as a quartet at all is undefined
Arrangements, fragments, incomplete works, "for string quartet and X" — the page is inconsistent and
so, therefore, is this dataset. Worth deciding a policy and stating it in the UI, or accepting the
inconsistency explicitly rather than by default.

### The 2014 archive is only half-used
`compare_2014.py` reports 28 composers who dropped off the list. Most are deleted articles, but a
few were renames the fold-matching doesn't catch (Fanny Mendelssohn → Fanny Hensel, Charles Wesley →
Charles Wesley junior). Worth a pass to confirm none is a real loss.

### ~~Gender is not in the data~~ — done, 2026-09-05, [#1](https://github.com/jsundram/quartet-composers/issues/1)
P21 ships as the eighth positional field: 276 women of 884, 219 of them plottable, births 1745–1989.
Both open questions were answered **filter**, not encoding, because a filter here is already a
highlight — nothing is removed, so "show me the women" and "where are they" are one gesture. What it
needed was volume: the kept dots come up to 0.55 while any filter is on. A permanent encoding was
rejected on the issue's own grounds — the only unspent channel is shape, and shape does not read at
a 2.5px radius among 790 marks.

### ~~Labels were a fixed set, not a function of zoom~~ — done, 2026-09-05
Thirteen hardcoded names at every zoom made the zoom decorative. Now a budget that grows with zoom,
filled from the seed then by PROMINENCE (z-scored distance from the centre of the visible cloud) and
frame-culled; at rest unfiltered the budget is pinned to the seed, so the resting picture and the
share card are unchanged. Prominence is recomputed over the VISIBLE set so a filter ranks its own
group. Four rankings were scored against the thirteen curated names, the only ground truth here:
prominence recovers 8, corner and readership 6 each. **No single scalar reproduces the curated set**
— which is the argument for keeping it as a seed rather than deriving it away.
[#7](https://github.com/jsundram/quartet-composers/issues/7) carries the scored comparison.

### ~~One composer is sized by a single month of page views~~ — done, 2026-09-10
The premise was wrong: `Fernand de la Tombelle` is a REDLINK (the article is at `de La Tombelle`),
so the canonical fell back to the raw title and the API was asked for a page nobody has written.
That request succeeds (invariant 5) and returned a stray hit that became his median. Nothing
downstream could see it — right shape, aligned series, plausible number. Three repairs:
`TITLE_FIXES` in `fetch_wikidata.py`, no invented canonical for a title that did not resolve, and
`validate.py`'s `check_resolved()`. The lesson is invariant 5's own, one step earlier: noticing
there is no title to ask is the other half of asking the right one.

### ~~Readership was counted under whatever the article is called TODAY~~ — done, 2026-09-08, [#23](https://github.com/jsundram/quartet-composers/issues/23)
Invariant 15, and the rule lives in `scripts/pagemoves.py`. Fanny Hensel shipped a median of 500
against a real 5,217 and the app captioned the rename as an obituary. **Twelve** articles had moved,
not one; only Fanny's is inside the statistic window, which is why a survey that priced the last
twelve months found a category of one. Three parts deliberately: an offline detector that only
generates SUSPECTS (no clean threshold — real moves run 9× to 1163×, genuine growth reaches 8×), the
move LOG as the arbiter of whether a move happened, and a numeric check of whether it STUCK, because
the log records events and not tenures.
Still open deliberately: an old title that is neither a redirect nor the qualifier-stripped form
(deleted, or now a different article) is unreachable from the canonical, so a move into one goes
unrepaired — `validate.py` says so rather than shipping it quietly.

---

## Interface

### Pressing Full screen during the un-fit tween pins the chart mid-tween — **known defect**
Clearing a filter tweens the frame out over 420ms. `setFull()` asks for a `Chart.resize()` on the
next frame, and `resize()` keeps whatever transform it finds when the reader has pinched — measured
by `zoomed()`, which cannot tell a pinch from a tween in flight. So a Full screen press inside that
420ms lands at k≈1.05 with the reset button lit and nothing finishes the tween. The fix is probably
for `resize()` to read the tween's TARGET (d3 keeps it on the node) or for `setFull()` to interrupt
to the target first. `ui.test.mjs`'s in-place reset works around it by letting the full-screen
relayout land first, which is a workaround in the suite and not a fix in the app.

### The full-screen strip drops four things, and says so nowhere
`tight()` trims the panel to two lines for the fixed-height strip: the percentile line, the
Wikipedia link, Prev/Next and the 12-month range all disappear. All four are one tap away and back
the moment you leave full screen. Recorded here so the omission is deliberate rather than forgotten.

### The Fame view drops birth year entirely
Which is what the mocked-up "canon path" would have added: joining the repertoire in birth order
draws the chronological walk through output-and-attention space without spending an axis on it.
Proposed, not chosen — the direction picked was B as mocked. Cheap to add if wanted.

### The share card labels six of the thirteen named composers
Richter, Shostakovich, Krommer, Ellerton, Tchaikovsky, Debussy and Prokofiev have dots on
`assets/og.png` but no names. At 1200×630 that is a deliberate density call, but it means the card's
key names a set the card only half-identifies. `make-og-svg.py` places its six labels by hand rather
than with a placer.

### A phone seats about twelve chart labels, whatever is emphasised
Measured across six emphasis sets at 390×844: 10, 11, 11, 11, 12, 12 placed. The budget is not the
constraint — at rest `cap` is pinned to the seed count — boxes that fit are. So a thirteen-name set
leaves one ring unnamed on a phone while the same set names all thirteen on a desktop. Options: a
larger `base` on narrow screens, dropping the ring for a dot the placer could not name, or letting a
label overhang the left margin. Each trades against something the resting view gets right today.

### The swarm hides the quartet count entirely
Documented in the hint text, but a reader landing on `#v=swarm` has to read the hint to know the
vertical axis means nothing. Consider dimming or removing the y-axis label there; absent is quieter
than it should be.

### Surname extraction is a heuristic on human names
`SURNAME` in `names.js` overrides the names the "last word" rule gets wrong. There will be more
nobody has noticed: French particles are dropped where a French index would keep them
(`de la Tombelle` → `Tombelle`), and a future non-Western name order will be silently reversed.
`Names.staleOverrides()` catches renames, not misjudgements. The stakes rose when the chart started
printing the same short form — a misjudged surname is now on the plot, not only in a table cell
whose `title` carries the full name.

**AUDITED against the whole roster, 2026-09-05**, and worth redoing after a re-scrape rather than
trusting. This is the record; `names.js` points here rather than carrying it, because the audit is
history and the rules it produced are in `scripts/names.test.mjs`. Two classes can break the rule
and both were checked exhaustively:
- **family-name-first** — only "Chen Yi". "Isang Yun", "Unsuk Chin" and "Shigeru Kan-no" carry
  Westernised article titles, so the last word IS the family name and the rule is right.
- **compound surnames** — found by listing the penultimate word of every 3-or-more-word name. Most
  are ordinary middle names; the overrides in `SURNAME` are the ones that are not.

### Two Fame dots can still overlap, in ways the golden-ratio jitter does not cover — **known defect**
[#45](https://github.com/jsundram/quartet-composers/issues/45) replaced per-name hash jitter with
`spreadJq()`: rank each quartet-count stripe by readership and walk `frac(k·φ)`, so dots adjacent in
y are pushed maximally apart in x. Debussy and Gershwin went from 0.469px apart to over 6px. Two
residuals survive, both measured, neither worth a mechanism yet:

- **Across stripes.** Adjacent counts are 0.079 decades apart where the roster piles up and the
  jitter is ±0.045 wide, so stripes overlap by construction — Rigel (6) and Martinaitytė (5) sit
  0.78px apart on a phone. Ranking inside a stripe cannot see this.
- **Along a run of near-ties.** The three-distance theorem bounds the gap between dots ADJACENT in
  the sequence; five composers sit on 38–39 views and two of them five ranks apart come within
  1.11px. The guarantee degrades as ~1/(φ·m) across a tied run of m.

A real fix is a relaxation pass — detect overlaps in screen space and repel, as `MIN_SEP` does for
the ring. It stops being a jitter at that point: it costs the "deterministic, pure function of the
row" property that lets `make-og-svg.py` duplicate it offline (invariant 14). Do not start without
deciding that trade. `ui.test.mjs` 4e2 holds a 1px floor per stripe.

### ~~A filter left the group with no emphasis of its own~~ — done, 2026-09-05
All the ringed outliers are men, so "Women" dimmed every ring to 0.07 and then cropped them off
screen once the frame started fitting the filter. The ring budget is now filled first by the curated
outliers the filter kept and then by `prom`, so it says the same thing about whatever group is on
screen. Half of [#7](https://github.com/jsundram/quartet-composers/issues/7): the ring is derived
because "wrote a lot and is read little" is computable over any group; the FILL is not.

### ~~A filter left the frame on the whole field~~ — done, 2026-09-05, [#6](https://github.com/jsundram/quartet-composers/issues/6)
Filtering to the women showed the group you had just filtered AWAY at full resolution.
`computeResting()` fits the frame to the kept dots, `resetZoom()` returns there, and `zoomed()` is
measured against it. It compounds with the zoom-driven label budget: closing in takes the view from
three names to eighteen, which turns "where are they" into "who are they". Deliberately NOT re-fitted
mid-brush-drag — the chart flying around under a moving finger is worse than the stale frame.

### ~~Chart labels printed the full Wikipedia title~~ — done, 2026-09-05, [#2](https://github.com/jsundram/quartet-composers/issues/2)
15 characters average where the table had settled on 7. The rule moved into `names.js` and serves
both forms from one shared-surname map, so they cannot drift about who needs more than a surname.
The win is not tidiness: `pickLabels()` is a greedy first-come placer, so halving every box is what
lets the names behind it find room.

### ~~The detail panel wastes most of its column on desktop~~ — done, 2026-09-06, [#13](https://github.com/jsundram/quartet-composers/issues/13)
~200px to ~306px, and the extra 100px says what the panel could not: whether a readership is steady
or spiking. The window went from 12 months to everything the API has, which cost nothing at the
network and 1.9 MB in `data/`; the headline number did NOT move, because `STAT_MONTHS` stays 12 and
`validate.py` now recomputes one from the other. The series ships as its own file because
`composers.json` is a BOOT dep and 884 series are ten times the roster's size. Two things it turned
up: a null month has to BREAK the path, and the hover reservation had to grow with it — caught by
measurement rather than by eye. The caption rule and the per-month readout are in CLAUDE.md.

### ~~1580–1700 is ~20% of the x-axis for three composers~~ — decided, 2026-09-05
The premise was wrong, which is why it looked like a trade-off: Allegri, Scarlatti and Telemann have
no stated quartet count, so the domain was spending 31% of the width where no dot can ever be drawn.
`X_DOMAIN` is derived in `setData()` from the PLOTTABLE birth years, snapped to a 50-year grid.
`make-og-svg.py` derives the same domain; keep them in step.

### ~~Lifespan is a diverging ramp, which is the wrong colour job~~ — done, 2026-09-05
YlGnBu, sequential, hot to cold — the honest job for a magnitude. The diverging ramp needed a
baseline it never had (it pivoted on the median lifespan of whoever was in the dataset, so the pivot
moved when the data did) and its neutral midpoint sat at 1.61:1 against `--plot`, making the most
COMMON lifespan the least visible dot. Stepped darker than canonical YlGnBu because `#edf8b1` is
1.08:1 on this surface; everything clears 3:1 and stays monotone in lightness in both modes, checked
with the palette validator rather than by eye.

### ~~A filter left the FILL with nothing to say~~ — done, 2026-09-07, [#7](https://github.com/jsundram/quartet-composers/issues/7)
Every name in `CANON` is a man, so "Women" drew 219 dots with three earned rings and nothing filled.
Deriving the fill was rejected again — a canon is a claim about what gets played, and no ranking
reproduces one — so the answer is a SECOND hand-written list, `WOMEN_CANON`, swapped in by
`Chart.setRepertoire()`. **Gated to the filter by design**: none of the nine clears 10,000 readers a
month, so at rest they would be nine filled dots in the densest part of the cloud under a key that
holds Mozart. The resting view, "Men" and the share card are byte-identical.
It exposed a defect the ring had all along: prominence is distance from the cloud's centre, so a
corner full of composers all scores high and nothing visual broke the tie — the ring landed 4px from
a filled dot. A derived ring now clears every emphasised dot by `MIN_SEP`, measured in screen space,
which also means re-deriving in `setMode()` and `resize()`.

### ~~The lede hardcoded three claims about the data, then described Fame in all four views, then collapsed the page~~ — done, 2026-09-07 to 09, [#24](https://github.com/jsundram/quartet-composers/issues/24), [#27](https://github.com/jsundram/quartet-composers/issues/27), [#36](https://github.com/jsundram/quartet-composers/issues/36)
Three issues, one sentence, and the end of it was DELETION — the lede is one static line now.
The shape of the lesson is worth keeping. First the typed claims were wrong (Cambini's median,
and a birth span that went false under the Women filter), so they were built from
`Chart.emphasisStats()`. Then #24 found the axis clause: true in Fame, false in Timeline and Swarm,
and already stated twice on screen by the axis titles and the per-mode hint — **cut, not derived**,
because a third statement can only be the copy that goes stale. Then the built clause turned out to
change LENGTH, so it emptied outside Fame and the paragraph collapsed, lifting the pill you had just
pressed 93px on a phone (#27). That bought a measured `reserveLede()`, a width-guarded
`ResizeObserver` and three suite sections — and still moved the page 20px, because the gender pill
changes what "resting" means (#36). So the sentence went.
What survives: the legend names the highlighted set, the axis titles and hint name the axes, and
`ui.test.mjs` 4m checks those two rather than the sentence, so cutting the prose could not quietly
cut the information. **The ordering is the lesson** — ask whether prose should exist before building
a mechanism to make it behave.

### ~~A view switch still moves the switcher, because each view sizes its own plot~~ — done, 2026-09-08, [#29](https://github.com/jsundram/quartet-composers/issues/29)
`measure()` picks the aspect ratio per mode, so pressing Timeline on a phone shortened the plot and
everything under it — the switcher pill included — came up to meet your finger. The ratios are right;
the ORDER changed. `.controls` now precedes `#plot`, on the rule the full-screen strip and
`.compact`'s reservation already follow: **nothing a finger rests on may be placed by a box the same
press resizes.**

| pressing each view in place | switcher moved, before | after | plot still resizes by |
|---|---|---|---|
| 390x844 | 61px | 0px | 61px |
| 1280x900 | 150px | 0px | 150px |

The desktop number is the surprise and the reason this is not phone-scoped. It costs 94px of the
phone's first screen, which leaves 92% of the plot above the fold instead of all of it. Full screen
keeps the controls underneath deliberately: `#plot` is `flex:1` there, so there is nothing to absorb.
`placeDetail()` had to re-anchor on `.legend`, or the phone panel lands above the plot.

### ~~Nothing compares `V` between a branch and its base~~ — done, 2026-09-08, [#32](https://github.com/jsundram/quartet-composers/issues/32)
`sw-lint.py`'s headline check reads `git diff --cached`, so it only ever bit in the hook — and #28
and #30 both bumped `v32` -> `v33` from the same base, byte-identically, so a three-way merge
resolved them silently and #30 would have landed three SHELL files with a net `V` delta of ZERO.
Caught by hand in review. `--base REF` is the sixth check, on pull requests, and the decision is per
PUSH: any bump clears it, the rule being only that `V` ends up past the base's.
**It takes TWO refs, and that is the design.** What the branch CHANGED is read from the merge base
(so a base that moved ahead does not come back as files this branch touched, which is also what
survives a rebase or a squash); which `V` it must CLEAR is read from the base BRANCH's tip, because
that is what it merges into — and against the merge base the motivating case PASSES. Three smaller
decisions, each with a case: the SHELL list is the UNION of both sides, a `V` tail that goes DOWN
fails with its own message, and a renamed stem is a deliberate reset. A missing merge base is
REPORTED rather than skipped, which is why the job checks out with `fetch-depth: 0`.

### ~~Three filters, three ways to undo them, and one of them moved the page~~ — done, 2026-09-09, [#35](https://github.com/jsundram/quartet-composers/issues/35), with [#31](https://github.com/jsundram/quartet-composers/issues/31)
One permanent `Reset filters` button beside `Reset zoom` clears all three filters, search included.
**The layout consequence is the point**: a control that is always present cannot resize the row it
is in, so the whole class of defect stops being possible rather than being mitigated — `#hist-clear`
left the filter bar entirely, taking its alignment and its checks with it. It also means the state
may be updated ABOVE the `settled` guard, so it lights on a drag's first frame, which the button it
replaces could never do. `resetFilters()` runs exactly ONE `applyFilters()`; 4m5 asserts the single
repaint with a MutationObserver rather than trusting the reading.
Two measurements worth keeping. Icons paid for the third button only by leaving the row: at 360 a
third word button is three lines (138px) and shrinking Share/Full screen in place is still three.
And the breakpoint later moved from 640 to 1100 (then to two intervals) because the row is two
lines from 641 to 1054 as well — the original table only ever asked about phones. See the
`placeChartTools()` bullet in CLAUDE.md for the bands and the four things a change must keep.
#31's own lesson outlived its fix: the first version of that entry prescribed reserving the
button's WIDTH, and the row never wrapped at all — the wrap points are pinned by `order`. A layout
fix prescribed from a description of the bug rather than a measurement of it would have reserved a
width that was never the constraint. Its sibling (`#hist-clear` at 28px against the 40px floor) hid
because the tap-target scan filters on `offsetParent`, which is null while an element is `hidden`:
**a state that hides a control needs its own pass there.**

---

## Pipeline

### `fetch_views.py --force` refetches every article
There is no way to refresh a single composer after fixing their title. Minor, but it makes fixing
one bad row a two-minute job instead of a two-second one.

### `validate.py` cannot re-check title resolution offline
It asserts that every page-view series is keyed by a canonical title *according to the cached
`people.json`*, so a stale `people.json` would satisfy it. The check that closes this is an online
one: re-resolve a sample and confirm nothing moved. Worth a periodic job rather than the commit gate.

### ~~The V bump was a chore in 8 of every 12 UI commits~~ — done, 2026-09-11
Measured while grading the repo against "lean": a one-idea UI change edited five files, and three
were bookkeeping — `sw.js` for the bump, plus the two docs. The bump is the one that is purely
derivable, since `sw-lint.py` already knows which files are `SHELL` and which of them the commit
stages, so the hook now runs `--fix` and writes it.
**Auto-write rather than block, and decline rather than guess.** Blocking was the other option and
is worse: the bump is not a decision, so stopping the commit to ask for one spends the author's
attention on arithmetic. It declines in the three states where writing would be wrong — mid-merge
(the resolution is the human's, and `--base` covers #32 in CI), with unstaged `sw.js` edits
(`git add sw.js` would sweep in work the author left out), and with no numeric tail (check 4 owns
that) — and in each it falls back to the old nag, so a decline is never silent.
`refresh.py` lost its own copy of the increment and calls `--bump` instead: two pieces of code that
rewrite the same declaration are two that can come to disagree about what it looks like.
Known and accepted: `git commit --amend` that adds a further shell edit bumps a second time, because
`HEAD` is then the commit being replaced. One extra cache generation costs one re-download, which is
the cheap side of invariant 1.

### ~~A top-up refetched the 62 articles younger than the window~~ — done, 2026-09-06
"Needs fetching" was `any(month not in cached)`, and an article created in 2019 never has a 2015
month, so it was missing something forever. A month the API answered "nothing" for is recorded as a
**null**; a MISSING month still means "never asked". A second run is now a true no-op at the
network. A 404 is deliberately NOT cached that way: it means the canonical title is wrong, and
caching it would silence the report that says so.

### ~~`data/pageviews.json` was 1.9 MB and rewritten whole on every top-up~~ — done, 2026-09-06
Flat arrays aligned to the shared `months` axis: **1.88 MB → 502 KB**, and a top-up changes 884
lines instead of 118k. The price is that alignment is load-bearing, so `build_data.py` and
`validate.py` both refuse a ragged cache and `validate.test.py` proves it.

---

## Testing

### The leanness pass, mid-flight — read this before touching the branch
Branch `claude/test-suite-effectiveness-5nmyk0`, pushed, no PR. The brief: this repo is a small
visualization that had become half comments and half tests, and much of its history is edits to docs
for numbers that move — apply the data-ink ratio to the codebase, aggressively but respectfully, by
DELETION.

**Done.** CLAUDE.md keeps every rule and lost every recomputable number (the three-way split is
stated at its top: rules here, history here, anything mechanical in a check). TODO.md's closed
entries are decision-plus-evidence. `prose-lint.py` and its suite are gone, with the thirteen doc
numbers they guarded. The `V` bump is `sw-lint.py --fix` in the hook, so it is not a human step and
`refresh.py` no longer carries a second copy of the regex. `codehash.py` proves a comments-only
change and both branch gates exempt one on that proof. `names.js` was cut from 158 lines to 141, 79
comment lines to 49, with `scripts/names.test.mjs` holding the rules the prose used to assert. The
statistic window is pinned and `fetch_views.test.py` runs on a frozen clock. `chart.js` and `app.js`
lost 101 comment lines between them, 8.9KB of 77KB, with no code change — codehash says so, and the
browser suite stayed at 259 green.

**`codehash.py` STAYS, suite included** — the decision, since it is the one place test code grew on
this branch. It is not scaffolding: both branch gates import `unchanged()`, the hook runs it, and it
is what made the three comment passes above safe to do at all. Its scenario suite is what makes a
wrong answer cheap (regex against division, `//` inside a template literal) and it found three
defects in the tool, so slimming it to the gate integration would be deleting the half that earns
the trust the gates place in it.

**Still owed, in order.** A second cut at `chart.js`/`app.js`, which is a different job from the
first: what is left there is nearly all local WHY, so it means deleting information rather than
words, and the question to ask per block is whether CLAUDE.md already argues it. `table.js` and
`histogram.js` are at about 30% comment and have not been touched. And the mutation catalogue below,
which is the thing that would let a check be DELETED with evidence rather than by eye.

**Two traps, both paid for once.** `git add -A` before running any harness that mutates the tree:
`git checkout --` restores from the INDEX, so a repair that is not staged is silently undone — that
is how an un-bootable `chart.js` shipped for two commits. And **a suite that dies at boot reddens
everything and is a VOID result, not a catch**: PAGE ERRORS in place of named failures, and a
mutation "caught" in a fraction of the usual time, is the tell.

### The suite misses pure functions, and nothing measures that but a mutation run
Measured Sep 2026: 39 one-line bugs injected, 25 caught. The data gate caught 6 of 7, the browser
suite 13 of 22, `sw.test.mjs` 1 of 5 — and every miss was a pure function or an untested entry
point, not one a layout or interaction bug. The rules that came out of it are in CLAUDE.md's Testing
section. What is still owed, in the order it is worth doing:

- ~~`fetch_views.test.py` cannot fail for the value it is named after~~ — done, 2026-09-12. It took
  `months_back(1)` as the last complete month and refused the month after that, so a `months_back()`
  ending ON the month in progress answered its own question — demonstrated, not argued: with that
  one-line mutation in place the old case still passed. The clock is frozen mid-month now, both
  literals come from the calendar, and a new case pins the whole axis (FLOOR at one end, the last
  complete month at the other). The mutation reddens two cases.
  (The same charge against `sw.test.mjs` reading `BOOT` out of `sw.js` is WITHDRAWN, with the
  install/activate coverage gap behind it: both files are vendored pwa-starter, stamped, and belong
  upstream. `sw.js`'s 588 lines are the most under-covered here and are deliberately not ours.)
- ~~The fold has no behavioural check~~ — done, 2026-09-11, with the prose-lint deletion below.
  `ui.test.mjs` asks `Table.matches('lutoslawski')` for Lutosławski and asserts a padded query
  matches the same rows as a bare one.
- ~~Nothing pins the statistic window~~ — done, 2026-09-12. `STAT_WINDOW` in `validate.py` holds
  the three artifacts that state it to twelve: the `views_months` axis, `readership.json`'s
  `stat_months`, and the `views_stat` prose the provenance line PRINTS, which is the one a reader
  can see. Two cases in `validate.test.py`, both red without it — one widens the window to 18 and
  rebuilds every median so the dataset is internally consistent, which is exactly what the
  one-character edit to `STAT_MONTHS` ships.
- ~~`names.js` has no suite~~ — done, 2026-09-12. `scripts/names.test.mjs` loads the module under a
  `window` stub and covers the last-word rule, both display forms, the floor-and-margin award, and
  three properties of the SHIPPED roster (no two composers share a chart label or a filed name; the
  filed column keeps surname groups contiguous). Proved non-vacuous by five mutations — dropping the
  margin, forename-as-suffix-slice, dropping the override lookup, dropping suffix handling, and
  letting the bare surname into `filed()` — each reddening 2 to 7 named checks. The suite is what
  made the comment pass below safe: every count the file stated in prose is now either a check or
  deleted.
- **A mutation catalogue, committed.** `ablate.py` proves a new check fails without its fix; nothing
  proves the suite catches a bug nobody wrote a check for, which is why answering that took an
  investigation rather than a command. A `scripts/mutate.py` with ~25 curated mutations and a stated
  floor makes it a command — and makes deleting a check safe, since the rate says whether anything
  else was holding the property up.

### ~~Nothing could tell a comment pass from a code deletion~~ — done, 2026-09-11
A comment-compression pass through `chart.js` deleted `function hash()` and `const MIN_SEP`, both
inside blocks it was rewriting. Both were repaired within minutes; what was not caught is that a
restore from the INDEX — my own mutation harness, whose `git checkout --` reads the index, which
still held the broken copy — silently undid the repair, and it was committed and pushed. The branch
was un-bootable for two commits. The tell was there and was waved off: one mutation "caught" in 11s
with PAGE ERRORS instead of a named failure, which is what a dead boot looks like.
The audit that should have caught it was "diff the file and read every line that is not a comment",
i.e. a human reading hundreds of changed lines for an absence, last thing. `scripts/codehash.py`
does it mechanically instead — AST for Python, a re-parse-verified scanner for JS and CSS — and both
branch gates import `unchanged()`, so a comments-only hunk is exempted on PROOF rather than on a
`No-test:` trailer. Verified against the real history: at the bad commit it reports chart.js as
**CODE CHANGED** and app.js, in that same commit, as comments-only.
Two things its own suite found in it: an unterminated block comment was stripped to EOF leaving text
that parsed, so the SOURCE is parsed too now; and a comment inside a template interpolation counts
as code, which is left that way because recursing into `${…}` means deleting inside a string, and a
false alarm is cheaper than a false pass.
Two smaller repairs fell out. Both gates now set `sys.dont_write_bytecode` — an import wrote
`scripts/__pycache__/` into the throwaway repos their own suite builds, which turned "the working
tree is clean afterwards" red, and a gate that litters cannot claim to restore. And every source
fixture in `fix-lint.test.py` carries real code now: they expressed "a source change" as `// FIXED`,
which the new exemption correctly reads as nothing to prove.

### ~~prose-lint kept thirteen numbers honest that should not have been written~~ — done, 2026-09-11
It was built to stop the docs lying, and it worked — it found three live drifts the day it was
written. But it is the wrong branch of this repo's own built-or-cut rule: the cure for "a doc states
a number that goes stale" is not a gate that checks the number, it is not writing the number.
Eleven of its twelve distinct claims bought a reader nothing — four curated-list sizes, five suite
case counts, a count of the bullets directly beneath it, and a `FOLD` name count. The twelfth,
"twelve articles moved", carried the one real point (it was not one), and says so now without the
integer.
**The shape is `reserveLede()` again**, one file over: build a mechanism to make a sentence behave,
then discover the sentence should not exist. It even argued for the wrong branch in its own
docstring — "a claim can often be made checkable by being made precise… worth reaching for first."
Cheaper than deriving it, more expensive than deleting it.
What it cost, measured over one sitting: five forced doc edits, **two of which were pure line-wrap
accidents** — a reflowed paragraph and a stale fact produce the same message, because the check
cannot tell them apart. Against that, `chart.js` had the rule right about `CANON` before any of this
existed: "deliberately NOT a count — every place that printed the number went stale in the same
commit."
So the numbers went, then the lint went: −301 lines, one hook step and two CI steps. What survives
is the half that is not prose — `og-lint.py`'s `check_counts()`, which holds the totals in
`manifest.json` and the two meta descriptions to something the data supports, because those strings
SHIP to readers. And the `FOLD` transcription was replaced by a check of the fold itself, which is
what should have guarded it all along.
`fix-lint.test.py` lost its stated-size case for the same reason — its subject was a number in the
docs — and prints its own total instead. A check goes when you delete what it was checking; not
because it is annoying.

### ~~`ui-test.sh` scores 231/240 under CI's Linux headless Chrome~~ — done, 2026-09-10, [#50](https://github.com/jsundram/quartet-composers/issues/50), [#53](https://github.com/jsundram/quartet-composers/issues/53), [#56](https://github.com/jsundram/quartet-composers/issues/56)
Never a browser problem: `ubuntu-latest` ships `/usr/bin/google-chrome` and `find_chrome` finds it.
Eight of the nine failures were one cause, the missing POINTER — and the fix this entry prescribed
was wrong in the way this repo cares about, silently. `Emulation.setEmulatedMedia` accepts
`features:[{name:"hover"},{name:"pointer"}]`, returns success and changes nothing (measured on
Chromium 141, headless and headful; `prefers-color-scheme` in the same call does take).
`--blink-settings` works at startup and is worse: the first `setTouchEmulationEnabled` restores the
platform value for every page in the browser, so one phone section poisons every desktop section
after it. What works is giving the machine a pointer rather than arguing with the page about one —
Chrome under `xvfb-run`, which a touch toggle restores TO.
The ninth was a FONT metric and was a real layout defect (#53): at 360px, the common Android width,
the table overflowed in EVERY face including SF, so the 390px check had been passing on the one
width where the narrowest font happens to clear. Fixed by giving back width that carried nothing —
the header word over a three-digit column, and the phone gutters — and the check now asserts both
widths. Since verified on Ubuntu 24.04 / Chromium 141 with `fc-match system-ui` resolving to DejaVu.
And the suite runs in CI now (#56). Three things the job needs, one of them not about the browser:
**node 22** (the CDP client is the global `WebSocket`), **`xvfb-run`**, and the **full Chrome** —
never `chrome-headless-shell`, which reports no pointer even under a display. The fourth was not on
the list and is the one worth remembering: **a SKIP IS A PASS**, so `REQUIRE_BROWSER=1` turns it
into a failure wherever a runner could quietly lose its Chrome. The prize is bigger than the suite —
`ablate.py --with-ui` runs there too, so a branch whose source is the page is ablated by something
other than a human remembering to.

---

## Deliberately not doing

**Per-language page views.** English Wikipedia readership systematically undercounts non-Anglophone
composers — a Czech composer's readers are on cs.wikipedia. Fixing it means Wikidata sitelinks and a
per-language fan-out, which trades a clean, stated bias for a messy, hidden one (which languages?
weighted how?). The current approach is to name the measure honestly instead. Revisit only with a
specific reason.

**Summing a composer's redirects into their readership.** Measured, not assumed:
`audit_redirects.py` prices all 2,888 redirects into the 884 articles, and 436 composers do read
higher — by a median of **1.024×**. Only 49 exceed 10%, and nothing in `CANON` moves at all. What the
sum buys is invisible on an axis spanning five orders of magnitude; what it costs is a stated measure
traded for one that depends on how many aliases an article happened to accumulate. A page MOVE is
not this: the article lived at the old title, so those months are the same measurement under a
different string, and they are stitched (invariant 15).

**Wikidata as a source for quartet counts.** Evaluated and rejected on evidence: Beethoven's
quartets are typed as generic "musical work/composition" with nothing linking them to the genre, so
a SPARQL count over the whole corpus returns four composers. See the note in `scrape_list.py`.
