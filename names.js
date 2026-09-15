// Display names: one canonical Wikipedia title, two shortened forms.
//
// The table files by SURNAME so the column sorts the way a reader expects -- all three Haydns
// together, not under J, M and F. The chart shortens for pixels: "Wolfgang Amadeus Mozart" is ~120px
// of ink where "Mozart" says it in 40, and the labeller is a greedy first-come placer, so a pixel
// one name does not need is one another name can have. Both forms come from ONE shared-surname map,
// so they can never disagree about who needs more than a surname. (The search fold stays in
// table.js: only search uses it.)
//
// It is a HEURISTIC -- "the last word", with SURNAME holding the names that rule is wrong about,
// which is a judgment call and not a fact. The rules and their exceptions are pinned in
// scripts/names.test.mjs; the audit behind the exception list is history, so it is in TODO.md.
// French and Dutch particles are left filing under the last word ("Fernand de La Tombelle" ->
// Tombelle) where a French index would keep them: still recognisable, and the point is to be narrow.
window.Names = (function () {
  const SUFFIXES = new Set(["junior", "jr", "jr.", "sr", "sr.", "ii", "iii", "iv"]);
  const SURNAME = {
    // Compound surnames the last-word rule splits in half.
    "Ralph Vaughan Williams": "Vaughan Williams",
    "David Vaughan Thomas": "Vaughan Thomas",
    "Peter Maxwell Davies": "Maxwell Davies",
    "Vincenza Garelli della Morea": "Garelli della Morea",
    "Tera de Marez Oyens": "de Marez Oyens",
    // Capitalised particles that are part of the name, not a nobiliary prefix to drop.
    "Alicia Van Buren": "Van Buren",
    "Nancy Van de Vate": "Van de Vate",
    // Family name FIRST: the article title is in Chinese order, so the last word is the given name.
    "Chen Yi": "Chen",
  };

  // "Haydn" is Joseph on any concert programme; the initial is what Michael needs. READERSHIP
  // decides because it is the only measure here of who a name lands on, and the MARGIN is the half
  // that has to be there: a floor alone hands the bare surname to whoever leads by one view once
  // both clear it, and readership is refetched monthly, so that is drift, not hypothesis.
  // CHART ONLY -- a bare "Haydn" filed beside "Haydn, Michael" is inconsistent about who gets a
  // forename, to save width a table has anyway.
  const DOMINANT_VIEWS = 10000, DOMINANT_MARGIN = 3;

  let names = [];
  const filedOf = new Map(), shortOf = new Map(), surOf = new Map(), viewsOf = new Map();

  // "Samuel Wesley (composer, born 1766)" -- a Wikipedia disambiguator, not part of the name.
  const bare = n => n.replace(/\s*\([^)]*\)\s*$/, "");

  function surnameOf(name) {
    if (SURNAME[name]) return SURNAME[name];
    const parts = bare(name).split(/\s+/);
    let end = parts.length - 1, suffix = "";
    if (end > 0 && SUFFIXES.has(parts[end].toLowerCase())) { suffix = " " + parts[end]; end--; }
    // Lowercase nobiliary particles are dropped, which is how English indexes file them:
    // "Ludwig van Beethoven" is under B, "Carl Ditters von Dittersdorf" under D.
    return parts[end] + suffix;
  }

  // Everything before the surname, wherever the surname sits. NOT a suffix slice off the end: the
  // family-name-first override puts the surname at the FRONT, and slicing gave "Chen Yi" a forename
  // of "Che" -- inert only while no other composer's name ends in "Chen", which is exactly what a
  // re-scrape changes.
  const forenameOf = (name, sur) => bare(name).replace(sur, "").replace(/\s+/g, " ").trim();

  // `views` is a PARALLEL array of readership medians because that is the shape the caller has: a
  // row per composer. Every lookup here is keyed by the canonical NAME, which is safe for exactly
  // one reason -- build_data.py refuses to write two rows that print the same name. If that
  // guarantee goes, this module breaks in four places, not one.
  function setData(list, views) {
    names = list.slice();
    filedOf.clear(); shortOf.clear(); surOf.clear(); viewsOf.clear();
    names.forEach((n, i) => viewsOf.set(n, (views && views[i]) || 0));
    const group = new Map();
    for (const n of names) {
      const s = surnameOf(n);
      surOf.set(n, s);
      if (!group.has(s)) group.set(s, []);
      group.get(s).push(n);
    }
    for (const [sur, members] of group) {
      // A UNIQUE surname is the whole display name in both forms: the narrowest the column can be,
      // and a one-word chart label.
      if (members.length < 2) {
        const only = members[0];
        filedOf.set(only, sur);
        shortOf.set(only, sur);
        continue;
      }
      // Shared. The table appends the forename ("Haydn, Joseph") because it sorts on this string
      // and the group has to stay adjacent. The chart keeps reading order and spends as little as
      // it can: an INITIAL where that identifies the person ("J. Haydn" against "M. Haydn"), the
      // full name only where it does not -- Ferdinand and Félicien David.
      const initial = new Map();
      for (const n of members) {
        const f = forenameOf(n, sur);
        const k = f ? f[0] : "";
        initial.set(k, (initial.get(k) || 0) + 1);
      }
      // The one member the bare surname already means, if the group has one.
      const rank = members.slice().sort((a, b) => viewsOf.get(b) - viewsOf.get(a));
      const dominant = viewsOf.get(rank[0]) >= DOMINANT_VIEWS
                    && viewsOf.get(rank[0]) >= DOMINANT_MARGIN * viewsOf.get(rank[1])
                     ? rank[0] : null;
      for (const n of members) {
        const f = forenameOf(n, sur);
        filedOf.set(n, f ? `${sur}, ${f}` : sur);
        // A family-name-first title ("Chen Yi") is already in its own order; an initial would print
        // "Y. Chen", reordering a name nobody writes that way. Fall through to the full title.
        const lead = bare(n).startsWith(sur);
        shortOf.set(n, !f ? sur
                   : n === dominant ? sur
                   : lead ? bare(n)
                   : initial.get(f[0]) === 1 ? `${f[0]}. ${sur}`
                   : bare(n));
      }
    }
  }

  return {
    setData, surnameOf,
    // "Haydn, Joseph" -- for a column that SORTS on the string it prints.
    filed: n => filedOf.get(n) || surnameOf(n),
    // "J. Haydn" -- for a label that has to fit next to the dot it names.
    short: n => shortOf.get(n) || surnameOf(n),
    surname: n => surOf.get(n) || surnameOf(n),
    // Override keys that no longer name a composer -- a pipeline rename. Asserted empty by both
    // suites.
    staleOverrides: () => Object.keys(SURNAME).filter(n => !names.includes(n)),
    // For the suite, which checks each override against the rule it overrides. Read-only by
    // convention, like Chart.colorOf.
    OVERRIDES: SURNAME,
  };
})();
