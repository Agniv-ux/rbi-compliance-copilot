"""Automatic sanity checks for eval/questions.csv.

For each answerable row:
  1. extract the text of every source_doc from data/raw ("new | old" rows list two docs),
  2. find the evidence_quote in that doc (ignoring whitespace, line breaks and hyphenation)
     and compare the page it is found on with the page column,
  3. check every number in expected_answer also appears in the evidence_quote,
  4. flag "simple" / "multi_part" rows whose source is repealed or withdrawn in data/metadata.csv.

Writes the result to an "auto_check" column (pass / fail: reasons) and prints a summary.
The "verified" column is never modified.

Usage: python eval/check_questions.py [path/to/questions.csv]
"""
import csv
import html
import re
import sys
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
METADATA = ROOT / "data" / "metadata.csv"
DEFAULT_CSV = ROOT / "eval" / "questions.csv"

SEP = " | "
STALE_STATUSES = {"repealed", "withdrawn"}
PLAIN_TYPES = {"simple", "multi_part"}

WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}
MULTIPLIERS = {"thousand": 1_000, "lakh": 100_000, "lakhs": 100_000, "crore": 10_000_000}

_doc_cache: dict[str, list[str]] = {}


def doc_path(name: str) -> Path:
    """Source documents live in data/raw; "metadata.csv" refers to data/metadata.csv."""
    return METADATA if name == METADATA.name else RAW / name


def doc_pages(name: str) -> list[str]:
    """Text of each page of a source document (an HTML or CSV file counts as one page)."""
    if name not in _doc_cache:
        path = doc_path(name)
        if path.suffix.lower() == ".pdf":
            _doc_cache[name] = [p.extract_text() or "" for p in PdfReader(path).pages]
        else:
            raw = path.read_text(encoding="utf-8", errors="replace")
            _doc_cache[name] = [html.unescape(re.sub(r"<[^>]+>", " ", raw))]
    return _doc_cache[name]


def squash(text: str) -> str:
    """Normalise for matching: unify quotes/dashes, then drop whitespace and hyphens.

    Dropping all whitespace also absorbs extraction artefacts such as "loans ." and
    hyphenation across line breaks ("on- boarding" vs "onboarding").
    """
    text = text.translate(str.maketrans({
        "‘": "'", "’": "'", "`": "'", "“": '"', "”": '"',
        "–": "-", "—": "-", "‐": "-", "‑": "-", "­": "-",
    }))
    return re.sub(r"[\s\-]+", "", text).lower()


def find_pages(quote: str, pages: list[str]) -> list[int]:
    """1-based pages whose text contains the quote; also matches quotes spanning two pages."""
    q = squash(quote)
    squashed = [squash(p) for p in pages]
    hits = [i + 1 for i, p in enumerate(squashed) if q in p]
    if not hits:
        hits = [i + 1 for i in range(len(squashed) - 1)
                if q in squashed[i] + squashed[i + 1] and q not in squashed[i + 1]]
    return hits


def numbers_in(text: str) -> set[float]:
    """Numeric values in text: digits ("60,000", "10%"), number words, lakh/crore/thousand multipliers."""
    tokens = re.findall(r"\d[\d,]*(?:\.\d+)?|[a-z]+", text.lower())
    values: set[float] = set()
    for i, tok in enumerate(tokens):
        if tok[0].isdigit():
            value = float(tok.replace(",", ""))
        elif tok in WORD_NUMBERS:
            value = float(WORD_NUMBERS[tok])
        else:
            continue
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        values.add(value * MULTIPLIERS[nxt] if nxt in MULTIPLIERS else value)
    return values


def fmt(n: float) -> str:
    return str(int(n)) if n == int(n) else str(n)


def load_status() -> dict[str, str]:
    with open(METADATA, encoding="utf-8", newline="") as f:
        return {r["file_name"]: r["status"] for r in csv.DictReader(f)}


def check_row(row: dict, status: dict[str, str]) -> tuple[str, list[str]]:
    """Return (auto_check value, human-readable 'found on' notes)."""
    if row["type"] == "unanswerable":
        return "skipped: unanswerable", []

    docs = row["source_doc"].split(SEP)
    stated_pages = row["page"].split(SEP)
    quotes = row["evidence_quote"].split(SEP)
    if not (len(docs) == len(stated_pages) == len(quotes)):
        return (f"fail: source_doc/page/evidence_quote have {len(docs)}/{len(stated_pages)}/"
                f"{len(quotes)} parts"), []

    problems, notes = [], []
    for doc, stated, quote in zip(docs, stated_pages, quotes):
        if not doc_path(doc).exists():
            problems.append(f"{doc} not in data/raw")
            continue
        hits = find_pages(quote, doc_pages(doc))
        notes.append(f"{doc} p{','.join(map(str, hits)) or '-'}")
        if not hits:
            problems.append(f"quote not found in {doc}")
        elif stated == "none" and doc == METADATA.name:
            pass  # metadata.csv has no pages
        elif stated not in {str(h) for h in hits}:
            problems.append(f"quote on p{','.join(map(str, hits))} of {doc}, not p{stated}")

    missing = numbers_in(row["expected_answer"]) - numbers_in(" ".join(quotes))
    if missing:
        problems.append("answer numbers not in quote: " + ", ".join(fmt(n) for n in sorted(missing)))

    if row["type"] in PLAIN_TYPES:
        for doc in docs:
            st = status.get(doc)
            if st is None:
                problems.append(f"{doc} not in metadata.csv")
            elif st in STALE_STATUSES:
                problems.append(f"{row['type']} question sourced from {st} doc {doc}")

    return ("fail: " + "; ".join(problems)) if problems else "pass", notes


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames)
        rows = list(reader)
    if "auto_check" not in fields:
        fields.append("auto_check")

    status = load_status()
    for row in rows:
        row["auto_check"], notes = check_row(row, status)
        print(f"{row['id']}  {row['type']:<12}  found: {'; '.join(notes) or '-'}")

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    outcome = Counter(r["auto_check"].split(":")[0] for r in rows)
    failed = [r for r in rows if r["auto_check"].startswith("fail")]
    print(f"\nSummary: {len(rows)} rows | " + " | ".join(f"{k}: {v}" for k, v in sorted(outcome.items())))
    by_type = Counter((r["type"], r["auto_check"].split(":")[0]) for r in rows)
    for t in sorted({r["type"] for r in rows}):
        print(f"  {t:<13} " + ", ".join(f"{o} {by_type[(t, o)]}" for o in ("pass", "fail", "skipped") if by_type[(t, o)]))
    if failed:
        print("\nFailed rows:")
        for r in failed:
            print(f"  {r['id']} ({r['type']}): {r['auto_check'][6:]}")
    print(f"\nWrote auto_check column to {csv_path}")


if __name__ == "__main__":
    main()
