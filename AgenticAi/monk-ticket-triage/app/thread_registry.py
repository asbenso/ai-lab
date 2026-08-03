"""Shared thread registry for HITL approval (Postgres in production, file locally)."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

_registry_lock = threading.Lock()
_postgres_ready = False
_postgres_pool = None

THREAD_REGISTRY_PATH = Path(os.getenv("THREAD_REGISTRY_PATH", "/tmp/monk_threads.json"))


def _use_postgres() -> bool:
    if os.getenv("MONK_CHECKPOINT", "").lower() == "postgres":
        return bool(os.getenv("POSTGRES_DSN"))
    dsn = os.getenv("POSTGRES_DSN", "")
    return (
        os.getenv("MONK_MEMORY") == "postgres"
        and bool(dsn)
        and "localhost" not in dsn
        and "127.0.0.1" not in dsn
    )


def _ensure_postgres() -> None:
    global _postgres_ready, _postgres_pool
    if _postgres_ready:
        return
    with _registry_lock:
        if _postgres_ready:
            return
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        _postgres_pool = ConnectionPool(
            os.environ["POSTGRES_DSN"],
            min_size=1,
            max_size=3,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
        with _postgres_pool.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS monk_thread_registry (
                    thread_id TEXT PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        _postgres_ready = True


def init_registry() -> None:
    if _use_postgres():
        _ensure_postgres()


def shutdown_registry() -> None:
    global _postgres_ready, _postgres_pool
    if _postgres_pool is not None:
        try:
            _postgres_pool.close()
        except Exception:
            pass
    _postgres_pool = None
    _postgres_ready = False


def _load_file_threads() -> set[str]:
    if not THREAD_REGISTRY_PATH.exists():
        return set()
    try:
        data = json.loads(THREAD_REGISTRY_PATH.read_text())
        return set(data) if isinstance(data, list) else set()
    except (json.JSONDecodeError, OSError):
        return set()


def _save_file_threads(threads: set[str]) -> None:
    THREAD_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    THREAD_REGISTRY_PATH.write_text(json.dumps(sorted(threads)))


def register_thread(thread_id: str) -> None:
    with _registry_lock:
        if _use_postgres():
            _ensure_postgres()
            with _postgres_pool.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO monk_thread_registry (thread_id)
                    VALUES (%s)
                    ON CONFLICT (thread_id) DO NOTHING
                    """,
                    (thread_id,),
                )
            return
        threads = _load_file_threads()
        threads.add(thread_id)
        _save_file_threads(threads)


def list_threads() -> set[str]:
    with _registry_lock:
        if _use_postgres():
            _ensure_postgres()
            with _postgres_pool.connection() as conn:
                rows = conn.execute("SELECT thread_id FROM monk_thread_registry").fetchall()
            return {row["thread_id"] for row in rows}
        return _load_file_threads()


def remove_thread(thread_id: str) -> None:
    with _registry_lock:
        if _use_postgres():
            _ensure_postgres()
            with _postgres_pool.connection() as conn:
                conn.execute(
                    "DELETE FROM monk_thread_registry WHERE thread_id = %s",
                    (thread_id,),
                )
            return
        threads = _load_file_threads()
        if thread_id in threads:
            threads.remove(thread_id)
            _save_file_threads(threads)
