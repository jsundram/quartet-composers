# issue #3 — the quartet-roulette composers on a phone

[#3](https://github.com/jsundram/quartet-composers/issues/3) asks whether the Fame view should
highlight the composers from [quartet-chooser](https://github.com/jsundram/quartet-chooser) plus
Franz Xaver Richter, instead of the curated thirteen. These are the three renders that answered it.

Unlike the artboards one level up, these are not drawn: they are `chart.js` itself, in headless
Chrome at 390×844 DPR 2, resting Fame view, no filter, with `CANON` and `OUTLIERS` patched per
variant. The counts come from `Chart.namedCount()` and the placed `font-size="10.5"` label
elements — read off the DOM, not counted by eye.

| render | emphasised | named | ringed, unnamed |
|---|---|---|---|
| `today.png` — seven filled, six ringed | 13 | 11 | 2 |
| `roulette-and-rings.png` — the 18 filled, today's rings kept | 22 | 13 | 9 |
| `roulette-only.png` — the 18 replace all thirteen | 18 | 10 | 8 |

## What they showed

**Bach cannot be plotted.** 17 of the 18 resolve to rows in `composers.json`; Bach does not, because
he wrote no string quartets and is absent from Wikipedia's list. The roulette set reaches him
through *The Art of Fugue*, which quartets play but which is not a quartet.

**A phone seats about ten names whatever you emphasise.** `pickLabels()` is greedy and
first-come on space, so the ceiling barely moves between the three: 11, 13, 10. Emphasising
eighteen therefore rings eight composers and names none of them — the defect in
[#10](https://github.com/jsundram/quartet-composers/issues/10), four times over — and the names it
drops are Shostakovich, Debussy, Ravel, Schubert, Mendelssohn, Schumann, Prokofiev and Grieg.

**A listening canon lives in one corner of this chart**, and this is the objection that survives
any fix to the label budget. The roulette composers were chosen as quartets worth playing, so
nearly all of them wrote between 1 and 16 and are heavily read: they pile into the upper left.
Below the `10k/quartet` diagonal the third render has no emphasis at all. Cambini (149 quartets,
read ~200 times a month), Ellerton and Krommer are not great, and that is exactly their job — they
are what the `1/quartet` and `10/quartet` diagonals label, and what makes the top-right dots mean
something.

Six of today's seven filled greats are already in the eighteen, so the swap does not improve the
top end. It crowds it, and it costs the bottom.

## Outcome

Not adopted as the resting set. The roulette list is worth having as a **filter**, on the contract
the other three already use (return a Set of indices, or null; `applyFilters()` intersects), so it
arrives with the label budget already grown by the frame fit and nothing gets ringed without a
name. That also leaves [#7](https://github.com/jsundram/quartet-composers/issues/7) alone: who
carried the form stays an editorial claim about seven people, not a list imported from a different
question.
