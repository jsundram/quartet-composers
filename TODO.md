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

### ~~One `No-test:` trailer disarmed both gates for a whole branch~~ — done, 2026-09-12
Found by using the escape hatch honestly. Two commits on the leanness branch carried
`No-test: TODO.md only` — true sentences about docs-only commits — and `excused()` read a trailer
anywhere in the range, so both gates skipped the branch entirely. `ablate --base` printed "skipped by
a No-test: trailer" while that branch rewrote `validate.py`, `names.js` and the gates themselves.
Scoping the trailer to commits that CHANGED SOURCE left the second half of the same hole: one
legitimately excused file excused every file beside it, which on a branch that deletes prose AND
rewrites a module is most of the diff. So it is per FILE now — a trailer speaks for the files its own
commit touched, and a file edited again with no trailer is back in the gate, because the second edit
is the unexplained one. The reason travels with the file, so a gate names what it let past and why.
`fix-lint.py` calls `excused()` instead of carrying a second copy of the regex; that was the third
exemption the pair had split into two implementations.
Four cases in `fix-lint.test.py`, all red under the rule they replace. And the branch that found it
is now ablated for real: a named check goes red in `names.test.mjs`, `fix-lint.test.py`,
`sw-lint.test.py` and `validate.test.py`.

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

## IMSLP

### ~~The dataset is built and joined; nothing is wired into the app yet~~ — done, 2026-09-15, [#61](https://github.com/jsundram/quartet-composers/issues/61)
`scripts/fetch_imslp.py` (network, cached in `data/imslp-scrape.json`) and `scripts/build_imslp.py`
(offline, writes `data/imslp-join.json`) feed `build_data.py`, which now writes TWO IMSLP columns
into `composers.json` — `imslp`, the work count, and `imslp_cat`, the category or `""` where one
line derives it — plus a third shipped file, `imslp-works.json` (81 KB, SHELL and not BOOT, not
rendered yet). The table has an `On IMSLP` column linking the number to the composer's category,
and the detail panel a row of matching Wikipedia and IMSLP pills where the bare Wikipedia
link used to sit alone. `V` is at v68.

The pipeline REORDERED to get there: `build_imslp.py` used to read `composers.json`, which would
now be a cycle, so it calls `build_data.build_rows()` instead — one reduction of the caches, so
the join and the app cannot disagree about who is on this list (invariant 4).

What the findings below turned into, in the end: the count shipped is `works_n`, printed as
"quartets" — looser than the parse, on purpose, because that is IMSLP's own category and what the
reader came for, and the danger the findings are really about is subtracting it from the `Quartets`
column rather than what it is called; `null` / `0`-with-a-link / `0`-without are the three answers,
carried by `imslp_cat` rather than by the digit (invariant 16); and the colour channel was not
taken.

**What is in it.** IMSLP catalogues 4,215 work pages under its own instrumentation category
`For 2 violins, viola, cello`, plus 722 more under the `(arr)` category, spread over 1,771
composer categories. 1,658 of those pages belong to people on this roster; 461 roster rows are
placed on IMSLP at all, 302 of them with at least one quartet page. Every one of the 4,926 pages
carries at least one score file, so "has a page" and "has a score" are the same question today.

**The join matches no names.** Work title → `(Surname, Forename)` → that IMSLP category page →
its `{{Wikidata|Q…}}` or `[[wikipedia:…]]` link → resolved through en.wikipedia to a canonical
title and QID → our `people.json` QID. Four rungs, in evidence order, counted over the composers
they placed: `wp-qid` 272, `p839` 102, `name+dates` 53, `imslp-qid` 34. Only the last rung starts
from a spelling, and it is accepted only when IMSLP's birth AND death years agree with Wikidata's
— five candidates were rejected on exactly that and are printed by name.

**Three things a UI must not get wrong.**

1. *A page is not a quartet, and nothing in the data can tell you which.* IMSLP's unit is a
   publication entry: Beethoven's 16 quartets occupy 23 pages — three of which are complete-set
   editions (`Sämtliche Streichquartette`, `17 Streichquartette`, `Trios, Quartette und Quintette`),
   two are multi-work opus pages, one is the Grosse Fuge and one a fragment. Haydn's 68 occupy 97.
   It runs the other way too: Giuseppe Cambini's stated 149 quartets are 14 pages. Of the 297 rows
   with both numbers, 61 have more pages than stated quartets and 129 have fewer.
   **There is no honest "% of their quartets you can download."** The two columns count different
   things and dividing them is a confident wrong number on every row. Show the page count, label
   it "score pages on IMSLP", and let the two sit side by side.
   The obvious repair — flag the collections and subtract them — **was tried and does not work**:
   IMSLP's own `Category:Collections` holds 22 of the 4,926 pages and none of Beethoven's three.
   The flag is fetched and shipped because it is free, and it must not be used as though it were
   complete. Deciding set-vs-single per page would mean parsing work titles ("6 String Quartets,
   Op.18"), which is a counting heuristic on top of a page count, and invariant 11's rule applies:
   grade it against the pages before believing it.

2. *Null, zero and absent are three answers.* `pages: 0` means IMSLP holds this composer and none
   of their quartets (159 rows — Stravinsky, Glass, Cage, Copland, Barber: all in copyright, which
   is the real finding and a good one). A row **missing from the join entirely** means we could
   not place them at all (423 rows), which is unknown, not empty. Colouring those two the same way
   states something false about 423 composers. This is invariant 10 arriving in a new field.

3. *The 423 is soft evidence, not proof.* It means: no Wikidata P839, no IMSLP composer page
   linking their article, and no page under any one-, two- or three-token `Surname, Forename`
   inversion of their name. That is decent evidence of absence and it is not the same as asking.
   Any copy on the page has to say "no IMSLP page found", never "not on IMSLP".

**What is still NOT done, deliberately:**
- **`imslp-works.json` is shipped and unread.** It is precached so the SHELL contract was settled
  once rather than twice; rendering the per-page list in the detail panel is the next feature and
  has to answer the panel's fixed-height problem first.
- **No "has scores" filter.** A fourth filter needs its own module on the `applyFilters()`
  contract (a Set of indices or null), not another special case in `app.js`.
- **No colour channel, and this is the one to argue with rather than repeat.** Fame already spends
  hue on emphasis and the timeline spends it on the lifespan ramp (invariant 8), so availability
  would be a fourth encoding competing for the channel already carrying the view's argument — and
  it is a three-state fact with a large "unknown" bucket, which is the hardest kind of thing to
  put in a legend honestly.
- **Arrangements are fetched and shipped nowhere.** Separate IMSLP category, different claim.
- `og-lint.py`'s `check_counts()` knows the two totals the shipped strings may state, so no IMSLP
  total may reach `manifest.json` or `index.html` without teaching it one.

### ~~Catalogue numbers de-duplicate the sets~~ — done, 2026-09-12
The page count is no longer the only number: `build_imslp.py` now reads `Opus/Catalogue Number`
off each work page and counts DISTINCT WORKS. **1,658 pages hold 2,046 works.** The mechanism is
that a set page states the designation its members share — `6 String Quartets, Op.18` carries
`Op.18` while the six individual pages carry `Op.18 No.1` through `No.6` — so expanding the set
and merging by id makes those six works rather than twelve.

Beethoven lands on 18: his 16 quartets plus the Große Fuge and the Hess 30 fugue, which is exactly
what IMSLP's own `Sämtliche Streichquartette` says it contains, and it explains the "18 quartets"
that looked like an error. Dvořák lands on 14 against a stated 14, Villa-Lobos 17 against 17,
Myaskovsky 13 against 13. The correction runs both ways and that is the point: Cambini's 14 pages
carry **76** works (his Trimpert numbers are what make that readable), Pleyel's 22 carry 68 against
a stated 70, while Boccherini's 79 pages collapse to 75 works. Exact agreement with the stated
count rose from 107 composers to 121.

Three rules are load-bearing and each has a case in `imslp.test.py` that goes red without it:

- **Alternate catalogues zip POSITIONALLY.** A page naming `Op.24 ; G.183-188` is six works named
  twice, not twelve; counting them separately put Boccherini at 153. Designations that disagree
  about how many works are present cannot be aligned, so the longest wins and the others are
  dropped rather than added.
- **Expansion needs evidence that N WORKS are present**, not merely a plural noun. `Echo of Songs,
  B.152` says "12 pieces" and is one work in twelve movements; expanding it invented eleven Dvořák
  quartets. The evidence accepted is IMSLP typing the page a Collection, or a title that opens
  with a number and names quartets — which is how Vachon Op.11 and both Kammel sets are caught,
  since they leave `Page Type` blank.
- **An anthology with no catalogue number is dropped, not counted.** `Selected String Quartets`
  reprints works that already have pages of their own, so adding it re-counts them.

**`works_n` is still not `quartets`.** 67 of the 297 composers with both numbers now exceed their
stated count, and the page is usually the better source: Rigel and Förster each hold three pages
of six-quartet sets against a stated six, and IMSLP's instrumentation category legitimately holds
fugues, fragments and single movements no numbered list counts. Invariant 11's rule applies to
this parse as much as to `scrape_list.py` — grade it against the page, not against the other
number. **An `audit_catalogue.py` that prints the parsed work ids beside their source field, for
a human to grade, is the honest next step** and is not written yet.

Two sources not yet used, both suggested during review: IMSLP's `List of works by <composer>`
pages enumerate a full catalogue and would give a better denominator than Wikipedia prose; and the
`Year/Date of Composition` field is already cached in `data/imslp-scrape.json` and unread.

### Parsing the work page: what the fields do and do not settle
Answered with a 100-page sample, 2026-09-11. IMSLP work pages carry two structured fields the
crawl does not read yet, and they are much better than anything the title or the categories give:

- **`Page Type=Collection`** is the set marker, and it beats `Category:Collections` by a mile —
  34 of 100 sampled pages against 22 of all 4,926. It is still not reliable: `3 String Quartets,
  Op.2 (Fesca)`, `6 String Quartets, Op.11 (Vachon)` and both Kammel sets state a count in the
  title and leave the field blank.
- **`Number of Movements/Sections`** starts with a digit on 91 of 100, and — this is the useful
  part — it names its own UNIT in words. `String Quartet No.14, Op.131` says "7 movements";
  `6 String Quartets, Op.2` says "6 quartets". So a parse can tell a set from a single work, which
  is exactly what the page count cannot.

So yes, parsing helps a lot: 660 of the 4,215 pages state a leading count in the title, 55 more
imply one with no digit at all (`Sämtliche Streichquartette`, `Complete String Quartets`,
`Ausgewählte Quartette`), and the field would resolve most of both.

**What it does not fix is the double counting, which is the whole problem.** Beethoven's complete
editions overlap his individual pages, and the fields say so out loud: `Sämtliche Streichquartette`
= "18 quartets (score) in 4 volumes", `17 Streichquartette` = "17 pieces", `6 String Quartets,
Op.18` = "6 quartets", plus sixteen `String Quartet No.N` pages. Summing the parsed counts gives
about 67 for a composer who wrote 16. Deciding which page subsumes which is a bibliographic
containment problem and IMSLP has no field for it.

And the residue is genuinely ambiguous, not merely unparsed. Real values from the sample:
`"3 quartets (or six?)"` (Hoffmeister Op.11 — IMSLP itself is unsure), `"4 quartets, 2 quintets"`
(Cambini Op.23 — the page is not all quartets), `"19 pieces"`, `"3 sets of variations"`,
`"30 canons"`, and `"6 pieces"` on a page titled `6 String Quartets`. Note also that IMSLP's own
"18 quartets" for Beethoven disagrees with the canonical 16.

Done, above: the fields are fetched for the attributable pages and `works_n` ships beside `pages`.
`pages` stays the headline on the coverage report because it is the number IMSLP itself can be
checked against by clicking a link.

### ~~A candidate page's own identity was ignored~~ — done, 2026-09-11
`fetch_wp` resolved the Wikipedia articles named by composer pages that HAD a quartet and not the
ones reached by name guess, so 58 pages that state their own Wikidata item or Wikipedia article
were judged on birth and death years alone. Fixed: candidates go through the same resolution and
the identifier rung is tried first. 51 of the 53 name-reached matches are now confirmed by an
identifier rather than by a guess (`cand-qid`), which is the difference between evidence and a
coincidence of spelling.

The same fix surfaced a second rule. **IMSLP not knowing about a RECENT death is staleness, not
disagreement** — Sofia Gubaidulina's page is locked, states 1931 and no death, and she died in
2025, so an exact name and an exact birth year were being rejected by a page nobody has edited
since. `STALE_DEATH` is 4 years and the birth year must then match EXACTLY rather than within the
usual slack. It stays bounded on purpose: Thomas Wilson died in 2001 and IMSLP still calls him
living, and at twenty-five years a score has plausibly been uploaded since, so the silence is
evidence against the match rather than lag. Four rejections remain and all four are pages that
state no dates at all.

### The 27 pre-1900 absences are verified, and they are the only real gaps
After 1900 an absence is a copyright boundary. Before it, checked by exact prefix listing over
`Category:<Surname>,` rather than by guessing full titles: IMSLP files other people under 15 of
those 27 surnames (`Still, John`, twenty `Thompson, …`) and not one of these composers, so this is
absence and not a spelling the join failed to guess. 21 of the 27 were born after 1870, most are
women, and none is read more than four thousand times a month — Nancy Dalberg, Mary Lucas, Eva
Ruth Spalding, Frida Kern, Dorothy Gow. If this project ever wants a contribution target rather
than a visualisation, that list is it.

**A better candidate generator follows from the same check.** Prefix listing finds a composer whose
FORENAME is spelled differently on IMSLP, which exact-title guessing cannot; the complete IMSLP
person index is also available in bulk (`API.ISCR.php` `type=1`, 1,000 per request, ~28 requests
for the whole site), which would turn all 422 unknowns into offline-answerable facts instead of
one prefix query each.

**The audit page sorts and compacts.** Each composer's table sorts on any column independently —
a sort across the page would interleave composers and answer nothing — and runs of ids collapse
(`Op.72 No.1, Op.72 No.2, Op.72 No.3` reads `Op.72 No.1–3`). Only CONSECUTIVE numbers on an
identical stem collapse, so `G.183–185, G.188` keeps its gap visible, which is the point.

**The parse is graded on a page, not against another number.** `scripts/imslp-audit.py` renders
every quartet page of the 22 composers the chart highlights — `CANON`, `OUTLIERS` and
`WOMEN_CANON`, READ out of `chart.js` rather than copied, since they change spelling when the
pipeline runs (invariant 7) — with the raw `Opus/Catalogue Number` field beside the work ids
derived from it and a link to settle a disagreement by looking. That is invariant 11's rule
applied to the second parser this repo has: `audit_counts.py` does it for `scrape_list.py`, and
this does it for the catalogue reader.

403 pages and 426 works across the 22, and the counts are split by KIND because conflating them
was itself a defect the first version shipped: 6 pages state no catalogue number at all (counted as
one work each), 23 are anthologies stating none (dropped), and **14 state one the parser could not
read**. That last group is the point of the page and was being labelled "no catalogue number —
counted as one", which is a parse failure reported as an absent field, by the one page whose job is
to surface parse failures. Haydn's `{{HaydnHob|n383|III:1-83}}` is a three-argument template the
`{{X|Y}}` reader does not match; those Hoboken numbers still go unread, and now say so.

The catalogue-template gaps are [#63](https://github.com/jsundram/quartet-composers/issues/63):
`{{K6|417b}}` prints as `K6.417b` where the notation is `K.417b`, and `{{HaydnHob|…}}` takes three
arguments so it is never rewritten at all — which reads `Hob.III:1-83`, an 83-work set, as one
work. Neither double-counts; both lose merges, and one loses 82 works from a single page.

### ~~A Wikidata IMSLP id kept its namespace and matched nothing~~ — done, 2026-09-12
P839 states `Category:Stravinsky,_Igor`; a work title's parenthetical is the bare
`Stravinsky, Igor`. Comparing them unstripped meant a composer joined ONLY by P839 never matched
the works crawl, so they read "on IMSLP, no quartets" while holding some. Five composers lost 15
pages between them and Stravinsky was one of them — silent, because zero quartets is exactly the
answer nobody questions for a 20th-century composer. `strip_ns()` and a case in `imslp.test.py`.
Roster coverage went from 302 composers to **307**, 1,658 pages to 1,673, 2,046 works to 2,061.

### Canada's public domain is the rule that predicts this dataset
IMSLP is hosted in Canada and follows Canadian PD: free once the last surviving author **died
before 1972** (life + 50). Canada moved to life + 70 in 2023 but NOT retroactively, so it binds
only people who died in 1972 or later — which means the 1972 line is fixed and does not advance
each January the way a rolling term would. Cross-tabbed against this roster:

| | with scores | on IMSLP, none | no page found | share |
|---|---|---|---|---|
| died before 1972 | 280 | 70 | 21 | **75%** |
| died 1972+ | 25 | 73 | 137 | 10% |
| living | 2 | 12 | 264 | 1% |

So **91 composers are free to host and are not there** — that is the gap worth naming, and it is
a better target than the 27 pre-1900 absences because it is the set IMSLP could legally hold
today. Everything after 1972 is a waiting list rather than a gap; the earliest becomes free in
2043. This should replace "born before 1900" as the report's framing of absence, and it now does.

Two cautions. 27 composers have scores despite not being PD in Canada, led by Shostakovich
(died 1975) and Milhaud (died 1974); their files carry a mix of Public Domain, Creative Commons
and BSD tags, so it is freely licensed modern engraving plus edition-specific claims rather than
one rule. And the rule is about the last surviving AUTHOR — editor and arranger included — so a
modern edition of an old work is not automatically free.

### `icatno` is IMSLP's own work number, and it is available in bulk
The "Internal Ref. No." on a work page (`IGB 12` on Bottesini's Gran Duo Concertante) is
`I` + the composer's initials + a sequence, assigned by IMSLP to works that have no published
catalogue number; a page without one renders `None [force assignment]`. It is NOT in the page
wikitext — the `#fte:imslppage` extension generates it — but `API.ISCR.php` `type=2` returns it as
`intvals.icatno` for every work on the site, 1,000 per request.

**Not fetched, deliberately.** It identifies a PAGE, and an uncatalogued page already counts as one
work, so it would not change a single count; the whole list is ~230 requests and ~70 MB against a
volunteer-funded server. It would be worth having as a stable per-page key if this ever needs one
that survives a page MOVE, which is the same problem invariant 15 solves for article titles — at
which point fetch it once and cache it, rather than re-deriving.

### ~~Two bugs the works-file sample exposed~~ — done, 2026-09-12
Both found by writing out real rows for #61 rather than by any check, which is the argument for
showing sample data before agreeing a format.

- **The collection flag read the wrong source.** Bit 4 came from `Category:Collections` (22 of
  4,926 pages) instead of the page's own `Page Type=Collection`, so `17 Streichquartette` was
  going to ship with `works: 0` and nothing on the row to explain the zero.
- **`str.title()` mangled a mixed-case catalogue prefix.** Fanny Hensel's `HelH 277`
  (Hellwig-Unruh) printed as `Helh.277`. Normalising only the first letter fixes it and retires
  the `WoO` special case, which existed only to survive `.title()`. The work total is unchanged at
  2,061, so nothing was merging on the mangled form.

### Exposing it in the app is [#61](https://github.com/jsundram/quartet-composers/issues/61)
The spec lives there, not here: two shipped files and their exact shapes, the precache and `V`
contract, the `validate.py` checks, the table column and the detail-panel pill. This file is for
the reasoning behind decisions already taken; a spec for work not started belongs where it can be
closed.

Two things found while writing it that are defects in what already exists, not part of that work:

- **~~`fetch_works()` skips the category crawl when the cache has it, so a monthly run would never
  discover a new work page.~~** — done, 2026-09-13 (#62). The crawl always runs now and prints what
  it found. The rule it settled is worth keeping: **every ABSENCE is re-asked, and only absences.**
  A composer page that yields no key, a P839 Wikidata does not state, a guessed category with no
  page behind it, an article IMSLP names that does not exist — each is an answer an editor can
  change, and a cache that never re-asks one has #62's defect a pass over. The mirror of it is that
  **an absence nothing CAN change is written down as an answer**: en.wikipedia reports a
  `{{wp|de:…}}` title in its own block and never under `pages`, and refuses a `{{wp|[[…]]}}` one as
  `invalid`, so re-asking either was a question no reply could ever settle. 233 of the 236
  unresolved titles are that shape. A warm run is 48 requests against ~238 cold, and `get()` asks
  for gzip now — `wbgetentities` has no per-property filter, so the P839 pass alone was pulling
  24.6 MB against 4.0 MB compressed.
  `scripts/fetch_imslp.test.py` is what keeps it that way: the defect was a property of the request
  SEQUENCE and nothing that reads the cache can see it. Six review rounds found five more defects
  of the same shape, three of them introduced by the previous round's fix — an answer recorded
  where nothing looks it up. That is the argument for the suite, not an argument about the crawl.
- **The off-roster half of the join is [#68](https://github.com/jsundram/quartet-composers/issues/68).**
  IMSLP holds 1,771 composers with a string quartet and this roster names 884; the join keeps only
  the inner half and `data/imslp-audit.json` counts the rest and drops it. 2,542 pages and 1,295
  composers in the plain category are off-roster, 539 of them identified on Wikidata and simply
  absent from the Wikipedia list — Anton Stamitz, Praeger, Mayseder, Carl Stamitz, J.C. Bach. The
  crawl already holds every page title and every composer page; the only fetching gap is work info
  for the off-roster pages, 51 requests and ~0.9 MB. The issue also records why the work COUNT is
  the hard part (two catalogue systems, no crosswalk) and why the category is clean enough not to
  filter (95.6% state a string quartet verbatim; ~12 flute-quartet pages).
- ~~**`data/imslp.json` is the scrape cache and reads like the two files beside it.**~~ — done,
  2026-09-15. The name collision #61 worried about never happened, since what ships is
  `imslp-works.json`; what the bare name did do was fail to say which STAGE wrote it, so the crawl
  is `data/imslp-scrape.json` now and the trio reads scrape -> join -> works. It was also badly
  encoded, and that was the real saving: `markers` spent 709 KB on four named booleans per page
  where one int does it in 263 KB, and `works` repeated three key names 4,937 times. 3.29 MB ->
  2.68 MB, 18% off, and every downstream file rebuilt byte-identical.
  What was NOT done is the last 65 KB: encoding each work triple on one line rather than letting
  `indent=1` spread it over five would get there, and it needs a serializer for one key of one
  file — clever, contained, and the kind of thing that breaks silently. The remaining bulk is the
  raw wikitext and it stays raw: a better parser must never cost a request. The "under 2 MB" an
  earlier version of this claimed was never reachable without giving that up.

**The coverage report is generated, not written.** `scripts/build_imslp.py` writes the audit to
`data/imslp-audit.json` and `scripts/imslp-report.py` renders it to a self-contained
`imslp-coverage.html`. No figure on that page is typed — every one is computed at render time from
`composers.json`, `data/imslp-join.json` and the audit, because the roster grows, the monthly top-up moves
every readership number and IMSLP gains scores. A coverage report typed once is wrong by the next
run, which is the built-or-cut rule applied to a page that is nothing but falsifiable prose.

Making it a page **inside the app** is a separate and more expensive decision, and it should not be
taken just because the report exists. This is a single-page PWA with a precache manifest: a second
route means another `SHELL` entry, another `V` bump on every edit to it (invariant 1), a decision
about whether it is a `BOOT` dep, and a navigation affordance on a page whose first screen is
already fought over (issue 29). The standalone file costs none of that and is the right home until
somebody wants the coverage numbers *while looking at the chart* — at which point the answer is
probably the detail panel and a table column, not a second page.

**Cost of a refresh.** ~238 requests for a cold crawl, one per second — measured off the shipped
cache at the batch sizes this uses, where markers (99) and work info (38) are over half of it. A warm one is 48: the two
instrumentation categories, because they are the only place a new work page can appear, and every
ABSENCE — the 797 composer pages that yield no key, the 485 roster QIDs stating no P839, the 477
guesses with no page or nothing joinable behind them, and the 3 articles that genuinely do not
resolve — the other 233 name another wiki, which en.wikipedia answers once and for good.
Everything else tops up by page title and `--refresh` is still the only way to make it re-ask,
which is what keeps megabytes of unchanged wikitext off a volunteer-funded server. Joining the
monthly `refresh.py` job is #61's step 4 — what is left is deciding when an IMSLP top-up is DUE,
and that needs the shipped file that issue adds, since the pageview window cannot answer for a
catalogue that moves on nobody's schedule.

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
