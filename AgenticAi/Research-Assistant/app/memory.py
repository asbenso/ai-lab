"""Long-term memory helpers backed by LangGraph stores."""

from __future__ import annotations

import os
import uuid
from functools import lru_cache
from typing import Any, Literal

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

_store: BaseStore | None = None
_store_cm = None


@lru_cache(maxsize=1)
def _store_index_config() -> dict[str, Any]:
    """Vector index config for semantic recall over the ``content`` field."""
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


def recall(
    store: BaseStore,
    namespace: tuple[str, ...],
    query: str,
    *,
    k: int = 3,
) -> list[dict]:
    """Search memories in ``namespace``. Each item has ``key``, ``value``, ``score``."""
    items = store.search(namespace, query=query or None, limit=k)
    return [
        {
            "key": item.key,
            "value": dict(item.value) if item.value is not None else {},
            "score": item.score,
        }
        for item in items
    ]


def remember(
    store: BaseStore,
    namespace: tuple[str, ...],
    content: str,
    kind: Literal["preference", "fact"],
) -> str:
    """Write a memory entry; returns the auto-generated key."""
    text = content.strip()
    if not text:
        raise ValueError("remember() requires non-empty content")
    key = f"{kind}-{uuid.uuid4().hex[:12]}"
    store.put(namespace, key, {"content": text, "kind": kind})
    return key


__all__ = ["get_store", "recall", "remember"]
