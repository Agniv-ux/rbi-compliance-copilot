"""Retrieval ablation: vector vs keyword vs hybrid on the same questions and expected sources.

Runs eval/retrieval_eval.evaluate() once per method and prints Recall@1/3/5/10 overall and per
type, plus every question whose rank differs between methods. Per-question results go to
eval/results/retrieval_<tag>_<method>.csv and the tables to eval/results/retrieval_ablation_<tag>.md.

Usage: python eval/retrieval_ablation.py [--tag v5_5C]
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
from retrieval_eval import evaluate, load_rows  # noqa: E402
from search import HYBRID_POOL, KEYWORD_MAX_DF, METHODS, RRF_K  # noqa: E402

TYPES = ("simple", "multi_part", "change", "status")
KS = (1, 3, 5, 10, 20, 30)  # R@20 / R@30: is the right paragraph in a reranker's candidate pool?
WATCH = ("q019", "q020", "q043")


def recall_rows(results_by_method):
    out = ["| method | group | n | " + " | ".join(f"R@{k}" for k in KS) + " |",
           "|---|---|---|" + "---|" * len(KS)]
    for method, results in results_by_method.items():
        for group in ("overall",) + TYPES:
            g = results if group == "overall" else [r for r in results if r["type"] == group]
            if g:
                cells = " | ".join(f"{sum(r[f'hit@{k}'] for r in g) / len(g):.1%}" for k in KS)
                out.append(f"| {method} | {group} | {len(g)} | {cells} |")
    return "\n".join(out)


def rank_changes(results_by_method):
    by_id = {}
    for method, results in results_by_method.items():
        for r in results:
            by_id.setdefault(r["id"], {"type": r["type"], "expected": r["expected"]})[method] = r["rank"] or f">{max(KS)}"
    out = ["| id | type | expected | " + " | ".join(results_by_method) + " |",
           "|---|---|---|" + "---|" * len(results_by_method)]
    for qid, row in by_id.items():
        ranks = [row[m] for m in results_by_method]
        if len(set(map(str, ranks))) > 1 or qid in WATCH:
            mark = " (watch)" if qid in WATCH else ""
            out.append(f"| {qid}{mark} | {row['type']} | {row['expected']} | " + " | ".join(map(str, ranks)) + " |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="v5_5C")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    rows = load_rows()
    results_by_method = {}
    for method in METHODS:
        results, unparseable = evaluate(rows, method, verbose=False, ks=KS)
        results_by_method[method] = results
        path = ROOT / "eval" / "results" / f"retrieval_{args.tag}_{method}.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(results[0]))
            w.writeheader()
            w.writerows(results)
        print(f"{method}: {len(results)} scored, {len(unparseable)} not parseable -> {path.relative_to(ROOT)}")

    report = "\n".join([
        f"# Retrieval ablation ({args.tag})", "",
        f"Settings: hybrid = top {HYBRID_POOL} vector + top {HYBRID_POOL} keyword (up to {2 * HYBRID_POOL} fused candidates), reciprocal rank fusion "
        f"k={RRF_K}; keyword = OR of the question's lexemes found in at most {KEYWORD_MAX_DF:.0%} of chunks, "
        "ranked with ts_rank_cd. Statuses as in retrieval_eval.py (active for simple / multi_part, "
        "all for change / status); boilerplate excluded.", "",
        "## Recall", "", recall_rows(results_by_method), "",
        f"## Questions whose rank differs between methods (rank of the first matching chunk; >{max(KS)} = miss)", "",
        rank_changes(results_by_method), "",
    ])
    out = ROOT / "eval" / "results" / f"retrieval_ablation_{args.tag}.md"
    out.write_text(report, encoding="utf-8")
    print("\n" + report + f"\n-> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
