"""Parse (if needed) and chunk every in-scope document listed in data/metadata.csv,
then print a summary table.

A document is in scope when its in_scope column is "yes" or "partial". Docling is
only run when data/parsed/<name>.json is missing, because parsing is slow on CPU.

Usage:
    python ingestion/process_all.py            # parse missing JSONs, chunk everything
    python ingestion/process_all.py --reparse  # parse again even if the JSON exists
"""
import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from chunker import CHUNK_DIR, MAX_CHARS, METADATA_CSV, PARSED_DIR, chunk_document, load_metadata  # noqa: E402

RAW_DIR = Path("data/raw")
IN_SCOPE = {"yes", "partial"}


def main_content_html(src):
    """RBI web pages wrap the content in nested layout tables next to large site
    menus, and Docling's HTML reader loses the content. Keep only the element that
    holds the most <p> paragraphs (the deepest one on a tie) and save it as a small
    standalone page for Docling."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(src.read_text(encoding="utf-8", errors="replace"), "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    best, best_count = soup.body or soup, -1
    for el in soup.find_all(["main", "article", "section", "div", "td"]):
        count = len(el.find_all("p"))
        if count > best_count or (count == best_count and best in el.parents):
            best, best_count = el, count
    title = soup.title.get_text(" ", strip=True) if soup.title else src.stem
    out = PARSED_DIR / f"{src.stem}.content.html"
    out.write_text(f"<html><head><meta charset='utf-8'><title>{title}</title></head>"
                   f"<body>{best.decode_contents()}</body></html>", encoding="utf-8")
    return out


def parse(src, converter):
    """Run Docling on one file and save <name>.md and <name>.json."""
    start = time.time()
    stem = src.stem
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() in (".html", ".htm"):
        src = main_content_html(src)
    result = converter.convert(src)
    doc = result.document
    (PARSED_DIR / f"{stem}.md").write_text(doc.export_to_markdown(), encoding="utf-8")
    json_path = PARSED_DIR / f"{stem}.json"
    json_path.write_text(json.dumps(doc.export_to_dict(), ensure_ascii=False), encoding="utf-8")
    print(f"  parsed in {time.time() - start:.0f} s -> {json_path}", flush=True)


def write_chunks(stem, chunks):
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CHUNK_DIR / f"{stem}.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return out_path


def summarize(name, meta, doc, chunks):
    lengths = [len(c["text"]) for c in chunks] or [0]
    main = sorted({int(re.match(r"\d+", c["para"]).group())
                   for c in chunks if c["region"] == "main" and c["para"]})
    gaps = sorted(set(range(1, main[-1] + 1)) - set(main)) if main else []
    annexes = {}
    for c in chunks:
        if c["region"] != "main" and c["para"]:
            annexes.setdefault(c["region"], set()).add(c["para"])
    pages = len(doc.get("pages", {})) or "-"
    return {
        "Document": name,
        "Status": meta.get("status") or "-",
        "In scope": meta.get("in_scope") or "-",
        "Pages": pages,
        "Chunks": len(chunks),
        "Chapters": len({c["chapter"] for c in chunks if c["chapter"]}),
        "Main paras": f"{main[0]}-{main[-1]} ({len(main)})" if main else "none",
        "Gaps": ", ".join(map(str, gaps)) if gaps else "none",
        "Annexes": "; ".join(f"{r.replace('annex_', 'Annex ')}: {len(v)}" for r, v in annexes.items()) or "-",
        "Preamble chunks": sum(1 for c in chunks if not c["para"]),
        "Split paras": len({(c["region"], c["para"]) for c in chunks if c["parts"] > 1}),
        "Boilerplate": sum(1 for c in chunks if c.get("boilerplate")),
        "Amendment notes": len({(c["region"], c["para"]) for c in chunks if c["amendment_note"]}),
        "Len min/median/max": f"{min(lengths)} / {statistics.median(lengths):.0f} / {max(lengths)}",
        f"Over {MAX_CHARS}": sum(1 for n in lengths if n > MAX_CHARS),
    }


def print_table(rows):
    if not rows:
        return
    cols = list(rows[0])
    print("| " + " | ".join(cols) + " |")
    print("|" + "|".join("---" for _ in cols) + "|")
    for row in rows:
        print("| " + " | ".join(str(row[c]) for c in cols) + " |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reparse", action="store_true", help="run Docling even if the JSON exists")
    args = ap.parse_args()

    metadata = load_metadata()
    todo = [(name, meta) for name, meta in metadata.items()
            if (meta.get("in_scope") or "").strip().lower() in IN_SCOPE]
    print(f"{len(todo)} in-scope documents in {METADATA_CSV}")

    converter = None
    rows, failed = [], []
    for name, meta in todo:
        src = RAW_DIR / name
        stem = src.stem
        json_path = PARSED_DIR / f"{stem}.json"
        print(f"\n== {name}", flush=True)
        try:
            if args.reparse or not json_path.exists():
                if not src.exists():
                    raise FileNotFoundError(f"{src} not found")
                if converter is None:
                    from docling.document_converter import DocumentConverter
                    converter = DocumentConverter()
                parse(src, converter)
            doc = json.loads(json_path.read_text(encoding="utf-8"))
            chunks = chunk_document(doc, meta, name)
            out_path = write_chunks(stem, chunks)
            print(f"  {len(chunks)} chunks -> {out_path}", flush=True)
            rows.append(summarize(name, meta, doc, chunks))
        except Exception as e:  # keep going so one bad file does not stop the batch
            print(f"  FAILED: {type(e).__name__}: {e}", flush=True)
            failed.append(name)

    print("\n\nSummary\n")
    print_table(rows)
    if failed:
        print(f"\nFailed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
