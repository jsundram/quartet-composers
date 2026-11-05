#!/usr/bin/env python3
# pwa-starter: none — this script is this repo's own
# /// script
# requires-python = ">=3.9"
# ///
"""Find the composers whose list entry disagrees with their article or with IMSLP, and pick the next.

    python3 scripts/list_discrepancies.py --scan      # fetch every article -> data/list-flags.json
    gh api 'repos/jsundram/quartet-composers/issues?labels=list-review&state=all&per_page=100' > i.json
    python3 scripts/list_discrepancies.py --issues i.json --limit 20 --out queue.json

--scan is a stage of scripts/refresh.py, because a cloud run gets rate-limited on the article fetch
and the runner does not. Picking the next batch reads that file and touches no network.

The output is evidence for a monthly agent to research, never a correction: a flag is often noise,
so nothing here changes a count, and a person posts any edit that comes of it.

A COMPOSER IS DONE ONCE RESEARCHED, whatever anybody does next. The record is the marker each
monthly issue carries, read from open and closed issues alike, so an ignored issue cannot bring its
composers back and nothing has to be merged or ticked. Only a change to the entry's text does.
"""
import argparse
import hashlib
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import scrape_list as sl                                # noqa: E402

ROOT = os.path.dirname(HERE)
FLAGS = os.path.join(ROOT, "data", "list-flags.json")
WP = "https://en.wikipedia.org/wiki/"
LIST_TITLE = "List_of_string_quartet_composers"
EDIT = "https://en.wikipedia.org/w/index.php?title=%s&action=edit"

NOUN = r"(?:string quartets|quartets for strings)"
ADJ = (r"(?:(?:published|unpublished|surviving|complete|completed|numbered|unnumbered|extant|known|"
       r"mature|full|acknowledged|official|major|early)\s+){0,2}")
STATED = re.compile(r"\b(%s|\d{1,3})\s+%s%s\b" % (sl.NUMWORD, ADJ, NOUN), re.I)
# "the first six string quartets" counts a part of the output, not all of it.
PART_OF = re.compile(r"\b(?:first|last|next|final|middle|late|later|early|earlier|remaining|another|"
                     r"more|further|additional|other|these|those|with|op|opus|the)\s+$", re.I)
NUMBERED = re.compile(r"(?<!Piano )(?<!Flute )(?<!Oboe )(?<!Clarinet )(?<!Horn )(?<!Guitar )"
                      r"\b(?:String\s+)?Quartet\s+No\.?\s*(\d{1,3})\b", re.I)
# An article about anybody may discuss these quartets, so their numbers are not its subject's.
CANON = re.compile(r"\b(?:Beethoven|Haydn|Mozart|Schubert|Bart[oó]k|Shostakovich|Brahms|Dvo[rř][aá]k|"
                   r"Mendelssohn|Schumann|Borodin|Debussy|Ravel)\b")
MARKER = re.compile(r"<!--\s*list-review\s+(\{.*?\})\s*-->", re.S)
ARTICLE_FLAGS = ("no count on list", "article states more", "article numbers higher",
                 "article states fewer")


def plain(wikitext):
    t = re.split(r"\n==+\s*(?:References|Notes|External links|Further reading|Sources|See also|"
                 r"Bibliography|Citations)\s*==+", wikitext)[0]
    t = re.sub(r"<ref[^>]*/>", "", t)
    t = re.sub(r"<ref.*?</ref>", "", t, flags=re.S)
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    for _ in range(4):                  # templates nest, and a regex cannot count
        t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"\[\[(?:File|Image|Category):[^\]]*\]\]", "", t)
    t = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"\[\[([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"'{2,}", "", t)
    return re.sub(r"<[^>]+>", "", t)


def sentences(text):
    t = re.sub(r"\b(Op|Opp|No|Nos|c|ca|St|Dr|Mr|Mrs)\.\s", r"\1~ ", text)
    return [s.replace("~", ".").strip() for s in re.split(r"(?<=[.!?])\s+|\n+", t) if s.strip()]


def clip(s, at, width=120):
    a, b = max(0, at - width), min(len(s), at + width)
    return ("…" if a else "") + s[a:b].strip() + ("…" if b < len(s) else "")


def evidence(name, wikitext):
    """-> (counts the article states, numbers it reaches), each [(value, quote, phrase)]."""
    surname = name.split()[-1]
    stated, numbered = [], []
    for s in sentences(plain(wikitext)):
        if CANON.search(s) and surname not in s:
            continue
        if re.search(r"\b\w+'s\s+String Quartet", s) and surname + "'s" not in s:
            continue
        for m in STATED.finditer(s):
            v = sl.to_int(m.group(1))
            if v is None or not 2 <= v <= 200 or PART_OF.search(s[:m.start()]):
                continue
            if re.match(r"\s*,?\s*(?:Op|Opp)\b", s[m.end():m.end() + 14], re.I):
                continue                # "three string quartets, Op. 1" is one set
            stated.append((v, clip(s, m.start()), m.group(0)))
        for m in NUMBERED.finditer(s):
            numbered.append((int(m.group(1)), clip(s, m.start()), m.group(0)))
    return stated, numbered


def flags_for(listed, imslp, stated, numbered):
    vals = sorted({v for v, _, _ in stated})
    top = vals[-1] if vals else None
    high = max((v for v, _, _ in numbered), default=None)
    if listed is None:
        return ["no count on list"] if top or high else []
    out = []
    if top and top > listed:
        out.append("article states more")
    if high and high > listed:
        out.append("article numbers higher")
    if len(vals) == 1 and top < listed:
        out.append("article states fewer")
    if imslp >= listed + 2:     # works, so a set paged twice inflates it: one extra proves nothing
        out.append("IMSLP has more")
    return out


def entry_hash(text):
    return hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:12]


def seen_in(issues):
    """{composer: entry hash when researched}, the newest issue winning."""
    seen = {}
    for issue in sorted(issues, key=lambda i: i.get("number", 0)):
        for m in MARKER.finditer(issue.get("body") or ""):
            seen.update(json.loads(m.group(1)))
    return seen


def marker(batch):
    return "<!-- list-review %s -->" % json.dumps(
        {b["composer"]: b["entry_hash"] for b in batch}, ensure_ascii=False)


def fragment(text):
    return "#:~:text=" + urllib.parse.quote(text, safe="").replace("-", "%2D")


def page_url(title):
    return WP + urllib.parse.quote(title.replace(" ", "_"), safe="(),'")


def entries(wikitext):
    """{list title: (raw line, its display label, the list section an edit link opens)}"""
    out, section = {}, 0
    for line in wikitext.split("\n"):
        if re.match(r"^==+[^=].*==+\s*$", line):
            section += 1
        m = sl.LINK.match(line) if line.startswith("*[[") else None
        if m:
            title = m.group(1).strip()
            out[title] = (line, (m.group(2) or re.sub(r" \(.*\)$", "", title)).strip(), section)
    return out


def fetch_articles(titles):
    """{title: wikitext} from the API, retrying what a dropped connection costs."""
    out = {}
    for i in range(0, len(titles), 40):
        batch, cont = titles[i:i + 40], {}
        while True:
            q = {"action": "query", "format": "json", "formatversion": 2, "prop": "revisions",
                 "rvprop": "content", "rvslots": "main", "titles": "|".join(batch)}
            req = urllib.request.Request(sl.API + "?" + urllib.parse.urlencode({**q, **cont}),
                                         headers={"User-Agent": sl.UA})
            for attempt in range(5):
                try:
                    with urllib.request.urlopen(req, timeout=90) as r:
                        d = json.load(r)
                    break
                except (OSError, http.client.HTTPException, ValueError):
                    if attempt == 4:
                        raise
                    time.sleep(2 ** attempt)
            for p in d["query"]["pages"]:
                if p.get("revisions"):
                    out[p["title"]] = p["revisions"][0]["slots"]["main"]["content"]
            cont = d.get("continue")
            if not cont:
                break
    return out


def scan(articles):
    """Every flagged composer on the shipped roster, whoever has already looked at them."""
    def load(*path):
        with open(os.path.join(ROOT, *path), encoding="utf-8") as f:
            return json.load(f)
    with open(sl.CACHE, encoding="utf-8") as f:
        wiki = entries(f.read())
    people = load("data", "people.json")
    shipped = load("composers.json")
    f = shipped["fields"]
    rows = {r[f.index("name")]: dict(zip(f, r)) for r in shipped["rows"]}
    flagged = []
    for e in load("data", "list.json")["entries"]:
        canonical = people[e["title"]]["canonical"]
        name = re.sub(r" \(.*\)$", "", canonical)
        row = rows.get(name)
        if row is None or e["title"] not in wiki:
            continue
        line, label, section = wiki[e["title"]]
        stated, numbered = evidence(name, articles.get(canonical, ""))
        imslp = row["imslp"] or 0
        flags = flags_for(row["quartets"], imslp, stated, numbered)
        if not flags:
            continue
        cat = row["imslp_cat"]
        flagged.append({
            "composer": name, "birth": row["birth"], "list_count": row["quartets"],
            "flags": flags, "entry_hash": entry_hash(sl.clean(line)), "list_wikitext": line,
            "list_url": WP + LIST_TITLE + fragment(label),
            "list_edit_url": EDIT % LIST_TITLE + "&section=%d" % section,
            "article_url": page_url(canonical),
            "article_edit_url": EDIT % urllib.parse.quote(canonical.replace(" ", "_"), safe="(),'"),
            "article_says": [{"value": v, "quote": q, "url": page_url(canonical) + fragment(p)}
                             for v, q, p in {t[0]: t for t in reversed(stated + numbered)}.values()],
            "imslp": imslp,
            "imslp_url": None if cat is None else "https://imslp.org/wiki/" + urllib.parse.quote(
                ("Category:" + (cat or name.split()[-1] + ", " + " ".join(name.split()[:-1])))
                .replace(" ", "_"), safe=",_:()'"),
        })
    return flagged


def next_batch(flagged, seen, limit):
    """-> (the next `limit` composers nobody has researched, how many more), article flags first."""
    todo = [b for b in flagged if seen.get(b["composer"]) != b["entry_hash"]]
    todo.sort(key=lambda b: (not set(b["flags"]) & set(ARTICLE_FLAGS), b["birth"]))
    return todo[:limit], len(todo[limit:])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scan", action="store_true", help="fetch the articles and rewrite the flags")
    ap.add_argument("--articles", help="with --scan, a {title: wikitext} file to read instead")
    ap.add_argument("--issues", help="the REST issue list; omit to treat everybody as new")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--out", help="where the next batch goes")
    args = ap.parse_args()
    if args.scan:
        if args.articles:
            with open(args.articles, encoding="utf-8") as f:
                articles = json.load(f)
        else:
            with open(os.path.join(ROOT, "data", "people.json"), encoding="utf-8") as f:
                articles = fetch_articles(sorted({p["canonical"] for p in json.load(f).values()}))
        flagged = scan(articles)
        with open(FLAGS, "w", encoding="utf-8") as f:
            json.dump(flagged, f, ensure_ascii=False, indent=1)
        print("%d composers flagged -> data/list-flags.json" % len(flagged))
        return 0
    if not args.out:
        ap.error("--out is required unless --scan")
    seen = {}
    if args.issues:
        with open(args.issues, encoding="utf-8") as f:
            seen = seen_in(json.load(f))
    with open(FLAGS, encoding="utf-8") as f:
        batch, waiting = next_batch(json.load(f), seen, args.limit)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"marker": marker(batch), "waiting_after_this": waiting, "composers": batch},
                  f, ensure_ascii=False, indent=1)
    print("%d composers to research, %d more waiting" % (len(batch), waiting))
    return 0


if __name__ == "__main__":
    sys.exit(main())
