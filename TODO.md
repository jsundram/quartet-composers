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
Tombelle, who has no Wikidata item either).

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

### One composer is sized by a single month of page views
`Fernand de la Tombelle` has no Wikidata item — dates come from page prose only — and his article
has exactly ONE month of view data (2026-08) out of the 134 the cache now holds. So his median,
min and max are all that same number, and his dot is sized by precisely the weather invariant 9
exists to smooth away. He is also the one composer with no sparkline: `sparkline()` needs two
points to draw a line. Harmless at one row out of 884, but it is the row where the pipeline's
guarantees don't hold, and worth deciding whether one month should count as a measurement at all.

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
are looking at. The repertoire filled in `--sel` is not, and the issue stays open for it — "who
carried the form" is an editorial claim about music history, and TODO records that no single
ranking reproduces the curated set (the best recovers 8 of 13).

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

## Deliberately not doing

**Per-language page views.** English Wikipedia readership systematically undercounts non-Anglophone
composers — a Czech composer's readers are on cs.wikipedia. Fixing it means Wikidata sitelinks and
a per-language fan-out, which trades a clean, stated bias for a messy, hidden one (which languages?
weighted how?). The current approach is to name the measure honestly instead. Revisit only with a
specific reason.

**Wikidata as a source for quartet counts.** Evaluated and rejected on evidence: Beethoven's
quartets are typed as generic "musical work/composition" with nothing linking them to the genre, so
a SPARQL count over the whole corpus returns four composers. See the note in `scrape_list.py`.
