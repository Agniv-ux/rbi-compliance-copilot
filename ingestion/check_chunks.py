"""Print a quick quality check for a chunks file.

Usage:
    python ingestion/check_chunks.py data/chunks/nbfc_kyc_md_2025.jsonl [--expect 76] [--seed 7]
"""
import argparse
import json
import random
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chunker import MAX_CHARS  # noqa: E402  (same limit the chunker uses)

parser = argparse.ArgumentParser()
parser.add_argument("path")
parser.add_argument("--expect", type=int, help="number of main-body paragraphs the document should have")
parser.add_argument("--seed", type=int, default=7, help="seed for picking sample chunks")
args = parser.parse_args()

chunks = [json.loads(line) for line in Path(args.path).read_text(encoding="utf-8").splitlines() if line.strip()]
print(f"File: {args.path}")
print(f"Chunks: {len(chunks)}")

print("\nChunks per region / chapter:")
counts = Counter((c["region"], c["chapter"] or "-") for c in chunks)
for (region, chapter), n in counts.items():  # insertion order = document order
    print(f"  {n:4}  {region:<10} {chapter}")

# Main-body paragraph coverage
main_paras = [c["para"] for c in chunks if c["region"] == "main" and c["para"]]
numbers = sorted({int(re.match(r"\d+", p).group()) for p in main_paras})
expected = args.expect or (max(numbers) if numbers else 0)
missing = sorted(set(range(1, expected + 1)) - set(numbers))
extra = [n for n in numbers if n > expected]
print(f"\nMain paragraphs: {len(numbers)} distinct numbers found, expected 1-{expected}")
print(f"  missing: {missing or 'none'}")
if extra:
    print(f"  unexpected: {extra}")
order = [int(re.match(r"\d+", p).group()) for p in dict.fromkeys(main_paras)]
print(f"  in order: {'yes' if order == sorted(order) else 'NO'}")

for region in dict.fromkeys(c["region"] for c in chunks if c["region"] != "main"):
    paras = list(dict.fromkeys(c["para"] for c in chunks if c["region"] == region and c["para"]))
    print(f"  {region} paragraphs: {', '.join(paras) or 'none'}")

split = Counter(c["para"] for c in chunks if c["parts"] > 1 and c["region"] == "main")
print(f"\nParagraphs split into parts (main): {dict(split) or 'none'}")
print("How each continuation part starts (lines after the [para ...] prefix):")
for c in chunks:
    if c["part"] > 1:
        lines = c["text"].split("\n")[1:3]
        print(f"  {c['chunk_id'].split('__', 1)[1]:<18} " + " / ".join(l[:70] for l in lines))

boiler = [c for c in chunks if c.get("boilerplate")]
print(f"\nBoilerplate chunks: {len(boiler)}")
for c in boiler:
    print(f"  {c['chunk_id']}: {c['text'][:90]!r}")
notes = [(c["chunk_id"], c["amendment_note"]) for c in chunks if c["amendment_note"]]
print(f"Chunks with amendment_note: {len(notes)}")
for cid, note in notes:
    print(f"  {cid}: {note[:120]}")

lengths = [len(c["text"]) for c in chunks]
print(f"\nChunk length (chars): min {min(lengths)}, median {statistics.median(lengths):.0f}, max {max(lengths)}")
over = [c["chunk_id"] for c in chunks if len(c["text"]) > MAX_CHARS]
print(f"Chunks over {MAX_CHARS} chars: {over or 'none'}")
shortest = sorted(chunks, key=lambda c: len(c["text"]))[:3]
print("Shortest: " + " | ".join(f"{c['chunk_id']} ({len(c['text'])}): {c['text'][:60]!r}" for c in shortest))

print("\n" + "=" * 70 + "\nSample chunks\n" + "=" * 70)
for c in random.Random(args.seed).sample(chunks, min(3, len(chunks))):
    meta = {k: v for k, v in c.items() if k != "text"}
    print(json.dumps(meta, ensure_ascii=False, indent=1))
    print("--- text ---")
    print(c["text"])
    print("=" * 70)
