"""LLM judges for the answer eval (JUDGE_PROVIDER / JUDGE_MODEL, e.g. Gemini Flash; lowest
reasoning / thinking level, temperature 0, structured JSON output). Shared by eval/answer_eval.py and eval/judge_agreement.py.

correctness - checks each key fact of the question (eval/questions.csv key_facts) against the
              answer: present / missing / contradicted. The verdict is computed in code:
                all present and none contradicted -> correct
                any contradicted, or none present  -> incorrect
                otherwise (some present)           -> partial
              Extra facts never count against the answer (they are not key facts). The same call
              says whether the answer is a refusal (declines the whole question).
refusal     - for unanswerable questions: does the answer refuse, by meaning?
faithful    - is every claim supported by the sources it cites?

votes=N makes N independent calls (separate cache entries) and takes the majority: per key fact
for correctness (ties -> "missing"), per verdict for faithfulness (ties -> partially_supported),
per boolean for refusals (ties -> not refused). `agreement` is the share of calls that agree with
the majority (1.0 = unanimous), averaged over facts for correctness.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from rag import llm  # noqa: E402
from rag.answer import source_block  # noqa: E402

VERDICTS = ("correct", "partial", "incorrect")
FACT_STATUSES = ("present", "missing", "contradicted")
FACT_SEP = " | "

CORRECTNESS_SYSTEM = """You grade answers from a question-answering system about RBI (Reserve Bank of India) regulations.

You get: the question, a numbered list of key facts that a correct answer must convey (written by a human expert), the evidence quote from the regulation, the system's answer, and the full text of the sources the system cited.

For EACH key fact decide:
- "present": the answer states this fact (same meaning; paraphrase is fine; "two years" = "2 years", "Rs 50,000" = "₹50,000"). Qualifiers in the fact (e.g. "at least", "only", a condition or exception) must also be conveyed.
- "missing": the answer does not state it, or states it too vaguely, or drops a qualifier or condition that is part of the fact.
- "contradicted": the answer states something incompatible with the fact (a different number, period or entity, or the opposite yes/no).

Rules:
- Only the SYSTEM ANSWER counts. The cited sources and the evidence quote are context, not part of the answer: a fact that appears in a source but not in the answer itself is "missing".
- Judge only the listed key facts. Other statements in the answer do not affect any key fact unless they contradict it.
- Ignore citation markers such as [S1].
- Saying that the documents do not cover a point is "missing" for that point, not "contradicted".
- note: for each fact, a few words quoting or pointing to where the answer states it, or what is missing / wrong.
- refused: true only if the answer declines the whole question (e.g. says the information is not in the documents and gives no answer). An answer that answers part of the question and says another part is not covered is not a refusal.
- reason: one or two sentences summarising your assessment."""


def correctness_schema(n_facts):
    return {
        "type": "object",
        "properties": {
            "facts": {
                "type": "array",
                "minItems": n_facts, "maxItems": n_facts,
                "items": {
                    "type": "object",
                    "properties": {
                        "fact": {"type": "integer"},
                        "status": {"type": "string", "enum": list(FACT_STATUSES)},
                        "note": {"type": "string"},
                    },
                    "required": ["fact", "status", "note"],
                    "additionalProperties": False,
                },
            },
            "refused": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["facts", "refused", "reason"],
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

You get an answer that contains citation markers like [S1], and each cited source exactly as the answering system saw it: a header line (document title, status tag, chapter, section, paragraph, page) and its text. The header is part of the source.
Split the answer into its factual claims. For each claim, check whether the source(s) cited for it (the marker(s) right after the claim, or at the end of the sentence or list) state it. A claim with no citation of its own is checked against the sources cited for its sentence or paragraph.

- "supported": every claim is stated in, or directly follows from, the cited sources (header or text).
- "partially_supported": most claims are supported, but at least one claim (or a number, period or condition in it) is not in its cited sources.
- "unsupported": the main claim(s) are not in the cited sources.

Judge only against the given sources, not against your own knowledge, even if a claim is true.
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


def split_facts(key_facts):
    return [f.strip() for f in (key_facts or "").split(FACT_SEP.strip()) if f.strip()]


def format_cited(cited):
    """The cited sources exactly as the answer model saw them (same header and text)."""
    if not cited:
        return "(the answer cites no sources)"
    return "\n\n---\n\n".join(source_block(c) for c in cited)


def verdict_from_facts(statuses):
    if not statuses or "contradicted" in statuses or "present" not in statuses:
        return "incorrect"
    return "correct" if all(s == "present" for s in statuses) else "partial"


def _majority(values, tie):
    counts = Counter(values).most_common()
    if len(counts) > 1 and counts[0][1] == counts[1][1]:
        top = tie
    else:
        top = counts[0][0]
    return top, sum(v == top for v in values) / len(values)


class Judge:
    def __init__(self, llmc, votes=1, model=None, faith_votes=None):
        self.llmc, self.votes, self.model = llmc, votes, model or llm.MODEL_JUDGE
        self.faith_votes = faith_votes or votes
        self.provider = llm.JUDGE_PROVIDER
        self.usage = []  # one generate() result per call

    def _call(self, system, user, schema, votes=None):
        out = []
        for v in range(votes or self.votes):
            r = self.llmc.generate(system, user, model=self.model, temperature=0, json_schema=schema, vote=v,
                                   provider=self.provider)
            self.usage.append(r)
            out.append(json.loads(r["text"]))
        return out

    def correctness(self, row, answer_text, cited):
        facts = split_facts(row["key_facts"])
        user = (f"Question: {row['question']}\n\n"
                "Key facts:\n" + "\n".join(f"{i}. {f}" for i, f in enumerate(facts, 1)) + "\n\n"
                f"Evidence quote: {row['evidence_quote']}\n\n"
                f"System answer:\n{answer_text}\n\n===\n\nCited sources:\n\n{format_cited(cited)}")
        calls = self._call(CORRECTNESS_SYSTEM, user, correctness_schema(len(facts)))
        per_fact, agreements = [], []
        for i in range(len(facts)):
            votes = [c["facts"][i]["status"] if i < len(c["facts"]) else "missing" for c in calls]
            status, agree = _majority(votes, tie="missing")
            note = next(c["facts"][i]["note"] for c in calls if i < len(c["facts"]) and c["facts"][i]["status"] == status) \
                if status in votes else ""
            per_fact.append({"fact": facts[i], "status": status, "note": note, "votes": votes})
            agreements.append(agree)
        refused, _ = _majority([c["refused"] for c in calls], tie=False)
        statuses = [f["status"] for f in per_fact]
        verdict = verdict_from_facts(statuses)
        # reason from a call whose own verdict matches the majority verdict, else the first
        reason = next((c["reason"] for c in calls
                       if verdict_from_facts([x["status"] for x in c["facts"]]) == verdict), calls[0]["reason"])
        return {
            "verdict": verdict, "refused": refused, "reason": reason,
            "facts": per_fact,
            "facts_present": f"{statuses.count('present')}/{len(statuses)}",
            "missing_facts": [f["fact"] for f in per_fact if f["status"] == "missing"],
            "wrong_facts": [f"{f['fact']} ({f['note']})" for f in per_fact if f["status"] == "contradicted"],
            "agreement": round(sum(agreements) / len(agreements), 3) if agreements else 1.0,
            "votes": [verdict_from_facts([x["status"] for x in c["facts"]]) for c in calls],
        }

    def refusal(self, row, answer_text):
        calls = self._call(REFUSAL_SYSTEM, f"Question: {row['question']}\n\nSystem answer:\n{answer_text}",
                           REFUSAL_SCHEMA)
        refused, agree = _majority([c["refused"] for c in calls], tie=False)
        reason = next(c["reason"] for c in calls if c["refused"] == refused)
        return {"refused": refused, "reason": reason, "agreement": round(agree, 3)}

    def faithfulness(self, answer_text, cited):
        user = f"Answer:\n{answer_text}\n\n===\n\nCited sources:\n\n{format_cited(cited)}"
        calls = self._call(FAITHFULNESS_SYSTEM, user, FAITHFULNESS_SCHEMA, votes=self.faith_votes)
        verdict, agree = _majority([c["verdict"] for c in calls], tie="partially_supported")
        pick = next((c for c in calls if c["verdict"] == verdict), calls[0])
        return {"verdict": verdict, "unsupported_claims": pick["unsupported_claims"] if pick["verdict"] == verdict else [],
                "reason": pick["reason"], "agreement": round(agree, 3)}

    def cost(self):
        return sum(r["cost_usd"] or 0 for r in self.usage)
