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

### Gender is not in the data — [#1](https://github.com/jsundram/quartet-composers/issues/1)
`fetch_wikidata.py` already fetches each composer's full claim set and keeps only P569/P570, so
P21 is one line away. Probed: 276 of 883 (31%) are women, 210 of them plottable, births
1745–1989. Enough for a filter, and the Readers view already implies the finding — the most-read
woman on the list is Florence Price at 8,001/mo against Mozart's 186,772. The issue carries the
numbers, the pipeline steps and the two decisions to make first (where the control lives, and
whether it is a filter or an encoding).

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

### One composer has no page-view data
`Fernand de la Tombelle` has no Wikidata item; dates come from page prose only. Harmless, but it is
the one row where the pipeline's guarantees don't hold.

### The 2014 archive is only half-used
`compare_2014.py` reports 28 composers who dropped off the list. Most are deleted articles, but a
few were renames the fold-matching doesn't catch (Fanny Mendelssohn → Fanny Hensel, Charles Wesley →
Charles Wesley junior). Worth a pass to confirm none is a real loss.

---

## Interface

### The full-screen strip drops four things, and says so nowhere
`tight()` in `app.js` trims the panel to two lines for the fixed-height strip above the chart: the
percentile line, the Wikipedia link, Prev/Next, and the 12-month range beside the median view count
all disappear. All four are one tap away and back the moment you leave full screen, and the range
is no longer load-bearing there — readership is now stated as "180k+" everywhere, so the strip no
longer claims a precision it can't support. Left here as a record of what the strip is missing.

### The detail panel wastes most of its column on desktop
It is ~200px tall in a full-height sticky column. The 12-month view series is already fetched and
cached and currently unused by the UI — a **sparkline** there would fill the space with the one
thing the panel is missing: whether this composer's readership is steady or spiking. `views_lo` and
`views_hi` already ship; the full series does not, so this needs a schema addition.

### ~~1580–1700 is ~20% of the x-axis for three composers~~ — decided, 2026-09-05
The premise was wrong, which is why it looked like a trade-off. Allegri (1582), Scarlatti (1660)
and Telemann (1681) have no stated quartet count, so they are TABLE-ONLY rows and were never on
the chart at all: the domain was spending 31% of the width on a stretch where no dot can ever be
drawn. `X_DOMAIN` is now derived in `setData()` from the PLOTTABLE birth years (1709–1989 today),
snapped out to a 50-year grid — 1700–2000. Nothing was dropped and no axis was broken.
`make-og-svg.py` derives the same domain; keep them in step.

### The Timeline view still spends hue on lifespan — the wrong colour job
The Readers view moved colour onto the argument; Timeline, Swarm and Lens still carry the
diverging orange↔purple lifespan ramp. Two problems with it, both measurable. A diverging scale
encodes POLARITY — distance either side of a meaningful baseline — and lifespan has none: the ramp
pivots on the median lifespan of whoever is currently in the dataset, which moves when the data
does. And its midpoint `--c-mid` (#cec7ba) sits at 1.61:1 against the plot surface, so the most
COMMON lifespan is the least visible dot on the chart. A sequential ramp (one hue, light→dark) is
the honest form; emphasis is the better one if those views get an argument of their own.

### The Readers view drops birth year entirely
Which is the thing the mocked-up "canon path" would have added: joining the seven in birth order
draws the chronological walk through output-and-attention space without spending an axis on it.
It was proposed, not chosen — the direction picked was B as mocked. Cheap to add if wanted.

### The share card labels six of the thirteen named composers
Richter, Shostakovich, Krommer and Ellerton have dots on `assets/og.png` but no names. At 1200×630
that is a deliberate density call, not an oversight — but it means the card's "the seven who carry
the form" key names a set the card only half-identifies.

### The swarm hides the quartet count entirely
Documented in the hint text, but a reader who lands on the swarm from a shared `#v=swarm` link has
to read the hint to know the vertical axis means nothing. Consider dimming or removing the y-axis
label there — currently it is just absent, which is quieter than it should be.

---

### Surname extraction is a heuristic on 884 human names
`SURNAME` in `table.js` overrides the seven the "last word" rule gets wrong today (compound
surnames, capitalised particles, one name in Chinese order). There will be more it gets wrong that
nobody has noticed: French particles are dropped where a French index would keep them
(`de la Tombelle` → `Tombelle`), and any future non-Western name order will be silently reversed.
`Table.staleOverrides()` catches renames, not misjudgements.

## Pipeline

### `fetch_views.py --force` refetches every article
There is no way to refresh a single composer after fixing their title. Minor, but it makes fixing
one bad row a two-minute job instead of a two-second one.

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
