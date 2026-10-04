"""Answer-quality eval: run rag.answer.answer() on every question in eval/questions.csv and score it.

For each question the system is called exactly as a user would (k=5, active documents only).
Scores, per question:
  1. correctness  - LLM judge (LLM_MODEL_JUDGE, default gpt-5.4) compares the answer with
                    expected_answer + evidence_quote, and also sees the full text of the cited
                    sources, so extra facts those sources support are not counted as wrong:
                    correct / partial / incorrect. The same call says whether the answer is a
                    refusal (declines the whole question), judged by meaning.
                    The exact refusal sentence needs no judge call.
  2. citation     - does any cited source match the expected doc + paragraph
                    (parsing and matching reused from eval/retrieval_eval.py; either target counts)?
  3. refusals     - unanswerable: correct if the answer refuses (by meaning); exact-sentence
                    refusals are reported separately. Answerable: refusal = false refusal.
  4. faithfulness - second judge call: is every claim supported by the sources it cites?
  5. diagnosis    - for every non-correct answer: were ALL expected paragraphs in the retrieved
                    top 5? yes -> generation_error, any missing -> retrieval_miss.

The judge runs with reasoning effort "none", temperature 0 and a strict JSON schema, so the same
input gets the same verdict.

Outputs: eval/results/answers_<model>[_<tag>].csv per model, eval/results/answer_eval_summary[_<tag>].md.

Usage:
    python eval/answer_eval.py                          # gpt-5.4-mini and gpt-5.4-nano
    python eval/answer_eval.py --models gpt-5.4-mini --limit 5
    python eval/answer_eval.py --models gpt-5.4-mini --tag v3_5A \
        --baseline eval/results/answers_gpt-5.4-mini.csv   # adds a before/after table
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
TYPES = ("simple", "multi_part", "change", "status", "unanswerable")
VERDICTS = ("correct", "partial", "incorrect")
JUDGE_WORKERS = 6
SAMPLE_SEED = 42

# ---- judge prompts ------------------------------------------------------------------------

CORRECTNESS_SYSTEM = """You grade answers from a question-answering system about RBI (Reserve Bank of India) regulations.

You get: the question, the expected answer (written by a human expert), the evidence quote from the regulation that the expected answer is based on, the system's answer, and the full text of the sources the system cited.

Decide whether the system's answer conveys the facts of the expected answer.
- "correct": every key fact of the expected answer is present (numbers, periods, amounts, conditions, entities) and nothing in the answer contradicts the expected answer or the evidence.
- "partial": no fact is wrong, but at least one key fact of the expected answer is missing or stated too vaguely (e.g. a qualifier like "at least" or a condition is dropped).
- "incorrect": a key fact is wrong or contradicted, most of the expected answer is missing, or the system refused to answer.

Rules:
- Additional facts must NOT lower the verdict if they are correct: consistent with the evidence, or stated in the cited sources' text. Only missing facts, and facts that contradict the evidence or are not supported by any given text, count against the answer.
- Judge meaning, not wording: "two years" = "2 years", "Rs 50,000" = "₹50,000", paraphrases are fine.
- Ignore citation markers such as [S1].
- missing_facts: key facts of the expected answer that the system's answer lacks (empty list if none).
- wrong_facts: statements in the system's answer that contradict the expected answer or evidence, or that no given text supports (empty list if none).
- refused: true only if the answer declines the whole question (e.g. says the information is not in the documents and gives no answer to it). An answer that answers part of the question and says another part is not covered is not a refusal.
- reason: one or two sentences."""

CORRECTNESS_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "missing_facts": {"type": "array", "items": {"type": "string"}},
        "wrong_facts": {"type": "array", "items": {"type": "string"}},
        "refused": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "missing_facts", "wrong_facts", "refused", "reason"],
    "additionalProperties": False,
}

REFUSAL_SYSTEM = """A question-answering system about RBI regulations must refuse questions that its documents do not answer. The question below is NOT answered by its documents.

Decide whether the system's answer refuses: it clearly says the documents do not provide this information, and it does not give a substantive answer to the question (no specific requirement, number, rule or recommendation presented as the answer). Mentioning what the documents do say about related topics is fine as long as it is not presented as the answer.

refused: true if the answer refuses, false otherwise. reason: one sentence."""

REFUSAL_SCHEMA = {
    "type": "object",
    "properties": {"refused": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["refused", "reason"],
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


def format_cited(cited):
    if not cited:
        return "(the answer cites no sources)"
    return "\n\n---\n\n".join(f"[{c['source']}] {c['title']} - {c['para']}\n{c['text'].strip()}" for c in cited)


def judge_correctness(row, ans, cited):
    user = (f"Question: {row['question']}\n\n"
            f"Expected answer: {row['expected_answer']}\n\n"
            f"Evidence quote: {row['evidence_quote']}\n\n"
            f"System answer:\n{ans}\n\n===\n\n"
            f"Cited sources:\n\n{format_cited(cited)}")
    return judge(CORRECTNESS_SYSTEM, user, CORRECTNESS_SCHEMA)


def judge_refusal(row, ans):
    return judge(REFUSAL_SYSTEM, f"Question: {row['question']}\n\nSystem answer:\n{ans}", REFUSAL_SCHEMA)


def judge_faithfulness(ans, cited):
    user = f"Answer:\n{ans}\n\n===\n\nCited sources:\n\n{format_cited(cited)}"
    return judge(FAITHFULNESS_SYSTEM, user, FAITHFULNESS_SCHEMA)


# ---- per-question scoring -----------------------------------------------------------------

def as_hit(source):
    """answer() source record -> the dict shape retrieval_eval.matches() expects."""
    return {"doc": source["doc"], "region": source["region"], "para": source["para_no"],
            "section": source["section"]}


def found(sources, target):
    return any(matches(as_hit(s), target) for s in sources)


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
        "exact_refusal": int(r["answer"].strip() == NOT_COVERED),
        "cited": fmt_sources(r["citations"]),
        "retrieved": fmt_sources(r["sources"]),
        "expected_in_top5": "" if not targets else int(any(found(r["sources"], t) for t in targets)),
        "all_expected_in_top5": "" if not targets else int(all(found(r["sources"], t) for t in targets)),
        "citation_match": "" if unanswerable or not targets else int(any(found(r["citations"], t) for t in targets)),
        "answer_input_tokens": r["input_tokens"], "answer_output_tokens": r["output_tokens"],
        "answer_reasoning_tokens": r["reasoning_tokens"], "answer_cost_usd": r["cost_usd"],
        "answer_seconds": r["seconds"],
        "_row": row, "_citations": r["citations"],
    }


def score_row(rec):
    row, unanswerable, exact = rec["_row"], rec["type"] == "unanswerable", rec["exact_refusal"]
    judge_in = judge_out = 0
    judge_cost = 0.0

    def add_usage(r):
        nonlocal judge_in, judge_out, judge_cost
        judge_in += r["input_tokens"]
        judge_out += r["output_tokens"]
        judge_cost += r["cost_usd"] or 0.0

    # 1 + 3. correctness and refusal
    if unanswerable:
        if exact:
            refused, reason = True, "exact refusal sentence"
        else:
            j, r = judge_refusal(row, rec["answer"])
            add_usage(r)
            refused, reason = j["refused"], j["reason"]
        c = {"verdict": "correct" if refused else "incorrect", "missing_facts": [], "wrong_facts": [],
             "refused": refused, "reason": reason}
    elif exact:
        c = {"verdict": "incorrect", "missing_facts": [row["expected_answer"]], "wrong_facts": [],
             "refused": True, "reason": "false refusal: the question is answerable from the documents"}
    else:
        c, r = judge_correctness(row, rec["answer"], rec["_citations"])
        add_usage(r)

    # 4. faithfulness (only for answers that make claims)
    if c["refused"]:
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
        diagnosis = "generation_error" if rec["all_expected_in_top5"] == 1 else "retrieval_miss"

    rec.update({
        "refused": int(c["refused"]),
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
        print(f"  {row['id']}: {'refused' if recs[-1]['exact_refusal'] else 'answered'}", flush=True)
    print(f"== {model}: judging with {llm.MODEL_JUDGE}", flush=True)
    with ThreadPoolExecutor(JUDGE_WORKERS) as pool:
        recs = list(pool.map(score_row, recs))
    for rec in recs:
        print(f"  {rec['id']}: {rec['verdict']:<9} {rec['faithfulness'] or '-':<19} {rec['diagnosis']}")
    return recs


def write_csv(recs, path):
    fields = [k for k in recs[0] if not k.startswith("_")]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(recs)


def load_csv(path):
    """Results CSV -> records with the numeric fields stats() needs (older CSVs lack some columns)."""
    with path.open(encoding="utf-8") as f:
        recs = list(csv.DictReader(f))
    for r in recs:
        for k in ("refused", "exact_refusal", "citation_match"):
            if r.get(k) not in (None, ""):
                r[k] = int(r[k])
        r.setdefault("exact_refusal", r.get("refused", 0))  # Step 4: refused == exact sentence
        for k in ("answer_cost_usd", "judge_cost_usd", "answer_seconds"):
            r[k] = float(r[k] or 0)
        for k in ("answer_input_tokens", "answer_output_tokens"):
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
    }


METRICS = [
    ("correct (all)", lambda s: pct(s["verdicts"]["correct"], s["n"])),
    ("partial (all)", lambda s: pct(s["verdicts"]["partial"], s["n"])),
    ("incorrect (all)", lambda s: pct(s["verdicts"]["incorrect"], s["n"])),
    *[(f"correct: {t}", lambda s, t=t: pct(s["by_type"].get(t, Counter())["correct"], s["type_n"].get(t, 0)))
      for t in TYPES],
    ("correct (answerable)", lambda s: pct(s["answerable_verdicts"]["correct"], s["n_answerable"])),
    ("citation accuracy", lambda s: pct(*s["citation"])),
    ("faithfulness: supported", lambda s: pct(s["faith"]["supported"], s["n_faith"])),
    ("faithfulness: partially supported", lambda s: pct(s["faith"]["partially_supported"], s["n_faith"])),
    ("faithfulness: unsupported", lambda s: pct(s["faith"]["unsupported"], s["n_faith"])),
    ("refusal accuracy (by meaning)", lambda s: pct(*s["refusal"])),
    ("refusal: exact sentence", lambda s: pct(*s["exact_refusal"])),
    ("false-refusal rate", lambda s: pct(*s["false_refusal"])),
    ("retrieval_miss / generation_error",
     lambda s: f"{s['diagnosis']['retrieval_miss']} / {s['diagnosis']['generation_error']}"),
    ("answer tokens in / out (total)", lambda s: f"{s['answer_tokens'][0]:,} / {s['answer_tokens'][1]:,}"),
    ("answering cost: total / per question", lambda s: f"${s['answer_cost']:.4f} / ${s['answer_cost'] / s['n']:.5f}"),
    ("judging cost: total / per question", lambda s: f"${s['judge_cost']:.4f} / ${s['judge_cost'] / s['n']:.5f}"),
    ("avg answer latency", lambda s: f"{s['seconds']:.2f}s"),
]


def metric_table(columns):
    """columns: {header: list of records}"""
    S = {h: stats(r) for h, r in columns.items()}
    out = ["| metric | " + " | ".join(columns) + " |", "|---|" + "---|" * len(columns)]
    out += [f"| {name} | " + " | ".join(fn(S[h]) for h in columns) + " |" for name, fn in METRICS]
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
            "| id | type | verdict | diagnosis | judge reason |", "|---|---|---|---|---|"]
    for r in recs:
        if r["verdict"] != "correct":
            reason = r["judge_reason"].replace("|", "/").replace("\n", " ")
            out.append(f"| {r['id']} | {r['type']} | {r['verdict']} | {r['diagnosis']} | {reason} |")
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


def write_summary(all_recs, path, baseline=None):
    first = next(iter(all_recs))
    parts = [
        "# Answer eval summary", "",
        f"Questions: {QUESTIONS.relative_to(ROOT).as_posix()} ({len(all_recs[first])}). "
        f"System called as a user would: k=5, active documents only. "
        f"Judge: {llm.MODEL_JUDGE} (reasoning effort none, temperature 0, strict JSON schema); "
        f"the correctness judge also sees the cited sources' text.", "",
        "Notes: partial and incorrect answers are both \"non-correct\" and get a diagnosis: "
        "retrieval_miss when any expected paragraph is missing from the retrieved top 5, otherwise "
        "generation_error. Unanswerable questions count as correct when the answer refuses by meaning. "
        "Citation accuracy excludes rows whose expected source is not a paragraph (q007: metadata.csv).", "",
    ]
    if baseline:
        name, recs = baseline
        cols = {f"before ({name})": recs, **{f"after ({m})": r for m, r in all_recs.items()}}
        parts += ["## Before / after", "", metric_table(cols), "",
                  "Questions whose verdict or diagnosis changed:", "", changed_questions(recs, all_recs[first]), ""]
    if len(all_recs) > 1:
        parts += ["## Model comparison", "", metric_table(all_recs), ""]
    parts += [model_section(m, r) + "\n" for m, r in all_recs.items()]
    parts += [f"## 10 random judge verdicts ({first}, seed {SAMPLE_SEED})", "", judge_sample(all_recs[first])]
    path.write_text("\n".join(parts), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=[llm.MODEL, llm.MODEL_CHEAP])
    ap.add_argument("--limit", type=int, help="only the first N questions (smoke test)")
    ap.add_argument("--tag", help="suffix for the output files, e.g. v3_5A")
    ap.add_argument("--baseline", type=Path, help="earlier answers_<model>.csv to compare the first model with")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if llm.MODEL_JUDGE in args.models:
        sys.exit(f"judge model {llm.MODEL_JUDGE} is also being graded; pick a different LLM_MODEL_JUDGE")

    with QUESTIONS.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))[: args.limit]
    suffix = f"_{args.tag}" if args.tag else ""
    baseline = None
    if args.baseline:
        path = args.baseline if args.baseline.is_absolute() else ROOT / args.baseline
        ids = {r["id"] for r in rows}
        baseline = (path.stem, [r for r in load_csv(path) if r["id"] in ids])

    RESULTS.mkdir(parents=True, exist_ok=True)
    all_recs = {}
    for model in args.models:
        all_recs[model] = run_model(rows, model)
        out = RESULTS / f"answers_{model}{suffix}.csv"
        write_csv(all_recs[model], out)
        print(f"-> {out.relative_to(ROOT)}")
    summary = RESULTS / f"answer_eval_summary{suffix}.md"
    write_summary(all_recs, summary, baseline)
    print(f"-> {summary.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
