#!/usr/bin/env node
// names.js offline: the last-word rule, the two display forms, and the bare-surname award.
//
// It exists because this is the most heuristic file here and the only one whose output is a
// JUDGMENT about 800-odd human names — and every claim the module used to make in prose ("the rule
// is right about 870 of them", "two groups qualify today", "eight rows fall through to the full
// name") is a count that moves when the pipeline runs. A count in a comment cannot go red. So the
// counts are gone and the RULES are here, fixture-driven, plus three properties asserted against
// the roster the app actually ships.
//
//     node scripts/names.test.mjs
import { readFileSync } from "node:fs";

const ROOT = new URL("..", import.meta.url).pathname;
const win = {};
new Function("window", readFileSync(ROOT + "names.js", "utf8"))(win);
const N = win.Names;

let fails = 0;
const check = (name, ok, extra = "") => {
  console.log(`${ok ? "ok  " : "FAIL"} ${name}${extra ? ` — ${extra}` : ""}`);
  if (!ok) fails++;
};
// Fixtures carry readership alongside the names because setData does: [name, views].
const load = rows => N.setData(rows.map(r => r[0]), rows.map(r => r[1]));
const eq = (name, got, want) => check(name, got === want, got === want ? "" : `got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);

// ---- 1. the surname, and the five kinds of name the last word gets wrong ------------------------
load([["Ludwig van Beethoven", 1], ["Carl Ditters von Dittersdorf", 1], ["Chen Yi", 1],
      ["Ralph Vaughan Williams", 1], ["Samuel Wesley (composer, born 1766)", 1],
      ["Alicia Van Buren", 1], ["Tera de Marez Oyens", 1]]);
eq("a lowercase particle files under the last word, as an English index does",
   N.surnameOf("Ludwig van Beethoven"), "Beethoven");
eq("...and so does a two-word one", N.surnameOf("Carl Ditters von Dittersdorf"), "Dittersdorf");
eq("a Wikipedia disambiguator is not part of the name",
   N.surnameOf("Samuel Wesley (composer, born 1766)"), "Wesley");
eq("a generational suffix stays with the surname", N.surnameOf("Joe Bloggs Jr."), "Bloggs Jr.");
eq("a compound surname comes from SURNAME, not from the last word",
   N.surnameOf("Ralph Vaughan Williams"), "Vaughan Williams");
eq("a CAPITALISED particle is part of the name", N.surnameOf("Alicia Van Buren"), "Van Buren");
eq("a family-name-FIRST title takes its first word", N.surnameOf("Chen Yi"), "Chen");

// Every override has to disagree with the rule it overrides: an entry the plain rule already gets
// right is a judgment call doing nothing, and it would sit there through the rename that made it
// dead. The rule is re-implemented here rather than read out of the module, because an override
// checked against the code that consults it first can only ever agree with itself.
const lastWord = n => n.replace(/\s*\([^)]*\)\s*$/, "").split(/\s+/).pop();
// `idle` is null rather than [] when the map is not exported, so a tree without it reports a named
// FAIL instead of dying on Object.entries — ablate.py reads a crash as proving nothing.
const idle = N.OVERRIDES && Object.entries(N.OVERRIDES).filter(([n, s]) => s === lastWord(n));
check("no SURNAME override merely restates the last-word rule", !!idle && idle.length === 0,
      idle ? idle.map(([n]) => n).join(", ") || `${idle.length} idle of ${Object.keys(N.OVERRIDES).length}`
           : "Names.OVERRIDES is not exported");

// ---- 2. the two forms, and who needs more than a surname ----------------------------------------
load([["Joseph Haydn", 28938], ["Michael Haydn", 2268], ["Ferdinand David", 900],
      ["Félicien David", 800], ["Maurice Ravel", 5000]]);
eq("a unique surname IS the chart label", N.short("Maurice Ravel"), "Ravel");
eq("...and the filed form too, so the column stays as narrow as it can",
   N.filed("Maurice Ravel"), "Ravel");
eq("the table appends the forename, because it sorts on the string it prints",
   N.filed("Joseph Haydn"), "Haydn, Joseph");
eq("the chart spends an INITIAL where that identifies the person",
   N.short("Michael Haydn"), "M. Haydn");
eq("...and the full name where it does not", N.short("Ferdinand David"), "Ferdinand David");

// ---- 3. the bare surname: a floor AND a margin --------------------------------------------------
// The floor alone would hand "Haydn" to whoever led by one view once both members cleared it —
// a label that identifies nobody — and readership is refetched monthly, so that is drift, not
// hypothesis.
eq("the surname a reader already attaches to ONE composer prints bare",
   N.short("Joseph Haydn"), "Haydn");
eq("...but never in the filed form, which would be inconsistent about who gets a forename",
   N.filed("Joseph Haydn"), "Haydn, Joseph");
load([["Joseph Haydn", 28938], ["Michael Haydn", 20000]]);
eq("two well-read members of one group: the lead is under the margin, so nobody takes it bare",
   N.short("Joseph Haydn"), "J. Haydn");
load([["Joseph Haydn", 900], ["Michael Haydn", 3]]);
eq("a 300x lead under the floor does not qualify either", N.short("Joseph Haydn"), "J. Haydn");

// ---- 4. the forename is everything BEFORE the surname, wherever the surname sits ----------------
// A suffix slice off the end yielded a forename of "Che" for "Chen Yi", inert only because no
// other composer's name ended in "Chen" — which is what a re-scrape changes.
load([["Chen Yi", 5000], ["Ann Chen", 10]]);
eq("a family-name-first title files under its own order", N.filed("Chen Yi"), "Chen, Yi");
eq("...and is never prefixed with an initial, which would reorder it", N.short("Chen Yi"), "Chen Yi");
eq("...while the other member of its group is initialled normally", N.short("Ann Chen"), "A. Chen");

// ---- 5. the shipped roster ---------------------------------------------------------------------
// Three properties of the real names, not of a fixture. The first two are what the whole
// shared-surname map is FOR; the third is what staleOverrides() is for.
const data = JSON.parse(readFileSync(ROOT + "composers.json", "utf8"));
const roster = data.rows.map(r => r[0]);
N.setData(roster, data.rows.map(r => r[4]));

const dup = form => {
  const seen = new Map();
  for (const n of roster) {
    const k = N[form](n);
    if (seen.has(k)) return `${form}: ${seen.get(k)} and ${n} both print "${k}"`;
    seen.set(k, n);
  }
  return "";
};
check("no two composers get the same chart label", dup("short") === "", dup("short"));
check("...nor the same filed name", dup("filed") === "", dup("filed"));

// Shared surnames have to stay ADJACENT under the column's own sort, which is the reason the filed
// form leads with the surname at all.
const sorted = roster.map(n => [N.filed(n), N.surname(n)]).sort((a, b) => a[0].localeCompare(b[0]));
const runs = new Map();
sorted.forEach(([, s], i) => { if (!runs.has(s)) runs.set(s, [i, i]); else runs.get(s)[1] = i; });
const split = [...runs].filter(([s, [a, b]]) => b - a + 1 !== roster.filter(n => N.surname(n) === s).length);
check("sorting the filed names keeps every surname group contiguous", split.length === 0,
      split.map(([s]) => s).join(", "));

check("every SURNAME override still names a composer in the roster", N.staleOverrides().length === 0,
      N.staleOverrides().join(", ") || `${roster.length} names`);

console.log(fails ? `\nFAIL: ${fails} of the above` : "\nall ok");
process.exit(fails ? 1 : 0);
