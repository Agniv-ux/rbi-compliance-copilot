"""Document-status lookup over the documents table (loaded from data/metadata.csv). No LLM.

get_document_status("KYC Master Direction 2016") finds the best-matching document by title / file
name and returns its title, status, issue date, updated_as_on, what replaced it (with that
document's title) and notes. status_label() gives the short tag shown in source headers
("CURRENT", "REPEALED on 2025-11-28, replaced by ...").

Usage:
    python rag/status.py "KYC Master Direction 2016"
"""
import json
import re
import sys
from datetime import date
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingestion"))
from db import connect  # noqa: E402

COLUMNS = ["file_name", "title", "doc_type", "topic", "entity", "issue_date", "updated_as_on",
           "status", "replaced_by", "amends", "in_scope", "notes"]
SUPERSEDED = ("repealed", "withdrawn", "incorporated")
MIN_SCORE = 0.35  # below this, no document is considered a match

STOPWORDS = {"the", "of", "on", "for", "and", "a", "an", "in", "to", "is", "are", "still", "force", "rbi",
             "reserve", "bank", "india", "directions", "direction", "what", "which", "where", "now", "it"}
ALIASES = {"md": "master", "nbfcs": "nbfc", "non": "nbfc", "banking": "nbfc", "companies": "nbfc",
           "know": "kyc", "customer": "kyc", "2nd": "second"}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december"]


@lru_cache(maxsize=1)
def load_documents():
    conn = connect()
    rows = conn.execute(f"SELECT {', '.join(COLUMNS)} FROM documents").fetchall()
    conn.close()
    return {r[0]: dict(zip(COLUMNS, r)) for r in rows}


def _iso(d):
    return d.isoformat() if isinstance(d, date) else d


def _tokens(text):
    words = re.findall(r"[a-z0-9]+", text.lower().replace("_", " "))
    return {ALIASES.get(w, w) for w in words if w not in STOPWORDS}


def _doc_tokens(doc):
    toks = _tokens(f"{doc['title']} {doc['file_name'].rsplit('.', 1)[0]} {doc['doc_type'] or ''}")
    if doc["issue_date"]:
        toks |= {str(doc["issue_date"].year), MONTHS[doc["issue_date"].month - 1]}
    return toks


def _score(query, doc):
    q = _tokens(query)
    if not q:
        return 0.0
    d = _doc_tokens(doc)
    overlap = len(q & d) / len(q)
    # a year or month in the query that the document does not have is strong evidence against it
    misses = [t for t in q - d if re.fullmatch(r"(19|20)\d\d", t) or t in MONTHS]
    fuzzy = SequenceMatcher(None, query.lower(), doc["title"].lower()).ratio()
    # an amendment only when the query asks for one ("NBFC KYC Directions" = the direction itself)
    unasked_amendment = doc["doc_type"] == "amendment" and "amendment" not in q
    return round(0.75 * overlap + 0.25 * fuzzy - 0.3 * len(misses) - 0.1 * unasked_amendment, 3)


def _stated_date(doc):
    """Repeal / withdrawal date, only when the notes state it ("Repealed on 2025-11-28 ...")."""
    m = re.search(r"\b(?:repealed|withdrawn)\s+on\s+(\d{4}-\d{2}-\d{2})", doc["notes"] or "", re.I)
    return m.group(1) if m else None


def describe(file_name):
    """Full status record for one document."""
    docs = load_documents()
    doc = docs[file_name]
    rep = docs.get(doc["replaced_by"])
    parent = docs.get(doc["amends"])
    return {
        "file_name": doc["file_name"], "title": doc["title"], "status": doc["status"],
        "entity": doc["entity"],
        "issue_date": _iso(doc["issue_date"]), "updated_as_on": _iso(doc["updated_as_on"]),
        "status_date": _stated_date(doc),
        "replaced_by": doc["replaced_by"], "replaced_by_title": rep["title"] if rep else None,
        "replaced_by_issue_date": _iso(rep["issue_date"]) if rep else None,
        # the replacement covers only NBFCs (the old document applied to all regulated entities)
        "replaced_for": "NBFCs" if rep and rep["entity"] == "nbfc" and doc["entity"] != "nbfc" else None,
        "amends": doc["amends"], "amends_title": parent["title"] if parent else None,
        "amends_status": parent["status"] if parent else None,
        "notes": doc["notes"],
    }


def status_label(file_name):
    """Short status tag for a source header. States only what the documents table says."""
    s = describe(file_name)
    status = s["status"]
    if status == "active":
        return "CURRENT"
    if status == "incorporated":
        target = s["amends_title"] or "the current direction"
        return f"INCORPORATED: its changes are already part of {target}"
    if status in ("repealed", "withdrawn"):
        label = status.upper() + (f" on {s['status_date']}" if s["status_date"] else "")
        if s["replaced_by_title"]:
            label += (f", replaced{' for ' + s['replaced_for'] if s['replaced_for'] else ''} by "
                      f"{s['replaced_by_title']} (issued {s['replaced_by_issue_date']})")
        elif s["amends_title"] and s["amends_status"] == status:
            label += f" (amendment to {s['amends_title']}, which is also {status})"
        return label + " - NOT in force"
    if status == "reference":
        return "REFERENCE: FAQ page, not a direction; check against current rules"
    return status.upper()


def get_document_status(name_or_query):
    """Best-matching document's status record, or match=None when nothing matches well enough.
    Returns {query, match, score, alternatives: [{file_name, title, score}, ...]}."""
    docs = load_documents()
    ranked = sorted(((_score(name_or_query, d), f) for f, d in docs.items()), reverse=True)
    best_score, best = ranked[0]
    return {
        "query": name_or_query,
        "match": describe(best) if best_score >= MIN_SCORE else None,
        "score": best_score,
        "alternatives": [{"file_name": f, "title": docs[f]["title"], "score": s} for s, f in ranked[1:4]],
    }


def status_text(record):
    """Plain-text rendering of describe() output (used as a source for the answer model)."""
    lines = [f"Document: {record['title']} ({record['file_name']})",
             f"Status: {record['status']}"]
    if record["status_date"]:
        lines.append(f"Status date: {record['status_date']}")
    lines.append(f"Issue date: {record['issue_date'] or 'not recorded'}")
    if record["updated_as_on"]:
        lines.append(f"Updated as on: {record['updated_as_on']}")
    if record["replaced_by"]:
        lines.append(f"Replaced by: {record['replaced_by_title']} ({record['replaced_by']}), "
                     f"issued {record['replaced_by_issue_date']}")
    if record["amends"]:
        lines.append(f"Amends: {record['amends_title']} ({record['amends']})")
    if record["notes"]:
        lines.append(f"Notes: {record['notes']}")
    return "\n".join(lines)


def as_source(record):
    """A describe() record as an extra source for rag.answer.answer(extra_sources=[...])."""
    return {"doc": record["file_name"], "title": record["title"], "para": "document status",
            "para_title": None, "pages": "", "status": record["status"],
            "header": f"Document status record (RBI documents register): {record['title']} "
                      f"[{status_label(record['file_name'])}]",
            "text": status_text(record)}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    query = " ".join(a for a in sys.argv[1:] if a != "--json")
    if not query:
        sys.exit('usage: python rag/status.py "KYC Master Direction 2016"')
    r = get_document_status(query)
    if r["match"]:
        print(status_text(r["match"]))
        print(f"\nLabel: {status_label(r['match']['file_name'])}")
    else:
        print(f'No document matches "{query}" well enough.')
    print(f"\nMatch score: {r['score']}  Other candidates: "
          + "; ".join(f"{a['file_name']} ({a['score']})" for a in r["alternatives"]))
    if "--json" in sys.argv:
        print(json.dumps(r, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
