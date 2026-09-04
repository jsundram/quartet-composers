// The data table. The chart answers "what does the field look like"; this answers "what exactly
// am I looking at" — and it is the accessible, printable, Ctrl-F-able copy of the same 466 rows.
//
// It is not a second view bolted on: selection is shared both ways (click a row, the dot rings;
// click a dot, the row highlights and scrolls into view) and the search box filters BOTH — matches
// stay opaque in the chart, everything else drops to 12%.
//
// No virtualization on purpose. 466 rows is ~2,800 DOM nodes, which builds in a few milliseconds
// and — the part that matters — keeps the browser's own find-in-page working, which a windowed
// list silently breaks.

window.Table = (function () {
  // `phone: false` marks a column that is HIDDEN on a narrow screen (styles.css does the hiding
  // via the class). Six columns do not fit 390px: the composer name wraps to three lines and
  // Quartets — the one the chart is about — scrolls off the right edge. Died and Lived are the
  // two to lose, because both are one tap away in the detail panel and neither is why you came.
  const COLS = [
    { key: "name",     label: "Composer",  num: false, phone: true },
    { key: "birth",    label: "Born",      num: true,  phone: true },
    { key: "death",    label: "Died",      num: true,  phone: false },
    { key: "lifespan", label: "Lived",     num: true,  phone: false },
    { key: "quartets", label: "Quartets",  num: true,  phone: true },
    { key: "views",    label: "Views",     num: true,  phone: true },
  ];
  const fmt = new Intl.NumberFormat();

  let theadEl, tbodyEl, cbSelect;
  let rows = [], view = [], sortKey = "views", sortDir = -1, selected = null;
  let order = [];               // composer indices in the order last rendered
  const trFor = new Map();      // composer index -> its <tr>, so selection is O(1), not a rebuild

  // NFD-strip so a search for "Dvořák" finds the ASCII-scraped "Antonin Dvorak" (and vice versa).
  //
  // NFD alone is not enough. It splits a letter into base + combining accent, which handles á é ö
  // — but ł, ø, đ, ß, æ and œ are single codepoints with NO decomposition, so they survive the
  // strip untouched and "lutoslawski" fails to find "Lutosławski". That is not hypothetical here:
  // scripts/build_data.py's RENAMES put exactly those characters back into the data. Map them by
  // hand first, then NFD the rest.
  const FOLD = { "ł": "l", "ø": "o", "đ": "d", "ð": "d", "þ": "th", "ß": "ss", "æ": "ae", "œ": "oe", "ı": "i" };
  const norm = s => s.toLowerCase().replace(/[łøđðþßæœı]/g, c => FOLD[c])
                     .normalize("NFD").replace(/[\u0300-\u036f]/g, "");

  function setData(r) { rows = r; rows.forEach(d => { d.key = norm(d.name); }); }

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
      b.textContent = c.label;
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
      // A living composer has no death year. Sort those to the end in BOTH directions rather than
      // letting null compare as 0 and drag every living composer to the top of an ascending sort.
      if (k === "death") {
        if (av == null && bv == null) return a.name.localeCompare(b.name);
        if (av == null) return 1;
        if (bv == null) return -1;
      }
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
      c0.appendChild(document.createTextNode(d.name));
      tr.appendChild(c0);

      tr.appendChild(cell(d.birth, "c-birth"));
      tr.appendChild(cell(d.death == null ? "—" : d.death, "c-death wide-only"));
      // "29+" for the living: the source stores age-in-2014 in the lifespan slot, so the honest
      // reading is "at least this long", not "died at". Footnoted in the page footer.
      tr.appendChild(cell(d.living ? d.lifespan + "+" : d.lifespan, "c-lifespan wide-only"));
      tr.appendChild(cell(d.quartets, "c-quartets"));
      tr.appendChild(cell(d.views ? fmt.format(d.views) : "—", "c-views"));

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

  function select(i, scroll) {
    if (selected != null && trFor.has(selected)) trFor.get(selected).setAttribute("aria-selected", "false");
    selected = i;
    const tr = i != null ? trFor.get(i) : null;
    if (!tr) return;
    tr.setAttribute("aria-selected", "true");
    // Only when the selection came from the CHART. Scrolling the table under a user who just
    // clicked a row in it yanks the thing they are reading out from under their finger.
    if (!scroll) return;
    // Deliberately NOT scrollIntoView: even with block:"nearest" it walks up and scrolls every
    // ancestor, so picking a dot yanked the whole DOCUMENT down and pushed the chart you just
    // clicked off the screen. Scroll only the table's own overflow box. (.scroll is
    // position:relative in styles.css so offsetTop is measured against it.)
    const box = tbodyEl.closest(".scroll");
    if (!box) return;
    const want = tr.offsetTop - (box.clientHeight - tr.offsetHeight) / 2;
    box.scrollTop = Math.max(0, Math.min(want, box.scrollHeight - box.clientHeight));
  }

  function init(opts) {
    theadEl = opts.thead; tbodyEl = opts.tbody; cbSelect = opts.onSelect;
  }

  return { init, setData, render, select, matches, ordered: () => order,
           count: () => rows.length };
})();
