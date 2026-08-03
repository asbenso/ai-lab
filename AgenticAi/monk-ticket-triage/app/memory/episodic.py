"""Episodic memory: similar past ticket resolutions from pgvector."""

from __future__ import annotations

import os

import psycopg

import app._env  # noqa: F401
from app.llm import get_embeddings

DEFAULT_DSN = "postgresql://postgres:postgres@localhost:5433/monk"

_SEARCH_SQL = """
SELECT id, domain, ticket_text, resolution_text,
       1 - (embedding <=> %s::vector) AS score
FROM past_resolutions
WHERE domain = %s
ORDER BY embedding <=> %s::vector
LIMIT %s
"""


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in values) + "]"


def similar_past_cases(ticket_text: str, domain: str, k: int = 3) -> list[dict]:
    """Find past resolutions similar to the current ticket text."""
    text = (ticket_text or "").strip()
    if not text:
        return []

    dsn = os.getenv("POSTGRES_DSN", DEFAULT_DSN)
    try:
        embedder = get_embeddings()
        query_vec = _vector_literal(embedder.embed_query(text))
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(_SEARCH_SQL, (query_vec, domain, query_vec, k))
            rows = cur.fetchall()
        return [
            {
                "id": str(row_id),
                "domain": str(row_domain),
                "ticket_text": str(t_text),
                "resolution_text": str(resolution_text),
                "score": float(score),
            }
            for row_id, row_domain, t_text, resolution_text, score in rows
        ]
    except Exception:
        return []


__all__ = ["similar_past_cases"]
