# mocks

Design artifacts — the artboards behind a decision, kept so the reasoning survives the decision.

## What is here

`Quartet Chart Directions` (published 2026-09-05) is the canvas that chose the view now called
**Fame** (it was **Readers** when these were drawn): three directions for re-encoding the chart
around "why are the greats great", plus a page-structure board. It is what `chart.js`'s `fame`
mode and the `#filters` row were picked from. The artboards keep the old name on purpose — they
are the record of a decision, not a second copy of the app.

| artboard | direction | outcome |
|---|---|---|
| `Today.dc.html` | the chart as it shipped — five variables, no argument | baseline |
| `Main.dc.html` | **A** · the canon drawn on the timeline, joined in birth order | not chosen |
| `OptionB.dc.html` | **B** · output across, attention up, readers-per-quartet diagonals | **chosen** |
| `OptionC.dc.html` | **C** · not a chart: three named groups and two columns | not chosen |
| `Page.dc.html` | one filter row, pills below the plot, phone width | **chosen** |

## Regenerating

The charts are drawn from `composers.json`, not sketched — same domains, same 0.35 radius
exponent, same name-hash jitter as `chart.js`, so an artboard is a picture of the real dataset and
goes stale the same way the app does.

```sh
python3 mocks/gen.py      # composers.json  -> mocks/chart-*.svg  (gitignored; ~270 KB)
python3 mocks/build.py    # chart-*.svg     -> mocks/*.dc.html + canvas.json
```

`build.py` embeds the SVGs, so the `.dc.html` files are self-contained and are what is committed.

## Republishing the canvas

The artboards are seeded into a Claude Design payload and published as an Artifact; `/design`
carries the helper and the current procedure. Re-seed from the files here rather than editing a
published page, and republish to the same URL to keep the link.

## Why these are not in the app

Nothing here ships. `gen.py` deliberately duplicates chart.js's scales rather than importing them —
same reason `scripts/make-og-svg.py` does (invariant 14): the app must not grow a build step, and a
mockup must not be able to break the app. If you change an encoding in `chart.js`, these do not
follow, and that is fine — they are a record of a decision, not a second implementation of it.
