// Display names: one canonical Wikipedia title, two shortened forms.
//
// The table files composers by SURNAME so the name column sorts the way a reader expects (all
// three Haydns together, not filed under J, M and F). The chart labels them by surname for the
// other half of the same reason: "Wolfgang Amadeus Mozart" is ~120px of ink laid across a plot
// where "Mozart" says the same thing in 40, and the labeller is a greedy first-come placer, so
// every pixel a name does not need is a pixel another name can have.
//
// Both are the same judgment about the same 884 human names, so it lives here rather than twice.
// The search fold (norm/FOLD) stays in table.js because only search uses it; which word is the
// surname -- and which composers the rule is wrong about -- is shared.
//
// The two forms are derived from ONE shared-surname map, so the table and the chart can never
// disagree about who needs more than a surname to be identified.
//
// It is a HEURISTIC on 884 human names. The rule is "the last word", which is right about 870
// times; SURNAME holds the ones it is wrong about. That list is a judgment call, not a fact, and
// staleOverrides() reports any entry that no longer names a composer so a pipeline rename shows
// up instead of silently doing nothing.
//
// AUDITED against all 884 (2026-09-05), which is worth redoing after a re-scrape rather than
// trusting. Two classes can break the rule and both were checked exhaustively:
//   family-name-first -- only "Chen Yi". "Isang Yun", "Unsuk Chin" and "Shigeru Kan-no" carry
//     Westernised article titles, so the last word IS the family name and the rule is right.
//   compound surnames -- found by listing the penultimate word of every 3+ word name; ~80 are
//     ordinary middle names and the five below are not.
// Left deliberately alone: French and Dutch particles file under the last word here
// ("Fernand de la Tombelle" -> Tombelle, "Louise Haenel de Cronenthall" -> Cronenthall), where a
// French index would keep the particle. Both are still recognisable, and the whole point is to
// be narrow.
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

  let names = [];
  const filedOf = new Map(), shortOf = new Map(), surOf = new Map();

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
  // family-name-first override puts it at the front, so "Chen Yi" with surname "Chen" was
  // yielding a forename of "Che". Inert today only because no other composer's name ends in
  // "Chen" -- exactly the kind of thing a re-scrape changes.
  const forenameOf = (name, sur) => bare(name).replace(sur, "").replace(/\s+/g, " ").trim();

  function setData(list) {
    names = list.slice();
    filedOf.clear(); shortOf.clear(); surOf.clear();
    const group = new Map();
    for (const n of names) {
      const s = surnameOf(n);
      surOf.set(n, s);
      if (!group.has(s)) group.set(s, []);
      group.get(s).push(n);
    }
    for (const [sur, members] of group) {
      // A UNIQUE surname is the whole display name in both forms -- the column stays as narrow as
      // it can be and the chart label is one word.
      if (members.length < 2) {
        const only = members[0];
        filedOf.set(only, sur);
        shortOf.set(only, sur);
        continue;
      }
      // Shared. The table appends the forename ("Haydn, Joseph") because it sorts on this string
      // and the surnames have to stay adjacent. The chart keeps reading order and spends as little
      // as it can get away with: an INITIAL where that identifies the person ("J. Haydn" against
      // "M. Haydn"), and the full name only where it does not -- Ferdinand and Félicien David,
      // Rebecca and Rhona Clarke, John and John Luther Adams. Eight rows in 884.
      const initial = new Map();
      for (const n of members) {
        const f = forenameOf(n, sur);
        const k = f ? f[0] : "";
        initial.set(k, (initial.get(k) || 0) + 1);
      }
      for (const n of members) {
        const f = forenameOf(n, sur);
        filedOf.set(n, f ? `${sur}, ${f}` : sur);
        // A family-name-first title ("Chen Yi") is already in its own order; prefixing an initial
        // would print "Y. Chen", which reorders a name nobody writes that way. Fall through to
        // the full title instead.
        const lead = bare(n).startsWith(sur);
        shortOf.set(n, !f ? sur
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
    // Override keys that no longer name a composer -- a pipeline rename, asserted empty by the UI
    // suite so the entry cannot sit there doing nothing.
    staleOverrides: () => Object.keys(SURNAME).filter(n => !names.includes(n)),
  };
})();
