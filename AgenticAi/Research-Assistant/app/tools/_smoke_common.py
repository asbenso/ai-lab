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


def _no_trace_enabled() -> bool:
    return (os.getenv("MONK_NO_TRACE") or "").strip().lower() in _TRUTHY


def smoke_setup() -> None:
    """Load `.env` and configure LangSmith for CLI smoke tests.

    LangSmith event tracking is **on by default** when ``LANGSMITH_API_KEY`` is set.
    Set ``MONK_NO_TRACE=1`` to suppress traces for a single run.
    """
    from pathlib import Path

    from dotenv import load_dotenv

    from app._env import sync_langsmith_env
    from app.tracing import disable_langsmith_tracing, setup_langsmith_tracing

    root = Path(__file__).resolve().parents[2]
    env_file = root / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)
    else:
        load_dotenv(override=True)
    sync_langsmith_env()

    if _no_trace_enabled():
        disable_langsmith_tracing(silent=True)
        print("LangSmith tracing OFF (MONK_NO_TRACE=1)")
        return

    if setup_langsmith_tracing(verbose=False):
        project = os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT") or "default"
        endpoint = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
        print(f"LangSmith tracing ON (project={project!r}, {endpoint})")
        return

    api_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
    if not api_key:
        print("LangSmith tracing OFF (missing LANGSMITH_API_KEY in .env)")
    else:
        print("LangSmith tracing OFF (API probe failed — run: uv run python -m app.tracing_check)")


def smoke_teardown() -> None:
    """Flush buffered LangSmith runs before the CLI exits."""
    from app.tracing import flush_langsmith_traces, langsmith_ui_hint, tracing_enabled

    flush_langsmith_traces()
    if tracing_enabled():
        print(langsmith_ui_hint())


def run_smoke_tool(fn, /, **kwargs):
    """Run a traced tool impl as its own root LangSmith run (CLI smoke tests only).

    Calls the ``_run_*`` helper directly instead of ``tool.invoke()`` so LangChain
    does not emit a second nameless tool run. Flushes after each tool so every
    step appears in LangSmith even when several run back-to-back.
    """
    from collections.abc import Callable
    from typing import TypeVar

    from langsmith.run_helpers import tracing_context

    from app.tracing import flush_langsmith_traces

    T = TypeVar("T")
    typed_fn: Callable[..., T] = fn
    with tracing_context(parent=False):
        result = typed_fn(**kwargs)
    flush_langsmith_traces()
    return result


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
