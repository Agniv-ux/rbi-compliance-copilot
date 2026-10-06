"""Search over the chunks table: vector (pgvector cosine), keyword (Postgres full text) or hybrid.

- vector:  BGE query embedding, cosine similarity (HNSW index).
- keyword: OR query over the question's meaningful words on the `tsv` column (english config),
           ranked with ts_rank_cd. Question words ("how", "must") are dropped, and so are words
           that occur in more than KEYWORD_MAX_DF of all chunks ("shall", "nbfc", "customer"):
           Postgres ranking has no IDF, so very common words would otherwise dominate an OR
           query. Rare terms (DLG, V-CIP, CKYCR, "112") are kept.
- hybrid:  top HYBRID_POOL from each, merged with reciprocal rank fusion (constant RRF_K).

Usage:
    python retrieval/search.py "How often must high-risk customers update KYC?"
    python retrieval/search.py "..." -k 10 --method hybrid --all-statuses --include-boilerplate
"""
import argparse
import re
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingestion"))
from db import EMBED_MODEL, connect  # noqa: E402

# BGE models expect this instruction in front of queries (not in front of passages)
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

COLUMNS = ["chunk_id", "doc", "title", "status", "updated_as_on", "region", "chapter", "section", "para",
           "para_title", "part", "parts", "page_start", "page_end", "amendment_note", "boilerplate", "text"]
METHODS = ("vector", "keyword", "hybrid")
HYBRID_POOL = 20     # candidates taken from each method before fusion
RRF_K = 60           # reciprocal rank fusion constant
KEYWORD_MAX_DF = 0.15  # drop query terms found in more than this share of chunks
KEYWORD_MIN_TERMS = 3  # ... but always keep at least this many of the rarest terms

# question words Postgres' english stopword list keeps
QUESTION_WORDS = {
    "how", "often", "what", "which", "when", "where", "who", "whom", "whose", "why", "whether",
    "must", "can", "could", "shall", "should", "would", "will", "may", "might", "need", "needs",
    "required", "require", "does", "do", "did", "is", "are", "was", "were", "be", "been", "has", "have",
    "any", "many", "much", "there", "still", "now", "also", "please", "tell", "explain", "list",
}


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


@lru_cache(maxsize=1)
def _lexeme_df():
    """({lexeme: number of chunks containing it}, number of chunks)."""
    conn = _conn()
    n = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
    df = dict(conn.execute("SELECT word, ndoc FROM ts_stat('SELECT tsv FROM chunks')").fetchall())
    conn.commit()
    return df, n


def embed_query(query):
    return _model().encode(QUERY_INSTRUCTION + query, normalize_embeddings=True, convert_to_numpy=True)


def keyword_terms(query):
    """Stemmed lexemes used for the keyword query, rarest first."""
    words = [w for w in re.findall(r"[\w-]+", query) if w.lower() not in QUESTION_WORDS]
    conn = _conn()
    vec = conn.execute("SELECT to_tsvector('english', %s)::text", (" ".join(words),)).fetchone()[0]
    conn.commit()
    lexemes = [lx for lx in re.findall(r"'((?:[^']|'')+)'", vec) if len(lx) > 1 or lx.isdigit()]
    df, n = _lexeme_df()
    ranked = sorted(set(lexemes), key=lambda lx: (df.get(lx, 0), lx))
    keep = [lx for lx in ranked if df.get(lx, 0) <= KEYWORD_MAX_DF * n]
    return keep if len(keep) >= KEYWORD_MIN_TERMS else ranked[:KEYWORD_MIN_TERMS]


def _filters():
    return """(%(statuses)s::text[] IS NULL OR status = ANY(%(statuses)s))
              AND (%(boiler)s OR NOT boilerplate)"""


def _params(statuses, include_boilerplate, k):
    return {"statuses": list(statuses) if statuses else None, "boiler": include_boilerplate, "k": k}


def vector_search(query, k, statuses, include_boilerplate):
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
                FROM chunks WHERE {_filters()}
                ORDER BY embedding <=> %(v)s
                LIMIT %(k)s""",
            {"v": vec, **_params(statuses, include_boilerplate, k)},
        ).fetchall()
    return [dict(zip(COLUMNS + ["score"], row)) for row in rows]


def keyword_search(query, k, statuses, include_boilerplate):
    terms = keyword_terms(query)
    if not terms:
        return []
    # lexemes are already stemmed: build the OR query with the 'simple' config, quoted
    tsquery = " | ".join("'" + t.replace("'", "''") + "'" for t in terms)
    conn = _conn()
    with conn.transaction():
        rows = conn.execute(
            f"""SELECT {', '.join(COLUMNS)}, ts_rank_cd(tsv, q) AS score
                FROM chunks, to_tsquery('simple', %(q)s) AS q
                WHERE tsv @@ q AND {_filters()}
                ORDER BY score DESC, chunk_id
                LIMIT %(k)s""",
            {"q": tsquery, **_params(statuses, include_boilerplate, k)},
        ).fetchall()
    return [dict(zip(COLUMNS + ["score"], row)) for row in rows]


def hybrid_search(query, k, statuses, include_boilerplate):
    pool = HYBRID_POOL  # fixed pool: up to 2 * HYBRID_POOL fused candidates, so k may be up to 40
    vec = vector_search(query, pool, statuses, include_boilerplate)
    kw = keyword_search(query, pool, statuses, include_boilerplate)
    fused = {}
    for name, hits in (("vector", vec), ("keyword", kw)):
        for rank, h in enumerate(hits, 1):
            entry = fused.setdefault(h["chunk_id"], {**h, "score": 0.0, "vector_rank": None, "keyword_rank": None})
            entry["score"] += 1 / (RRF_K + rank)
            entry[f"{name}_rank"] = rank
    # ties (same fused score) keep the vector order
    order = sorted(fused.values(), key=lambda h: (-h["score"], h["vector_rank"] or 10**6))
    return order[:k]


def search(query, k=5, statuses=("active",), include_boilerplate=False, method="vector"):
    """Top-k chunks. statuses=None searches every status. method: vector / keyword / hybrid.
    Returns a list of dicts with the chunk's metadata, its text and `score` (cosine similarity,
    ts_rank_cd or the fused RRF score; hybrid hits also carry vector_rank / keyword_rank)."""
    fn = {"vector": vector_search, "keyword": keyword_search, "hybrid": hybrid_search}.get(method)
    if fn is None:
        raise ValueError(f"method must be one of {METHODS}")
    return fn(query, k, statuses, include_boilerplate)


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
    ap.add_argument("--method", choices=METHODS, default="vector")
    ap.add_argument("--all-statuses", action="store_true", help="include repealed / withdrawn / ... documents")
    ap.add_argument("--include-boilerplate", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    hits = search(args.query, k=args.k, statuses=None if args.all_statuses else ("active",),
                  include_boilerplate=args.include_boilerplate, method=args.method)
    print(f'Query: "{args.query}"  [{args.method}]')
    if args.method != "vector":
        print(f"Keyword terms: {keyword_terms(args.query)}")
    print()
    for rank, h in enumerate(hits, 1):
        pages = f"p{h['page_start']}" + (f"-{h['page_end']}" if h["page_end"] != h["page_start"] else "")
        snippet = " ".join(h["text"].split())[:200]
        ranks = f"  (vector #{h['vector_rank'] or '-'}, keyword #{h['keyword_rank'] or '-'})" if "vector_rank" in h else ""
        print(f"{rank}. {h['score']:.3f}  {h['doc']}  {where(h)}  {pages}  [{h['status']}]{ranks}")
        print(f"   {snippet}\n")


if __name__ == "__main__":
    main()
