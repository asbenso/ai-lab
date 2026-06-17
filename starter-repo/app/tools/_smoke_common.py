"""Shared helpers for tool smoke tests."""

from __future__ import annotations

import os

_TRUTHY = frozenset({"true", "1", "yes"})

PREVIEW_CHARS = 200
SKIP_FETCH_HOSTS = ("youtube.com", "youtu.be", "twitter.com", "x.com")
SEARCH_QUERY = "LangGraph agent tutorial"
SEARCH_K = 3
LOCAL_DOCS_QUERY = "IAM access key rotation"
LOCAL_DOCS_K = 3
SUMMARIZE_FOCUS = "state"
FALLBACK_FETCH_URL = (
    "https://www.freecodecamp.org/news/how-to-develop-ai-agents-using-langgraph-a-practical-guide"
)


def _trace_smoke_enabled() -> bool:
    return (os.getenv("MONK_TRACE_SMOKE") or "").strip().lower() in _TRUTHY


def smoke_setup() -> None:
    """Load `.env`; disable LangSmith by default for CLI smoke tests.

    Set ``MONK_TRACE_SMOKE=1`` to keep tracing on (e.g. ``MONK_TRACE_SMOKE=1 uv run python -m app.tools``).
    """
    from pathlib import Path

    from dotenv import load_dotenv

    from app._env import sync_langsmith_env
    from app.tracing import (
        disable_langsmith_tracing,
        enable_langsmith_tracing,
        ensure_langsmith_tracing,
    )

    root = Path(__file__).resolve().parents[2]
    env_file = root / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)
    else:
        load_dotenv(override=True)
    sync_langsmith_env()
    if _trace_smoke_enabled():
        enable_langsmith_tracing()
        if ensure_langsmith_tracing(verbose=True):
            project = os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT") or "default"
            endpoint = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
            print(f"LangSmith tracing ON for smoke run (project={project!r}, {endpoint})")
        else:
            print("LangSmith tracing requested (MONK_TRACE_SMOKE=1) but probe failed; runs will not appear.")
        return
    # .env sets LANGSMITH_TRACING=true; smoke tests must not send traces by default.
    disable_langsmith_tracing(silent=True)


def preview(text: str, max_chars: int = PREVIEW_CHARS) -> str:
    """Single-line preview; ellipsis only when text is actually truncated."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[:max_chars].rstrip() + "..."


def pick_fetchable_url(results: list[dict]) -> str:
    """Prefer an article URL from search hits (skip video/social hosts)."""
    for hit in results:
        url = hit.get("url", "")
        if not url.startswith("http"):
            continue
        if any(host in url for host in SKIP_FETCH_HOSTS):
            continue
        return url
    if results:
        return results[0].get("url", FALLBACK_FETCH_URL)
    return FALLBACK_FETCH_URL
