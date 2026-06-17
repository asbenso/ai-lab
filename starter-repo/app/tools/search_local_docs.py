"""Vector search over ingested document chunks in pgvector."""

from __future__ import annotations

import os

import psycopg
from langchain_core.tools import tool

from app.llm import get_embeddings
from ingest.upsert import _sanitize_table

DEFAULT_DSN = "postgresql://postgres:postgres@localhost:5433/monk"

_SEARCH_SQL = """
SELECT chunk_id, source_url, 1 - (embedding <=> %s::vector) AS score, text
FROM {table}
ORDER BY embedding <=> %s::vector
LIMIT %s
"""


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in values) + "]"


def _search_rows(query: str, k: int, table: str, dsn: str) -> list[dict]:
    safe_table = _sanitize_table(table)
    embedder = get_embeddings()
    query_vec = _vector_literal(embedder.embed_query(query))
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            _SEARCH_SQL.format(table=safe_table),
            (query_vec, query_vec, k),
        )
        rows = cur.fetchall()
    return [
        {
            "chunk_id": str(chunk_id),
            "source_url": str(source_url),
            "score": float(score),
            "text": str(text),
        }
        for chunk_id, source_url, score, text in rows
    ]


@tool
def search_local_docs(query: str, k: int = 5, table: str = "docs") -> list[dict]:
    """Search the ingested document corpus for content relevant to a query. Use this when the user asks about content in our internal documentation. Returns a list of citations each with a real source_url that you MUST cite back."""
    dsn = os.getenv("POSTGRES_DSN", DEFAULT_DSN)
    return _search_rows(query, k, table, dsn)


if __name__ == "__main__":
    from app.tools._smoke_common import smoke_setup
    from app.tools._smoke_demo import demo_search_local_docs

    smoke_setup()
    demo_search_local_docs()
