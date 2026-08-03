"""Embed every chunk in a corpus and upsert into a pgvector table.

Usage:
    uv run python -m ingest.upsert --corpus data/sample-corpus/aws-docs --table docs
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

import psycopg

from app.llm import get_embeddings
from ingest.chunk import iter_corpus

DEFAULT_DSN = "postgresql://postgres:postgres@localhost:5433/monk"


def _sanitize_table(table: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise ValueError(f"invalid table name: {table!r}")
    return table


def ensure_table(conn: psycopg.Connection, table: str, dim: int) -> None:
    """Create the table + index if missing. Idempotent."""
    table = _sanitize_table(table)
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table} (
                chunk_id TEXT PRIMARY KEY,
                source_url TEXT NOT NULL,
                text TEXT NOT NULL,
                embedding vector({dim})
            );
            """
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS {table}_embedding_idx "
            f"ON {table} USING hnsw (embedding vector_cosine_ops);"
        )
    conn.commit()


def upsert_corpus(corpus_dir: Path, table: str, dsn: str | None = None, batch_size: int = 32) -> int:
    table = _sanitize_table(table)
    dsn = dsn or os.getenv("POSTGRES_DSN", DEFAULT_DSN)
    embedder = get_embeddings()
    items = list(iter_corpus(corpus_dir))
    if not items:
        print(f"[ingest] no .md files found under {corpus_dir}")
        return 0
    # Probe dim by embedding one chunk.
    sample_vec = embedder.embed_query("dimension probe")
    dim = len(sample_vec)
    with psycopg.connect(dsn) as conn:
        ensure_table(conn, table, dim)
        total = 0
        t0 = time.time()
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            texts = [t for _, _, t in batch]
            vecs = embedder.embed_documents(texts)
            with conn.cursor() as cur:
                for (chunk_id, url, text), vec in zip(batch, vecs, strict=False):
                    vec_lit = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
                    cur.execute(
                        f"""
                        INSERT INTO {table} (chunk_id, source_url, text, embedding)
                        VALUES (%s, %s, %s, %s::vector)
                        ON CONFLICT (chunk_id) DO UPDATE
                            SET source_url = EXCLUDED.source_url,
                                text       = EXCLUDED.text,
                                embedding  = EXCLUDED.embedding
                        """,
                        (chunk_id, url, text, vec_lit),
                    )
            conn.commit()
            total += len(batch)
            print(f"[ingest] {total}/{len(items)}")
        dur = time.time() - t0
        print(f"[ingest] done. {total} chunks upserted into {table} in {dur:.1f}s.")
    return total


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", type=Path, required=True, help="Directory containing .md files")
    p.add_argument("--table", default="docs", help="Pgvector table name (default: docs)")
    args = p.parse_args()
    if not args.corpus.exists():
        print(f"ERR: corpus not found: {args.corpus}")
        return 1
    upsert_corpus(args.corpus, args.table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
