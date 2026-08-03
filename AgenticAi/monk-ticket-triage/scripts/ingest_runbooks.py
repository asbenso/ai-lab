"""Ingest domain runbooks into pgvector tables for search_runbooks."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import app._env  # noqa: F401
from app.llm import get_embeddings
from app.tools._paths import DATA_DIR, domain_data_dir

DEFAULT_DSN = "postgresql://postgres:postgres@localhost:5433/monk"
_SOURCE_RE = re.compile(r"<!--\s*source:\s*(\S+)\s*-->", re.IGNORECASE)


def _sanitize_table(table: str) -> str:
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", table):
        raise ValueError(f"Invalid table name: {table!r}")
    return table


def _read_markdown(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    match = _SOURCE_RE.search(text)
    if match:
        return match.group(1), text[match.end() :].lstrip("\n")
    return f"runbook://{path.stem}", text


def _chunk_text(text: str, max_chars: int = 700) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", text.strip())
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if buf_len + len(paragraph) + 2 <= max_chars or not buf:
            buf.append(paragraph)
            buf_len += len(paragraph) + 2
        else:
            chunks.append("\n\n".join(buf))
            buf = [paragraph]
            buf_len = len(paragraph)
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks or [text[:max_chars]]


def ensure_table(conn: psycopg.Connection, table: str, dim: int) -> None:
    safe = _sanitize_table(table)
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {safe} (
                chunk_id TEXT PRIMARY KEY,
                source_url TEXT NOT NULL,
                text TEXT NOT NULL,
                embedding vector({dim})
            );
            """
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS {safe}_embedding_idx "
            f"ON {safe} USING hnsw (embedding vector_cosine_ops);"
        )
    conn.commit()


def ingest_domain(domain: str, dsn: str) -> int:
    table = _sanitize_table("runbooks_" + domain.replace("-", "_"))
    runbooks_dir = domain_data_dir(domain) / "runbooks"
    if not runbooks_dir.is_dir():
        print(f"[ingest] skip {domain}: no runbooks dir at {runbooks_dir}")
        return 0

    embedder = get_embeddings()
    items: list[tuple[str, str, str]] = []
    for path in sorted(runbooks_dir.glob("*.md")):
        url, body = _read_markdown(path)
        for index, chunk in enumerate(_chunk_text(body)):
            chunk_id = f"{path.stem}::chunk-{index:03d}"
            items.append((chunk_id, url, chunk))

    if not items:
        print(f"[ingest] skip {domain}: no markdown files")
        return 0

    dim = len(embedder.embed_query("dimension probe"))
    with psycopg.connect(dsn) as conn:
        ensure_table(conn, table, dim)
        with conn.cursor() as cur:
            for chunk_id, url, text in items:
                vec = embedder.embed_query(text)
                vec_lit = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
                cur.execute(
                    f"""
                    INSERT INTO {table} (chunk_id, source_url, text, embedding)
                    VALUES (%s, %s, %s, %s::vector)
                    ON CONFLICT (chunk_id) DO UPDATE
                        SET source_url = EXCLUDED.source_url,
                            text = EXCLUDED.text,
                            embedding = EXCLUDED.embedding
                    """,
                    (chunk_id, url, text, vec_lit),
                )
        conn.commit()
    print(f"[ingest] {domain} -> {table}: {len(items)} chunk(s)")
    return len(items)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest P2 runbooks into pgvector")
    parser.add_argument(
        "--domain",
        action="append",
        choices=["support", "it-helpdesk", "oncall"],
        help="Domain to ingest (repeatable; default: all under data/)",
    )
    args = parser.parse_args()
    dsn = os.getenv("POSTGRES_DSN", DEFAULT_DSN)
    domains = args.domain or [p.name for p in DATA_DIR.iterdir() if p.is_dir()]
    total = 0
    for domain in domains:
        total += ingest_domain(domain, dsn)
    print(f"[ingest] done: {total} chunk(s) total")


if __name__ == "__main__":
    main()
