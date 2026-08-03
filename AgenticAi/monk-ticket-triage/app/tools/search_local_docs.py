"""Shared pgvector search utility (used by search_runbooks)."""

from __future__ import annotations

import os
import re

import psycopg

import app._env  # noqa: F401 — POSTGRES_DSN from monk-ticket-triage/.env
from app.llm import get_embeddings
from app.tools._paths import domain_data_dir

DEFAULT_DSN = "postgresql://postgres:postgres@localhost:5433/monk"

_SEARCH_SQL = """
SELECT chunk_id, source_url, 1 - (embedding <=> %s::vector) AS score, text
FROM {table}
ORDER BY embedding <=> %s::vector
LIMIT %s
"""


def _sanitize_table(table: str) -> str:
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", table):
        raise ValueError(f"Invalid table name: {table!r}")
    return table


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in values) + "]"


def _search_runbook_files(domain: str, query: str, k: int) -> list[dict]:
    """Keyword fallback when pgvector table is unavailable."""
    runbooks_dir = domain_data_dir(domain) / "runbooks"
    if not runbooks_dir.is_dir():
        return []
    terms = [t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9\-]+", query) if len(t) > 2]
    hits: list[tuple[float, dict]] = []
    for path in sorted(runbooks_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        score = sum(1 for term in terms if term in lower) / max(len(terms), 1)
        if score <= 0:
            continue
        source = ""
        for line in text.splitlines()[:3]:
            if "source:" in line:
                source = line.split("source:", 1)[1].strip().rstrip("-->").strip()
                break
        hits.append(
            (
                score,
                {
                    "chunk_id": path.stem,
                    "source_url": source or f"runbook://{domain}/{path.stem}",
                    "score": score,
                    "text": text[:1200],
                },
            )
        )
    hits.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in hits[:k]]


def search_local_docs(query: str, k: int = 5, table: str = "docs") -> list[dict]:
    """Search an ingested pgvector table; falls back to runbook markdown files."""
    safe_table = _sanitize_table(table)
    dsn = os.getenv("POSTGRES_DSN", DEFAULT_DSN)
    try:
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
    except Exception:
        domain = table.removeprefix("runbooks_").replace("_", "-")
        if table.startswith("runbooks_"):
            return _search_runbook_files(domain, query, k)
        return []
