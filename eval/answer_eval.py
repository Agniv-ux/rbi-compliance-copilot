"""Answer-quality eval: run rag.answer.answer() on every question in eval/questions.csv and score it.

For each question the system is called exactly as a user would (k=5, active documents only).
Scores, per question (judges in eval/judges.py, JUDGE_PROVIDER / JUDGE_MODEL, e.g. Gemini Flash):
  1. correctness  - each key fact (questions.csv key_facts) is present / missing / contradicted;
                    the verdict is computed in code (all present = correct, some = partial,
                    none or any contradicted = incorrect). Extra facts never count against the
                    answer. The same call says whether the answer is a refusal (by meaning).
                    The exact refusal sentence needs no judge call.
  2. citation     - does any cited source match the expected doc + paragraph
                    (parsing and matching reused from eval/retrieval_eval.py; either target counts)?
  3. refusals     - unanswerable: correct if the answer refuses (by meaning); exact-sentence
                    refusals are reported separately. Answerable: refusal = false refusal.
  4. faithfulness - is every claim supported by the sources it cites (header + text)?
  5. diagnosis    - for every non-correct answer: were ALL expected paragraphs in the retrieved
                    top 5? yes -> generation_error, any missing -> retrieval_miss.

Noise controls:
  --judge-votes N  majority of N independent judge calls (default 1)
  cache            answers and judge calls are cached in eval/cache/ (see eval/llm_cache.py) and
                   reused on re-runs; --no-cache sends every call again
  --repeat N       N full runs with the cache bypassed; reports mean and min-max per metric

Routing (--routing):
    none   (default, the honest run) - every question in "current" mode, as a user would ask it.
    manual - clearly labelled hand routing that Step 6's agent should learn to do itself:
             change questions in "compare" mode; status questions get the document-status record
             (rag.status.get_document_status, hand-written query per question) as an extra source.
             With --reuse <run A csv>, only routed questions are re-answered; the rest are copied.

Outputs: eval/results/answers_<model>[_<tag>].csv per model, eval/results/answer_eval_summary[_<tag>].md
(--repeat: answers_<model>_<tag>_r<i>.csv and answer_eval_summary_<tag>_repeat.md).

Usage:
    python eval/answer_eval.py --limit 5
    python eval/answer_eval.py --tag v5_5C --method hybrid --judge-votes 3 \\
        --baseline eval/results/answers_gpt-5.4-mini_v4_5B.csv
    python eval/answer_eval.py --tag v5_5C_routed --routing manual --judge-votes 3 \\
        --reuse eval/results/answers_<model>_v5_5C.csv --baseline <csv> <csv>
    python eval/answer_eval.py --tag v5_5C --repeat 3
"""
import argparse
import csv
import random
import statistics
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
from judges import VERDICTS, Judge  # noqa: E402
from llm_cache import CachedLLM  # noqa: E402
from rag import llm  # noqa: E402
from rag.answer import DEFAULT_METHOD, NOT_COVERED, answer  # noqa: E402
from rag.status import as_source, get_document_status  # noqa: E402
from retrieval_eval import describe, matches, parse_targets  # noqa: E402
from search import METHODS  # noqa: E402

QUESTIONS = ROOT / "eval" / "questions.csv"
RESULTS = ROOT / "eval" / "results"
TYPES = ("simple", "multi_part", "change", "status", "unanswerable")
JUDGE_WORKERS = 6
SAMPLE_SEED = 42

# --routing manual: the document each status question is about, as an agent would name it
STATUS_QUERIES = {
    "q006": "Digital Lending Directions 2025",
    "q007": "KYC Master Direction 2016",
    "q043": "Digital Lending Directions 2025",
}


class Settings:
    def __init__(self, method, votes, cache, faith_votes=None):
        self.method, self.votes, self.faith_votes = method, votes, faith_votes or votes
        self.answers = CachedLLM("answers", enabled=cache)
        self.judge_calls = CachedLLM("judge", enabled=cache)


# ---- per-question scoring -----------------------------------------------------------------

def as_hit(source):
    """answer() source record -> the dict shape retrieval_eval.matches() expects."""
    return {"doc": source["doc"], "region": source["region"], "para": source["para_no"],
            "section": source["section"]}


def found(sources, target):
    return any(matches(as_hit(s), target) for s in sources)


def fmt_sources(sources):
    return " || ".join(f"{s['source']} {s['doc']} {s['para']} p{s['pages']}" for s in sources)


def fmt_ids(sources):
    return " || ".join(f"{s['source']}={s['chunk_id'] or 'status:' + s['doc']}" for s in sources)


def route(row, routing):
    """(mode, extra_sources, label) for one question."""
    if routing == "manual" and row["type"] == "change":
        return "compare", None, "compare"
    if routing == "manual" and row["type"] == "status" and row["id"] in STATUS_QUERIES:
        st = get_document_status(STATUS_QUERIES[row["id"]])
        if st["match"]:
            return "current", [as_source(st["match"])], f"current+status({st['match']['file_name']})"
    return "current", None, "current"


def answer_row(row, model, routing, settings):
    mode, extra, label = route(row, routing)
    r = answer(row["question"], model=model, mode=mode, extra_sources=extra,  # defaults: k=5, active
               method=settings.method, generate=settings.answers.generate)
    targets, unparsed = parse_targets(row)
    unanswerable = row["type"] == "unanswerable"
    return {
        "id": row["id"], "type": row["type"], "routing": label, "method": r["method"],
        "question": row["question"], "expected_answer": row["expected_answer"], "key_facts": row["key_facts"],
        "expected_source": "; ".join(describe(t) for t in targets) or "; ".join(unparsed),
        "answer": r["answer"],
        "exact_refusal": int(r["answer"].strip() == NOT_COVERED),
        "cited": fmt_sources(r["citations"]),
        "cited_chunk_ids": fmt_ids(r["citations"]),
        "retrieved": fmt_sources(r["sources"]),
        "expected_in_top5": "" if not targets else int(any(found(r["sources"], t) for t in targets)),
        "all_expected_in_top5": "" if not targets else int(all(found(r["sources"], t) for t in targets)),
        "citation_match": "" if unanswerable or not targets else int(any(found(r["citations"], t) for t in targets)),
        "answer_input_tokens": r["input_tokens"], "answer_output_tokens": r["output_tokens"],
        "answer_reasoning_tokens": r["reasoning_tokens"], "answer_cost_usd": r["cost_usd"],
        "answer_seconds": r["seconds"],
        "_row": row, "_citations": r["citations"],
    }


def score_row(rec, settings):
    row, unanswerable, exact = rec["_row"], rec["type"] == "unanswerable", rec["exact_refusal"]
    judge = Judge(settings.judge_calls, votes=settings.votes, faith_votes=settings.faith_votes)

    # 1 + 3. correctness and refusal
    if unanswerable:
        if exact:
            j = {"refused": True, "reason": "exact refusal sentence", "agreement": 1.0}
        else:
            j = judge.refusal(row, rec["answer"])
        c = {"verdict": "correct" if j["refused"] else "incorrect", "refused": j["refused"], "reason": j["reason"],
             "facts_present": "", "missing_facts": [], "wrong_facts": [], "facts": [],
             "agreement": j["agreement"], "votes": []}
    elif exact:
        c = {"verdict": "incorrect", "refused": True,
             "reason": "false refusal: the question is answerable from the documents",
             "facts_present": f"0/{len(row['key_facts'].split('|'))}", "missing_facts": [row["key_facts"]],
             "wrong_facts": [], "facts": [], "agreement": 1.0, "votes": []}
    else:
        c = judge.correctness(row, rec["answer"], rec["_citations"])

    # 4. faithfulness (only for answers that make claims)
    if c["refused"]:
        f = {"verdict": "", "unsupported_claims": [], "reason": "refusal: nothing to check", "agreement": ""}
    elif not rec["_citations"]:
        f = {"verdict": "unsupported", "unsupported_claims": [], "reason": "answer cites no sources", "agreement": ""}
    else:
        f = judge.faithfulness(rec["answer"], rec["_citations"])

    # 5. diagnosis
    if c["verdict"] == "correct":
        diagnosis = ""
    elif unanswerable:
        diagnosis = "generation_error"  # nothing to retrieve; the model should have refused
    else:
        diagnosis = "generation_error" if rec["all_expected_in_top5"] == 1 else "retrieval_miss"

    rec.update({
        "refused": int(c["refused"]),
        "verdict": c["verdict"], "facts_present": c["facts_present"],
        "fact_statuses": " | ".join(f"{x['status']}" for x in c["facts"]),
        "missing_facts": "; ".join(c["missing_facts"]),
        "wrong_facts": "; ".join(c["wrong_facts"]), "judge_reason": c["reason"],
        "judge_agreement": c["agreement"], "judge_votes": " ".join(c["votes"]),
        "faithfulness": f["verdict"], "unsupported_claims": "; ".join(f["unsupported_claims"]),
        "faithfulness_reason": f["reason"], "faithfulness_agreement": f["agreement"],
        "diagnosis": diagnosis,
        "judge_input_tokens": sum(r["input_tokens"] for r in judge.usage),
        "judge_output_tokens": sum(r["output_tokens"] for r in judge.usage),
        "judge_cost_usd": round(judge.cost(), 6),
    })
    return rec


def run_model(rows, model, routing, settings, reuse=None):
    """reuse: {id: scored record} from an earlier run; questions that route to plain "current"
    mode are copied from it instead of being answered again."""
    todo = [r for r in rows if not (reuse and r["id"] in reuse and route(r, routing)[2] == "current")]
    print(f"\n== {model}: answering {len(todo)} questions (routing={routing}, method={settings.method}; "
          f"{len(rows) - len(todo)} copied from the reused run)", flush=True)
    fresh = []
    for row in todo:  # sequential: search() shares one DB connection
        fresh.append(answer_row(row, model, routing, settings))
        print(f"  {row['id']}: {fresh[-1]['routing']:<45} "
              f"{'refused' if fresh[-1]['exact_refusal'] else 'answered'}", flush=True)
    print(f"== {model}: judging with {llm.JUDGE_PROVIDER}/{llm.MODEL_JUDGE} "
          f"(votes: correctness {settings.votes}, faithfulness {settings.faith_votes})", flush=True)
    with ThreadPoolExecutor(JUDGE_WORKERS) as pool:
        scored = {r["id"]: r for r in pool.map(lambda r: score_row(r, settings), fresh)}
    recs = [scored.get(r["id"]) or reuse[r["id"]] for r in rows]
    for rec in recs:
        print(f"  {rec['id']}: {rec['verdict']:<9} {rec.get('facts_present', ''):<5} "
              f"{rec['faithfulness'] or '-':<19} {rec['diagnosis']}")
    print(f"   cache: answers {settings.answers.hits} hit / {settings.answers.misses} sent; "
          f"judge {settings.judge_calls.hits} hit / {settings.judge_calls.misses} sent")
    return recs


def write_csv(recs, path):
    fields = list(dict.fromkeys(k for r in recs for k in r if not k.startswith("_")))
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(recs)


def load_csv(path):
    """Results CSV -> records with the numeric fields stats() needs (older CSVs lack some columns)."""
    with path.open(encoding="utf-8") as f:
        recs = list(csv.DictReader(f))
    for r in recs:
        for k in ("refused", "exact_refusal", "citation_match", "expected_in_top5", "all_expected_in_top5"):
            if r.get(k) not in (None, ""):
                r[k] = int(r[k])
        r.setdefault("exact_refusal", r.get("refused", 0))  # Step 4: refused == exact sentence
        for k in ("answer_cost_usd", "judge_cost_usd", "answer_seconds"):
            r[k] = float(r[k] or 0)
        for k in ("answer_input_tokens", "answer_output_tokens", "answer_reasoning_tokens",
                  "judge_input_tokens", "judge_output_tokens"):
            if k in r:
                r[k] = int(r[k] or 0)
    return recs


# ---- summary ------------------------------------------------------------------------------

def pct(num, den):
    return f"{num / den:.1%} ({num}/{den})" if den else "n/a"


def stats(recs):
    answerable = [r for r in recs if r["type"] != "unanswerable"]
    unanswerable = [r for r in recs if r["type"] == "unanswerable"]
    cit = [r for r in answerable if r["citation_match"] != ""]
    faith = [r for r in recs if r["faithfulness"]]
    by_type = defaultdict(list)
    for r in recs:
        by_type[r["type"]].append(r)
    agree = [float(r["judge_agreement"]) for r in recs if r.get("judge_agreement") not in (None, "")]
    n = len(recs)
    return {
        "n": n,
        "verdicts": Counter(r["verdict"] for r in recs),
        "by_type": {t: Counter(r["verdict"] for r in g) for t, g in by_type.items()},
        "type_n": {t: len(g) for t, g in by_type.items()},
        "answerable_verdicts": Counter(r["verdict"] for r in answerable),
        "n_answerable": len(answerable),
        "citation": (sum(r["citation_match"] for r in cit), len(cit)),
        "faith": Counter(r["faithfulness"] for r in faith), "n_faith": len(faith),
        "refusal": (sum(r["refused"] for r in unanswerable), len(unanswerable)),
        "exact_refusal": (sum(r["exact_refusal"] for r in unanswerable), len(unanswerable)),
        "false_refusal": (sum(r["refused"] for r in answerable), len(answerable)),
        "diagnosis": Counter(r["diagnosis"] for r in recs if r["diagnosis"]),
        "answer_cost": sum(r["answer_cost_usd"] or 0 for r in recs),
        "judge_cost": sum(r["judge_cost_usd"] for r in recs),
        "answer_tokens": (sum(r["answer_input_tokens"] for r in recs), sum(r["answer_output_tokens"] for r in recs)),
        "seconds": sum(r["answer_seconds"] for r in recs) / n,
        "agreement": sum(agree) / len(agree) if agree else None,
    }


def _share(num, den):
    return num / den if den else None


# (name, text cell, numeric value for --repeat)
METRICS = [
    ("correct (all)", lambda s: pct(s["verdicts"]["correct"], s["n"]), lambda s: _share(s["verdicts"]["correct"], s["n"])),
    ("partial (all)", lambda s: pct(s["verdicts"]["partial"], s["n"]), lambda s: _share(s["verdicts"]["partial"], s["n"])),
    ("incorrect (all)", lambda s: pct(s["verdicts"]["incorrect"], s["n"]), lambda s: _share(s["verdicts"]["incorrect"], s["n"])),
    *[(f"correct: {t}",
       lambda s, t=t: pct(s["by_type"].get(t, Counter())["correct"], s["type_n"].get(t, 0)),
       lambda s, t=t: _share(s["by_type"].get(t, Counter())["correct"], s["type_n"].get(t, 0))) for t in TYPES],
    ("correct (answerable)", lambda s: pct(s["answerable_verdicts"]["correct"], s["n_answerable"]),
     lambda s: _share(s["answerable_verdicts"]["correct"], s["n_answerable"])),
    ("citation accuracy", lambda s: pct(*s["citation"]), lambda s: _share(*s["citation"])),
    ("faithfulness: supported", lambda s: pct(s["faith"]["supported"], s["n_faith"]),
     lambda s: _share(s["faith"]["supported"], s["n_faith"])),
    ("faithfulness: partially supported", lambda s: pct(s["faith"]["partially_supported"], s["n_faith"]),
     lambda s: _share(s["faith"]["partially_supported"], s["n_faith"])),
    ("faithfulness: unsupported", lambda s: pct(s["faith"]["unsupported"], s["n_faith"]),
     lambda s: _share(s["faith"]["unsupported"], s["n_faith"])),
    ("refusal accuracy (by meaning)", lambda s: pct(*s["refusal"]), lambda s: _share(*s["refusal"])),
    ("refusal: exact sentence", lambda s: pct(*s["exact_refusal"]), lambda s: _share(*s["exact_refusal"])),
    ("false-refusal rate", lambda s: pct(*s["false_refusal"]), lambda s: _share(*s["false_refusal"])),
    ("retrieval_miss / generation_error",
     lambda s: f"{s['diagnosis']['retrieval_miss']} / {s['diagnosis']['generation_error']}", None),
    ("judge agreement (share of votes = majority)",
     lambda s: f"{s['agreement']:.1%}" if s["agreement"] is not None else "n/a", lambda s: s["agreement"]),
    ("answer tokens in / out (total)", lambda s: f"{s['answer_tokens'][0]:,} / {s['answer_tokens'][1]:,}", None),
    ("answering cost: total / per question", lambda s: f"${s['answer_cost']:.4f} / ${s['answer_cost'] / s['n']:.5f}",
     lambda s: s["answer_cost"] / s["n"]),
    ("judging cost: total / per question", lambda s: f"${s['judge_cost']:.4f} / ${s['judge_cost'] / s['n']:.5f}",
     lambda s: s["judge_cost"] / s["n"]),
    ("avg answer latency", lambda s: f"{s['seconds']:.2f}s", None),
]


def metric_table(columns):
    """columns: {header: list of records}"""
    S = {h: stats(r) for h, r in columns.items()}
    out = ["| metric | " + " | ".join(columns) + " |", "|---|" + "---|" * len(columns)]
    out += [f"| {name} | " + " | ".join(fn(S[h]) for h in columns) + " |" for name, fn, _ in METRICS]
    return "\n".join(out)


def repeat_table(runs):
    """runs: list of record lists -> per-metric run values, mean and min-max."""
    S = [stats(r) for r in runs]
    head = " | ".join(f"run {i}" for i in range(1, len(runs) + 1))
    out = [f"| metric | {head} | mean | min-max |", "|---|" + "---|" * (len(runs) + 2)]
    for name, _, num in METRICS:
        if num is None:
            continue
        vals = [num(s) for s in S]
        if any(v is None for v in vals):
            continue
        money = "cost" in name
        fmt = (lambda v: f"${v:.5f}") if money else (lambda v: f"{v:.1%}")
        out.append(f"| {name} | " + " | ".join(fmt(v) for v in vals)
                   + f" | {fmt(statistics.mean(vals))} | {fmt(min(vals))} - {fmt(max(vals))} |")
    diag = [f"{s['diagnosis']['retrieval_miss']} / {s['diagnosis']['generation_error']}" for s in S]
    out.append("| retrieval_miss / generation_error | " + " | ".join(diag) + " | | |")
    return "\n".join(out)


def unstable_questions(runs):
    by_id = defaultdict(list)
    for recs in runs:
        for r in recs:
            by_id[r["id"]].append(r["verdict"])
    rows = [(qid, v) for qid, v in by_id.items() if len(set(v)) > 1]
    if not rows:
        return "(none: every question got the same verdict in every run)"
    out = ["| id | verdicts per run |", "|---|---|"]
    out += [f"| {qid} | {' / '.join(v)} |" for qid, v in rows]
    return "\n".join(out)


def changed_questions(before, after):
    old = {r["id"]: r for r in before}
    out = ["| id | type | before | after | before diagnosis | after diagnosis |", "|---|---|---|---|---|---|"]
    for r in after:
        b = old.get(r["id"])
        if b and (b["verdict"], b["diagnosis"]) != (r["verdict"], r["diagnosis"]):
            out.append(f"| {r['id']} | {r['type']} | {b['verdict']} | {r['verdict']} | "
                       f"{b['diagnosis'] or '-'} | {r['diagnosis'] or '-'} |")
    return "\n".join(out) if len(out) > 2 else "(none)"


def model_section(model, recs):
    s = stats(recs)
    n, v = s["n"], s["verdicts"]
    out = [f"## {model}", "",
           f"Correctness (all {n}): correct {pct(v['correct'], n)}, partial {pct(v['partial'], n)}, "
           f"incorrect {pct(v['incorrect'], n)}", "",
           "| type | n | correct | partial | incorrect |", "|---|---|---|---|---|"]
    for t in TYPES:
        if t in s["by_type"]:
            c, tn = s["by_type"][t], s["type_n"][t]
            out.append(f"| {t} | {tn} | " + " | ".join(pct(c[x], tn) for x in VERDICTS) + " |")
    f, nf = s["faith"], s["n_faith"]
    out += ["",
            f"- Citation accuracy (answerable, expected paragraph known): {pct(*s['citation'])}",
            f"- Faithfulness (answers that make claims): supported {pct(f['supported'], nf)}, "
            f"partially supported {pct(f['partially_supported'], nf)}, unsupported {pct(f['unsupported'], nf)}",
            f"- Refusal accuracy (unanswerable, by meaning): {pct(*s['refusal'])}; "
            f"exact refusal sentence: {pct(*s['exact_refusal'])}",
            f"- False-refusal rate (answerable): {pct(*s['false_refusal'])}",
            f"- Non-correct answers: retrieval_miss {s['diagnosis']['retrieval_miss']}, "
            f"generation_error {s['diagnosis']['generation_error']}",
            f"- Cost: answering ${s['answer_cost']:.4f} total (${s['answer_cost'] / n:.5f}/question); "
            f"judging ${s['judge_cost']:.4f} total (${s['judge_cost'] / n:.5f}/question)",
            "", "Non-correct answers:", "",
            "| id | type | verdict | facts | diagnosis | judge reason |", "|---|---|---|---|---|---|"]
    for r in recs:
        if r["verdict"] != "correct":
            reason = r["judge_reason"].replace("|", "/").replace("\n", " ")
            out.append(f"| {r['id']} | {r['type']} | {r['verdict']} | {r.get('facts_present', '')} | "
                       f"{r['diagnosis']} | {reason} |")
    return "\n".join(out)


def judge_sample(recs, n=10):
    sample = sorted(random.Random(SAMPLE_SEED).sample(recs, min(n, len(recs))), key=lambda r: r["id"])
    out = []
    for r in sample:
        out += [f"### {r['id']} ({r['type']}) - {r['verdict']}", "",
                f"- **Question:** {r['question']}",
                f"- **Key facts:** {r.get('key_facts') or '(unanswerable: must refuse)'}",
                f"- **System answer:** {' '.join(r['answer'].split())}",
                f"- **Fact statuses:** {r.get('fact_statuses') or '-'}",
                f"- **Verdict:** {r['verdict']}",
                f"- **Reason:** {r['judge_reason']}", ""]
    return "\n".join(out)


def header_lines(n, settings, routing):
    return [
        "# Answer eval summary", "",
        f"Questions: {QUESTIONS.relative_to(ROOT).as_posix()} ({n}). System called as a user would: k=5, "
        f"active documents only, retrieval method **{settings.method}**. Answers: {', '.join(sorted({llm.MODEL}))} "
        f"(temperature 0). Judge: {llm.JUDGE_PROVIDER} {llm.MODEL_JUDGE} (lowest thinking level, temperature 0, "
        f"structured JSON; majority of {settings.votes} call(s) for correctness, {settings.faith_votes} for "
        "faithfulness); correctness = key facts present / missing / "
        "contradicted, verdict computed in code.", "",
        f"**Judge changed in Step 5C**: Step 5B (v4_5B) was graded by gpt-5.4 with a holistic verdict; this run "
        f"is graded by {llm.JUDGE_PROVIDER} {llm.MODEL_JUDGE} checking key facts. Scores are therefore not directly "
        "comparable to v4_5B: a change can come from the system or from the judge.", "",
        "Notes: partial and incorrect answers are both \"non-correct\" and get a diagnosis: "
        "retrieval_miss when any expected paragraph is missing from the retrieved top 5, otherwise "
        "generation_error. Unanswerable questions count as correct when the answer refuses by meaning. "
        "Citation accuracy excludes rows whose expected source is not a paragraph (q007: metadata.csv). "
        "Costs count cached calls at their original cost.", "",
        "**Routing: " + ("none - every question in default current mode, as a user would ask it.**" if routing == "none"
                         else "MANUAL (not what a user gets) - change questions in compare mode; status questions "
                              "with the document-status record as an extra source; everything else copied from "
                              "the default run.**"), "",
    ]


def write_summary(all_recs, path, settings, baselines=(), routing="none"):
    first = next(iter(all_recs))
    parts = header_lines(len(all_recs[first]), settings, routing)
    if baselines:
        cols = {**{name: recs for name, recs in baselines}, **{f"this run ({m})": r for m, r in all_recs.items()}}
        parts += ["## Before / after", "", metric_table(cols), ""]
        for name, recs in baselines:
            parts += [f"Questions whose verdict or diagnosis changed vs {name}:", "",
                      changed_questions(recs, all_recs[first]), ""]
    if len(all_recs) > 1:
        parts += ["## Model comparison", "", metric_table(all_recs), ""]
    parts += [model_section(m, r) + "\n" for m, r in all_recs.items()]
    parts += [f"## 10 random judge verdicts ({first}, seed {SAMPLE_SEED})", "", judge_sample(all_recs[first])]
    path.write_text("\n".join(parts), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=[llm.MODEL])
    ap.add_argument("--limit", type=int, help="only the first N questions (smoke test)")
    ap.add_argument("--ids", nargs="+", help="only these question ids")
    ap.add_argument("--tag", help="suffix for the output files, e.g. v5_5C")
    ap.add_argument("--baseline", type=Path, nargs="+", default=[],
                    help="earlier answers_<model>.csv file(s) to compare the first model with")
    ap.add_argument("--routing", choices=["none", "manual"], default="none")
    ap.add_argument("--reuse", type=Path, help="scored CSV whose plain current-mode rows are copied, not re-run")
    ap.add_argument("--method", choices=METHODS, default=DEFAULT_METHOD, help="retrieval method")
    ap.add_argument("--judge-votes", type=int, default=1, help="majority of N judge calls")
    ap.add_argument("--faith-votes", type=int, help="votes for the faithfulness judge (default: --judge-votes)")
    ap.add_argument("--no-cache", action="store_true", help="send every answer and judge call again")
    ap.add_argument("--repeat", type=int, default=1, help="N runs with the cache bypassed; report mean / min-max")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if llm.MODEL_JUDGE in args.models:
        sys.exit(f"judge model {llm.MODEL_JUDGE} is also being graded; pick a different JUDGE_MODEL")

    with QUESTIONS.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.ids:
        rows = [r for r in rows if r["id"] in set(args.ids)]
    rows = rows[: args.limit]
    suffix = f"_{args.tag}" if args.tag else ""
    ids = {r["id"] for r in rows}

    def resolve(path):
        return path if path.is_absolute() else ROOT / path

    baselines = [(p.stem, [r for r in load_csv(resolve(p)) if r["id"] in ids]) for p in args.baseline]
    reuse = {r["id"]: r for r in load_csv(resolve(args.reuse))} if args.reuse else None
    RESULTS.mkdir(parents=True, exist_ok=True)

    if args.repeat > 1:
        model = args.models[0]
        runs = []
        for i in range(1, args.repeat + 1):
            settings = Settings(args.method, args.judge_votes, cache=False, faith_votes=args.faith_votes)
            print(f"\n######## repeat {i}/{args.repeat} (cache bypassed)")
            runs.append(run_model(rows, model, args.routing, settings))
            write_csv(runs[-1], RESULTS / f"answers_{model}{suffix}_r{i}.csv")
        parts = header_lines(len(rows), settings, args.routing)
        parts += [f"## Noise: {args.repeat} runs, cache bypassed ({model})", "", repeat_table(runs), "",
                  "Questions whose verdict differs between runs:", "", unstable_questions(runs), ""]
        out = RESULTS / f"answer_eval_summary{suffix}_repeat.md"
        out.write_text("\n".join(parts), encoding="utf-8")
        print(f"-> {out.relative_to(ROOT)}")
        return

    settings = Settings(args.method, args.judge_votes, cache=not args.no_cache, faith_votes=args.faith_votes)
    all_recs = {}
    for model in args.models:
        all_recs[model] = run_model(rows, model, args.routing, settings, reuse)
        out = RESULTS / f"answers_{model}{suffix}.csv"
        write_csv(all_recs[model], out)
        print(f"-> {out.relative_to(ROOT)}")
    summary = RESULTS / f"answer_eval_summary{suffix}.md"
    write_summary(all_recs, summary, settings, baselines, args.routing)
    print(f"-> {summary.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
