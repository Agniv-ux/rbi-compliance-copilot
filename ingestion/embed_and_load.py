"""Embed every chunk in data/chunks/*.jsonl and upsert it into Postgres.

- documents: upserted from data/metadata.csv
- chunks:    upserted with embed_text and its embedding; chunks that no longer exist in a
             document's .jsonl are deleted. Chunks whose embed_text did not change keep their
             stored embedding, so re-runs only embed what is new or changed.

Usage:
    python ingestion/embed_and_load.py
    python ingestion/embed_and_load.py --reembed   # embed everything again
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import EMBED_MODEL, connect, create_schema  # noqa: E402

CHUNK_DIR = Path("data/chunks")
METADATA_CSV = Path("data/metadata.csv")
BATCH_SIZE = 16

DOC_COLUMNS = ["file_name", "title", "doc_type", "topic", "entity", "issue_date", "updated_as_on",
               "status", "replaced_by", "amends", "in_scope", "notes"]
CHUNK_COLUMNS = ["chunk_id", "doc", "title", "status", "updated_as_on", "region", "chapter", "section",
                 "para", "para_title", "part", "parts", "page_start", "page_end", "amendment_note",
                 "boilerplate", "text", "embed_text", "embedding"]


def build_embed_text(c):
    """"<title> › <chapter> › <section> › para <para>: <para_title>\\n<text>", skipping empty parts.
    Annex chunks have no chapter, so the annex name takes its place."""
    where = c["chapter"] or (c["region"].replace("annex_", "Annex ") if c["region"] != "main" else None)
    if c["para"]:
        label = f"para {c['para']}: {c['para_title']}" if c["para_title"] else f"para {c['para']}"
    else:
        label = c["para_title"] if c["para_title"] not in (c["section"], where) else None
    head = " › ".join(p for p in (c["title"], where, c["section"], label) if p)
    return f"{head}\n{c['text']}"


def load_documents(conn):
    with METADATA_CSV.open(encoding="utf-8") as f:
        rows = [{k: (v.strip() or None) for k, v in row.items()} for row in csv.DictReader(f)]
    cols = ", ".join(DOC_COLUMNS)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in DOC_COLUMNS[1:])
    with conn.cursor() as cur:
        cur.executemany(
            f"INSERT INTO documents ({cols}) VALUES ({', '.join(['%s'] * len(DOC_COLUMNS))}) "
            f"ON CONFLICT (file_name) DO UPDATE SET {updates}",
            [[row.get(c) for c in DOC_COLUMNS] for row in rows])
    conn.commit()
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reembed", action="store_true", help="embed every chunk, even unchanged ones")
    args = ap.parse_args()
    start = time.time()

    conn = connect()
    create_schema(conn)
    n_docs = load_documents(conn)
    print(f"documents: {n_docs} rows upserted from {METADATA_CSV}")

    chunks = []
    for path in sorted(CHUNK_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                c = json.loads(line)
                c["embed_text"] = build_embed_text(c)
                chunks.append(c)
    print(f"chunks: {len(chunks)} read from {CHUNK_DIR}")

    # reuse stored embeddings when embed_text is unchanged
    stored = {} if args.reembed else dict(conn.execute(
        "SELECT chunk_id, embed_text FROM chunks WHERE embedding IS NOT NULL").fetchall())
    todo = [c for c in chunks if stored.get(c["chunk_id"]) != c["embed_text"]]
    print(f"to embed: {len(todo)} (unchanged and skipped: {len(chunks) - len(todo)})")

    if todo:
        from sentence_transformers import SentenceTransformer

        t0 = time.time()
        model = SentenceTransformer(EMBED_MODEL, device="cpu")
        print(f"model {EMBED_MODEL} loaded in {time.time() - t0:.0f} s (max {model.max_seq_length} tokens)")
        vectors = model.encode([c["embed_text"] for c in todo], batch_size=BATCH_SIZE,
                               normalize_embeddings=True, show_progress_bar=True, convert_to_numpy=True)
        for c, v in zip(todo, vectors):
            c["embedding"] = v

    cols = ", ".join(CHUNK_COLUMNS)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in CHUNK_COLUMNS[1:])
    unchanged_updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in CHUNK_COLUMNS[1:] if c != "embedding")
    with conn.cursor() as cur:
        cur.executemany(
            f"INSERT INTO chunks ({cols}) VALUES ({', '.join(['%s'] * len(CHUNK_COLUMNS))}) "
            f"ON CONFLICT (chunk_id) DO UPDATE SET {updates}",
            [[c.get(k) for k in CHUNK_COLUMNS] for c in todo])
        # metadata may change without the embed_text changing (e.g. status in metadata.csv)
        rest = [c for c in chunks if "embedding" not in c]
        cols_no_vec = [k for k in CHUNK_COLUMNS if k != "embedding"]
        cur.executemany(
            f"INSERT INTO chunks ({', '.join(cols_no_vec)}) VALUES ({', '.join(['%s'] * len(cols_no_vec))}) "
            f"ON CONFLICT (chunk_id) DO UPDATE SET {unchanged_updates}",
            [[c.get(k) for k in cols_no_vec] for c in rest])
        # drop chunks that disappeared from a re-chunked document
        removed = 0
        for doc in {c["doc"] for c in chunks}:
            ids = [c["chunk_id"] for c in chunks if c["doc"] == doc]
            cur.execute("DELETE FROM chunks WHERE doc = %s AND NOT (chunk_id = ANY(%s))", (doc, ids))
            removed += cur.rowcount
    conn.commit()

    counts = conn.execute("""
        SELECT c.doc, d.status, count(*), count(c.embedding), sum(c.boilerplate::int)
        FROM chunks c JOIN documents d ON d.file_name = c.doc GROUP BY c.doc, d.status ORDER BY c.doc
    """).fetchall()
    conn.close()

    print(f"stale chunks removed: {removed}\n")
    print(f"{'document':<45} {'status':<13} {'chunks':>6} {'embedded':>8} {'boilerplate':>11}")
    for doc, status, n, n_vec, n_boiler in counts:
        print(f"{doc:<45} {status:<13} {n:>6} {n_vec:>8} {n_boiler:>11}")
    print(f"{'TOTAL':<45} {'':<13} {sum(r[2] for r in counts):>6} {sum(r[3] for r in counts):>8}")
    print(f"\nembedded {len(todo)} chunks; total time {time.time() - start:.0f} s")


if __name__ == "__main__":
    main()
