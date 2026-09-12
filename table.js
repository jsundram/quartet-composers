// The data table. The chart answers "what does the field look like"; this answers "what exactly
// am I looking at" — and it is the accessible, printable, Ctrl-F-able copy of the same rows.
//
// It is not a second view bolted on: selection is shared both ways (click a row, the dot rings;
// click a dot, the row highlights and scrolls into view) and the search box filters BOTH — matches
// stay opaque in the chart, everything else drops to 12%.
//
// No virtualization on purpose: the whole roster builds in a few milliseconds, and — the part that
// matters — a windowed list silently breaks the browser's own find-in-page.

window.Table = (function () {
  // `phone: false` marks a column that is HIDDEN on a narrow screen (styles.css does the hiding
  // via the class). Six columns do not fit 390px: the composer name wraps to three lines and
  // Quartets — the one the chart is about — scrolls off the right edge. Died and Lived are the
  // two to lose, because both are one tap away in the detail panel and neither is why you came.
  //
  // `short` is the phone HEADER, asked for by the column's WIDTH and not its meaning: a header word
  // sets the column when it is wider than any value under it, and "Quartets" over three digits was
  // buying ~30px it never used. In no measured face did the phone columns fit 360px before that went.
  // styles.css swaps which span is drawn; the accessible name keeps both, for the reason below.
  const COLS = [
    { key: "name",     label: "Composer",  num: false, phone: true },
    { key: "birth",    label: "Born",      num: true,  phone: true },
    { key: "death",    label: "Died",      num: true,  phone: false },
    { key: "lifespan", label: "Lived",     num: true,  phone: false },
    { key: "quartets", label: "Quartets",  num: true,  phone: true, short: "Qts" },
    { key: "views",    label: "Views",     num: true,  phone: true },
  ];
  const fmt = new Intl.NumberFormat();
  const THIS_YEAR = new Date().getFullYear();
  // Age today for someone with no death date. Read off the clock rather than baked at build time,
  // so a cached copy opened next year still shows the right number.
  const age = d => THIS_YEAR - d.birth;

  let theadEl, tbodyEl, cbSelect;
  let rows = [], view = [], sortKey = "views", sortDir = -1, selected = null;
  let order = [];               // composer indices in the order last rendered
  const trFor = new Map();      // composer index -> its <tr>, so selection is O(1), not a rebuild

  // NFD-strip so a search for "Dvořák" finds the ASCII-scraped "Antonin Dvorak" (and vice versa).
  //
  // NFD alone is not enough: it splits a letter into base + combining accent, which handles á é ö, but
  // ł, ø and the rest below are single codepoints with NO decomposition, so they survive the strip and
  // "lutoslawski" fails to find "Lutosławski". Hand map FIRST, then NFD the rest. Not every entry has
  // a name in today's roster — the map is the rule for the scrape, not a census of it (invariant 13).
  const FOLD = { "ł": "l", "ø": "o", "đ": "d", "ð": "d", "þ": "th", "ß": "ss", "æ": "ae", "œ": "oe", "ı": "i" };
  const norm = s => s.toLowerCase().replace(/[łøđðþßæœı]/g, c => FOLD[c])
                     .normalize("NFD").replace(/[\u0300-\u036f]/g, "");

  // ---- display names --------------------------------------------------------
  // names.js owns the rule, and serves the chart from the same map, so the two cannot drift apart
  // about who needs a forename.

  function setData(r) {
    rows = r;
    rows.forEach(d => {
      d.key = norm(d.name);
      d.display = Names.filed(d.name);
    });
  }

  function matches(q) {
    const t = norm(q.trim());
    if (!t) return null;                                   // null = "everything", no filtering
    const terms = t.split(/\s+/);
    const set = new Set();
    for (const d of rows) if (terms.every(w => d.key.includes(w))) set.add(d.i);
    return set;
  }

  function header() {
    theadEl.innerHTML = "";
    for (const c of COLS) {
      const th = document.createElement("th");
      th.className = (c.num ? "num " : "") + "c-" + c.key + (c.phone ? "" : " wide-only");
      if (sortKey === c.key) th.setAttribute("aria-sort", sortDir === 1 ? "ascending" : "descending");
      const b = document.createElement("button");
      b.type = "button";
      if (c.short) {
        // Two spans rather than one swapped string, and the DRAWN one FIRST so it leads the accessible
        // name (WCAG 2.5.3, which CLAUDE.md argues). On a wide screen the abbreviation is display:none
        // and drops out of the name entirely, which is why neither span may become an aria-label.
        const abbr = document.createElement("span");
        abbr.className = "th-short";
        abbr.textContent = c.short;
        const full = document.createElement("span");
        full.className = "th-full";
        full.textContent = c.label;
        b.append(abbr, full);
      } else {
        b.textContent = c.label;
      }
      // Numbers want largest-first on the first click; names want A-Z. Getting this backwards
      // makes every numeric column open on the least interesting end of the data.
      b.onclick = () => {
        if (sortKey === c.key) sortDir = -sortDir;
        else { sortKey = c.key; sortDir = c.num ? -1 : 1; }
        render();
      };
      th.appendChild(b);
      theadEl.appendChild(th);
    }
  }

  function sorted(list) {
    const k = sortKey;
    return list.slice().sort((a, b) => {
      let av = a[k], bv = b[k];
      // `lifespan` is null for the living, but their AGE is the meaningful sort key and is never
      // null, so substitute it rather than banishing them to the end of the column.
      if (k === "lifespan") { av = av == null ? age(a) : av; bv = bv == null ? age(b) : bv; }
      // Everything else sorts nulls to the end in BOTH directions, rather than letting null
      // compare as 0 and drag every living composer (no death year) or unparsed row (no quartet
      // count) to the top of an ascending sort.
      if (av == null || bv == null) {
        if (av == null && bv == null) return a.name.localeCompare(b.name);
        return av == null ? 1 : -1;
      }
      // Sorting the NAME column sorts what is on screen -- surname first, forename only as a
      // tie-break. Sorting by the full title put Joseph Haydn under J.
      if (k === "name") return sortDir * a.display.localeCompare(b.display);
      if (typeof av === "string") return sortDir * av.localeCompare(bv);
      return sortDir * (av - bv) || a.name.localeCompare(b.name);
    });
  }

  function render(visible) {
    if (visible !== undefined) view = visible;
    header();
    const list = sorted(view ? rows.filter(d => view.has(d.i)) : rows);
    order = list.map(d => d.i);
    trFor.clear();
    const frag = document.createDocumentFragment();

    if (!list.length) {
      const tr = document.createElement("tr");
      tr.className = "empty-row";
      const td = document.createElement("td");
      td.colSpan = COLS.length;   // the hidden-on-phone columns still count for the span
      td.textContent = "No composer matches that search.";
      tr.appendChild(td);
      frag.appendChild(tr);
    }

    for (const d of list) {
      const tr = document.createElement("tr");
      tr.tabIndex = 0;
      tr.setAttribute("aria-selected", d.i === selected ? "true" : "false");
      tr.onclick = () => cbSelect && cbSelect(d.i);
      tr.onkeydown = ev => {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); cbSelect && cbSelect(d.i); }
      };

      const c0 = document.createElement("td");
      c0.className = "c-name";
      const chip = document.createElement("span");
      chip.className = "chip";
      // The chip repeats the dot's color so a row and its dot are recognizably the same thing.
      // It is decoration only — the Lived column carries the same fact as a number, so nothing
      // here is encoded in color alone.
      chip.style.background = d.living ? "transparent" : Chart.colorOf(d);
      chip.style.boxShadow = d.living ? "inset 0 0 0 1.4px " + Chart.colorOf(d) : "none";
      c0.appendChild(chip);
      c0.appendChild(document.createTextNode(d.display));
      // The canonical title stays reachable as the cell's tooltip.
      c0.title = d.name;
      tr.appendChild(c0);

      tr.appendChild(cell(d.birth, "c-birth"));
      tr.appendChild(cell(d.death == null ? "—" : d.death, "c-death wide-only"));
      // For the living, "83+" is their age today and a true lower bound on the lifespan; for the
      // dead it is the lifespan. Both are numbers you can sort, which is why they share a column.
      tr.appendChild(cell(d.lifespan == null ? age(d) + "+" : d.lifespan, "c-lifespan wide-only"));
      tr.appendChild(cell(d.quartets == null ? "—" : d.quartets, "c-quartets"));
      tr.appendChild(cell(d.views == null ? "—" : fmt.format(d.views), "c-views"));

      trFor.set(d.i, tr);
      frag.appendChild(tr);
    }
    tbodyEl.innerHTML = "";
    tbodyEl.appendChild(frag);
    return list.length;
  }

  function cell(v, cls) {
    const td = document.createElement("td");
    td.className = "num " + cls;
    td.textContent = v;
    return td;
  }

  // Just the chips: called when the CHART's encoding changes (Chart.colorOf follows the view), so
  // the rows, the scroll position and the focused element all survive a view switch.
  function repaintChips() {
    for (const [i, tr] of trFor) {
      const d = rows[i], chip = tr.querySelector(".chip");
      if (!chip) continue;
      chip.style.background = d.living ? "transparent" : Chart.colorOf(d);
      chip.style.boxShadow = d.living ? "inset 0 0 0 1.4px " + Chart.colorOf(d) : "none";
    }
  }

  function select(i, scroll) {
    if (selected != null && trFor.has(selected)) trFor.get(selected).setAttribute("aria-selected", "false");
    selected = i;
    const tr = i != null ? trFor.get(i) : null;
    if (!tr) return;
    tr.setAttribute("aria-selected", "true");
    // Only when the selection came from the CHART. Scrolling the table under a user who just
    // clicked a row in it yanks the thing they are reading out from under their finger.
    if (!scroll) return;
    // Deliberately NOT scrollIntoView: even with block:"nearest" it walks up and scrolls every ancestor,
    // so picking a dot pushed the chart you just clicked off the screen. Only the table's own overflow
    // box. (.scroll is position:relative in styles.css, so offsetTop is measured against it.)
    const box = tbodyEl.closest(".scroll");
    if (!box) return;
    const want = tr.offsetTop - (box.clientHeight - tr.offsetHeight) / 2;
    box.scrollTop = Math.max(0, Math.min(want, box.scrollHeight - box.clientHeight));
  }

  function init(opts) {
    theadEl = opts.thead; tbodyEl = opts.tbody; cbSelect = opts.onSelect;
  }

  return { init, setData, render, repaintChips, select, matches, ordered: () => order };
})();
