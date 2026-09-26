import psycopg

conn = psycopg.connect("postgresql://rbi:rbi_pass@localhost:5432/rbi_copilot")
with conn.cursor() as cur:
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
    print("pgvector version:", cur.fetchone()[0])
conn.commit()
conn.close()
print("Setup OK ✅")