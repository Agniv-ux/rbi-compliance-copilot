"""Answer a question from the retrieved RBI chunks, with [S#] citations.

Usage:
    python rag/answer.py "How often must high-risk customers update KYC?"
    python rag/answer.py "..." --cheap -k 8
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rag import llm  # noqa: E402
from retrieval.search import search, where  # noqa: E402

NOT_COVERED = "Not covered in the provided RBI documents."

SYSTEM_PROMPT = f"""You are a compliance assistant for Indian NBFCs. You answer questions using ONLY the RBI document excerpts given as numbered sources [S1], [S2], ...

Rules:
1. Use only the information in the sources. Do not use outside knowledge, and do not guess.
2. Cite every claim with the source number(s) it comes from, e.g. [S1] or [S2][S4]. Put the citation right after the claim.
3. Keep numbers, amounts, time periods, dates and conditions exactly as the sources state them. Do not round, paraphrase away qualifiers ("at least", "not later than"), or drop conditions.
4. If the sources do not answer the question, reply exactly: {NOT_COVERED}
   Reply with that sentence alone, with no citations or other text.
5. Be concise: answer the question directly in a few sentences or a short list."""

CITATION_RE = re.compile(r"\[(S\d+(?:\s*[,;]\s*S?\d+)*)\]")


def pages(hit):
    if hit["page_end"] and hit["page_end"] != hit["page_start"]:
        return f"{hit['page_start']}-{hit['page_end']}"
    return str(hit["page_start"])


def format_source(n, hit):
    lines = [f"[S{n}] {hit['title']} ({hit['doc']})",
             f"Location: {where(hit)}" + (f" - {hit['para_title']}" if hit["para_title"] else ""),
             f"Pages: {pages(hit)}"]
    if hit.get("amendment_note"):
        lines.append(f"Amendment note: {hit['amendment_note']}")
    lines.append(f"Text:\n{hit['text'].strip()}")
    return "\n".join(lines)


def build_prompt(question, hits):
    sources = "\n\n---\n\n".join(format_source(n, h) for n, h in enumerate(hits, 1))
    return f"Sources:\n\n{sources}\n\n---\n\nQuestion: {question}"


def cited_numbers(text, n_sources):
    """Source numbers cited in the text, in order of first use; out-of-range numbers are dropped."""
    seen = []
    for group in CITATION_RE.findall(text):
        for num in re.findall(r"\d+", group):
            n = int(num)
            if 1 <= n <= n_sources and n not in seen:
                seen.append(n)
    return seen


def source_record(n, hit):
    return {"source": f"S{n}", "doc": hit["doc"], "title": hit["title"], "para": where(hit),
            "para_title": hit["para_title"], "pages": pages(hit), "score": round(hit["score"], 3),
            "chunk_id": hit["chunk_id"], "status": hit["status"],
            # raw location fields (for matching against expected paragraphs) and the text itself
            "region": hit["region"], "section": hit["section"], "para_no": hit["para"], "text": hit["text"]}


def answer(question, k=5, model=None, statuses=("active",)):
    hits = search(question, k=k, statuses=statuses)
    result = llm.generate(SYSTEM_PROMPT, build_prompt(question, hits), model=model)
    text = result["text"].strip()
    sources = [source_record(n, h) for n, h in enumerate(hits, 1)]
    used = cited_numbers(text, len(hits))
    return {
        "question": question,
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
    ap.add_argument("--all-statuses", action="store_true", help="include repealed / withdrawn / ... documents")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # rupee signs etc. on the Windows console

    r = answer(args.question, k=args.k, model=llm.MODEL_CHEAP if args.cheap else None,
               statuses=None if args.all_statuses else ("active",))
    print(f"Q: {r['question']}\n\n{r['answer']}\n")
    print("Citations:" if r["citations"] else "Citations: none")
    for c in r["citations"]:
        print(f"  [{c['source']}] {c['doc']}  {c['para']}  p{c['pages']}")
    print("\nRetrieved:")
    for s in r["sources"]:
        print(f"  [{s['source']}] {s['score']:.3f}  {s['doc']}  {s['para']}  p{s['pages']}")
    cost = f"${r['cost_usd']:.5f}" if r["cost_usd"] is not None else "unknown (no price)"
    print(f"\nModel: {r['model']}  tokens in/out/reasoning: {r['input_tokens']}/{r['output_tokens']}/"
          f"{r['reasoning_tokens']}  cost: {cost}  time: {r['seconds']}s")


if __name__ == "__main__":
    main()
