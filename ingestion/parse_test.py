import json
import sys
import time
from pathlib import Path
from docling.document_converter import DocumentConverter

RAW_DIR = Path("data/raw")
OUT_DIR = Path("data/parsed")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Which file to parse: pass a name, or use a small default
file_name = sys.argv[1] if len(sys.argv) > 1 else "kyc_amendment_2025_08.pdf"
pdf_path = RAW_DIR / file_name

print(f"Parsing {pdf_path} ...")
start = time.time()

converter = DocumentConverter()
result = converter.convert(pdf_path)
markdown = result.document.export_to_markdown()

out_path = OUT_DIR / (pdf_path.stem + ".md")
out_path.write_text(markdown, encoding="utf-8")

# Structured document (labels, page numbers) for the chunker
json_path = OUT_DIR / (pdf_path.stem + ".json")
json_path.write_text(json.dumps(result.document.export_to_dict(), ensure_ascii=False), encoding="utf-8")

print(f"Done in {time.time() - start:.1f} seconds")
print(f"Saved to {out_path} ({len(markdown):,} characters)")
print(f"Saved to {json_path}")
print("\n----- First 1500 characters -----\n")
print(markdown[:1500])