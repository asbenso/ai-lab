"""Environment variable helpers (no app imports — safe during package init)."""

from __future__ import annotations

import os

_TRUTHY = frozenset({"true", "1", "yes"})


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in _TRUTHY


def sync_langsmith_env() -> None:
    """Mirror LangSmith vars to legacy LANGCHAIN_* names LangChain still reads."""
    api_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY") or ""
    # Personal access tokens use the default workspace; a stale WORKSPACE_ID → 403 writes.
    if api_key.startswith("lsv2_pt_"):
        os.environ.pop("LANGSMITH_WORKSPACE_ID", None)
    if api_key and not os.getenv("LANGCHAIN_API_KEY"):
        os.environ["LANGCHAIN_API_KEY"] = api_key
    project = os.getenv("LANGSMITH_PROJECT")
    if project and not os.getenv("LANGCHAIN_PROJECT"):
        os.environ["LANGCHAIN_PROJECT"] = project
    endpoint = os.getenv("LANGSMITH_ENDPOINT")
    if endpoint and not os.getenv("LANGCHAIN_ENDPOINT"):
        os.environ["LANGCHAIN_ENDPOINT"] = endpoint
    if _is_truthy(os.getenv("LANGSMITH_TRACING")):
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
