"""Seed sample past resolutions into pgvector for episodic memory."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import app._env  # noqa: F401
from app.llm import get_embeddings

DEFAULT_DSN = "postgresql://postgres:postgres@localhost:5433/monk"

SAMPLES: list[tuple[str, str, str, str]] = [
    (
        "it-helpdesk",
        "vpn-001",
        "VPN client hangs on connecting since this morning.",
        "Removed stale VPN profile, re-imported latest gateway bundle, verified system clock.",
    ),
    (
        "it-helpdesk",
        "vpn-002",
        "Cannot reach internal wiki over VPN; split tunnel issue.",
        "Updated split-tunnel routes and had user restart the VPN client.",
    ),
    (
        "support",
        "mfa-001",
        "Cannot log in - MFA loop after entering authenticator codes.",
        "Cleared cookies, resynced authenticator app time, reset MFA device.",
    ),
    (
        "support",
        "billing-001",
        "Cancelled plan but still charged on renewal date.",
        "Confirmed cancellation date and issued refund per billing policy.",
    ),
    (
        "oncall",
        "outage-001",
        "503 storm on api-gateway after deploy.",
        "Rolled back api-core to last good release; error rate recovered within 12 minutes.",
    ),
]


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in values) + "]"


def main() -> None:
    dsn = os.getenv("POSTGRES_DSN", DEFAULT_DSN)
    embedder = get_embeddings()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for domain, row_id, ticket_text, resolution_text in SAMPLES:
            combined = f"{ticket_text}\n{resolution_text}"
            vec = _vector_literal(embedder.embed_query(combined))
            cur.execute(
                """
                INSERT INTO past_resolutions (id, domain, ticket_text, resolution_text, embedding)
                VALUES (%s, %s, %s, %s, %s::vector)
                ON CONFLICT (id) DO UPDATE
                    SET domain = EXCLUDED.domain,
                        ticket_text = EXCLUDED.ticket_text,
                        resolution_text = EXCLUDED.resolution_text,
                        embedding = EXCLUDED.embedding
                """,
                (row_id, domain, ticket_text, resolution_text, vec),
            )
        conn.commit()
    print(f"[seed] upserted {len(SAMPLES)} past_resolutions row(s)")


if __name__ == "__main__":
    main()
