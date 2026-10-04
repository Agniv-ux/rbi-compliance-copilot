"""Database settings, connection and schema (Postgres + pgvector).

Settings come from .env (see .env.example):
    DATABASE_URL=postgresql://rbi:rbi_pass@localhost:5432/rbi_copilot
    EMBED_MODEL=BAAI/bge-base-en-v1.5

Usage:
    python ingestion/db.py     # create the schema (safe to run again)
"""
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-base-en-v1.5")
EMBED_DIM = 768  # bge-base-en-v1.5

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;

-- one row per source document (all columns of data/metadata.csv)
CREATE TABLE IF NOT EXISTS documents (
    file_name     TEXT PRIMARY KEY,
    title         TEXT,
    doc_type      TEXT,
    topic         TEXT,
    entity        TEXT,
    issue_date    DATE,
    updated_as_on DATE,
    status        TEXT,
    replaced_by   TEXT,
    amends        TEXT,
    in_scope      TEXT,
    notes         TEXT
);

-- one row per chunk (data/chunks/*.jsonl) plus its embedding
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id       TEXT PRIMARY KEY,
    doc            TEXT NOT NULL REFERENCES documents(file_name),
    title          TEXT,
    status         TEXT,
    updated_as_on  DATE,
    region         TEXT,
    chapter        TEXT,
    section        TEXT,
    para           TEXT,
    para_title     TEXT,
    part           INTEGER,
    parts          INTEGER,
    page_start     INTEGER,
    page_end       INTEGER,
    amendment_note TEXT,
    boilerplate    BOOLEAN NOT NULL DEFAULT FALSE,
    text           TEXT NOT NULL,
    embed_text     TEXT NOT NULL,
    embedding      vector({EMBED_DIM}),
    tsv            tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv_gin ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_doc_idx ON chunks (doc);
CREATE INDEX IF NOT EXISTS chunks_status_idx ON chunks (status);
"""


def connect():
    """Open a connection with the pgvector type registered."""
    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=10)
    except psycopg.OperationalError as e:
        raise SystemExit(f"Cannot reach Postgres at {DATABASE_URL.rsplit('@', 1)[-1]}: {e}\n"
                         "Is the database container running? Start it with: docker compose up -d") from None
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.commit()
    register_vector(conn)
    return conn


def create_schema(conn):
    conn.execute(SCHEMA)
    conn.commit()


if __name__ == "__main__":
    with connect() as conn:
        create_schema(conn)
        rows = conn.execute("""
            SELECT table_name, count(*) FROM information_schema.columns
            WHERE table_name IN ('documents', 'chunks') GROUP BY table_name ORDER BY table_name
        """).fetchall()
        version = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()[0]
    print(f"pgvector {version}; schema ready: " + ", ".join(f"{t} ({n} columns)" for t, n in rows))
