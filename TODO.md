# Open work

Written down so a session that starts cold can pick any item up without reconstructing the
reasoning. Roughly in the order I'd do them. Anything marked **known defect** is something the
current build gets wrong today, not an enhancement.

---

## Accessibility

### The readership brush has no keyboard path — **known defect**
`histogram.js` is drag-only. The search box filters from the keyboard, the brush does not, so a
keyboard-only user cannot reach the readership filter at all. This regresses the pwa-starter
checklist's own "semantic controls" row, and it was introduced knowingly under time pressure.

Cheapest honest fix: a visually-hidden pair of `<input type="number">` (min/max views) bound to the
same `setRange()` the brush uses, inside the existing `role="group"`. A `<input type="range">` pair
is tempting but two thumbs on one axis is worse for screen readers than two labelled numbers.
Do NOT solve it by making the SVG focusable and hand-rolling arrow-key handling — that reinvents a
form control badly.

### Chart is `role="img"` with a text alternative that isn't equivalent
The `aria-label` says "the table below carries the same data", which is true only for the plotted
rows — the 94 with no quartet count are in the table but not the chart, and nothing says so to a
screen reader. Either state the count in the label or drop the claim.

---

## Data quality

### ~~Gender is not in the data~~ — done, 2026-09-05, [#1](https://github.com/jsundram/quartet-composers/issues/1)
P21 ships as the eighth positional field. The probe held up exactly: 276 women of 884 (31%), 219
of them plottable, births 1745–1989, and one composer with no claim at all (Fernand de la
Tombelle, who has no Wikidata item either). That last one turned out not to be a composer without
a claim but a redlink without an article — see "One composer is sized by a single month of page
views" below; the count is zero now, and `setProv()` has a branch for it.

Both open questions were answered **filter**, not encoding, and for the same reason: a filter here
is ALREADY a highlight. Nothing is removed — `opacityOf()` drops the rest to 0.07 — so "show me
the women" and "where are they" are the same gesture, and the Fame view keeps the band visible
against the field. What the filter did need was volume: at the resting 0.22 the kept dots were
barely separable from the ghosts, so while ANY filter is on they come up to 0.55. That is the
whole encoding, it costs no new channel, and the search box and the brush got it too.

A permanent encoding was rejected on the issue's own grounds. Fame spends fill on the repertoire and
stroke on the outliers; the other three views spend fill on lifespan and stroke on living. The only
unspent channel is shape, and shape does not read at a 2.5px radius among 790 marks.

The pills live on the readership row, so they survive full screen where `.tablehead` does not. On a
phone they take a third line rather than crowding the brush.

One thing the filter exposed: all thirteen composers the Fame view labels are men, so "Women"
drew 219 emphasised dots with no name on any of them — it answered "where are they" and refused to
answer "who". Fixing it properly meant fixing the labels generally, which is the entry below — and
then the RING, which had the same defect one channel over and is now derived per filter too (the
Interface section).

### ~~Labels were a fixed set, not a function of zoom~~ — done, 2026-09-05
The Fame view labelled thirteen hardcoded names and nothing else, at every zoom level, which
made the zoom decorative: pinching in promised detail and delivered scale. It now works the way a
map does — a budget that grows with the zoom (`base × (1 + log₂ k)`), filled from the seed and then
by PROMINENCE, and frame-culled, so zooming into a region names what is in that region. At rest,
unfiltered, the budget is pinned to the seed, so the resting picture and the share card are exactly
what they were.

Prominence is z-scored distance from the centre of the visible cloud — how far a dot stands out
from the crowd it is drawn in. Recomputed over the VISIBLE set, so a filter ranks that group
against itself: filtered to the women, readership would name whoever has the biggest article
(Beach, Monk — one quartet each, known for other work), while prominence names Kats-Chernin and
Vrebalov, who wrote 25 and 18 of them.

Four rankings were checked against the thirteen hand-picked names, which is the only ground truth
here. Prominence recovers 8; corner (quartets × readers) and readership recover 6 each; readership
is blind to the whole prolific end. **No single scalar reproduces the curated set** — which is the
argument for keeping it as the seed rather than deriving it away.

What the view should ASSERT at first sight — whether the thirteen stay curated, and whether the
fill and ring emphasis should follow a filter the way the labels now do — is left open on purpose:
it is an editorial question, not a ranking bug.
[#7](https://github.com/jsundram/quartet-composers/issues/7) carries the scored comparison of the
four rankings, the Ravel/Corea substitution nobody wrote down a reason for, and the four decisions.

### Readership is displayed to two significant figures; the data has one meaningful one
`twoSig()` in `app.js` quantizes the median to two figures and floors it, so Mozart reads "180k+"
rather than "186,772". Two is a guess, not a derivation: the honest input is the 12-month spread,
which for Mozart runs 140k–390k — a factor of 2.8, i.e. barely one significant figure. A defensible
rule would pick the number of figures from each composer's OWN spread rather than fixing it at two.
The table deliberately keeps the exact value: it sorts on that column.

### 94 of 885 entries (11%) have no quartet count
They are listed in the table and excluded from the chart. `python3 scripts/audit_counts.py --null`
shows them. Most are entries that enumerate works without ever using the word "quartet"
("VSTO (1993)."), where counting dated titles would usually be right — but the same rule would
also count "(1907–1949)" as a work, which is why it is currently off. Worth another pass with a
tighter enumeration test.

### Ranges are read as whichever bound the regex reaches first
Czerny's entry says "at least 20 and as many as 40 string quartets" and the parser returns 40. It
should either take the lower bound consistently, or store a range and let the UI show it. Right now
the choice is an accident of regex ordering, which is the worst of the three options.

### Semantic mismatches need a human, and only one has had one
`OVERRIDE` in `scrape_list.py` holds exactly one entry (Paganini — his "fifteen string quartets"
are for guitar quartet; the honest count is three). There are almost certainly more. Finding them
means reading the ~460 entries the "N string quartets" rule fires on and looking for a qualifier
the regex can't see. `scripts/audit_counts.py --rule "N string quartets"` samples them.

### What counts as a quartet at all is undefined
Arrangements, fragments, incomplete works, "for string quartet and X" — the page is inconsistent
and so, therefore, is this dataset. Worth deciding a policy and stating it in the UI, or accepting
the inconsistency explicitly rather than by default.

### ~~One composer is sized by a single month of page views~~ — done, 2026-09-10
The premise was wrong, and this entry repeated the mistake: `Fernand de la Tombelle` was not a
composer with one month of data. **There is no such article.** The list page links a redlink —
lowercase `la`, where the article is at `Fernand de La Tombelle` — so he was the one row that
resolved to nothing, the canonical fell back to the raw title, and `fetch_views.py` asked the
pageviews API for a page nobody has written. That request succeeds (invariant 5), and it returned
a stray hit which became his twelve-month median.

Nothing downstream could have seen it: the row was the right shape, the series was aligned, the
median really was the median of what was there, and a tiny count is plausible for an obscure name.
It was only wrong against a page that was never being counted. So the repair is three things —
`TITLE_FIXES` in `fetch_wikidata.py` records the real title, that script no longer invents a
canonical for a title that did not resolve, and `validate.py`'s `check_resolved()` refuses to ship
one. He now has a full series, a sparkline and an ordinary readership.

The lesson is invariant 5's own, one step earlier: asking the RIGHT title is half of it, and
noticing there is no title to ask is the other half.

### ~~Readership was counted under whatever the article is called TODAY~~ — done, 2026-09-08, [#23](https://github.com/jsundram/quartet-composers/issues/23)
The pageviews API counts the string that was REQUESTED, so an article that was renamed inside the
window had every earlier month filed under a name nobody was asking for. Invariant 5 protects
against reading a redirect INSTEAD of its target; nothing protected against the mirror image, and
asking the correct title still undercounted.

Fanny Hensel was the case that showed it: her article sat at "Fanny Mendelssohn" until March 2026,
so her shipped median of **500** was not a readership at all — it was the midpoint of a series half
of which measured a redirect. The real figure is **5,217**, an order of magnitude on a log axis, and
it moves her from last to second in `WOMEN_CANON`. The app also NARRATED the artefact: against ten
years of ~41-a-month the post-move months are a 34.9× peak where `SPIKE` fires at 3×, so the panel
captioned a rename as an obituary.

`scripts/pagemoves.py` now holds the rule (invariant 15) and **twelve** articles turn out to have
moved, not one. Only Fanny's move is inside the twelve-month statistic window, so the other eleven
changed nothing on the chart and everything about their sparklines — Leopold Koželuch's first
eighteen months read 1 a month and were really 600; Franz Schmidt's read 2 and were really 1,200.
That is why the survey on the issue found a category of one: it priced the last twelve months, and
eleven of the twelve moves are older than that.

Three parts, deliberately: an offline detector that only generates SUSPECTS (the shape has no clean
threshold — real moves run 9× to 1163×, genuine growth reaches 8×), the move LOG as the arbiter of
whether a move happened, and a numeric check of whether it STUCK. That last one is not belt and
braces: the log records events, not tenures, so a move reverted twenty minutes later leaves the
same two entries a permanent one does, and the first version of this — log only — put Roberto
Gerhard at a title he never occupied and made his series worse than leaving it alone.

Still open, and deliberately: an old title that is neither a redirect nor the qualifier-stripped
form (deleted, or now a different article) is not reachable from the canonical title, so a move
into one would go unrepaired. `validate.py` would say so rather than shipping it quietly.

### The 2014 archive is only half-used
`compare_2014.py` reports 28 composers who dropped off the list. Most are deleted articles, but a
few were renames the fold-matching doesn't catch (Fanny Mendelssohn → Fanny Hensel, Charles Wesley →
Charles Wesley junior). Worth a pass to confirm none is a real loss.

---

## Interface

### ~~A filter left the group with no emphasis of its own~~ — done, 2026-09-05
All six ringed outliers are men, so "Women" dimmed every ring to 0.07 and — once the frame started
fitting the filter — cropped them off screen entirely. The ring budget (six) is now filled first by
the curated outliers the filter kept and then by `prom`, so it says the same thing about whatever
group is on screen. "Men" keeps all six and derives none; the resting view and the share card are
untouched; below `MIN_FIELD` nothing is derived, because a ring needs a crowd to stand out from.

This settles half of [#7](https://github.com/jsundram/quartet-composers/issues/7): the OUTLIER ring
is derived, because "wrote a lot and is read little" is a computable property of whatever group you
are looking at. The repertoire filled in `--sel` is not — "who carried the form" is an editorial
claim about music history, and TODO records that no single ranking reproduces the curated set (the
best recovers 8 of 13). The other half is below.

### ~~A filter left the frame on the whole field~~ — done, 2026-09-05, [#6](https://github.com/jsundram/quartet-composers/issues/6)
Filtering to the 276 women gave the same picture with 600 dots dimmed and the survivors still in
the corner they always occupied — the frame was showing the group you had just filtered AWAY at
full resolution. `computeResting()` now fits the frame to the kept dots, `resetZoom()` returns
there rather than to the full extent, and `zoomed()` is measured against it so a fitted frame does
not light the reset button as though the reader had pinched.

It compounds with the zoom-driven label budget: closing in on the women takes the view from three
names to eighteen, which is what turns "where are they" into "who are they".

Deliberately NOT re-fitted mid-brush-drag — `settled` travels from `applyFilters()` into
`setFilter()` — because the chart flying around under a finger that is still moving is worse than
the stale frame it fixes.

### ~~Chart labels printed the full Wikipedia title~~ — done, 2026-09-05, [#2](https://github.com/jsundram/quartet-composers/issues/2)
15 characters average where the table had already settled on 7. The rule moved out of `table.js`
into `names.js` and now serves both, deriving the table's "Haydn, Joseph" and the chart's
"J. Haydn" from ONE shared-surname map so the two cannot drift apart about who needs more than a
surname. The win is not only tidiness: `pickLabels()` is a greedy first-come placer, so halving
every box is what lets the names behind it find room.

### Pressing Full screen during the un-fit tween pins the chart mid-tween — **known defect**
Clearing a filter tweens the frame back out over 420ms (`goTo()` in `chart.js`). `setFull()` asks
for a `Chart.resize()` on the next frame, and `resize()` keeps whatever transform it finds when the
reader has pinched — measured by `zoomed()`, which cannot tell a pinch from a tween in flight. So a
Full screen press inside that 420ms lands the chart at k≈1.05 with the reset button lit, and
nothing ever finishes the tween. Found by `ui.test.mjs`'s in-place reset (#48), which section 7
left in exactly that state; the reset now lets the full-screen relayout land before it presses
reset zoom, which is a workaround in the suite and not a fix in the app. The fix is probably for
`resize()` to read the tween's TARGET rather than its current frame — d3 keeps it on the node —
or for `setFull()` to interrupt to the target first.

### The full-screen strip drops four things, and says so nowhere
`tight()` in `app.js` trims the panel to two lines for the fixed-height strip above the chart: the
percentile line, the Wikipedia link, Prev/Next, and the 12-month range beside the median view count
all disappear. All four are one tap away and back the moment you leave full screen, and the range
is no longer load-bearing there — readership is now stated as "180k+" everywhere, so the strip no
longer claims a precision it can't support. Left here as a record of what the strip is missing.

### ~~The detail panel wastes most of its column on desktop~~ — done, 2026-09-06, [#13](https://github.com/jsundram/quartet-composers/issues/13)
It was ~200px tall in a full-height sticky column and is ~306px now, and the extra 100px says the
thing the panel could not: whether a composer's readership is steady or spiking. Saariaho runs flat
for eight years and spikes 18× in June 2023, the month she died; Haydn has slid a third since 2015.

The window went from 12 months to **everything the API has** — 2015-07 on, 134 months — which cost
nothing at the network (`monthly` returns the whole range in one request, so it was the same ~880
calls) and 1.9 MB in `data/`. The headline number did NOT move with it: `STAT_MONTHS = 12` in
`build_data.py` keeps the median over the last twelve, so every dot on the chart is byte-identical
to what it was. That was the point of separating them, and `validate.py` now recomputes one from
the other so a half-rebuild cannot ship.

The series ships as its own file rather than a ninth field. `composers.json` is a BOOT dep — the
page paints nothing without it — and 884 monthly series are ten times the roster's size, so
putting them there would have paid for a decoration on the critical path. `readership.json` is
precached but not a boot dep, fetched after the first paint, and simply absent if it never comes.

Two things it turned up. A null month has to BREAK the path: 61 articles did not exist in 2015 and
drawing their blank years as zero claims nobody read a page that was not there — the label row says
"from Jul 2025" instead of the axis span for those. And the compact panel's hover reservation
(`min-height`) had to grow with it, which `ui.test.mjs` caught by measurement rather than by eye.

**The caption names the spike if there is one, the trend otherwise.** Naming the peak
unconditionally was wrong for most of the roster: the median composer's biggest month is 3.1× their
typical one — a composer read thirty times a month hits ninety by chance — so it cried spike about
noise on half the list, and buried the real story for the steady ones (Haydn's 1.7× peak against a
line that has slid 42%). The test is the peak against the 95th percentile of that composer's OWN
months, which is scale-free; at 3× it fires on 18% of the roster and what it picks out is almost
entirely obituaries — Payne, Coates, Schnebel, Erőd, Van de Vate, Charrière.

**Any month can be read.** Hover, tap or arrow-key the line and the caption becomes
`Jun 2023 · 42,195` with a cursor on that month; it replaces the summary rather than adding a line,
because the compact panel reserves a fixed height. That exposed a bug one layer out: the document
keydown listener stole the arrows from the focused sparkline and stepped the COMPOSER, so the
readout answered about someone else. Self-handling elements now mark themselves `[data-keys]`.

Still open: the counts printed here are exact where the panel above rounds. That is deliberate —
a month is a tally, the median is a smoothed estimate — but it is a split worth re-reading if the
rounding rule is ever revisited.

### ~~1580–1700 is ~20% of the x-axis for three composers~~ — decided, 2026-09-05
The premise was wrong, which is why it looked like a trade-off. Allegri (1582), Scarlatti (1660)
and Telemann (1681) have no stated quartet count, so they are TABLE-ONLY rows and were never on
the chart at all: the domain was spending 31% of the width on a stretch where no dot can ever be
drawn. `X_DOMAIN` is now derived in `setData()` from the PLOTTABLE birth years (1709–1989 today),
snapped out to a 50-year grid — 1700–2000. Nothing was dropped and no axis was broken.
`make-og-svg.py` derives the same domain; keep them in step.

### ~~Lifespan is a diverging ramp, which is the wrong colour job~~ — done, 2026-09-05
The ramp is YlGnBu now: died young is yellow, lived long is deep blue, hot to cold and
SEQUENTIAL, which is the honest job for a magnitude. It fixes both halves at once. The old
diverging ramp needed a baseline to diverge from and never had one — it pivoted on the median
lifespan of whoever was in the dataset, so the pivot moved when the data did. And its neutral
midpoint sat at 1.61:1 against `--plot`, which made the single most COMMON lifespan the least
visible dot on the chart.

Stepped darker than canonical YlGnBu deliberately: `#edf8b1` is 1.08:1 on this surface, so the
published ramp's pale end is invisible here. Everything clears 3:1 and stays monotone in lightness
in both modes, checked with the dataviz palette validator rather than by eye.

### ~~A filter left the FILL with nothing to say~~ — done, 2026-09-07, [#7](https://github.com/jsundram/quartet-composers/issues/7)
The ring was derived per filter in September; the fill was not, and every name in `CANON` is a man,
so "Women" drew 219 dots with three earned rings and **nothing filled at all** — the channel that
carries the view's actual claim went silent for a third of the roster.

Deriving it was rejected on the same grounds as before: a canon is a claim about what gets played,
and no ranking reproduces one. So the answer is a SECOND hand-written list — `WOMEN_CANON`, nine in
birth order, 1805 to 1962 — swapped in by `Chart.setRepertoire()` when the pill changes.

**Gated to the filter, and that is the design, not a caveat.** Not one of the nine clears 10,000
readers a month (Price tops them at 8,001; `CANON`'s median is Tchaikovsky at 58,023), so at rest
they would be nine filled dots low in the densest part of a 790-dot cloud under a key reading "the
repertoire" — captioned as the set that holds Mozart. It is a different claim, and it is legible
exactly when the women are the picture. The resting view, "Men" and the share card are
byte-identical: `make-og-svg.py` regenerated to no diff at all, because it draws the view at rest.

Two things fell out of it. The legend had to rename the FILL as well as the ring, so the phrase
moved into `REPERTOIRES` beside the list it names — one editorial claim, one place. And curating a
composer REMOVES her from the ring pool (`refreshEmphasis` ranks over dots not in `namedSet`), so
filling Kats-Chernin and Price freed their ring slots.

That exposed a defect the ring had all along: prominence is distance from the CENTRE of the cloud,
so a corner full of composers all scores high and nothing visual broke the tie. The ring landed on
Meredith Monk, whose disc came within 4px of Amy Beach's — one filled, one ringed, reading as a
single smudge. A derived ring now has to clear every emphasised dot by `MIN_SEP` (3% of the plot
diagonal, floored at four dot radii), measured in screen space because "on top of" is a claim
about pixels — which also means re-deriving in `setMode()` and `resize()`, since a rule about the
picture is wrong the moment the picture changes shape. What it finds
instead is Vrebalov (18 quartets, 152 readers — the women's Cambini), Auerbach and Firsova: all
three "wrote a lot, read little", which is exactly what the curated outliers say at rest. The
read-a-lot end of that group is not lost, it is carried by the fill, where Price and Beach are.

The one thing the set cannot include: **Caroline Shaw and Jessie Montgomery**, two of the most
programmed living quartet composers, have `quartets: null` and so cannot be plotted at all. Same
for Tania León, Joan Tower and Chen Yi. That is the 94-row gap in the section above, showing up
somewhere it costs something.

### ~~The lede hardcoded three claims about the data~~ — done, 2026-09-07
"The names picked out are the repertoire, 1709 to 1906; Giuseppe Cambini wrote 149 quartets and is
read about 200 times a month" was typed into `index.html`, and nothing checked any of it. Cambini's
median is 216, so the rounded figure was already wrong; and the first two clauses went false the
moment the Women filter picked out nine composers born 1805 to 1962 while the sentence above them
still said 1709 to 1906.

`setLede()` builds it from `Chart.emphasisStats()` now — the same rule `#count`, the search
placeholder and `setProv()` already followed. The rounding follows invariant 9 ("about 210", not
216), using "about" rather than `atLeast()`'s "+" because this is a sentence and both say the same
thing. Two edges: one surviving curated composer is named ("The one name picked out is Joseph
Haydn"), because "1732 to 1732" is not a range, and none leaves the sentence empty rather than
written about nobody.

Still typed, and correctly so: the clause saying what readership MEANS. That is not a fact about
the data. The clause naming the AXES was left typed here on the same reasoning and turned out not
to belong to it — the entry below.

### ~~The lede described the Fame view in all four views~~ — done, 2026-09-08, [#24](https://github.com/jsundram/quartet-composers/issues/24)
"Across is how many quartets they wrote, up is how much their English Wikipedia article is read"
was typed into `index.html` and printed in every view. It is true in Fame, false in Timeline and
Swarm (across is birth year), and only half true in Lens — and the per-mode `HINTS` under the
chart said the right thing about 600 vertical pixels below, so the page contradicted itself on one
screen. A shared `#v=swarm` link opened on the contradiction.

**Cut, not derived.** The axes are already stated twice on screen by whichever view is drawn: the
axis titles inside the plot (`quartets written →` / `birth year →`) and the hint under it. A third
statement of the same fact can only ever be the copy that goes stale, and Swarm shows why swapping
two nouns per mode would not have worked anyway — its vertical position means nothing, so there is
no "up is" to write. The lede now says what the page IS and leaves the geometry to the geometry.

**The issue was half the bug.** The clause the September fix BUILT had the same defect one clause
over: `Chart.emphasisStats()` reports the curated fill and the derived rings regardless of mode,
and `setMode()` never called `setLede()` — but every emphasis channel is Fame-only (`fillOf`,
`strokeOf`, `widthOf`, `labelColorOf` all fall through to the lifespan encoding), so Timeline,
Swarm and Lens were captioned "The names picked out are the repertoire, 1709 to 1906" over a
picture that picks nothing out. `emphasisStats()` returns null outside Fame now — the gate is in
`chart.js`, which is the file that knows which channels are Fame-only, so a fifth mode gets it
right for free — and `setMode()` calls `setLede()` beside the `renderLegend()` it already called.
Outside Fame the sentence is not reworded, it is unmade.

The rule in `CLAUDE.md` was sharpened to the form the issue proposed: **prose the app can falsify
is built or cut; only prose it cannot is typed.** "States a number" was the wrong test — this
clause states none and the app falsifies it anyway, about the VIEW rather than about the data.
Build it when nothing else on the page says it; cut it when something does.

Five checks in `ui.test.mjs` (4m2), four of them red before the change: the lede names no axes in
Fame or Swarm, a `#v=swarm` boot makes no claim about names picked out, and the switcher — the
path that actually broke, since `goto()` re-boots the app and a pill does not — drops the claim.
The fifth, that coming back to Fame restores the sentence, passed on the old code too and
trivially so: the lede never changed on a mode switch at all, so it could not fail to be restored.
It is a regression guard for the new `setLede()` call, not evidence of the old bug.

### ~~An empty lede clause collapses the paragraph and shoves the chart up~~ — done, 2026-09-08, [#27](https://github.com/jsundram/quartet-composers/issues/27)
The lede's built clause is one to three lines depending on the viewport, and when
`Chart.emphasisStats()` returns null it empties — so everything below it moves up. Measured
(headless Chrome, 390x844 and 1280x900):

| trigger | phone: plot moves | desktop: plot moves |
|---|---|---|
| type "cambini" (no curated survivor) | 61px | 20px |
| press a view pill | 41px | 41px |

**Pre-existing, but it got a much commoner trigger.** The search case is old — `applyFilters()` has
always called `setLede()`, and the 4m section already asserts the clause empties at `#q=cambini`.
What #24 added is the mode switch, which before moved the plot 0px at both widths: pressing
Timeline on a phone now lifts the switcher pill you just tapped 93px (was 52px, from the legend
changing shape), so a quick second tap at the same spot lands on the wrong control. That is the
same complaint the full-screen strip's fixed height and `.compact`'s hover `min-height` answer,
one component up the page.

Cutting the axis clause moved the other way and by more: the resting lede is 40px shorter at both
widths (phone 162 to 122, desktop 101 to 81), so there is less above the fold to move at all.

**Not fixed with #24, deliberately, because the obvious fix is the kind of number this repo bans.**
A `min-height` on `.lede` has to cover the TALLEST state, and that state is a function of both the
viewport (122px at 390, 81px at 1280 — different wrapping, so one px value cannot serve both) and
the DATA (the sentence names a composer and two figures; "Only Joseph Haydn is left from the
repertoire" is a third the length). Hardcoding it per breakpoint is a claim about the data typed
into CSS, which is the drift `setLede()` exists to prevent, and reserving the tallest state leaves
a blank band above the fold in the filtered case, which is most of the time anyone is filtering.
**The fix is the measured reservation the issue asked for.** `reserveLede()` in `app.js` writes the
RESTING sentence into the same span, reads the paragraph's height at the current width, writes the
shown text back and sets that height as an inline `min-height`. Synchronous, so nothing paints
between the two writes. The resting sentence comes from `Chart.emphasisStats(true)`, a new flag
that answers "what would this sentence be with no filter and in Fame" by re-reading the same arrays
with the mode gate and the visibility test dropped — it disturbs nothing that is drawn, and only
`chart.js` can say what the resting claim is. `ledeClause()` is split out of `setLede()` so the
sentence that is measured and the sentence that is printed cannot come to differ.

Neither number is typed anywhere: the reservation is 122px on a phone and 82px at 1280 because
that is what the paragraph measures there, and a `ResizeObserver` on `.lede` re-measures when the
width changes. Guarded on the WIDTH — setting `min-height` changes the height and re-enters the
observer, so re-measuring on every callback is a loop.

Reserving the RESTING sentence rather than the tallest possible one is what avoids the blank band:
the box is exactly the paragraph the reader arrived at, so nothing is held open that the page did
not already have. It is `min-height` rather than `height` because the resting sentence is not
provably the longest — under a filter the example comes from a derived ring, whose name and figures
are not Cambini's — though every filter state measured (`#r=751-4501`, `#g=female`, `#q=haydn`,
`#q=o`, `#r=2000-500000`) wraps to the same three lines on a phone.

**What it does not settle.** The chart's TOP no longer moves; the switcher pill below it still
rises 52px on a phone when you press Timeline, because `measure()` gives each view its own aspect
ratio (0.98 for Fame against 0.82 for the timeline on a narrow screen) and the plot is that much
shorter. So the double-tap hazard the issue describes is 93px -> 52px, not gone. The remainder is
an encoding decision rather than a collapse, and it is [#29](https://github.com/jsundram/quartet-composers/issues/29).

**The measured sentence has to be the printed one, and under one pill it was not.** Splitting
`ledeClause()` out of `setLede()` guarantees the two strings are built the same way; it does not
guarantee they are built from the same STATE. `emphasisStats(true)` drops the mode gate and the
visibility test, but the gender pill also SWAPS the curated fill, and `WOMEN_CANON` holds none of
the three curated outliers — so under "Women" the page rings three derived composers while the
measurement was still reading `outlierIdx`. It measured "the women's repertoire, 1805 to 1962;
Giuseppe Cambini wrote 149 quartets", a sentence naming a dot that filter does not draw. Nothing
was visibly wrong — both wrap to three lines at 320/360/390/430/768 — but the margin was the
name-length luck of two different composers, and invariant 4 says those names change spelling when
the pipeline runs. The resting rings now follow the swap: the curated outliers while the curated
fill is on screen, whatever the swap derived otherwise (unfiltered, `ringIdx` is empty and that is
the outliers again). Checked as STRINGS rather than as a height, in 4m3.

**And a reservation kept through full screen is not a reservation.** `.lede` is `display:none`
there, so `reserveLede()` has nothing to measure and keeps the box it last set — which is right,
since the windowed layout comes back to it. What it keeps stops being a MEASUREMENT the moment the
claim changes behind the hidden paragraph, and the `ResizeObserver`'s width guard then reads "same
width, nothing to do" on the way out. At 360: boot, enter full screen, press Women, come back, and
a 122px box sat under a 143px paragraph. It recovered on the next `setLede()` — every path that
empties the clause goes through one — so it was safe by luck rather than by construction. The bail
now invalidates the width instead, and the guard re-measures once on the way back. Invisible at
390, where the two sentences wrap to the same height.

Nine checks in `ui.test.mjs` (4m3). Seven were red before the reservation existed: at 390 and at
1280, that the reservation equals the paragraph's own height, that emptying the clause with a search moves the
plot 0px, and that a view pill does too — both driven IN PLACE rather than by a boot, which lays
the page out once and could never show the jump, and both measured at 40.6px with the reservation
disabled, so the checks have real force — plus that a 1280→390 re-wrap re-measures
(82→122), which is the one a hardcoded `min-height` could never pass at both widths. The last two
are the review findings above — the strings check and the full-screen round trip — both green on
the first cut of this work only because `atRest` did not exist yet to be wrong, and both red
against the cut that introduced it (measured 149-quartet Cambini under the women's noun; 122
against 143 at 360).

### ~~A view switch still moves the switcher, because each view sizes its own plot~~ — done, 2026-09-08, [#29](https://github.com/jsundram/quartet-composers/issues/29)
`measure()` in `chart.js` picks the aspect ratio per mode — 0.98 for Fame against 0.82 for the
timeline on a narrow screen, 0.44 for the swarm — so pressing Timeline on a 390px phone shortened
the plot by 52px and everything under it, the switcher pill included, came up to meet your finger.
That was the residue of [#27](https://github.com/jsundram/quartet-composers/issues/27) after the
lede stopped collapsing (93px -> 52px), and it is a different thing: not a box that vanished but a
picture that is honestly a different shape.

**So the ratios are not what changed — the ORDER is.** A single height for all four views spends
empty card on the timeline or squeezes the Fame cloud (466 dots at 0.6 on a phone merge the log
bands into stripes), and reserving the tallest leaves a blank band under the short ones, which is
the "held-open box" #27 went out of its way to avoid. The rule underneath is the one the
full-screen strip and `.compact`'s hover reservation already follow one component up: **nothing a
finger rests on may be placed by a box that the same press resizes.** The controls are the only
thing under the plot that is a control, so the controls moved above it — `.controls` now precedes
`#plot` in `index.html`, and the margin moved with it.

Measured at both widths, pressing each view in place from Fame (worst case across the four):

| | switcher moves, before | after | plot still resizes by |
|---|---|---|---|
| 390x844 | 61px (52px for Timeline, 61px for the swarm) | 0px | 61px |
| 1280x900 | 150px (the swarm) | 0px | 150px |

The desktop number is the surprise and the reason this is not scoped to phones: the swarm is 150px
shorter than Fame at 1280, three times the shift the issue was filed about. Everything below the
plot — the detail panel on a phone, the legend, the hint — still moves by exactly that much, which
is correct. It is a picture changing shape, and none of it is a control.

**The cost is 94px of the phone's first screen**, spent before a dot: 82px of pills-and-buttons
plus their margin, which pushes the plot's top from 456 to 550 and leaves 294 of the plot's 321px
above the fold (92%) instead of all of it. That is what the comment in `index.html` used to defend — "four view
pills and three buttons above it were half the first screen" — and it is the cheaper half of the
trade now that the row is the only thing standing between a second tap and the wrong control. At
1280 it costs 50px and the plot still ends above the fold.

**Full screen keeps them underneath**, and that is not an oversight: `#plot` is `flex:1` there, so
its height is a function of the viewport and not of the view — nothing to absorb — and every pixel
above the chart is a pixel of chart. `styles.css` already orders `#viz`'s children in that layout,
so the DOM move did not disturb it.

One other thing had to move with the row: `placeDetail()` anchored the phone panel on `.controls`,
which after the move would have inserted it ABOVE the plot. It anchors on `.legend` now — and the
existing "the answer lands within a finger's reach of the chart" check is what catches that (112px
below the plot when the two disagree).

Five checks in `ui.test.mjs` (4m4, plus one in section 7). The four in 4m4 are two pairs — that the
switcher does not move, and that the plot's height changed anyway, because the first passes
trivially on a chart that had stopped resizing at all. Both "does not move" checks are red before
the change, at 61px and 150px. The fifth, that full screen puts the controls back below the chart,
passed before too: it is a guard against somebody unifying the two layouts, not evidence of a bug.

### ~~Nothing compares `V` between a branch and its base~~ — done, 2026-09-08, [#32](https://github.com/jsundram/quartet-composers/issues/32)
`sw-lint.py`'s headline check — a staged SHELL file with an unchanged `V` — reads
`git diff --cached`, so it only ever bit in the pre-commit hook, and `checks.yml` said so in its
own header. That left one hole, and the #24/#27/#29 stack fell into it: #28 and #30 both bumped
`quartets-v32` -> `v33` from the same base, byte-identically, so a three-way merge resolved them
silently and #30 would have landed `app.js`, `index.html` and `styles.css` with a net `V` delta of
ZERO — every installed client keeping the old `styles.css`, with the controls back under the plot.
Rebasing removed the last trace: #30's commit no longer touched `sw.js` at all, so no hook fired on
the line that matters. It was caught by hand in review.

`scripts/sw-lint.py --base REF` is the sixth check, and CI runs it on pull requests with
`github.event.pull_request.base.sha`. **The decision the issue asked for was per PUSH**: any bump
clears it, so a branch that bumps twice or jumps several generations is not punished — the rule is
only that `V` ends up past the base's.

**It takes TWO refs, and that is the whole design.** What the branch CHANGED is read from the merge
base, so a base that moved ahead does not come back as files this branch touched (the same property
that makes it survive a rebase, a squash and a stack). Which `V` it has to CLEAR is read from the
base BRANCH's tip, because the tip is what it is about to merge into — and this is exactly where
the naive version fails: against the merge base, the motivating case PASSES, since both PRs did
differ from their own `v32` base. That distinction is the one thing about this check that is not
obvious, so `sw-lint.test.py` opens with it.

Three smaller decisions, each with a case in the test file: the SHELL list is the UNION of both
sides (dropping an entry is itself a shell change, since clients keep serving it out of the old
generation until `V` moves); a `V` whose tail goes DOWN fails with its own message, because the
tail ORDERS generations and a lower one merges as the stale cache; and a renamed stem is a
deliberate reset, so the tails stop being comparable and `V` merely differing is the whole answer.
A missing merge base — what a too-shallow CI checkout looks like — is REPORTED rather than skipped,
which is why the job's checkout is `fetch-depth: 0`. A check that passes when it could not run is
the failure mode this whole issue is about.

Eighteen cases in `scripts/sw-lint.test.py`, offline and ~1s, each building a throwaway repo with
real branches — the failure `--base` catches looks correct from either side alone and cannot be
staged from a single commit. It also asserts `git merge-tree` resolves the incident's merge without
a conflict, which is the reason nothing upstream of CI sees it. `sw-lint.py` is a vendored
pwa-starter file and its stamp now reads `(+ the --base branch check)` rather than `(unmodified)`.

### ~~Three filters, three ways to undo them, and one of them moved the page~~ — done, 2026-09-09, [#35](https://github.com/jsundram/quartet-composers/issues/35)
One permanent `Reset filters` button in `.controls` beside `Reset zoom` clears all three filters —
search included, because the name is plural and a typed query is a filter. `disabled` and muted at
rest, accent-filled when live, which is the same fill the pressed gender pill and the readership
bars carry and the only place the page answers "is anything filtered?" in one glance.

**The layout consequence is the point, not a side effect.** A control that is always present cannot
resize the row it is in, so the whole class of defect the entry below is about stops being possible
rather than being mitigated: `#hist-clear` left `.filterbar` entirely, taking `order:6`, its
`margin-left:auto` alignment and the "flush with the brush's right edge" checks with it. Those
existed only to make an appearing box harmless. It also means the button's state may be updated
ABOVE the `settled` guard — a colour and a `disabled` flag move nothing — so it lights up on the
first frame of a brush drag, which the button it replaces could never do.

`resetFilters()` runs exactly ONE `applyFilters()`, which is what its branch is for: `Histogram
.clear()` moves the brush to null and d3-brush emits "end" for a programmatic move, so it comes back
through `onChange` on its own; with no range there is nothing to emit and the other side makes the
call itself. Rebuilding ~880 rows twice is the one thing here that visibly stutters, and 4m5 asserts
the single repaint with a MutationObserver rather than trusting the reading.

**Share and Full screen became icons on the canvas below 640px, and that is what paid for it.**
`.controls` is already two lines at 390 and a word button takes it to three — 48px of a phone's
first screen. Measured, `.controls` height and lines:

| | 390 | 360 | 1280 |
|---|---|---|---|
| before | 90 (2) | 90 (2) | 38 (1) |
| + a third word button | 138 (3) | 138 (3) | 38 (1) |
| …with Share/Full screen as icons IN the row | 90 (2) | **138 (3)** | 38 (1) |
| …lifted onto the canvas | 90 (2) | 90 (2) | 38 (1) |

So shrinking them in place does not pay for it at 360; only lifting them out does. See the
`placeChartTools()` bullet in `CLAUDE.md` for what makes the overlay safe and the four things a
change there must keep.

**They are in the axis-title band, not in a corner, and that was measured rather than judged.** Dots
the 86x40 group would cover, summed over Fame/Timeline/Swarm/Lens at 390: top-left 11, top-right 90,
bottom-right 239, bottom-left 3. The first placement was top right on the strength of the Fame view,
where it looks empty — and the SWARM piles 90 dots and the "Rachmaninoff" label exactly there. Even
the best corner ate the axis origin ("1700"), and raising the box off the bottom did not buy that
back, because the y-axis ticks run up the left edge: at +40px it still caught them and started
covering dots instead. The band is the only placement that covers NOTHING, in every view.
They are CENTRED on the axis title's line. Bottom-aligning them to its baseline was tried first and
read a touch high — a 16px glyph beside 11px text carries more visual mass below its own middle than
the letters do. The offsets are derived, not nudged: the title's box centre is 4.47px above its
baseline and the baseline is 8px above the plot area (chart.js draws `text.ttl` at `y=-8`), so the
glyph's centre lands at `BAND - 12.47` and the 40px target, whose bottom is the glyph's bottom,
starts 3.5px down. The band is 48 so that target also stays CLEAR of the plot area — it is
invisible, so a dot it overlaps silently stops being TAPPABLE rather than merely being hidden, and
at 46 it shadowed 12 dots in the swarm, whose blob reaches the top of its box. The coverage check
therefore counts the whole button, not the glyph, and the alignment check measures the title's own
box rather than repeating the constant.

They are bare glyphs, not pills: 16px at `var(--muted)`, no border and no background, in an
invisible 40px hit target — the first version put a bordered disc round each one, which is 40px of
visible chrome next to an 11px axis title and reads as furniture rather than as the platform's own
shape for a control on content. The suite taps 3px in from a corner, ~12px clear of the mark, so it
is the invisible half of the target being tested and not the glyph.
`Chart.setTopReserve(48)` widens `m.top` from 22 so a 40px target fits with clearance; the chart is
TOLD rather than reading the breakpoint, because two copies of "640px" is two things that can
disagree and `chart.js` would be the one silently reserving space for a control that had moved. The
cost is 26px of data height and no page height — `ch` comes from the aspect ratio, so the band takes
its room from the dots' area and the outer box is unchanged.

Two traps worth remembering, both of which cost a debugging round here:

- **`[hidden]` is only `display:none` in the UA sheet.** Giving `.btn` a `display` for its icon
  un-hid the search box's ×, which wrapped the search row and ran the page 50px tall until a filter
  was applied. Answered once with `[hidden]{ display:none !important }`, with a check that notices
  if it is ever dropped.
- **`#chart-tools .btn .ico` (1,2,0) out-specifies `#fs .ico-out` (1,1,0)**, so the state rules for
  the two full-screen glyphs have to carry the group's id too. Written without it, both glyphs
  showed at once. Same specificity trap as the one below, one selector along.
- **`#plot svg{ width:100% }` means the CHART, and moving the buttons into `#plot` made it a
  descendant selector over their icons.** An 18px glyph rendered at 38x38 — 95% of its button — with
  a 3.2px stroke, and `body.fs #plot svg{ height:100% }` repeated it in full screen. Fixed with
  `> svg` plus an explicit size on `.ico`, since a width ATTRIBUTE loses to any stylesheet. Worth
  noting how it hid: on a desktop the buttons are still in the controls row, so the rule never
  reaches them and the bug is invisible in exactly the place a change is usually eyeballed.

**Follow-up, 2026-09-09: the breakpoint moved from 640 to 1100.** The table above only ever asked
about phones, and the answer for 1280 (38px, one line, so nothing to pay for) was read as the answer
for every desktop. It is not: the row is two lines from 641 to 1054 as well, so the icons are worth
44px of page height on a 1024 laptop for the same reason they are at 390. Re-measured, `.controls`
height by viewport width, words in the row:

| | 390 | 700 | **800** | **860** | 900 | 1024 | 1054 | 1056 | 1280 |
|---|---|---|---|---|---|---|---|---|---|
| words in the row | 82 (2) | 82 (2) | **38 (1)** | **38 (1)** | 82 (2) | 82 (2) | 82 (2) | 38 (1) | 38 (1) |
| icons on the canvas | 82 (2) | 38 (1) | 38 (1) | 38 (1) | 38 (1) | 38 (1) | 38 (1) | 38 (1) | 38 (1) |

Above the wrap point the words cost nothing and the band would cost 26px of data height for no page
height at all, so that is where they stay.

**The first answer was a single `(max-width:1100px)`, and code review caught that it is wrong in a
120px band** — the two bold columns. The row's width is not monotonic in the viewport's: what
decides it is the CARD, and the `(min-width:900px)` two-column grid takes 194px off that. Stepping
4px with the words in the row: 641-743 wraps (card 582-681), **744-899 fits** (682-837), 900-1055
wraps (524-679), 1056+ fits (680+). So the words belong in TWO bands, and `iconsOnPlot()` is
`NARROW` (`max-width:799px`) or `SQUEEZED` (`min-width:900px and max-width:1100px`) — two queries
and not one list, because only the second is the grid's and full screen has no grid, so `SQUEEZED`
is skipped under `.fs`. 780-899 no longer spends 26px of data height to buy nothing. The edges are 799 and 1100 rather than the 743 and 1055 the row wraps at
because `share()` swaps the label to "Link copied", which is wider than "Share" and moves both out
(to 780 and 1092) — a breakpoint inside either gap would have let a PRESS on Share wrap the row and
drop the plot 44px under the cursor that just pressed it, which is the rule the controls row already
follows one row down. Both sit clear on the ICON side, because the two errors are not equal: that
shift against 26px of data height. Those widths are this machine's font metrics (the 90px in the
older table is another machine's), so they are defended by checks rather than by arithmetic:
`ui.test.mjs` presses Share at 800 and at 1101, the first width in each band that draws the words,
and fails if the row grows.

The same review found the second half of it. The icon LOOK lived in that width query too, so the
CSS and `placeChartTools()` answered the same question independently — and every state where the JS
had not run yet drew the icon look in the row: a cold boot before `app.js`, and permanently on
`start()`'s error path, which bails before the move. Two bare glyphs with clipped labels and no
click handlers, above an error paragraph. The look is now scoped to `#plot > #chart-tools`, so it
follows the DOM and `app.js` holds the only copy of the breakpoint.

Two things the wider breakpoint buys beyond the pixels. The icon layout is no longer invisible on
the machine the code is written on — every bug in this group so far (the stretched glyph, the
36px button, the two glyphs at once) hid in a layout a desktop never drew. And the corner had only
ever been measured at 390; it is now measured at 1024 too, in all four views, which is where the
swarm spreads across a card twice as wide. Still zero coverage. What the words were still buying up
there was a NAME on hover, so both buttons carry a `title` and `label()` writes it with the span.

### ~~The lede's reserved height still moves the page~~ — done by DELETION, 2026-09-09, [#36](https://github.com/jsundram/quartet-composers/issues/36)
Not fixed — the sentence it was about is gone. `reserveLede()` reserved the height of the RESTING
sentence, and the gender pill changed what "resting" meant (`Chart.setRepertoire()` swaps `CANON`
for `WOMEN_CANON`), so the reservation was correct at every instant and still moved the page 20px
when the claim itself got shorter. Every option on the issue traded one cost for another: reserve
the tallest claim and hold a blank band open, or accept the step.

The fourth option was not on the issue and is the one taken — **stop making the claim**. The lede is
one static line now, "Everyone on Wikipedia's List of String Quartet Composers, visualized." That
deleted `setLede()`, `ledeClause()`, `reserveLede()`, its `ResizeObserver`, `Chart.emphasisStats()`
and three sections of `ui.test.mjs`, and it took [#27](https://github.com/jsundram/quartet-composers/issues/27)'s
mechanism with it — a paragraph that cannot change length cannot collapse. `ui.test.mjs` 4m5 also
went back to measuring ABSOLUTE tops, having needed an offset from `#filters` purely to stay clear
of this defect.

Nothing was lost, and 4m checks that rather than asserting it: the legend still names the
highlighted set, the axis titles and the per-mode hint still name the axes, and `setProv()` still
says readership is English-only and what that undercounts. The one thing that did go is the
editorial framing "familiarity to English speakers, not importance" — the substantive half of it is
in the footnote, and the page states its own case elsewhere.

### ~~The readership brush shows its Clear button mid-drag~~ — done, 2026-09-08, [#31](https://github.com/jsundram/quartet-composers/issues/31)
The rule [#29](https://github.com/jsundram/quartet-composers/issues/29) settled — nothing a finger
rests on may be placed by a box the same press resizes — had one exception left, and it was the row
directly above the one that issue was about. It turned out to be TWO defects meeting on one button,
and fixing either alone still moved the page.

**WHEN it appeared.** `applyFilters()` set `$("hist-clear").hidden = !Histogram.getRange()` BEFORE
the `settled !== false` guard, so the button arrived on the first frame of a brush drag rather than
at the end of the gesture. The line moved inside the guard. That does NOT cost the `#r=` boot,
which was the first objection to it: boot calls `applyFilters(true)` after `Histogram.setRange()`,
and `settled !== false` passes `true`. `applyFilters(false)` has exactly one source in the app —
`Histogram.init`'s `onChange` — and inside `histogram.js` `done=false` comes only from
`.on("brush", ...)`; `.on("end", ...)` passes `true` on both branches.

**WHERE it appeared**, which is the half this entry originally got wrong and is worth reading if
you are about to prescribe a layout fix from a description rather than from a measurement.

> The first version of this entry said `.filterbar` WRAPS when the button appears and that the fix
> was to reserve the button's WIDTH. Both are false. Below 640px the row is already three lines —
> `.filterbar #hist{ flex:1 0 100%; order:3 }`, with `#gender-label`/`#gender` at order 4/5 — so
> the wrap points are pinned by `order`, not by available width. At order 0 the button simply
> landed on line one beside the `Readership` label, and the whole shift was that line going from a
> 17.4px `<label>` to a button. Line one had ~200px spare, so reserving width would have changed
> nothing at all. Nothing wraps, and no line is ever added.

Which also means the honest cost was never 10.6px. That figure was measured on a NARROW DESKTOP:
`setDeviceMetricsOverride` leaves `(pointer:coarse)` false, and the button is 28px there. On a real
touch device it is 40px (see below), and the step is **22.6px** — measured at 390 and at 360, both
`moved=[0, 22.6, 22.6, 22.6, 22.6]` for `#hist`, `#gender`, `.controls` and `#plot`.

**The fix is `#hist-clear{ order:6; margin-left:auto }` below 640px**: the button takes the gender
pills' third line, which is already 42px tall, so a 40px button costs it nothing. Measured at 390,
360, 430, 640, 700 and 1280, touch and not, every box in and under the filter row is IDENTICAL with
the button shown and hidden — no step mid-drag and none on release either. There is no residue left
to accept, so the "reserve the width" trade this entry used to defer is gone rather than deferred.

Its one real cost is copy, and it was known going in: `styles.css` already records that with the
readout gone this button ends up beside the word "Gender", where it reads as if it clears that.
`margin-left:auto` parks it at the far right, which puts its right edge exactly on the brush's
(359px at 390 wide) — the only positional cue saying which control it belongs to. The word cannot
carry it: "Clear views" wraps the row at 360. So the ACCESSIBLE name does
(`aria-label="Clear readership filter"`), which alignment can never give a screen reader, and which
also improves the wide row where the same adjacency has always existed.

### ~~`#hist-clear` was 28px on a real touch device~~ — done, 2026-09-08, with [#31](https://github.com/jsundram/quartet-composers/issues/31)
12px under the 40px floor `@media (hover:none) and (pointer:coarse) and (max-width:800px)` exists to
enforce, because `#hist-clear{ min-height:28px }` is an ID and outranks `.btn` whatever the order —
the same specificity trap `styles.css` already documents for `.seg.sm`, which DID opt back in while
this button never did. Fixed by naming the ID in that rule.

It survived because the suite could not see it. The tap-target scan filters on `offsetParent`,
which is null while an element is `hidden`, and it ran at `BASE` with no range applied — so the one
`.btn` on the page that is hidden at rest was the only one never audited, 8px under its own
assertion. The scan now runs a second time with a filter applied. **A third state that hides a
control needs a third pass there**, which is the general shape of the hole rather than this
instance of it.

Worth knowing that the two fixes are coupled in the direction that would have bitten: raising the
button to 40px WITHOUT moving it more than doubles the step it causes, 10.6px to 22.6px. Taking the
accessibility fix on its own would have made the layout defect worse.

### The Fame view drops birth year entirely
Which is the thing the mocked-up "canon path" would have added: joining the repertoire in birth order
draws the chronological walk through output-and-attention space without spending an axis on it.
It was proposed, not chosen — the direction picked was B as mocked. Cheap to add if wanted.

### The share card labels six of the thirteen named composers
Richter, Shostakovich, Krommer, Ellerton, Tchaikovsky, Debussy and Prokofiev have dots on
`assets/og.png` but no names. At 1200×630 that is a deliberate density call, not an oversight —
but it means the card's "the repertoire, in birth order" key names a set the card only
half-identifies. The four diagonal label spots that closed #10 on the page are NOT in
`make-og-svg.py`, whose six labels are placed by hand rather than by a placer.

### A phone seats about twelve chart labels, whatever is emphasised
Measured across six different emphasis sets at 390×844: 10, 11, 11, 11, 12, 12 names placed. The
budget is not the constraint — at rest `cap` is pinned to the seed count — the constraint is
boxes that fit. So a thirteen-name set leaves one ring unnamed on a phone (currently Prokofiev,
at 2 quartets in the densest part of the cloud) while the same set names all thirteen on a
desktop. Options if it starts to matter: a larger `base` on narrow screens, dropping the ring for
a dot the placer could not name, or letting a phone label overhang into the left margin. Not done
because every one of them trades against something the resting view is currently getting right.

### The swarm hides the quartet count entirely
Documented in the hint text, but a reader who lands on the swarm from a shared `#v=swarm` link has
to read the hint to know the vertical axis means nothing. Consider dimming or removing the y-axis
label there — currently it is just absent, which is quieter than it should be.

---

### Surname extraction is a heuristic on 884 human names
`SURNAME` in `names.js` overrides the eight the "last word" rule gets wrong today (compound
surnames, capitalised particles, one name in Chinese order). There will be more it gets wrong that
nobody has noticed: French particles are dropped where a French index would keep them
(`de la Tombelle` → `Tombelle`), and any future non-Western name order will be silently reversed.
`Names.staleOverrides()` catches renames, not misjudgements. The stakes went up when the chart
labels started printing the same short form: a misjudged surname is now on the plot, not only in
a table cell whose `title` still carries the full name.

### Two Fame dots can still overlap, in ways the golden-ratio jitter does not cover — **known defect**
[#45](https://github.com/jsundram/quartet-composers/issues/45) replaced the Fame view's per-name
hash jitter with `spreadJq()`: rank each quartet-count stripe by readership and walk `frac(k·φ)`, so
dots adjacent in y are pushed maximally apart in x. That killed the reported failure — Debussy and
Gershwin went from 0.469px apart (with Gershwin painted on top of him and owning the right half of
his hit area) to over 6px, and the worst same-count pair on a phone from 0.045px to 1.11px. Two
residuals survive it, both measured, neither worth a mechanism yet:

- **Across stripes.** Adjacent counts are 0.079 decades apart down where the roster piles up and
  the jitter is ±0.045 wide, so the stripes overlap by construction. Rigel (6 quartets) and
  Martinaitytė (5) sit 0.78px apart on a phone. Ranking inside a stripe cannot see this. The only
  fixes are narrowing the jitter — which reintroduces the crowding it exists to break up — or
  giving up on the offset being a pure function of the row.
- **Along a run of near-ties.** The three-distance theorem bounds the gap between dots ADJACENT in
  the sequence; five composers sit on 38–39 views, and two of them five ranks apart (Barbillion,
  Charrière) come within 1.11px. The guarantee degrades as ~1/(φ·m) across a tied run of m.

A real fix is a relaxation pass — detect overlaps in screen space and repel — which is what
`MIN_SEP` does for the ring channel. It is not a jitter any more at that point: it costs the
"deterministic, stable between renders, pure function of the row" property that lets
`make-og-svg.py` duplicate it offline (invariant 14). Do not start it without deciding that trade
first. `ui.test.mjs` 4e2 holds the line at a 1px floor per stripe, so a regression past the point
already won fails loudly.

---

## Pipeline

### `fetch_views.py --force` refetches every article
There is no way to refresh a single composer after fixing their title. Minor, but it makes fixing
one bad row a two-minute job instead of a two-second one.

### ~~A top-up refetched the 62 articles younger than the window~~ — done, 2026-09-06
"Needs fetching" was `any(month not in cached)`, and an article created in 2019 never has a 2015
month, so it was missing something forever. A month the API answered "nothing" for is now recorded
as a **null** — asked, and there was nothing there — which is the same distinction invariant 10
makes everywhere else, and a MISSING month still means "never asked". A second run is now a true
no-op at the network: `0 need fetching, 884 already complete`. A 404 is deliberately NOT cached
that way: it means the canonical title in `people.json` is wrong, and caching it would silence the
report that says so on every run after the first.

### ~~`data/pageviews.json` was 1.9 MB and rewritten whole on every top-up~~ — done, 2026-09-06
Each series is a flat array aligned to the shared `months` axis now, one line per composer:
**1.88 MB → 502 KB**, and a monthly top-up changes 884 lines instead of 118k. The `{month: count}`
form was repeating the month key 884 times per month for nothing. The price is that alignment is
load-bearing — an array one element short shifts every month by one and the numbers stay entirely
plausible — so `build_data.py` and `validate.py` both refuse a ragged cache, and
`validate.test.py` proves it.


### `validate.py` cannot re-check title resolution offline
It asserts that every page-view series is keyed by a canonical title *according to the cached
`people.json`* — so a stale `people.json` would satisfy it. The check that closes this is an
online one: re-resolve a sample and confirm nothing moved. Worth adding to a periodic job rather
than the commit gate.

---

## Testing

### ~~`ui-test.sh` scores 231/240 under CI's Linux headless Chrome~~ — done, 2026-09-10, [#50](https://github.com/jsundram/quartet-composers/issues/50), [#53](https://github.com/jsundram/quartet-composers/issues/53), [#56](https://github.com/jsundram/quartet-composers/issues/56)
Never a browser problem — the premise that CI has no browser is simply false: `ubuntu-latest` ships
`/usr/bin/google-chrome`, `/usr/bin/chromium` and `/usr/bin/chromium-browser`, and `find_chrome`
picks the first up without help. Measured on #43 with a temporary `ui` job (since removed): the
suite runs to completion and 231 of the 240 checks pass. Two things had to be fixed to get that
far and both are still in `ui-test.sh`, because they are worth having anywhere: `--disable-dev-shm-usage`
(a CI container's `/dev/shm` is ~64MB and Chrome dies reaching past it) and a readiness loop that
prints `chrome.log` instead of expiring into a bare `ECONNREFUSED` from node with the log already
deleted by the EXIT trap.

**Eight of the nine were one cause and are fixed — but not by the fix this entry prescribed.**
The cause was right: `@media (hover:hover) and (pointer:fine)` (`styles.css:267`), which a headless
Linux Chrome does not satisfy, so the hover previews never fire and the panel's `min-height`
reservation is never applied. The prescription was wrong, and wrong in the way this repo cares
about — silently. `Emulation.setEmulatedMedia` accepts `features:[{name:"hover",…},{name:"pointer",…}]`,
returns an empty success, and CHANGES NOTHING: Blink's media-feature overrides cover
prefers-color-scheme and its neighbours, not the pointer ones (measured on Chromium 141, both
headless and headful; `prefers-color-scheme` in the same call does take). `--blink-settings=`
`primaryPointerType=4,availablePointerTypes=4,primaryHoverType=2,availableHoverTypes=2` DOES work
at startup and is still the wrong answer: the first `setTouchEmulationEnabled` restores to the
platform value rather than the flagged one when it is switched off, and it does so for every page
in the browser, so one phone section poisons every desktop section after it. A suite that
interleaves them cannot use it.
What works is giving the machine a pointer instead of arguing with the page about one:
`ui-test.sh` launches Chrome under **`xvfb-run`** when there is one, X reports a fine pointer and
hover, and a touch toggle now restores TO that. The eight are back, and the font metric below is
fixed too, so nothing on that list is still failing. The suite asserts which of the two it got — `the desktop viewport really reports a fine
pointer`, section 2 — rather than leaving eight later checks to imply it, which is what turned a
platform difference into eight bug reports against the app.

**The ninth was a font metric and is FIXED** (#53): `table does not overflow its box at 390px —
335 vs 326`. Neither option this entry offered survived the measuring it asked for. Pinning a face
asserts about a layout no reader has — and a bundled webfont, the option nobody wrote down, is that
same claim plus a precache entry, since the table still has to fit whatever face is drawn before it
loads. A tolerance blunts a check whose real bug is a column pushed off the edge.
What the measurement found is that the layout was the defect: ~6px of margin at 390px in the
narrowest face on hand, none in the widest — and at 360px, the common Android width, it overflowed
in EVERY face including the Mac's own SF (310 vs 296, Views clipped mid-number, sort arrow halved).
The 390px check had been passing on the one width where the narrowest font happens to clear.
So the fix gave back the width that was carrying nothing: the header word "Quartets" over a
three-digit column (`short` in `table.js`, drawn as "Qts" with the full word kept as the sort
button's accessible name) and the phone cell gutters, 8px to 6px. The check now asserts 390 AND
360, because one width in the runner's own font is measuring the font.
It was designed on macOS, where a Linux run was inference and the widest face installed stood in
for DejaVu, and it has since been RUN there: 251 of 251 on Ubuntu 24.04 / Chromium 141 under
`xvfb-run`, with `fc-match system-ui` resolving to DejaVu Sans and no SF on the box to fall back
to. The stand-in was accurate rather than merely convenient — predicted ~49px of slack at 390 and
~19px at 360 against a measured 47.6 and 17.6. `styles.css`'s comment still says inference on
purpose: it describes how the number was ARRIVED at, and the next person changing that layout will
be on a Mac too.

**And the suite now RUNS in CI** (#56), in a `ui` job of its own — deliberately split out of #53
so a workflow change could be reviewed on its own. Both blockers this entry named were gone by
then: the browser was never missing, and the font check was a real layout defect rather than a
platform quirk. Three things the job needed, one of them not obvious. **node 22**, because
`ui.test.mjs`'s entire CDP client is the global `WebSocket` that node 20 does not have — and of
the three jobs already in `checks.yml` the two that set node up at all (`sw` and `gates`) pinned
20, while `data` has no `setup-node` step, so copying one was the way to get an immediate failure
that looks like a browser problem and is not. **`xvfb-run`**, for the pointer (#50). And the FULL
Chrome rather than `chrome-headless-shell`, which `find_chrome` prefers from a Playwright cache
and which reports no pointer even under a display — a bare `ubuntu-latest` has no such cache, so
that one is a hazard only if a Playwright install is ever added to the job.
The fourth thing was not on the list and is the one worth remembering: `ui-test.sh` exits **0**
when it finds no browser, which is deliberate for laptops and means a job that quietly loses its
Chrome goes green having tested nothing. `REQUIRE_BROWSER=1` turns that skip, and both pointer
warnings, into a failure; the job sets it, and so does the ablate step, which reaches the suite
through `ablate.py` and can pass nothing but the environment.
The prize was bigger than the suite: `ablate.py --with-ui` runs on the runner now, so the gates
job has stopped printing "no CI-runnable suite covers this branch's source" for exactly the
branches that change what the page LOOKS like. #55's own ablation was owed locally and run by
hand; it went red in the right two places, and nothing in CI could have known that.

## IMSLP

### The dataset is built and joined; nothing is wired into the app yet — 2026-09-11
`scripts/fetch_imslp.py` (network, cached in `data/imslp.json`) and `scripts/build_imslp.py`
(offline, writes `imslp.json`) exist and run. `imslp.json` is NOT referenced by `index.html`,
`sw.js` or any module, so nothing about the shipped app has changed and `V` has not moved.

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
   is the real finding and a good one). A row **missing from `imslp.json` entirely** means we could
   not place them at all (423 rows), which is unknown, not empty. Colouring those two the same way
   states something false about 423 composers. This is invariant 10 arriving in a new field.

3. *The 423 is soft evidence, not proof.* It means: no Wikidata P839, no IMSLP composer page
   linking their article, and no page under any one-, two- or three-token `Surname, Forename`
   inversion of their name. That is decent evidence of absence and it is not the same as asking.
   Any copy on the page has to say "no IMSLP page found", never "not on IMSLP".

**What shipping it needs**, roughly in order:
- `build_data.py` writes the per-composer count into `composers.json` as a new field, and
  `imslp.json` becomes the lazily-fetched companion the way `readership.json` already is — SHELL
  but NOT BOOT (invariant 2), since links in the detail panel are decoration nothing waits for.
- `sw.js`: add `imslp.json` to `SHELL`, leave it out of `BOOT`, bump `V` (invariant 1).
- `validate.py`: the gate this needs is that every `imslp.json` key is a row name in
  `composers.json` and every `cats` entry is one the cache actually holds — the drift invariant 4
  warns about, one file over.
- Detail panel: the composer's IMSLP category link plus their work pages, which is the feature's
  actual point and the cheapest half.
- Table column: the page count, sortable, `—` where absent.
- A fourth filter would need its own module on the `applyFilters()` contract (a Set of indices or
  null), not another special case in `app.js`.
- `og-lint.py`'s stated-count rule and `prose-lint.py`'s composer-count rule both need to know
  about any new total that reaches the docs.
- **A colour channel is the expensive option and should be argued for separately.** Fame already
  spends hue on emphasis and the timeline spends it on the lifespan ramp (invariant 8), so
  availability would be a fourth encoding competing for the one channel that is already carrying
  the view's argument — and it is a three-state fact with a 423-row "unknown" bucket, which is the
  hardest kind of thing to put in a legend honestly.

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
`Year/Date of Composition` field is already cached in `data/imslp.json` and unread.

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

- **`fetch_works()` skips the category crawl when the cache has it, so a monthly run would never
  discover a new work page.** Every other pass is keyed by title and tops up correctly — only
  discovery is broken, and it is the cheapest pass on the list (~12 requests). This has to be
  fixed before `refresh.py` can sensibly run the IMSLP stages monthly.
- **`data/imslp.json` is the scrape cache and collides by name with the shipped file #61 adds.**
  Rename to `data/imslp-scrape.json`. It is also 3.5 MB and badly encoded — `markers` spends
  648 KB on four named booleans per page where an int bitmask would do, and `works` repeats three
  key names 4,937 times. Under 2 MB is easily reachable without giving up the raw wikitext, which
  must stay raw: a better parser must never cost a request.

**The coverage report is generated, not written.** `scripts/build_imslp.py` writes the audit to
`data/imslp-audit.json` and `scripts/imslp-report.py` renders it to a self-contained
`imslp-coverage.html`. No figure on that page is typed — every one is computed at render time from
`composers.json`, `imslp.json` and the audit, because the roster grows, the monthly top-up moves
every readership number and IMSLP gains scores. A coverage report typed once is wrong by the next
run, which is the built-or-cut rule applied to a page that is nothing but falsifiable prose.

Making it a page **inside the app** is a separate and more expensive decision, and it should not be
taken just because the report exists. This is a single-page PWA with a precache manifest: a second
route means another `SHELL` entry, another `V` bump on every edit to it (invariant 1), a decision
about whether it is a `BOOT` dep, and a navigation affordance on a page whose first screen is
already fought over (issue 29). The standalone file costs none of that and is the right home until
somebody wants the coverage numbers *while looking at the chart* — at which point the answer is
probably the detail panel and a table column, not a second page.

**Cost of a refresh.** ~165 requests, one per second, everything cached and never refetched;
`--refresh` is the only way to re-ask. It does not belong in the monthly `refresh.py` job yet —
IMSLP's catalogue moves slowly and the run is the one part of this pipeline that talks to a
volunteer-funded server.

---

## Deliberately not doing

**Per-language page views.** English Wikipedia readership systematically undercounts non-Anglophone
composers — a Czech composer's readers are on cs.wikipedia. Fixing it means Wikidata sitelinks and
a per-language fan-out, which trades a clean, stated bias for a messy, hidden one (which languages?
weighted how?). The current approach is to name the measure honestly instead. Revisit only with a
specific reason.

**Summing a composer's redirects into their readership.** Measured, not assumed:
`scripts/audit_redirects.py` prices all 2,888 redirects into the 884 articles, and 436 composers do
read higher — by a median of **1.024×**. Only 49 exceed 10%, and nothing in `CANON` moves at all
(Mozart 186,772 → 191,780; every one of the ten rounds to 1.0×). What the sum buys is invisible on
an axis spanning five orders of magnitude; what it costs is a stated measure — page views for this
article — traded for one that depends on how many aliases the article happened to accumulate, which
is an artefact of Wikipedia's edit history rather than of readership. Same trade as the per-language
question above, same answer. A page MOVE is not this: the article lived at the old title, so those
months are the same measurement under a different string, and they are stitched (invariant 15).

**Wikidata as a source for quartet counts.** Evaluated and rejected on evidence: Beethoven's
quartets are typed as generic "musical work/composition" with nothing linking them to the genre, so
a SPARQL count over the whole corpus returns four composers. See the note in `scrape_list.py`.
