"""Judge agreement with human verdicts in eval/gold_verdicts.csv.

gold_verdicts.csv holds 15 fixed system answers (from the Step 5B runs) with their cited chunks.
Fill in `my_verdict` (correct / partial / incorrect) for the rows you grade, then run this script:
it re-judges each graded answer with the current correctness judge (key facts, eval/judges.py; for
unanswerable questions the refusal judge) and compares it - and the Step 5B judge's verdict stored
in the file - with yours. Judge calls are cached (eval/cache/judge/).

Usage: python eval/judge_agreement.py [--judge-votes 3]
Output: eval/results/judge_agreement.md
"""
import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
from judges import VERDICTS, Judge  # noqa: E402
from llm_cache import CachedLLM  # noqa: E402
from rag import llm  # noqa: E402
from rag.answer import NOT_COVERED, source_record  # noqa: E402
from rag.status import as_source, describe  # noqa: E402
from retrieval.search import COLUMNS, _conn  # noqa: E402

GOLD = ROOT / "eval" / "gold_verdicts.csv"
QUESTIONS = ROOT / "eval" / "questions.csv"
OUT = ROOT / "eval" / "results" / "judge_agreement.md"


def cited_records(cited_chunk_ids):
    """'S1=<chunk_id> || S6=status:<file>' -> source records as the answer model saw them."""
    out = []
    for item in filter(None, (cited_chunk_ids or "").split(" || ")):
        source, ref = item.split("=", 1)
        if ref.startswith("status:"):
            rec = as_source(describe(ref.removeprefix("status:")))
            out.append({"score": 1.0, "region": None, "section": None, "para_no": None, "chunk_id": None,
                        **rec, "source": source})
            continue
        row = _conn().execute(f"SELECT {', '.join(COLUMNS)}, 0.0 FROM chunks WHERE chunk_id = %s", (ref,)).fetchone()
        if row is None:
            raise SystemExit(f"chunk {ref} no longer exists; rebuild gold_verdicts.csv")
        rec = source_record(int(source[1:]), dict(zip(COLUMNS + ["score"], row)))
        out.append(rec)
    return out


def judge_row(gold, question, judge):
    answer_text = gold["system_answer"]
    if question["type"] == "unanswerable":
        refused = answer_text.strip() == NOT_COVERED or judge.refusal(question, answer_text)["refused"]
        return "correct" if refused else "incorrect", ""
    if answer_text.strip() == NOT_COVERED:
        return "incorrect", "false refusal"
    c = judge.correctness(question, answer_text, cited_records(gold["cited_chunk_ids"]))
    return c["verdict"], f"{c['facts_present']} facts present; " + " | ".join(f["status"] for f in c["facts"])


def confusion(pairs):
    out = ["| mine \\ judge | " + " | ".join(VERDICTS) + " |", "|---|" + "---|" * len(VERDICTS)]
    counts = Counter(pairs)
    for mine in VERDICTS:
        out.append(f"| {mine} | " + " | ".join(str(counts[(mine, j)]) for j in VERDICTS) + " |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge-votes", type=int, default=3)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    questions = {r["id"]: r for r in csv.DictReader(QUESTIONS.open(encoding="utf-8"))}
    gold = list(csv.DictReader(GOLD.open(encoding="utf-8")))
    graded = [g for g in gold if g["my_verdict"].strip()]
    bad = [g["id"] for g in graded if g["my_verdict"].strip().lower() not in VERDICTS]
    if bad:
        raise SystemExit(f"my_verdict must be one of {VERDICTS}; check {bad}")
    if not graded:
        raise SystemExit(f"No rows graded yet: fill in my_verdict in {GOLD.relative_to(ROOT)} first.")

    judge = Judge(CachedLLM("judge"), votes=args.judge_votes)
    rows = []
    for g in graded:
        mine = g["my_verdict"].strip().lower()
        new, detail = judge_row(g, questions[g["id"]], judge)
        rows.append({"id": g["id"], "type": g["type"], "mine": mine, "new": new, "old": g["step5B_judge_verdict"],
                     "detail": detail, "notes": g["my_notes"]})
        print(f"  {g['id']}: mine {mine:<9} new judge {new:<9} step5B judge {g['step5B_judge_verdict']}")

    n = len(rows)
    ai_graded = all(r["notes"].startswith("[graded by Claude") for r in rows)
    who = "reference verdicts graded by Claude (AI), NOT a human" if ai_graded else "your verdicts"
    agree_new = sum(r["mine"] == r["new"] for r in rows)
    agree_old = sum(r["mine"] == r["old"] for r in rows)
    lines = [
        f"# Judge agreement with {'AI reference' if ai_graded else 'human'} verdicts", "",
        f"Compared against: **{who}**." + (" This checks the judge against an independent grader from another "
        "model family; it is not human ground truth." if ai_graded else ""), "",
        f"{n} of {len(gold)} gold answers graded. New judge: {llm.JUDGE_PROVIDER} {llm.MODEL_JUDGE}, key facts, majority of "
        f"{args.judge_votes} call(s). Step 5B judge: the holistic judge whose verdict is stored in the file.", "",
        "| judge | agrees with the reference | exact agreement |", "|---|---|---|",
        f"| new (key facts) | {agree_new}/{n} | {agree_new / n:.0%} |",
        f"| step 5B (holistic) | {agree_old}/{n} | {agree_old / n:.0%} |", "",
        "## Confusion matrix, new judge (rows: reference)", "", confusion([(r["mine"], r["new"]) for r in rows]), "",
        "## Disagreements (new judge)", "",
        "| id | type | reference | new judge | step 5B judge | judge detail | reference notes |", "|---|---|---|---|---|---|---|",
    ]
    lines += [f"| {r['id']} | {r['type']} | {r['mine']} | {r['new']} | {r['old']} | {r['detail']} | {r['notes']} |"
              for r in rows if r["mine"] != r["new"]] or ["| - | | | | | | |"]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nnew judge agrees {agree_new}/{n}, step 5B judge {agree_old}/{n} -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
