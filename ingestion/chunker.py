"""Split a Docling-parsed RBI document into one chunk per numbered paragraph.

Reads data/parsed/<name>.json (Docling export_to_dict) and writes
data/chunks/<name>.jsonl. Works from Docling item labels and page numbers,
plus text patterns that are common to RBI directions and circulars.

Usage:
    python ingestion/chunker.py                      # every JSON in data/parsed
    python ingestion/chunker.py nbfc_kyc_md_2025.pdf # one document
"""
import csv
import html
import json
import re
import sys
from pathlib import Path

PARSED_DIR = Path("data/parsed")
CHUNK_DIR = Path("data/chunks")
METADATA_CSV = Path("data/metadata.csv")

# BGE embeds at most 512 tokens (~2,000 chars of RBI English); embed_and_load adds a
# heading line, so chunk text stays well under that
MAX_CHARS = 1800
MIN_ROOM = 600  # when a big clause must be split, start it in the current part if this much space is left

# ---------- patterns ----------

ROMAN = r"[IVXL]+"
CHAPTER_RE = re.compile(
    rf"^(?i:chapter)\s*[-–]?\s*({ROMAN}|\d+)\b(?!\s+(?:of|to|in|and|under|as|shall|is|read|above|below)\b)\s*[-–:]?\s*(.*)$")
# a chapter heading glued to the end of the previous item, after a sentence end
INLINE_CHAPTER_RE = re.compile(rf"(?<=[.;:])\s+(?=(?i:chapter)\s*[-–]?\s*(?:{ROMAN}|\d+)\b\s*[-–:])")
SECTION_RE = re.compile(r"^(?:([A-H])\.\s+(\S.*)|Part\s*[-–]?\s*([IVX]+|[A-Z]|\d+)\b\s*[-–:]?\s*(.*))$")
SUBSECTION_RE = re.compile(r"^([A-H])\.\d+(?:\.\d+)*\s+[A-Z]\S*")  # "B.1 Phases of Projects", "H.4 Guidelines ..."
ANNEX_START_RE = re.compile(rf"^(?:Annex(?:ure)?|Appendix)\s*[-–:]?\s*({ROMAN}|\d+|[A-Z])\b")
ANNEX_END_RE = re.compile(rf"\b(?:Annex(?:ure)?|Appendix)\s*[-–:]?\s*({ROMAN}|\d+)\s*$")
# words that make "... Annex II" a sentence reference rather than a heading
ANNEX_REF_WORD_RE = re.compile(
    r"\b(?:in|see|to|of|per|under|with|vide|at|and|or|the|refer|given|placed|annexed|enclosed|is|are)\s*$", re.I)


def annex_at_end(text):
    """An Annex heading glued to the end of a short line ("Chief General Manager Annex - I").
    A sentence that merely mentions an annex ("See Annex II", "... given in Annex II.")
    does not start one: the heading must be the last thing in the line (no full stop) and
    the words before it must not end with a preposition or verb."""
    if len(text) >= 150:
        return None
    m = ANNEX_END_RE.search(text)
    if not m or ANNEX_REF_WORD_RE.search(text[:m.start()]):
        return None
    return m
# "12." / "11A." at the start of an item (not "3.1", not a quoted "51A.")
# (a bare "3." item also counts: Docling sometimes puts the number in its own item)
# FAQ pages number questions "Q 8." / "Q.8." - treated the same as paragraph "8."
PARA_RE = re.compile(r"^(?:Q\.?\s*)?(\d{1,3})([A-Z])?\.(?:\s+(?=\S)|(?=[A-Z][a-z])|$)")  # also "4.These"
# a paragraph number hidden inside an item, right after a sentence end
# (may follow a sentence end or a run-in heading, and may be followed by a flattened footnote number)
INLINE_PARA_RE = re.compile(r"(?<=[.;:a-z])\s+(\d{1,3})\.\s+(?=(?:\d{1,3}\s+)?[A-Z])")
CROSS_REF_RE = re.compile(r"(?:para(?:graph)?|section|rule|clause|chapter|annex|item|no)\.?\s*$", re.I)
# start of a sub-clause: (1)  (i)  (a)  a)  i.  3.1
SUBCLAUSE_RE = re.compile(r"^(?:\(\s*(?:\d{1,2}|[ivxl]+|[a-z])\s*\)|(?:\d{1,2}|[ivxl]+|[a-z])\)|[ivxl]+\.|\d+\.\d+\.?)\s")
INLINE_SUBCLAUSE_RE = re.compile(r"(?<=[.;:])\s+(?=\((?:\d{1,2}|[ivxl]+|[a-z])\)\s)")
FOOTNOTE_RE = re.compile(
    r"^(\d{1,3})\s*((?:Inserted|Substituted|Amended|Deleted|Added|Omitted)\b.*"
    r"(?:with effect from|w\.e\.f\.?|vide).*)$", re.I | re.S)
# footnote marker: "[1Explanation" / "[ 1 Explanation", or a flattened superscript "(c) 2 The ..." / "31. 93 For ..."
FOOTNOTE_MARK_RE = r"(?:\[\s*{n}\s*|(?:^|(?<=\)\s)|(?<=\.\s)){n}\s+)(?=[A-Z(‘'\"\[])"  # "31. 3 [*****]" too

SIGNATURE_RE = re.compile(r"^\((?:[A-Z][A-Za-z.]*\s*){1,6}\)(?:\s|$)")
SKIP_BLOCK_RE = re.compile(r"^(?:Copy (?:for information )?to\b|To,?$|Encl(?:osure)?s?\b)", re.I)
TOC_HEADER_RE = re.compile(r"^(?:Table of Contents|Contents|Index)$", re.I)
# TOC line: dot leader then a page number (Docling may merge several TOC lines into one item)
DOT_LEADER_RE = re.compile(r"\.{8,}\s*\d{1,3}\b|\.{5,}\s*\d*\s*$")
MASTHEAD_RE = re.compile(
    r"^(?:RESERVE BANK OF INDIA|RBI/|[A-Z]+\.[A-Z.]+(?:No\.)?\s*\d|www\.|https?://|Tel|Fax|E-?mail|"
    r"(?:All|The)\s.*(?:NBFCs?|Banks?|Entities)\s*$|Madam|Dear Sir|"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}$)",
    re.I)
PREAMBLE_HEADER_RE = re.compile(r"^(?:Introduction|Preamble|Background)\b", re.I)
# closing lines with no rule in them ("All concerned are requested to ensure strict compliance ...")
BOILERPLATE_RE = re.compile(
    r"requested to (?:ensure|note)\b|ensure strict compliance|strict compliance of this|"
    r"acknowledge (?:the )?receipt|yours faithfully|"
    r"for (?:your )?information and (?:necessary|appropriate) action", re.I)
BOILERPLATE_MAX_CHARS = 300
# lists of repealed / referenced circulars: rows with a circular reference number
# ("03.10.42/2012-13", "RBI/2019-20/258") or numbered table rows ending in a date
CIRCULAR_REF_RE = re.compile(r"\d{2}\.\d{2}\.\d{2,3}/\d{4}-\d{2}|RBI/\d{4}-\d{2}/\d+")
CIRCULAR_ROW_RE = re.compile(
    r"^\s*\d{1,3}\.\s*\|.*\|\s*(?:[A-Z][a-z]+\s+\d{1,2}\s*,\s*\d{4}|\d{2}\.\d{2}\.\d{4})\b")
CIRCULAR_LIST_SHARE = 0.5


def is_circular_list(text):
    """True when most lines of a chunk are rows of a circular list (no rules, only references)."""
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("[")]
    rows = sum(bool(CIRCULAR_REF_RE.search(ln) or CIRCULAR_ROW_RE.match(ln)) for ln in lines)
    return len(lines) >= 3 and rows / len(lines) >= CIRCULAR_LIST_SHARE
# placeholder left where RBI deleted a paragraph: "15. Deleted", "42. [Deleted]", "31. [*****]"
DELETED_RE = re.compile(r"^(?:\d{1,3}[A-Z]?\.\s*)?(?:\d{1,3}\s*)?\[?\s*(?:Deleted|\*+)\s*\]?\.?\s*(?:\d{1,3})?$", re.I)


# ---------- text cleaning ----------

def clean(text):
    text = html.unescape(text)
    text = re.sub(r"\[([^\]]+)\]\((?:https?://|www\.)[^)]*\)", r"\1", text)  # Markdown links -> text
    text = text.replace("\\_", "_")
    text = re.sub(r"\b(\d{1,2})\s+(st|nd|rd|th)\b", r"\1\2", text)          # 2 nd -> 2nd
    text = re.sub(r"(\w)-\s+(?!(?:and|or|to)\b)(\w)", r"\1-\2", text)       # sub- rule -> sub-rule
    text = re.sub(r"\bMoneyLaundering\b", "Money-Laundering", text)
    text = re.sub(r"\bAnti(?=[A-Z][a-z])", "Anti-", text)                   # AntiMoney -> Anti-Money
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# ---------- reading the Docling document ----------

def iter_items(doc):
    """Yield body items in reading order as flat dicts. Pictures (and the
    watermark text Docling finds inside them) and furniture are dropped."""
    def resolve(ref):
        _, kind, idx = ref.split("/")
        return doc[kind][int(idx)]

    def page_of(item):
        return item["prov"][0]["page_no"] if item.get("prov") else None

    def top_of(item):
        """Distance of the item's top edge from the top of its page (None if unknown)."""
        if not item.get("prov"):
            return None
        prov = item["prov"][0]
        box = prov.get("bbox") or {}
        if "t" not in box:
            return None
        if box.get("coord_origin", "BOTTOMLEFT") == "TOPLEFT":
            return box["t"]
        height = doc.get("pages", {}).get(str(prov["page_no"]), {}).get("size", {}).get("height")
        return height - box["t"] if height else None

    def walk(node, in_picture=False):
        for child in node.get("children", []):
            item = resolve(child["$ref"])
            ref = item["self_ref"]
            if item.get("content_layer", "body") != "body":
                continue
            if ref.startswith("#/pictures"):
                # Docling sometimes puts real text (a chapter heading, footnotes) inside a
                # picture region; keep it, flagged, and let prepare_items drop logo text
                yield from walk(item, in_picture=True)
                continue
            if ref.startswith("#/groups"):
                if item.get("label") == "inline":
                    parts = [resolve(c["$ref"]) for c in item.get("children", [])]
                    texts = [p.get("text", "") for p in parts if p.get("text")]
                    if texts:
                        first = parts[0]
                        yield {"label": first.get("label", "text"), "text": " ".join(texts),
                               "page": page_of(first), "top": top_of(first), "marker": "",
                               "in_picture": in_picture}
                else:
                    yield from walk(item, in_picture)
                continue
            if ref.startswith("#/tables"):
                yield {"label": item["label"], "text": table_to_text(item), "page": page_of(item),
                       "top": top_of(item), "marker": "", "in_picture": in_picture}
                continue
            marker = item.get("marker") or ""
            if marker in ("·", "•", "-", "–", "*"):
                marker = "•"
            yield {"label": item["label"], "text": item.get("text", ""), "page": page_of(item),
                   "top": top_of(item), "marker": marker, "in_picture": in_picture}
            yield from walk(item, in_picture)

    yield from walk(doc["body"])


def prepare_items(doc):
    """iter_items plus layout repairs:
    - drop logo / stamp text repeated across pages ("BANK", "IGNI", "Withdrawn"),
      and strip a stamp word glued to the end of other items;
    - keep text found inside picture regions only when it is structural (a chapter or
      annex heading, a footnote, a chapter title after a bare heading) or long;
    - a chapter or Annex heading printed at the top of a page but read after the page's content
      is moved back in front of that content."""
    items = list(iter_items(doc))
    n_pages = len({it["page"] for it in items if it["page"] is not None}) or 1

    def short_words(text):
        return len(text) <= 25 and re.fullmatch(r"[A-Za-z]+(?: [A-Za-z]+){0,2}", text)

    # repeated short text: standalone on >= 15% of pages -> drop those items;
    # also glued to item ends on >= 50% of pages -> strip it from item ends too
    candidates = {it["text"].strip() for it in items if short_words(it["text"].strip())}
    repeated, stamps = set(), set()
    for w in candidates:
        alone = {it["page"] for it in items if it["text"].strip() == w}
        glued = {it["page"] for it in items if it["text"].rstrip().endswith(" " + w)}
        if len(alone) >= max(3, 0.15 * n_pages):
            repeated.add(w)
        if len(alone | glued) >= max(3, n_pages / 2):
            repeated.add(w)
            stamps.add(w)
    tail = re.compile(r"\s+(?:" + "|".join(map(re.escape, stamps)) + r")\s*$") if stamps else None

    kept = []
    for it in items:
        text = it["text"].strip()
        if text in repeated:
            continue
        if tail:
            it["text"] = tail.sub("", it["text"])
        if it.get("in_picture"):
            prev_bare_chapter = bool(kept) and bool(re.fullmatch(rf"(?i:chapter)\s*[-–]?\s*{ROMAN}", kept[-1]["text"].strip()))
            structural = (CHAPTER_RE.match(text) or ANNEX_START_RE.match(text)
                          or FOOTNOTE_RE.match(text) or re.fullmatch(r"\d{1,3}\s*\[\*+\]", text))
            if not (structural or prev_bare_chapter or len(text) >= 40):
                continue
        kept.append(it)
    items = kept

    # chapter or annex heading below its content in reading order but above it on the page
    i = 0
    while i < len(items):
        it = items[i]
        text = clean(it["text"])
        if ((ANNEX_START_RE.match(text) and len(text) < 150) or (CHAPTER_RE.match(text) and len(text) < 250)) \
                and it["top"] is not None:
            j = i
            while j > 0 and items[j - 1]["page"] == it["page"]:
                j -= 1
            before = items[j:i]
            if before and all(b["top"] is not None and b["top"] > it["top"] for b in before):
                items.insert(j, items.pop(i))
        i += 1
    return items


def table_to_text(table):
    rows = []
    for row in table.get("data", {}).get("grid", []):
        cells = [c.get("text", "").strip() for c in row]
        rows.append(" | ".join(cells))
    return "\n".join(rows)


# ---------- chunking ----------

class Paragraph:
    def __init__(self, region, chapter, section, para, header_title=None):
        self.region = region
        self.chapter = chapter
        self.section = section
        self.para = para                  # "12", "11A" or None for preamble text
        self.header_title = header_title  # heading text when the paragraph started as a heading
        self.lines = []                   # [text, set of pages]
        self.notes = []

    def add(self, text, page, as_new_line=False):
        if not text:
            return
        pages = {page} if page is not None else set()
        if (self.lines and not as_new_line
                and not re.search(r"[.:;!?)\]\"'’”]$", self.lines[-1][0])
                and not SUBCLAUSE_RE.match(text) and not text.startswith("•")):
            self.lines[-1][0] += " " + text  # sentence continues (page break or line-wise item)
            self.lines[-1][1] |= pages
        else:
            self.lines.append([text, pages])

    @property
    def pages(self):
        return sorted(set().union(*(p for _, p in self.lines))) if self.lines else []

    @property
    def text(self):
        return "\n".join(t for t, _ in self.lines).strip()


def para_title(p):
    first = re.sub(r"^(?:Q\.?\s*)?\d{1,3}[A-Z]?\.\s*", "", p.lines[0][0]) if p.lines else ""
    if not first and len(p.lines) > 1:
        first = p.lines[1][0]  # the number was a bare "4." item; the text starts on the next line
    colon = first.find(":")
    if 0 < colon <= 150:
        return first[:colon].strip(" -–")
    if p.header_title:
        return p.header_title
    if len(first) <= 100:
        return first.rstrip(".")
    return first[:100].rsplit(" ", 1)[0] + "…"


def marker_kind(text, last_letter):
    """Kind of clause marker a line starts with: decimal 3.1, num (1), roman (i), letter (a), bullet."""
    if re.match(r"^\d+\.\d+\.?\s", text):
        return "decimal"
    if re.match(r"^(?:\(\d{1,2}\)|\d{1,2}\))\s", text):
        return "num"
    m = re.match(r"^(?:\(([a-z]+)\)|([a-z]+)[.)])\s", text)
    if m:
        s = m.group(1) or m.group(2)
        # "(i)" right after "(h)" is a letter, not a roman numeral
        if re.fullmatch(r"[ivxl]+", s) and not (len(s) == 1 and last_letter and ord(s) == ord(last_letter) + 1):
            return "roman"
        return "letter" if len(s) == 1 else None
    if text.startswith("•"):
        return "bullet"
    return None


def clause_levels(texts):
    """Nesting level per line (None for unmarked lines). Levels follow the order in
    which marker kinds first appear, so (1) > (i) > (a) and a) > i. both work.
    Decimal sub-paragraphs (5.1, 5.2) are always the top level."""
    order, levels, last_letter = [], [], None
    for text in texts:
        kind = marker_kind(text, last_letter)
        if kind == "letter":
            last_letter = re.match(r"^\(?([a-z])", text).group(1)
        if kind and kind != "decimal" and kind not in order:
            order.append(kind)
        levels.append(-1 if kind == "decimal" else order.index(kind) if kind else None)
    return levels


def lead_in(text):
    """First sentence of a clause, used to repeat context on continuation parts."""
    m = re.match(r"^(.{15,250}?[.:;])(?:\s|$)", text)
    if m:
        return m.group(1)
    return text if len(text) <= 250 else text[:250].rsplit(" ", 1)[0] + "…"


def size(lines):
    return sum(len(line[0]) + 1 for line in lines)


def split_nodes(nodes, budget, first_budget, ctx):
    """Split [(text, pages, level)] into parts that fit. Cuts at the shallowest
    clause level first; goes one level deeper only inside a clause that is too
    big alone. Every part after the first repeats the lead-in of the clauses it
    continues (`ctx` plus this clause's own lead-in)."""
    if size(nodes) <= first_budget:
        return [[(t, p) for t, p, _ in nodes]]

    own = nodes[0][2]
    child_levels = [lv for _, _, lv in nodes[1:] if lv is not None and (own is None or lv > own)]
    rep = ctx + ([lead_in(nodes[0][0])] if own is not None else [])
    if not child_levels:
        return split_sentences(nodes, budget, first_budget, [(f"{c} (contd.)", set()) for c in rep])

    level = min(child_levels)
    head, blocks = [], []
    for node in nodes:
        if node[2] == level:
            blocks.append([node])
        elif blocks:
            blocks[-1].append(node)  # unmarked lines (Explanation, Provided that) and deeper clauses
        else:
            head.append(node)
    # an unmarked line right before the list ("Provided that where the customer has submitted,")
    # is the list's real lead-in, so repeat it too
    if (len(head) > 1 and head[-1][2] is None and len(head[-1][0]) <= 250
            and re.search(r"[:,\-–]$", head[-1][0])):
        rep = rep + [head[-1][0]]
    rep_lines = [(f"{c} (contd.)", set()) for c in rep]

    parts = []
    cur = [(t, p) for t, p, _ in head]
    if size(cur) > first_budget:
        # the text before the first clause at this level is itself too big (e.g. an
        # (i)-(ix) list before 5.1): split it by its own structure
        pieces = split_nodes(head, budget, first_budget, ctx)
        parts, cur = pieces[:-1], pieces[-1]

    for block in blocks:
        lines = [(t, p) for t, p, _ in block]
        cap = first_budget if not parts else budget
        if size(cur) + size(lines) <= cap:
            cur += lines
            continue
        if size(rep_lines) + size(lines) <= budget:
            parts.append(cur)
            cur = rep_lines + lines
            continue
        # the clause itself is too big: split it one level deeper. Start in the
        # current part if there is real room left, so a heading is never left alone.
        room = cap - size(cur)
        if room >= MIN_ROOM:
            sub = split_nodes(block, budget, room, rep)
            sub[0] = cur + sub[0]
        else:
            if cur:
                parts.append(cur)
            sub = split_nodes(block, budget, budget - size(rep_lines), rep)
            sub[0] = rep_lines + sub[0]
        parts.extend(sub[:-1])
        cur = sub[-1]
    if cur:
        parts.append(cur)
    return parts


def split_sentences(nodes, budget, first_budget, rep_lines):
    """Last resort for a clause with no sub-clauses: cut at line breaks (table rows)
    and sentence ends, and as a final fallback at a word boundary."""
    pages = set().union(*(p for _, p, _ in nodes))
    cap_later = budget - size(rep_lines)
    pieces = []  # (text, separator that followed it)
    for line in "\n".join(t for t, _, _ in nodes).split("\n"):
        for s in re.split(r"(?<=[.;])\s+(?=[A-Z(\"'‘])", line):
            while len(s) > cap_later:
                cut = s.rfind(" ", 0, cap_later)
                cut = cut if cut > 0 else cap_later
                pieces.append((s[:cut], " "))
                s = s[cut:].strip()
            pieces.append((s, " "))
        pieces[-1] = (pieces[-1][0], "\n")
    parts, cur = [], ""
    for s, sep in pieces:
        cap = first_budget if not parts else cap_later
        if cur and len(cur) + len(s) > cap:
            parts.append(cur.rstrip())
            cur = s + sep
        else:
            cur += s + sep
    parts.append(cur.rstrip())
    return [[(parts[0], pages)]] + [rep_lines + [(t, pages)] for t in parts[1:]]


def split_long(lines, prefix):
    """Split a paragraph's [text, pages] lines into parts of at most MAX_CHARS.
    Returns [(text, pages)]; parts after the first start with `prefix`."""
    whole = "\n".join(t for t, _ in lines).strip()
    if len(whole) <= MAX_CHARS:
        return [(whole, set().union(*(p for _, p in lines)))]

    budget = MAX_CHARS - len(prefix) - 30
    # a line holding several clauses (Docling merged them) is opened up first
    expanded = []
    for text, pages in lines:
        subs = INLINE_SUBCLAUSE_RE.split(text) if len(text) > budget else [text]
        expanded += [(s, set(pages)) for s in subs if s.strip()]
    levels = clause_levels([t for t, _ in expanded])
    nodes = [(t, p, lv) for (t, p), lv in zip(expanded, levels)]

    parts = split_nodes(nodes, budget, budget, [])
    out = []
    for k, part in enumerate(parts):
        text = "\n".join(t for t, _ in part).strip()
        pages = set().union(*(p for _, p in part))
        out.append((text if k == 0 else f"{prefix} (contd.)\n{text}", pages))
    return out


def chunk_document(doc, meta, doc_name):
    stem = Path(doc_name).stem
    paragraphs = []
    region, chapter, section = "main", None, None
    prev_num = 0            # last accepted paragraph number in this region
    started = False         # past the masthead / table of contents?
    skipping = False        # inside a signature / distribution block
    in_toc = False
    restart_ok = False      # first chapter just began: a "1." may restart the numbering
    pending_title = False   # bare "CHAPTER III" seen; its title is on the next line
    section_root = None     # last lettered section ("H. Microfinance"), parent of "H.4 ..."
    current = Paragraph(region, chapter, section, None)
    footnotes = []

    def new_paragraph(para=None, header_title=None):
        nonlocal current
        if current.lines:
            paragraphs.append(current)
        current = Paragraph(region, chapter, section, para, header_title)

    def start_chapter(m):
        nonlocal chapter, section, section_root, current, restart_ok, pending_title
        new_paragraph()
        if chapter is None:
            restart_ok = True
        title = m.group(2).strip(" -–:")
        chapter = f"Chapter {m.group(1)} - {title}".strip(" -")
        section = section_root = None
        pending_title = not title
        current = Paragraph(region, chapter, section, None)

    for item in prepare_items(doc):
        label, page = item["label"], item["page"]
        raw = item["text"].strip()
        text = clean(raw)
        if label == "caption" and not ANNEX_START_RE.match(text):
            continue
        if not text or label in ("page_header", "page_footer", "document_index", "picture"):
            continue
        # bare page numbers, lone separators, footer URLs
        if (re.fullmatch(r"\d{1,3}", text) or re.fullmatch(r"[*_\-–. ]+", text)
                or re.fullmatch(r"(?:www\.|https?://)\S+", text)):
            continue
        if DOT_LEADER_RE.search(text):
            continue  # table-of-contents line

        if label == "footnote" or (FOOTNOTE_RE.match(text) and len(text) < 400):
            m = FOOTNOTE_RE.match(text)
            if m:
                footnotes.append((m.group(1), m.group(2).strip(), page, current))
                continue

        # ----- annex boundary (may sit at the end of a signature line) -----
        m = ANNEX_START_RE.match(text) or annex_at_end(text)
        if m:
            new_paragraph()
            region, chapter, section, section_root, pending_title = f"annex_{m.group(1)}", None, None, None, False
            prev_num, started, skipping, in_toc, restart_ok = 0, True, False, False, False
            current = Paragraph(region, chapter, section, None)
            rest = text[m.end():].strip(" -–:") if ANNEX_START_RE.match(text) else ""
            if rest:  # "Annex I - Key Facts Statement": the title is metadata, not a chunk of its own
                section = section_root = rest
                current = Paragraph(region, chapter, section, None)
            continue

        if skipping:
            continue

        # ----- masthead and table of contents -----
        if label == "section_header" and TOC_HEADER_RE.match(text):
            in_toc = True
            continue
        if not started:
            is_content = (
                CHAPTER_RE.match(text)
                or PARA_RE.match(text) and item["marker"] == ""
                or re.fullmatch(r"\d{1,3}\.", item["marker"])
                or (label == "section_header" and PREAMBLE_HEADER_RE.match(text))
                or (label != "section_header" and len(text) >= 200 and not in_toc)
            )
            if not is_content:
                continue
            started, in_toc = True, False
        if in_toc:
            if label == "section_header":
                in_toc = False
            else:
                continue

        # ----- signature, "To,", "Copy for information to" -----
        if (SIGNATURE_RE.match(text) and len(text) < 150) or SKIP_BLOCK_RE.match(text):
            new_paragraph()
            skipping = True
            continue

        # ----- chapter / section headings -----
        m = CHAPTER_RE.match(text)
        if m and len(text) < 250:
            start_chapter(m)
            continue
        if pending_title:
            pending_title = False
            if (len(text) < 120 and not current.lines and not PARA_RE.match(text)
                    and not SECTION_RE.match(text) and not SUBSECTION_RE.match(text)):
                # "CHAPTER III" + "Customer Acceptance Policy"; a title ending in a dash
                # ("... Agreements -") continues on the next line
                sep = " " if chapter.endswith(("-", "–")) else " - "
                chapter = f"{chapter}{sep}{text.rstrip(':')}"
                current.chapter = chapter
                pending_title = text.endswith(("-", "–"))
                continue
        if SUBSECTION_RE.match(text) and len(text) < 120 and label in ("section_header", "text"):
            new_paragraph()
            letter = text[0]
            heading = text.rstrip(":").strip()
            section = f"{section_root} › {heading}" if section_root and section_root.startswith(letter + ".") else heading
            current = Paragraph(region, chapter, section, None)
            continue
        if label == "section_header":
            m = SECTION_RE.match(text)
            if m:
                new_paragraph()
                section = section_root = text.rstrip(":").strip()
                current = Paragraph(region, chapter, section, None)
                continue
            if current.para is None and not PARA_RE.match(text):
                if PREAMBLE_HEADER_RE.match(text):
                    new_paragraph()
                    section = text.rstrip(":")
                    current = Paragraph(region, chapter, section, None)
                    continue

        # ----- numbered paragraphs -----
        marker = item["marker"]
        line = f"{marker} {text}" if marker and marker != "•" else (f"• {text}" if marker == "•" else text)

        for segment in INLINE_CHAPTER_RE.split(line):
            # a paragraph number buried inside the item ("... 3.4 The order ... 4. Regarding ...")
            head, tail = segment, None
            mi = INLINE_PARA_RE.search(segment)
            while mi and (int(mi.group(1)) != prev_num + 1 or CROSS_REF_RE.search(segment[:mi.start()])):
                mi = INLINE_PARA_RE.search(segment, mi.end())
            if mi and not PARA_RE.match(segment):
                head, tail = segment[:mi.start()].strip(), segment[mi.start():].strip()

            for piece in (head, tail):
                if not piece:
                    continue
                mc = CHAPTER_RE.match(piece)
                if mc and len(piece) < 250:
                    start_chapter(mc)  # "Chapter V: Reporting ... 16. Reporting to CICs ..."
                    continue
                m = PARA_RE.match(piece)
                if m:
                    num, suffix = int(m.group(1)), m.group(2)
                    first_ok = prev_num == 0 and num in (1, 2)
                    # numbering restarts at 1 in the first chapter: earlier numbers were the preamble's
                    restart = restart_ok and num == 1 and prev_num > 0 and not suffix
                    if suffix:
                        # "33A." follows 33, or 32 when 33 itself was deleted
                        accepted = num in (prev_num, prev_num + 1)
                    else:
                        accepted = num == prev_num + 1 or first_ok or restart
                        if not accepted and num == prev_num + 2 and prev_num > 0:
                            # one paragraph number was not found (merged into another item,
                            # dropped by the parser, ...): accept, but say so
                            accepted = True
                            print(f"  WARNING {stem}: {region} para {num} follows {prev_num} "
                                  f"(para {prev_num + 1} not found) on page {page}", flush=True)
                    if accepted:
                        if restart:
                            for p in paragraphs:
                                if p.region == region and p.chapter is None:
                                    p.para = None
                        prev_num, restart_ok = num, False
                        header = re.sub(r"^(?:Q\.?\s*)?\d{1,3}[A-Z]?\.\s*", "", piece).rstrip(":") if label == "section_header" else None
                        new_paragraph(f"{num}{suffix or ''}", header)
                        current.add(piece, page, as_new_line=True)
                        continue
                current.add(piece, page)

    new_paragraph()

    # ----- attach amendment footnotes to the paragraph carrying the marker -----
    for num, note, page, fallback in footnotes:
        pattern = re.compile(FOOTNOTE_MARK_RE.format(n=num), re.M)
        target = None
        for p in reversed(paragraphs):
            if p.pages and min(p.pages) <= page <= max(p.pages) + 1 and any(pattern.search(t) for t, _ in p.lines):
                target = p
                break
        if target:
            for line in target.lines:
                line[0] = pattern.sub(lambda m: "[" if m.group(0).startswith("[") else "", line[0])
        else:
            target = fallback if fallback in paragraphs else (paragraphs[-1] if paragraphs else None)
        if target:
            target.notes.append(note)

    # ----- build chunk records -----
    chunks, seen = [], set()
    for p in paragraphs:
        body = p.text
        if not body:
            continue
        annex = "Annex " + p.region.split("_", 1)[1] if p.region != "main" else None
        title = para_title(p) if p.para else (p.section or p.chapter or (f"{annex} (preamble)" if annex else "Preamble"))
        where = f"{annex}, " if annex else ""
        prefix = f"[{where}para {p.para}. {title}]" if p.para else f"[{where}{title}]"
        parts = split_long(p.lines, prefix)
        for k, (part, pages) in enumerate(parts, 1):
            base = f"{stem}__{p.region}__{'p' + p.para if p.para else 'pre'}__{k}"
            cid, n = base, 2
            while cid in seen:
                cid, n = f"{base}_{n}", n + 1
            seen.add(cid)
            chunks.append({
                "chunk_id": cid,
                "doc": doc_name,
                "title": meta.get("title"),
                "status": meta.get("status"),
                "updated_as_on": meta.get("updated_as_on") or None,
                "region": p.region,
                "chapter": p.chapter,
                "section": p.section,
                "para": p.para,
                "para_title": title,
                "part": k,
                "parts": len(parts),
                "page_start": min(pages) if pages else None,
                "page_end": max(pages) if pages else None,
                "amendment_note": "; ".join(p.notes) or None,
                "boilerplate": (len(parts) == 1 and len(part) <= BOILERPLATE_MAX_CHARS
                                and bool(BOILERPLATE_RE.search(part) or DELETED_RE.match(part)))
                               or is_circular_list(part),
                "text": part,
            })
    return chunks


def load_metadata():
    with METADATA_CSV.open(encoding="utf-8") as f:
        return {row["file_name"]: row for row in csv.DictReader(f)}


def main():
    metadata = load_metadata()
    if len(sys.argv) > 1:
        stems = [Path(a).stem for a in sys.argv[1:]]
    else:
        stems = [p.stem for p in sorted(PARSED_DIR.glob("*.json"))]
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)

    for stem in stems:
        json_path = PARSED_DIR / f"{stem}.json"
        if not json_path.exists():
            print(f"Skipping {stem}: {json_path} not found (run parse_test.py first)")
            continue
        doc = json.loads(json_path.read_text(encoding="utf-8"))
        doc_name = next((name for name in metadata if Path(name).stem == stem), stem + ".pdf")
        chunks = chunk_document(doc, metadata.get(doc_name, {}), doc_name)
        out_path = CHUNK_DIR / f"{stem}.jsonl"
        with out_path.open("w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        print(f"{stem}: {len(chunks)} chunks -> {out_path}")


if __name__ == "__main__":
    main()
