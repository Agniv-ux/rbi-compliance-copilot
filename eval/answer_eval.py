"""Answer-quality eval: run rag.answer.answer() on every question in eval/questions.csv and score it.

For each question the system is called exactly as a user would (k=5, active documents only).
Scores, per question:
  1. correctness  - LLM judge (LLM_MODEL_JUDGE, default gpt-5.4) compares the answer with
                    expected_answer + evidence_quote: correct / partial / incorrect.
                    Unanswerable questions: correct only if the answer is exactly the refusal
                    sentence (no judge call). An answerable question that gets the refusal is
                    a false refusal and is scored incorrect (no judge call).
  2. citation     - does any cited source match the expected doc + paragraph
                    (parsing and matching reused from eval/retrieval_eval.py; either target counts)?
  3. refusals     - refusal accuracy (unanswerable) and false-refusal rate (answerable).
  4. faithfulness - second judge call: is every claim supported by the sources it cites?
  5. diagnosis    - for every non-correct answer: was an expected paragraph in the retrieved
                    top 5? -> retrieval_miss / generation_error.

The judge runs with reasoning effort "none", temperature 0 and a strict JSON schema, so the same
input gets the same verdict.

Outputs: eval/results/answers_<model>.csv per model, eval/results/answer_eval_summary.md.

Usage:
    python eval/answer_eval.py                          # gpt-5.4-mini and gpt-5.4-nano
    python eval/answer_eval.py --models gpt-5.4-mini --limit 5
"""
import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
from rag import llm  # noqa: E402
from rag.answer import NOT_COVERED, answer  # noqa: E402
from retrieval_eval import describe, matches, parse_targets  # noqa: E402

QUESTIONS = ROOT / "eval" / "questions.csv"
RESULTS = ROOT / "eval" / "results"
SUMMARY = RESULTS / "answer_eval_summary.md"
TYPES = ("simple", "multi_part", "change", "status", "unanswerable")
VERDICTS = ("correct", "partial", "incorrect")
JUDGE_WORKERS = 6
SAMPLE_SEED = 42

# ---- judge prompts ------------------------------------------------------------------------

CORRECTNESS_SYSTEM = """You grade answers from a question-answering system about RBI (Reserve Bank of India) regulations.

You get: the question, the expected answer (written by a human expert), the evidence quote from the regulation that the expected answer is based on, and the system's answer.

Decide whether the system's answer conveys the facts of the expected answer.
- "correct": every key fact of the expected answer is present (numbers, periods, amounts, conditions, entities) and nothing in the answer contradicts the expected answer or the evidence.
- "partial": no fact is wrong, but at least one key fact of the expected answer is missing or stated too vaguely (e.g. a qualifier like "at least" or a condition is dropped).
- "incorrect": a key fact is wrong or contradicted, most of the expected answer is missing, or the system refused to answer.

Rules:
- Additional facts that are correct and consistent with the evidence must NOT lower the verdict. Only missing or wrong facts do.
- Judge meaning, not wording: "two years" = "2 years", "Rs 50,000" = "₹50,000", paraphrases are fine.
- Ignore citation markers such as [S1].
- missing_facts: key facts of the expected answer that the system's answer lacks (empty list if none).
- wrong_facts: statements in the system's answer that contradict the expected answer or evidence (empty list if none).
- reason: one or two sentences."""

CORRECTNESS_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "missing_facts": {"type": "array", "items": {"type": "string"}},
        "wrong_facts": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "missing_facts", "wrong_facts", "reason"],
    "additionalProperties": False,
}

FAITHFULNESS_SYSTEM = """You check whether an answer is faithful to the sources it cites.

You get an answer that contains citation markers like [S1], and the full text of each cited source.
Split the answer into its factual claims. For each claim, check whether the source(s) cited for it (the marker(s) right after the claim, or at the end of the sentence or list) state it. A claim with no citation of its own is checked against the sources cited for its sentence or paragraph.

- "supported": every claim is stated in, or directly follows from, the text of the sources it cites.
- "partially_supported": most claims are supported, but at least one claim (or a number, period or condition in it) is not in its cited sources.
- "unsupported": the main claim(s) are not in the cited sources.

Judge only against the given source text, not against your own knowledge, even if a claim is true.
unsupported_claims: the claims that are not supported (empty list if none). reason: one or two sentences."""

FAITHFULNESS_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["supported", "partially_supported", "unsupported"]},
        "unsupported_claims": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "unsupported_claims", "reason"],
    "additionalProperties": False,
}


def judge(system, user, schema):
    r = llm.generate(system, user, model=llm.MODEL_JUDGE, temperature=0, json_schema=schema)
    return json.loads(r["text"]), r


def judge_correctness(row, ans):
    user = (f"Question: {row['question']}\n\n"
            f"Expected answer: {row['expected_answer']}\n\n"
            f"Evidence quote: {row['evidence_quote']}\n\n"
            f"System answer:\n{ans}")
    return judge(CORRECTNESS_SYSTEM, user, CORRECTNESS_SCHEMA)


def judge_faithfulness(ans, cited):
    sources = "\n\n---\n\n".join(f"[{c['source']}] {c['title']} - {c['para']}\n{c['text'].strip()}"
                                 for c in cited)
    user = f"Answer:\n{ans}\n\n===\n\nCited sources:\n\n{sources}"
    return judge(FAITHFULNESS_SYSTEM, user, FAITHFULNESS_SCHEMA)


# ---- per-question scoring -----------------------------------------------------------------

def as_hit(source):
    """answer() source record -> the dict shape retrieval_eval.matches() expects."""
    return {"doc": source["doc"], "region": source["region"], "para": source["para_no"],
            "section": source["section"]}


def any_match(sources, targets):
    return any(matches(as_hit(s), t) for s in sources for t in targets)


def fmt_sources(sources):
    return " || ".join(f"{s['source']} {s['doc']} {s['para']} p{s['pages']}" for s in sources)


def answer_row(row, model):
    r = answer(row["question"], model=model)  # defaults: k=5, statuses=("active",)
    targets, unparsed = parse_targets(row)
    unanswerable = row["type"] == "unanswerable"
    return {
        "id": row["id"], "type": row["type"], "question": row["question"],
        "expected_answer": row["expected_answer"],
        "expected_source": "; ".join(describe(t) for t in targets) or "; ".join(unparsed),
        "answer": r["answer"],
        "refused": int(r["answer"].strip() == NOT_COVERED),
        "cited": fmt_sources(r["citations"]),
        "retrieved": fmt_sources(r["sources"]),
        "expected_in_top5": "" if not targets else int(any_match(r["sources"], targets)),
        "citation_match": "" if unanswerable or not targets else int(any_match(r["citations"], targets)),
        "answer_input_tokens": r["input_tokens"], "answer_output_tokens": r["output_tokens"],
        "answer_reasoning_tokens": r["reasoning_tokens"], "answer_cost_usd": r["cost_usd"],
        "answer_seconds": r["seconds"],
        "_row": row, "_citations": r["citations"],
    }


def score_row(rec):
    row, unanswerable = rec["_row"], rec["type"] == "unanswerable"
    judge_in = judge_out = 0
    judge_cost = 0.0

    def add_usage(r):
        nonlocal judge_in, judge_out, judge_cost
        judge_in += r["input_tokens"]
        judge_out += r["output_tokens"]
        judge_cost += r["cost_usd"] or 0.0

    # 1. correctness
    if unanswerable:
        ok = rec["refused"]
        c = {"verdict": "correct" if ok else "incorrect", "missing_facts": [], "wrong_facts": [],
             "reason": "exact refusal sentence" if ok else "should have refused (exact refusal sentence)"}
    elif rec["refused"]:
        c = {"verdict": "incorrect", "missing_facts": [row["expected_answer"]], "wrong_facts": [],
             "reason": "false refusal: the question is answerable from the documents"}
    else:
        c, r = judge_correctness(row, rec["answer"])
        add_usage(r)

    # 4. faithfulness (only for answers that make claims)
    if rec["refused"]:
        f = {"verdict": "", "unsupported_claims": [], "reason": "refusal: nothing to check"}
    elif not rec["_citations"]:
        f = {"verdict": "unsupported", "unsupported_claims": [], "reason": "answer cites no sources"}
    else:
        f, r = judge_faithfulness(rec["answer"], rec["_citations"])
        add_usage(r)

    # 5. diagnosis
    if c["verdict"] == "correct":
        diagnosis = ""
    elif unanswerable:
        diagnosis = "generation_error"  # nothing to retrieve; the model should have refused
    else:
        diagnosis = "generation_error" if rec["expected_in_top5"] == 1 else "retrieval_miss"

    rec.update({
        "verdict": c["verdict"], "missing_facts": "; ".join(c["missing_facts"]),
        "wrong_facts": "; ".join(c["wrong_facts"]), "judge_reason": c["reason"],
        "faithfulness": f["verdict"], "unsupported_claims": "; ".join(f["unsupported_claims"]),
        "faithfulness_reason": f["reason"], "diagnosis": diagnosis,
        "judge_input_tokens": judge_in, "judge_output_tokens": judge_out,
        "judge_cost_usd": round(judge_cost, 6),
    })
    return rec


def run_model(rows, model):
    print(f"\n== {model}: answering {len(rows)} questions", flush=True)
    recs = []
    for row in rows:  # sequential: search() shares one DB connection
        recs.append(answer_row(row, model))
        print(f"  {row['id']}: {'refused' if recs[-1]['refused'] else 'answered'}", flush=True)
    print(f"== {model}: judging with {llm.MODEL_JUDGE}", flush=True)
    with ThreadPoolExecutor(JUDGE_WORKERS) as pool:
        recs = list(pool.map(score_row, recs))
    for rec in recs:
        print(f"  {rec['id']}: {rec['verdict']:<9} {rec['faithfulness'] or '-':<19} {rec['diagnosis']}")
    return recs


def write_csv(recs, model):
    path = RESULTS / f"answers_{model}.csv"
    fields = [k for k in recs[0] if not k.startswith("_")]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(recs)
    return path


# ---- summary ------------------------------------------------------------------------------

def pct(num, den):
    return f"{num / den:.1%} ({num}/{den})" if den else "n/a"


def stats(recs):
    answerable = [r for r in recs if r["type"] != "unanswerable"]
    unanswerable = [r for r in recs if r["type"] == "unanswerable"]
    cit = [r for r in answerable if r["citation_match"] != ""]
    faith = [r for r in recs if r["faithfulness"]]
    n = len(recs)
    return {
        "n": n,
        "verdicts": Counter(r["verdict"] for r in recs),
        "answerable_verdicts": Counter(r["verdict"] for r in answerable),
        "n_answerable": len(answerable),
        "citation": (sum(r["citation_match"] for r in cit), len(cit)),
        "faith": Counter(r["faithfulness"] for r in faith), "n_faith": len(faith),
        "refusal": (sum(r["refused"] for r in unanswerable), len(unanswerable)),
        "false_refusal": (sum(r["refused"] for r in answerable), len(answerable)),
        "diagnosis": Counter(r["diagnosis"] for r in recs if r["diagnosis"]),
        "answer_cost": sum(r["answer_cost_usd"] or 0 for r in recs),
        "judge_cost": sum(r["judge_cost_usd"] for r in recs),
        "answer_tokens": (sum(r["answer_input_tokens"] for r in recs), sum(r["answer_output_tokens"] for r in recs)),
        "seconds": sum(r["answer_seconds"] for r in recs) / n,
    }


def model_section(model, recs):
    s = stats(recs)
    n, v = s["n"], s["verdicts"]
    out = [f"## {model}", "",
           f"Correctness (all {n}): correct {pct(v['correct'], n)}, partial {pct(v['partial'], n)}, "
           f"incorrect {pct(v['incorrect'], n)}", "",
           "| type | n | correct | partial | incorrect |", "|---|---|---|---|---|"]
    by_type = defaultdict(list)
    for r in recs:
        by_type[r["type"]].append(r)
    for t in TYPES:
        g = by_type.get(t, [])
        if g:
            c = Counter(r["verdict"] for r in g)
            out.append(f"| {t} | {len(g)} | " + " | ".join(pct(c[x], len(g)) for x in VERDICTS) + " |")
    f, nf = s["faith"], s["n_faith"]
    out += ["",
            f"- Citation accuracy (answerable, expected paragraph known): {pct(*s['citation'])}",
            f"- Faithfulness (answers that make claims): supported {pct(f['supported'], nf)}, "
            f"partially supported {pct(f['partially_supported'], nf)}, unsupported {pct(f['unsupported'], nf)}",
            f"- Refusal accuracy (unanswerable): {pct(*s['refusal'])}",
            f"- False-refusal rate (answerable): {pct(*s['false_refusal'])}",
            f"- Non-correct answers: retrieval_miss {s['diagnosis']['retrieval_miss']}, "
            f"generation_error {s['diagnosis']['generation_error']}",
            f"- Cost: answering ${s['answer_cost']:.4f} total (${s['answer_cost'] / n:.5f}/question); "
            f"judging ${s['judge_cost']:.4f} total (${s['judge_cost'] / n:.5f}/question)",
            "", "Non-correct answers:", "",
            "| id | type | verdict | diagnosis | judge reason |", "|---|---|---|---|---|"]
    for r in recs:
        if r["verdict"] != "correct":
            reason = r["judge_reason"].replace("|", "/").replace("\n", " ")
            out.append(f"| {r['id']} | {r['type']} | {r['verdict']} | {r['diagnosis']} | {reason} |")
    return "\n".join(out)


def comparison(all_recs):
    models = list(all_recs)
    S = {m: stats(r) for m, r in all_recs.items()}
    rows = [
        ("correct (all)", lambda s: pct(s["verdicts"]["correct"], s["n"])),
        ("partial (all)", lambda s: pct(s["verdicts"]["partial"], s["n"])),
        ("incorrect (all)", lambda s: pct(s["verdicts"]["incorrect"], s["n"])),
        ("correct (answerable)", lambda s: pct(s["answerable_verdicts"]["correct"], s["n_answerable"])),
        ("citation accuracy", lambda s: pct(*s["citation"])),
        ("faithfulness: supported", lambda s: pct(s["faith"]["supported"], s["n_faith"])),
        ("refusal accuracy", lambda s: pct(*s["refusal"])),
        ("false-refusal rate", lambda s: pct(*s["false_refusal"])),
        ("retrieval_miss / generation_error",
         lambda s: f"{s['diagnosis']['retrieval_miss']} / {s['diagnosis']['generation_error']}"),
        ("answer tokens in / out (total)", lambda s: f"{s['answer_tokens'][0]:,} / {s['answer_tokens'][1]:,}"),
        ("answering cost: total / per question", lambda s: f"${s['answer_cost']:.4f} / ${s['answer_cost'] / s['n']:.5f}"),
        ("judging cost: total / per question", lambda s: f"${s['judge_cost']:.4f} / ${s['judge_cost'] / s['n']:.5f}"),
        ("avg answer latency", lambda s: f"{s['seconds']:.2f}s"),
    ]
    out = ["| metric | " + " | ".join(models) + " |", "|---|" + "---|" * len(models)]
    out += [f"| {name} | " + " | ".join(fn(S[m]) for m in models) + " |" for name, fn in rows]
    return "\n".join(out)


def judge_sample(recs, n=10):
    sample = sorted(random.Random(SAMPLE_SEED).sample(recs, min(n, len(recs))), key=lambda r: r["id"])
    out = []
    for r in sample:
        out += [f"### {r['id']} ({r['type']}) - {r['verdict']}", "",
                f"- **Question:** {r['question']}",
                f"- **Expected:** {r['expected_answer']}",
                f"- **System answer:** {' '.join(r['answer'].split())}",
                f"- **Verdict:** {r['verdict']}"
                + (f" (missing: {r['missing_facts']})" if r["missing_facts"] else "")
                + (f" (wrong: {r['wrong_facts']})" if r["wrong_facts"] else ""),
                f"- **Reason:** {r['judge_reason']}", ""]
    return "\n".join(out)


def write_summary(all_recs):
    first = next(iter(all_recs))
    parts = [
        "# Answer eval summary", "",
        f"Questions: {QUESTIONS.relative_to(ROOT).as_posix()} ({len(all_recs[first])}). "
        f"System called as a user would: k=5, active documents only. "
        f"Judge: {llm.MODEL_JUDGE} (reasoning effort none, temperature 0, strict JSON schema).", "",
        "Notes: partial and incorrect answers are both \"non-correct\" and get a diagnosis. "
        "Change/status questions whose expected source is a repealed or superseded document cannot "
        "retrieve it with active-only search, so they show up as retrieval_miss by design. "
        "Citation accuracy excludes rows whose expected source is not a paragraph (q007: metadata.csv).", "",
        "## mini vs nano", "", comparison(all_recs), "",
    ]
    parts += [model_section(m, r) + "\n" for m, r in all_recs.items()]
    parts += [f"## 10 random judge verdicts ({first}, seed {SAMPLE_SEED})", "", judge_sample(all_recs[first])]
    SUMMARY.write_text("\n".join(parts), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=[llm.MODEL, llm.MODEL_CHEAP])
    ap.add_argument("--limit", type=int, help="only the first N questions (smoke test)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if llm.MODEL_JUDGE in args.models:
        sys.exit(f"judge model {llm.MODEL_JUDGE} is also being graded; pick a different LLM_MODEL_JUDGE")

    with QUESTIONS.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))[: args.limit]

    RESULTS.mkdir(parents=True, exist_ok=True)
    all_recs = {}
    for model in args.models:
        all_recs[model] = run_model(rows, model)
        print(f"-> {write_csv(all_recs[model], model).relative_to(ROOT)}")
    write_summary(all_recs)
    print(f"-> {SUMMARY.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
