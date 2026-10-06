"""Answer a question from the retrieved RBI chunks, with [S#] citations.

Modes:
    current  (default) - search active documents only; the answer is the rule in force.
    compare            - search active documents AND, separately, superseded ones (repealed /
                         withdrawn / incorporated); the answer says what changed ("earlier: ... /
                         now: ...") and cites both.

Usage:
    python rag/answer.py "How often must high-risk customers update KYC?"
    python rag/answer.py "..." --cheap -k 8
    python rag/answer.py "Who decides the cooling-off period, and did this change?" --compare
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rag import llm  # noqa: E402
from rag.status import SUPERSEDED, status_label  # noqa: E402
from retrieval.search import METHODS, search, where  # noqa: E402

NOT_COVERED = "Not covered in the provided RBI documents."
MODES = ("current", "compare")
DEFAULT_METHOD = "vector"  # retrieval method; see eval/results/retrieval_ablation_v5_5C.md

SYSTEM_PROMPT = f"""You are a compliance assistant for Indian NBFCs. You answer questions using ONLY the RBI document excerpts given as numbered sources [S1], [S2], ...

Rules:
1. Use only the information in the sources. Do not use outside knowledge, and do not guess.
2. Cite every claim with the source number(s) it comes from, e.g. [S1] or [S2][S4]. Put the citation right after the claim.
3. Keep numbers, amounts, time periods, dates and conditions exactly as the sources state them. Do not round, paraphrase away qualifiers ("at least", "not later than"), or drop conditions.
4. Always keep the conditions, exceptions and qualifiers that limit a rule: who it applies to, when it applies, and what must have happened first (e.g. "for customers who have not complied after the advance intimations", "unless allowed under extant statutory guidelines"). Never state a limited rule as if it applied generally.
5. Only state that a document or rule is in force, repealed, withdrawn, amended or applicable if a source explicitly says so. Never infer a document's status. If no source states it, say so instead of guessing.
6. If the sources do not answer the question, reply exactly: {NOT_COVERED}
   Reply with that sentence alone, with no citations or other text.
7. Be concise: answer the question directly in a few sentences or a short list."""

COMPARE_RULES = """

Compare mode. Each source header carries a status tag: [CURRENT] sources are in force; [REPEALED ...], [WITHDRAWN ...] and [INCORPORATED ...] sources are superseded.
8. The CURRENT source is always the rule in force. Never present a superseded source as the current rule.
9. Use superseded sources only to describe what the rule was before and what changed.
10. When the question asks about a change, answer in the form "Earlier: ... [S#] / Now: ... [S#]", citing a superseded source for "Earlier" and a CURRENT source for "Now". If the rule did not change, say so and cite both. If only one side is in the sources, say which side is missing."""


def pages(hit):
    if hit["page_start"] is None:  # HTML pages (FAQs) have no page numbers
        return ""
    if hit["page_end"] and hit["page_end"] != hit["page_start"]:
        return f"{hit['page_start']}-{hit['page_end']}"
    return str(hit["page_start"])


def location(hit):
    """'Chapter III - Digital Lending › B. Conduct ... › para 11: Cooling-off period, p. 18'"""
    path = [hit["region"].replace("annex_", "Annex ")] if hit["region"] != "main" else []
    path += [x for x in (hit["chapter"], hit["section"]) if x]
    part = f" (part {hit['part']}/{hit['parts']})" if hit["parts"] > 1 else ""
    if hit["para"]:
        path.append(f"para {hit['para']}{part}" + (f": {hit['para_title']}" if hit["para_title"] else ""))
    elif hit["para_title"] and hit["para_title"] not in path:
        path.append(hit["para_title"] + part)  # preamble text: its title is the section / chapter
    elif path:
        path[-1] += part
    pg = pages(hit)
    if not pg:
        return " › ".join(path)
    return " › ".join(path) + (f", pp. {pg}" if "-" in pg else f", p. {pg}")


def header(hit):
    """'<title> [CURRENT] › Chapter ... › para N: title, p. X' - shown to the answer model and the judges."""
    return f"{hit['title']} [{status_label(hit['doc'])}] › {location(hit)}"


def source_record(n, hit):
    return {"source": f"S{n}", "doc": hit["doc"], "title": hit["title"], "para": where(hit),
            "para_title": hit["para_title"], "pages": pages(hit), "score": round(hit["score"], 3),
            "chunk_id": hit["chunk_id"], "status": hit["status"], "header": header(hit),
            "amendment_note": hit.get("amendment_note"),
            # raw location fields (for matching against expected paragraphs) and the text itself
            "region": hit["region"], "section": hit["section"], "para_no": hit["para"], "text": hit["text"]}


def source_block(record):
    """One source exactly as the answer model sees it (the eval judges get the same block)."""
    lines = [f"[{record['source']}] {record['header']}"]
    if record.get("amendment_note"):
        lines.append(f"Amendment note: {record['amendment_note']}")
    lines.append(f"Text:\n{record['text'].strip()}")
    return "\n".join(lines)


def build_prompt(question, records):
    sources = "\n\n---\n\n".join(source_block(r) for r in records)
    return f"Sources:\n\n{sources}\n\n---\n\nQuestion: {question}"


CITATION_RE = re.compile(r"\[(S\d+(?:\s*[,;]\s*S?\d+)*)\]")


def cited_numbers(text, n_sources):
    """Source numbers cited in the text, in order of first use; out-of-range numbers are dropped."""
    seen = []
    for group in CITATION_RE.findall(text):
        for num in re.findall(r"\d+", group):
            n = int(num)
            if 1 <= n <= n_sources and n not in seen:
                seen.append(n)
    return seen


def retrieve(question, k, mode, statuses, method):
    if mode == "current":
        return search(question, k=k, statuses=statuses, method=method)
    # compare: current rules first, then the superseded versions (same method for both)
    return (search(question, k=k, statuses=("active",), method=method)
            + search(question, k=k, statuses=SUPERSEDED, method=method))


def answer(question, k=5, model=None, statuses=("active",), mode="current", extra_sources=None,
           method=None, generate=None):
    """mode: "current" (active documents, or `statuses`) or "compare" (top k active + top k superseded;
    `statuses` is ignored). extra_sources: records added after the retrieved ones, each with at least
    header, text, doc, title, para, pages (e.g. a document-status record from rag.status).
    method: retrieval method (vector / keyword / hybrid; default DEFAULT_METHOD).
    generate: replacement for llm.generate with the same signature (the eval passes a cached one)."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    method = method or DEFAULT_METHOD
    hits = retrieve(question, k, mode, statuses, method)
    sources = [source_record(n, h) for n, h in enumerate(hits, 1)]
    for extra in extra_sources or []:
        sources.append({"score": 1.0, "region": None, "section": None, "para_no": None, "chunk_id": None,
                        **extra, "source": f"S{len(sources) + 1}"})
    system = SYSTEM_PROMPT + (COMPARE_RULES if mode == "compare" else "")
    result = (generate or llm.generate)(system, build_prompt(question, sources), model=model, temperature=0)
    text = result["text"].strip()
    used = cited_numbers(text, len(sources))
    return {
        "question": question,
        "mode": mode,
        "method": method,
        "answer": text,
        "not_covered": text.rstrip() == NOT_COVERED,
        "citations": [sources[n - 1] for n in used],
        "sources": sources,
        "model": result["model"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "reasoning_tokens": result["reasoning_tokens"],
        "cost_usd": result["cost_usd"],
        "seconds": result["seconds"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--cheap", action="store_true", help="use LLM_MODEL_CHEAP")
    ap.add_argument("--compare", action="store_true", help="also retrieve superseded documents and describe what changed")
    ap.add_argument("--method", choices=METHODS, default=None, help=f"retrieval method (default {DEFAULT_METHOD})")
    ap.add_argument("--all-statuses", action="store_true", help="current mode: include repealed / withdrawn / ... documents")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # rupee signs etc. on the Windows console

    r = answer(args.question, k=args.k, model=llm.MODEL_CHEAP if args.cheap else None,
               statuses=None if args.all_statuses else ("active",),
               mode="compare" if args.compare else "current", method=args.method)
    print(f"Q: {r['question']}  [{r['mode']} mode, {r['method']} search]\n\n{r['answer']}\n")
    print("Citations:" if r["citations"] else "Citations: none")
    for c in r["citations"]:
        print(f"  [{c['source']}] {c['doc']}  {c['para']}  {'p' + c['pages'] if c['pages'] else ''}  ({c['status']})")
    print("\nRetrieved:")
    for s in r["sources"]:
        print(f"  [{s['source']}] {s['score']:.3f}  {s['doc']}  {s['para']}  {'p' + s['pages'] if s['pages'] else ''}  ({s['status']})")
    cost = f"${r['cost_usd']:.5f}" if r["cost_usd"] is not None else "unknown (no price)"
    print(f"\nModel: {r['model']}  tokens in/out/reasoning: {r['input_tokens']}/{r['output_tokens']}/"
          f"{r['reasoning_tokens']}  cost: {cost}  time: {r['seconds']}s")


if __name__ == "__main__":
    main()
