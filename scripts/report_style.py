"""The look shared by the two generated IMSLP pages.

Kept in one importable module rather than copied into each, because they are one design and a
second copy is a second thing to keep in step. Hyphenated script names cannot be imported, which
is why this is the module and they are the entry points.
"""
CSS = """
:root{
  --paper:#eef1f5; --card:#f7f9fb; --ink:#151a21; --muted:#5b6775; --rule:#ccd5de;
  --accent:#2b4c7c; --have:#1a6e62; --none:#a3651f; --unknown:#8d99a6;
  --chipbg:#e3e9ef;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --paper:#0f131a; --card:#161c25; --ink:#e4eaf1; --muted:#95a2b1; --rule:#27313d;
    --accent:#7ea6dd; --have:#4fb8a4; --none:#d69b4e; --unknown:#7d8896; --chipbg:#1e2733;
  }
}
:root[data-theme="dark"]{
  --paper:#0f131a; --card:#161c25; --ink:#e4eaf1; --muted:#95a2b1; --rule:#27313d;
  --accent:#7ea6dd; --have:#4fb8a4; --none:#d69b4e; --unknown:#7d8896; --chipbg:#1e2733;
}
*{ box-sizing:border-box }
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:"IBM Plex Sans",system-ui,sans-serif; font-size:16px; line-height:1.6;
  -webkit-font-smoothing:antialiased;
}
main{ max-width:60rem; margin:0 auto; padding:clamp(1.5rem,4vw,4rem) clamp(1.1rem,4vw,2.5rem) 5rem }
section{ margin-top:clamp(2.5rem,5vw,4rem); padding-top:clamp(2rem,4vw,3rem);
  border-top:1px solid var(--rule) }
h1,h2,h3{ font-family:Spectral,Georgia,serif; font-weight:600; text-wrap:balance; margin:0 }
h1{ font-size:clamp(2rem,5vw,3.1rem); line-height:1.1; letter-spacing:-.015em }
h2{ font-size:clamp(1.4rem,2.6vw,1.9rem); margin-bottom:.6rem }
h3{ font-size:1.05rem; margin:2rem 0 .5rem }
p{ margin:.85rem 0; max-width:64ch }
a{ color:var(--accent) }
a:focus-visible,li a:focus-visible{ outline:2px solid var(--accent); outline-offset:2px }
code{ font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.88em }
.eyebrow{ font-size:.72rem; text-transform:uppercase; letter-spacing:.14em; color:var(--muted);
  margin:0 0 1rem }
.lede{ font-size:clamp(1.05rem,1.6vw,1.2rem); margin-top:1.2rem }
.lede strong{ font-weight:600 }
.stamp{ font-family:"IBM Plex Mono",monospace; font-size:.76rem; color:var(--muted) }
.note{ font-size:.9rem; color:var(--muted) }

/* Two funnels. Each step is a SUBSET of the one above it, so the steps are indented by their own
   share and carry it as a figure — the shape says "narrowing" before any number is read, which a
   flat row of five totals leaves the reader to work out. */
.funnels{ display:grid; grid-template-columns:repeat(auto-fit,minmax(19rem,1fr)); gap:1.6rem 3rem;
  margin-top:2.2rem }
.fun .eyebrow{ margin-bottom:.5rem }
.fun ol{ list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:.45rem;
  counter-reset:none }
.fun li{ display:grid; grid-template-columns:auto 1fr auto; align-items:baseline;
  column-gap:.6rem; padding:.45rem .7rem; background:var(--card);
  border-left:3px solid var(--accent) }
.fun li:nth-child(2){ margin-left:1.1rem }
.fun li:nth-child(3){ margin-left:2.2rem }
.fun b{ font-family:Spectral,Georgia,serif; font-size:1.5rem; font-weight:600; line-height:1;
  font-variant-numeric:tabular-nums }
.fun span{ font-size:.82rem }
.fun em{ font-family:"IBM Plex Mono",monospace; font-style:normal; font-size:.74rem;
  color:var(--muted); font-variant-numeric:tabular-nums }
.fun i{ grid-column:2/4; font-style:normal; font-size:.72rem; color:var(--muted);
  line-height:1.3; margin-top:.15rem }
@media (max-width:26rem){ .fun li:nth-child(2){ margin-left:.5rem }
  .fun li:nth-child(3){ margin-left:1rem } }

.legend{ display:flex; flex-wrap:wrap; gap:1.1rem; margin:1.4rem 0 .9rem; font-size:.82rem }
.key{ display:flex; align-items:center; gap:.45rem; color:var(--muted) }
.sw{ width:.85rem; height:.85rem; display:inline-block; border-radius:2px }
.sw.have,.seg.have{ background:var(--have) }
.sw.none,.seg.none{ background:var(--none) }
.sw.unknown,.seg.unknown{ background:var(--unknown) }
.bands{ display:flex; flex-direction:column; gap:.4rem }
.band{ display:grid; grid-template-columns:3.6rem 1fr 2.6rem; align-items:center; gap:.75rem }
.yr,.pc{ font-family:"IBM Plex Mono",monospace; font-size:.8rem; color:var(--muted);
  font-variant-numeric:tabular-nums }
.pc{ text-align:right }
.bar{ display:flex; height:1.6rem; border-radius:2px; overflow:hidden; background:var(--chipbg) }
.seg{ display:flex; align-items:center; justify-content:center; min-width:0 }
.seg i{ font-style:normal; font-family:"IBM Plex Mono",monospace; font-size:.7rem; color:#fff;
  opacity:.92; padding:0 .2rem }

table{ width:100%; border-collapse:collapse; margin:.8rem 0; font-size:.9rem }
th,td{ text-align:left; padding:.42rem .6rem; border-bottom:1px solid var(--rule) }
thead th{ font-size:.7rem; text-transform:uppercase; letter-spacing:.09em; color:var(--muted);
  font-weight:500 }
.num{ text-align:right; font-variant-numeric:tabular-nums;
  font-family:"IBM Plex Mono",monospace }
.mono{ font-family:"IBM Plex Mono",monospace; font-size:.84em; color:var(--muted) }
.prov th{ font-weight:400 }
.prov .track{ width:45%; padding-right:0 }
.prov .track span{ display:block; height:.55rem; background:var(--accent); border-radius:2px }
.cols{ display:grid; grid-template-columns:repeat(auto-fit,minmax(17rem,1fr)); gap:0 2.5rem }
.chip{ font-size:.74rem; padding:.12rem .5rem; border-radius:999px; background:var(--chipbg);
  color:var(--muted); white-space:nowrap }
.chip.none{ color:var(--none) } .chip.unknown{ color:var(--unknown) }
.chips{ list-style:none; padding:0; margin:1rem 0; display:flex; flex-wrap:wrap; gap:.5rem }
.chips a{ display:inline-flex; gap:.5rem; align-items:baseline; text-decoration:none;
  border:1px solid var(--rule); background:var(--card); padding:.3rem .6rem; border-radius:3px;
  font-size:.84rem; color:var(--ink) }
.chips a:hover{ border-color:var(--accent) }
.chips span{ font-family:"IBM Plex Mono",monospace; font-size:.76rem; color:var(--muted) }
footer{ margin-top:3.5rem; padding-top:1.5rem; border-top:1px solid var(--rule);
  font-size:.82rem; color:var(--muted) }
footer p{ max-width:70ch }
.band.wide{ grid-template-columns:11rem 1fr 2.6rem }
.band.wide .yr{ font-family:"IBM Plex Sans",sans-serif; font-size:.82rem }
@media (max-width:34rem){ .band{ grid-template-columns:3rem 1fr 2.2rem }
  .band.wide{ grid-template-columns:7rem 1fr 2.2rem } .seg i{ display:none } }
"""


EXTRA = """
/* The audit page is a working surface, not a read-through: 22 composers and 400 rows, scanned by
   jumping between them. Everything vertical is tightened against the report's rhythm so more of
   one composer's catalogue is on screen at once. */
main{ max-width:72rem; padding-top:2rem }
section{ margin-top:1.6rem; padding-top:1.2rem }
h2{ font-size:1.25rem }
p{ margin:.5rem 0 }
.lede{ margin-top:.7rem }
.who{ margin-top:1.1rem; padding-top:.7rem; border-top:1px solid var(--rule) }
.who:first-of-type{ border-top:none; margin-top:.6rem }
.who h3{ margin:0 0 .15rem; font-size:1rem; display:flex; align-items:baseline; gap:.55rem;
  flex-wrap:wrap }
.who h3 a{ text-decoration:none }
.tally{ font-family:"IBM Plex Mono",monospace; font-size:.74rem; color:var(--muted);
  font-weight:400; letter-spacing:0 }
.tally b{ color:var(--ink); font-weight:500 }

.audit{ font-size:.82rem; table-layout:fixed; margin:.25rem 0 .1rem }
.audit th,.audit td{ padding:.2rem .5rem .2rem 0; vertical-align:top; word-break:break-word }
.audit td{ line-height:1.35 }
.audit thead th{ padding-bottom:.1rem }
.audit .raw{ font-family:"IBM Plex Mono",monospace; font-size:.76rem; color:var(--muted) }
.audit .ids{ font-family:"IBM Plex Mono",monospace; font-size:.76rem }
.audit tr.flag td{ background:color-mix(in srgb, var(--none) 14%, transparent) }
.audit tr.drop td{ background:color-mix(in srgb, var(--unknown) 18%, transparent);
  color:var(--muted) }

/* Sorting. The header is a real button so it is reachable by keyboard and announced as a
   control; aria-sort carries the state and the arrow is drawn from it, so the two cannot
   disagree. */
.audit thead th{ padding-right:.5rem }
.audit th button{ all:unset; cursor:pointer; display:inline-flex; gap:.3rem; align-items:center;
  font:inherit; color:inherit; text-transform:inherit; letter-spacing:inherit; width:100% }
.audit th.num button{ justify-content:flex-end }
.audit th button:hover{ color:var(--ink) }
.audit th button:focus-visible{ outline:2px solid var(--accent); outline-offset:2px }
.audit th button::after{ content:"\2195"; opacity:.35; font-size:.9em }
.audit th[aria-sort="ascending"] button::after{ content:"\2191"; opacity:1 }
.audit th[aria-sort="descending"] button::after{ content:"\2193"; opacity:1 }
.audit th[aria-sort] button{ color:var(--ink) }

.tag{ font-size:.66rem; text-transform:uppercase; letter-spacing:.08em; color:var(--muted);
  border:1px solid var(--rule); border-radius:2px; padding:0 .28rem; white-space:nowrap }
.empty{ color:var(--muted); font-style:italic; font-size:.85rem; margin:.15rem 0 }
"""
