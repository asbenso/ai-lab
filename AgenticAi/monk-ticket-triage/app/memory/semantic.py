"""Semantic memory: per-user facts and preferences via LangGraph Store."""

from __future__ import annotations

import re

from app.memory._store import get_store, new_memory_key


def _namespace_label(user_id: str) -> str:
    label = re.sub(r"[^a-zA-Z0-9_-]", "_", user_id.strip())
    if not label:
        raise ValueError("user_id is required")
    return label


def _user_namespace(user_id: str) -> tuple[str, str]:
    return ("users", _namespace_label(user_id))


def recall_user(user_id: str, k: int = 3) -> list[dict]:
    """Return up to ``k`` memories for the user. Each item has ``key``, ``value``, ``score``."""
    store = get_store()
    items = store.search(_user_namespace(user_id), query=None, limit=k)
    return [
        {
            "key": item.key,
            "value": dict(item.value) if item.value is not None else {},
            "score": item.score,
        }
        for item in items
    ]


def remember_user(user_id: str, content: str) -> str:
    """Persist a stable fact about the user. Returns the generated memory key."""
    text = content.strip()
    if not text:
        raise ValueError("remember_user() requires non-empty content")
    store = get_store()
    key = new_memory_key("fact")
    store.put(
        _user_namespace(user_id),
        key,
        {"content": text, "kind": "fact", "user_id": user_id.strip()},
    )
    return key


__all__ = ["recall_user", "remember_user"]
