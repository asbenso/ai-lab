"""Shared LangGraph store factory for Project 2 memory layers."""

from __future__ import annotations

import os
import uuid
from functools import lru_cache
from typing import Any

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

import app._env  # noqa: F401

_store: BaseStore | None = None
_store_cm = None


@lru_cache(maxsize=1)
def _store_index_config() -> dict[str, Any]:
    from app.llm import get_embeddings

    embed = get_embeddings()
    dims = len(embed.embed_query("probe"))
    return {"dims": dims, "embed": embed, "fields": ["content"]}


def get_store() -> BaseStore:
    """Return a process-lifetime memory store (InMemory or Postgres)."""
    global _store, _store_cm
    if _store is not None:
        return _store

    index = _store_index_config()
    mode = (os.getenv("MONK_MEMORY") or "memory").strip().lower()
    if mode == "postgres":
        dsn = os.getenv("POSTGRES_DSN", "").strip()
        if not dsn:
            raise RuntimeError("MONK_MEMORY=postgres requires POSTGRES_DSN in the environment")
        from langgraph.store.postgres import PostgresStore

        _store_cm = PostgresStore.from_conn_string(dsn, index=index)
        _store = _store_cm.__enter__()
        _store.setup()
    else:
        _store = InMemoryStore(index=index)
    return _store


def new_memory_key(prefix: str = "fact") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"
