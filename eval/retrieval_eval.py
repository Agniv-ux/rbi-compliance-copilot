"""Retrieval baseline: does search() find the expected source paragraph?

For every answerable question in eval/questions.csv:
  - parse (source_doc, source_section) into expected targets: doc + region + paragraph(s)
    ("Chapter VI, para 42(1)" -> para 42; "paras 6-30" -> any of 6..30;
     "Annex I, Part 2, item 6" -> any chunk of Annex I whose section mentions "Part 2");
    two-source rows ("a.pdf | b.pdf" with "x | y") give two targets, and either one counts;
  - run search() with k=10: status "active" for simple / multi_part questions, every
    status for change / status questions;
  - record the rank of the first chunk that matches a target.

Reports Recall@1/3/5/10 overall and per type, the questions that missed the top 5, and the
questions whose source could not be parsed. Per-question results go to
eval/results/retrieval_baseline.csv.

Usage: python eval/retrieval_eval.py [--out eval/results/<name>.csv]
"""
import argparse
import csv
import re
import sys
from collections import defaultdict
from itertools import zip_longest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "retrieval"))
from search import search, where  # noqa: E402

QUESTIONS = ROOT / "eval" / "questions.csv"
OUT = ROOT / "eval" / "results" / "retrieval_baseline.csv"
KS = (1, 3, 5, 10)
SEP = " | "
ACTIVE_ONLY_TYPES = {"simple", "multi_part"}


def parse_target(doc, section):
    """One expected location, or None when it cannot be mapped to chunks."""
    doc, section = (doc or "").strip(), (section or "").strip()
    if not doc.endswith((".pdf", ".html")) or not section or section.lower() == "none":
        return None
    target = {"doc": doc, "region": "main", "paras": None, "section_contains": None}
    annex = re.search(r"\b(?:Annex(?:ure)?|Appendix)\s*[-–]?\s*([IVX]+|\d+)\b", section)
    if annex:
        target["region"] = f"annex_{annex.group(1)}"
        part = re.search(r"\bPart\s+\w+", section)
        target["section_contains"] = part.group(0) if part else None
    rng = re.search(r"\bparas?\s*(\d+)\s*[-–]\s*(\d+)\b", section)
    single = re.search(r"\bpara\s*(\d+[A-Z]?)\b", section)
    if rng:
        target["paras"] = {str(n) for n in range(int(rng.group(1)), int(rng.group(2)) + 1)}
    elif single:
        target["paras"] = {single.group(1)}  # first "para N" is the source ("para 4(1) (inserts ... para 63)")
    elif not annex:
        return None  # no paragraph and no annex: nothing to match
    return target


def parse_targets(row):
    docs = [d.strip() for d in (row["source_doc"] or "").split(SEP.strip())]
    sections = [s.strip() for s in (row["source_section"] or "").split(SEP.strip())]
    if len(sections) == 1 and len(docs) > 1:
        sections = sections * len(docs)
    targets, unparsed = [], []
    for doc, section in zip_longest(docs, sections, fillvalue=""):
        t = parse_target(doc, section)
        (targets if t else unparsed).append(t or f"{doc} :: {section}")
    return targets, unparsed


def matches(hit, target):
    if hit["doc"] != target["doc"] or hit["region"] != target["region"]:
        return False
    if target["paras"] is not None and hit["para"] not in target["paras"]:
        return False
    if target["section_contains"] and target["section_contains"] not in (hit["section"] or ""):
        return False
    return True


def describe(target):
    region = "" if target["region"] == "main" else target["region"].replace("annex_", "Annex ") + " "
    if target["paras"] is None:
        paras = target["section_contains"] or "any"
    elif len(target["paras"]) == 1:
        paras = "para " + next(iter(target["paras"]))
    else:
        nums = sorted(int(re.match(r"\d+", p).group()) for p in target["paras"])
        paras = f"paras {nums[0]}-{nums[-1]}"
    return f"{target['doc']} {region}{paras}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT, help="per-question results CSV")
    out = ap.parse_args().out
    out = out if out.is_absolute() else ROOT / out

    with QUESTIONS.open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["type"] != "unanswerable"]

    results, unparseable = [], []
    for row in rows:
        targets, unparsed = parse_targets(row)
        if not targets:
            unparseable.append((row, unparsed))
            continue
        statuses = ("active",) if row["type"] in ACTIVE_ONLY_TYPES else None
        hits = search(row["question"], k=max(KS), statuses=statuses)
        rank = next((i for i, h in enumerate(hits, 1) if any(matches(h, t) for t in targets)), None)
        # for two-source questions: were *all* sources found in the top 10?
        all_found = all(any(matches(h, t) for h in hits) for t in targets)
        results.append({
            "id": row["id"], "type": row["type"], "question": row["question"],
            "expected": "; ".join(describe(t) for t in targets),
            "unparsed_part": "; ".join(unparsed),
            "statuses": "active" if statuses else "all",
            "rank": rank or "",
            **{f"hit@{k}": int(bool(rank and rank <= k)) for k in KS},
            "all_sources_in_top10": int(all_found),
            "top5": " || ".join(f"{h['doc']} {where(h)} ({h['score']:.3f})" for h in hits[:5]),
        })
        print(f"  {row['id']}: rank {rank or '-'}", flush=True)

    # ---------- report ----------
    def recall_line(name, group):
        n = len(group)
        cells = "  ".join(f"R@{k} {sum(r[f'hit@{k}'] for r in group) / n:5.1%}" for k in KS)
        return f"{name:<11} n={n:<3} {cells}"

    print(f"\nRetrieval eval -> {out.name} ({len(results)} questions scored, {len(unparseable)} not parseable)\n")
    print(recall_line("overall", results))
    by_type = defaultdict(list)
    for r in results:
        by_type[r["type"]].append(r)
    for t in ("simple", "multi_part", "change", "status"):
        if by_type.get(t):
            print(recall_line(t, by_type[t]))

    misses = [r for r in results if not r["hit@5"]]
    print(f"\nMissed the top 5 ({len(misses)}):")
    for r in misses:
        print(f"\n  {r['id']} [{r['type']}, statuses={r['statuses']}] rank={r['rank'] or '>10'}")
        print(f"    Q: {r['question']}")
        print(f"    expected: {r['expected']}")
        for i, got in enumerate(r["top5"].split(" || "), 1):
            print(f"    {i}. {got}")

    two_source = [r for r in results if ";" in r["expected"]]
    if two_source:
        print(f"\nTwo-source questions with only one source in the top 10: "
              f"{[r['id'] for r in two_source if not r['all_sources_in_top10']] or 'none'}")

    print(f"\nCould not parse ({len(unparseable)}):")
    for row, unparsed in unparseable:
        print(f"  {row['id']} [{row['type']}]: {'; '.join(unparsed)}")

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    print(f"\nPer-question results: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
