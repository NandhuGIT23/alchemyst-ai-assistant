"""
db.py
-----
Handles all PostgreSQL + pgvector interactions:
  - setup_db()      : create the extension and table (run once)
  - save_chunks()   : upsert chunks + embeddings into the table
  - search()        : cosine similarity retrieval at query time
  - clear_chunks()  : wipe the table (useful when re-ingesting)

Schema
------
  documents
  ├── id          SERIAL PRIMARY KEY
  ├── source_url  TEXT
  ├── page_title  TEXT
  ├── chunk_index INTEGER
  ├── text        TEXT
  └── embedding   VECTOR(1536)          ← pgvector column

The HNSW index makes cosine similarity search fast even at 100k+ rows.
"""

import psycopg2
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector
from config import DATABASE_URL, EMBEDDING_DIM, TOP_K


def _connect():
    conn = psycopg2.connect(DATABASE_URL)
    register_vector(conn)
    return conn


# ── Schema setup ─────────────────────────────────────────────────────────────

def setup_db():
    """
    Idempotent: safe to call on every startup.
    Creates pgvector extension, documents table, and HNSW index if missing.
    """
    conn = _connect()
    with conn:
        with conn.cursor() as cur:
            # 1. Enable pgvector
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            # 2. Documents table
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS documents (
                    id          SERIAL PRIMARY KEY,
                    source_url  TEXT        NOT NULL,
                    page_title  TEXT        DEFAULT '',
                    chunk_index INTEGER     DEFAULT 0,
                    text        TEXT        NOT NULL,
                    embedding   VECTOR({EMBEDDING_DIM})
                );
            """)

            # 3. HNSW index for fast cosine similarity search
            #    (only created once; no error if it already exists)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS documents_embedding_hnsw
                ON documents
                USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
            """)

            # 4. Index on source_url for fast re-ingestion deletes
            cur.execute("""
                CREATE INDEX IF NOT EXISTS documents_source_url_idx
                ON documents (source_url);
            """)

    conn.close()
    print("[db] Schema ready (extension + table + indexes).")


# ── Write ─────────────────────────────────────────────────────────────────────

def save_chunks(chunks: list[dict], embeddings: list[list[float]]):
    """
    Upsert strategy: delete existing rows for these URLs, then insert fresh.
    This handles re-ingestion when page content changes.

    chunks     : list of { text, source_url, page_title, chunk_index }
    embeddings : parallel list of float vectors (same length as chunks)
    """
    if not chunks:
        return

    conn = _connect()
    with conn:
        with conn.cursor() as cur:
            # Delete stale rows for any URL we are about to re-insert
            urls = list({c["source_url"] for c in chunks})
            cur.execute(
                "DELETE FROM documents WHERE source_url = ANY(%s);",
                (urls,)
            )

            # Bulk insert
            rows = [
                (
                    c["source_url"],
                    c.get("page_title", ""),
                    c.get("chunk_index", 0),
                    c["text"],
                    embedding,
                )
                for c, embedding in zip(chunks, embeddings)
            ]

            execute_values(
                cur,
                """
                INSERT INTO documents (source_url, page_title, chunk_index, text, embedding)
                VALUES %s
                """,
                rows,
                template="(%s, %s, %s, %s, %s::vector)",
            )

    conn.close()
    print(f"[db] Saved {len(chunks)} chunks to documents table.")


# ── Read ──────────────────────────────────────────────────────────────────────

def search(query_embedding: list[float], top_k: int = TOP_K) -> list[dict]:
    """
    Cosine similarity search.
    Returns top_k most relevant chunks as list of dicts:
      { text, source_url, page_title, score }
    """
    conn = _connect()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT text, source_url, page_title,
                       1 - (embedding <=> %s::vector) AS score
                FROM   documents
                ORDER  BY embedding <=> %s::vector
                LIMIT  %s;
                """,
                (query_embedding, query_embedding, top_k),
            )
            rows = cur.fetchall()

    conn.close()

    return [
        {
            "text":       row[0],
            "source_url": row[1],
            "page_title": row[2],
            "score":      round(float(row[3]), 4),
        }
        for row in rows
    ]


# ── Utility ───────────────────────────────────────────────────────────────────

def clear_chunks():
    """Wipe all rows. Useful when doing a full re-ingest from scratch."""
    conn = _connect()
    with conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE documents RESTART IDENTITY;")
    conn.close()
    print("[db] documents table cleared.")


def get_stats() -> dict:
    """Return row count and distinct URL count — handy for health checks."""
    conn = _connect()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*), COUNT(DISTINCT source_url) FROM documents;")
            total_chunks, total_pages = cur.fetchone()
    conn.close()
    return {"total_chunks": total_chunks, "total_pages": total_pages}
