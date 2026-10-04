"""Semantic search over the chunks table (pgvector, cosine similarity).

Usage:
    python retrieval/search.py "How often must high-risk customers update KYC?"
    python retrieval/search.py "..." -k 10 --all-statuses --include-boilerplate
"""
import argparse
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingestion"))
from db import EMBED_MODEL, connect  # noqa: E402

# BGE models expect this instruction in front of queries (not in front of passages)
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

COLUMNS = ["chunk_id", "doc", "title", "status", "updated_as_on", "region", "chapter", "section", "para",
           "para_title", "part", "parts", "page_start", "page_end", "amendment_note", "boilerplate", "text"]


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBED_MODEL, device="cpu")


@lru_cache(maxsize=1)
def _conn():
    return connect()


@lru_cache(maxsize=1)
def _iterative_scan_supported():
    version = _conn().execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()[0]
    _conn().commit()
    return tuple(int(x) for x in version.split(".")[:2]) >= (0, 8)


def embed_query(query):
    return _model().encode(QUERY_INSTRUCTION + query, normalize_embeddings=True, convert_to_numpy=True)


def search(query, k=5, statuses=("active",), include_boilerplate=False):
    """Top-k chunks by cosine similarity. statuses=None searches every status.
    Returns a list of dicts with the chunk's metadata, its text and `score` (cosine similarity)."""
    vec = embed_query(query)
    conn = _conn()
    iterative = _iterative_scan_supported()  # cached; runs outside the transaction below
    with conn.transaction():
        # HNSW filters after the index scan: look at more candidates so that k rows
        # survive the status / boilerplate filter, and (pgvector >= 0.8) keep scanning
        # until they do
        conn.execute(f"SET LOCAL hnsw.ef_search = {max(100, 10 * k)}")
        if iterative:
            conn.execute("SET LOCAL hnsw.iterative_scan = strict_order")  # exact ranking order
        rows = conn.execute(
            f"""SELECT {', '.join(COLUMNS)}, 1 - (embedding <=> %(v)s) AS score
                FROM chunks
                WHERE (%(statuses)s::text[] IS NULL OR status = ANY(%(statuses)s))
                  AND (%(boiler)s OR NOT boilerplate)
                ORDER BY embedding <=> %(v)s
                LIMIT %(k)s""",
            {"v": vec, "statuses": list(statuses) if statuses else None,
             "boiler": include_boilerplate, "k": k},
        ).fetchall()
    return [dict(zip(COLUMNS + ["score"], row)) for row in rows]


def where(hit):
    """Short location label: 'para 42', 'Annex I para 5', 'Annex I' ..."""
    region = hit["region"].replace("annex_", "Annex ") if hit["region"] != "main" else ""
    para = f"para {hit['para']}" if hit["para"] else (hit["para_title"] or "preamble")
    part = f" (part {hit['part']}/{hit['parts']})" if hit["parts"] > 1 else ""
    return f"{region} {para}{part}".strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--all-statuses", action="store_true", help="include repealed / withdrawn / ... documents")
    ap.add_argument("--include-boilerplate", action="store_true")
    args = ap.parse_args()

    hits = search(args.query, k=args.k, statuses=None if args.all_statuses else ("active",),
                  include_boilerplate=args.include_boilerplate)
    print(f'Query: "{args.query}"\n')
    for rank, h in enumerate(hits, 1):
        pages = f"p{h['page_start']}" + (f"-{h['page_end']}" if h["page_end"] != h["page_start"] else "")
        snippet = " ".join(h["text"].split())[:200]
        print(f"{rank}. {h['score']:.3f}  {h['doc']}  {where(h)}  {pages}  [{h['status']}]")
        print(f"   {snippet}\n")


if __name__ == "__main__":
    main()
