"""LangSmith / LangChain tracing helpers."""

from __future__ import annotations

import functools
import logging
import os
from collections.abc import Callable
from typing import Any, TypeVar

_TRUTHY = frozenset({"true", "1", "yes"})
_warned_disabled = False

DEFAULT_LANGSMITH_API_URLS = (
    "https://api.smith.langchain.com",
    "https://eu.api.smith.langchain.com",
)

TRACE_PREVIEW_CHARS = 500

F = TypeVar("F", bound=Callable[..., Any])


def trace_preview_text(text: str, *, max_chars: int = TRACE_PREVIEW_CHARS) -> str:
    """Collapse whitespace and truncate long strings for LangSmith payloads."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[:max_chars].rstrip() + f"... ({len(text)} chars total)"


def truncate_trace_text_input(inputs: dict) -> dict:
    """Shrink large ``text`` tool inputs before they are logged to LangSmith."""
    out = dict(inputs)
    text = out.get("text")
    if isinstance(text, str) and len(text) > TRACE_PREVIEW_CHARS:
        out["text"] = trace_preview_text(text)
    return out


def truncate_trace_text_output(output: Any) -> Any:
    """Shrink large string tool outputs before they are logged to LangSmith."""
    if isinstance(output, str) and len(output) > TRACE_PREVIEW_CHARS:
        return trace_preview_text(output)
    return output


def truncate_trace_list_field(output: Any, field: str) -> Any:
    """Shrink a long string field inside each dict in a tool result list."""
    if not isinstance(output, list):
        return output
    trimmed: list[Any] = []
    for item in output:
        if not isinstance(item, dict):
            trimmed.append(item)
            continue
        row = dict(item)
        value = row.get(field)
        if isinstance(value, str) and len(value) > TRACE_PREVIEW_CHARS:
            row[field] = trace_preview_text(value)
        trimmed.append(row)
    return trimmed


def truncate_trace_search_results(output: Any) -> Any:
    """Shrink Tavily ``content`` snippets in traced web-search results."""
    return truncate_trace_list_field(output, "content")


def truncate_trace_local_docs_results(output: Any) -> Any:
    """Shrink chunk ``text`` fields in traced local-doc search results."""
    return truncate_trace_list_field(output, "text")


def tool_trace(
    name: str,
    *,
    process_inputs: Callable[[dict], dict] | None = None,
    process_outputs: Callable[..., Any] | None = None,
) -> Callable[[F], F]:
    """Wrap a tool implementation with a LangSmith ``@traceable`` tool run."""
    from langsmith import traceable

    return traceable(
        run_type="tool",
        name=name,
        process_inputs=process_inputs,
        process_outputs=process_outputs,
    )


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in _TRUTHY


def enable_langsmith_tracing() -> None:
    """Turn on LangSmith tracing (reads LANGSMITH_API_KEY / LANGSMITH_PROJECT from env)."""
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    ensure_langsmith_tracing.cache_clear()


def disable_langsmith_tracing(*, silent: bool = False) -> None:
    """Turn off LangSmith tracing so local runs don't flood stderr with 403s on bad keys."""
    global _warned_disabled
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    _quiet_langsmith_logs()
    ensure_langsmith_tracing.cache_clear()
    if not silent and not _warned_disabled:
        _warned_disabled = True
        print(
            "LangSmith: tracing disabled (API key cannot write runs — often 403). "
            "Run: uv run python -m app.tracing_check"
        )


def tracing_opted_out() -> bool:
    """Return True when LangSmith event tracking was explicitly disabled."""
    if _is_truthy(os.getenv("MONK_NO_TRACE")):
        return True
    for key in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"):
        value = (os.getenv(key) or "").strip().lower()
        if value in ("false", "0", "no"):
            return True
    return False


def tracing_requested() -> bool:
    """LangSmith event tracking is on by default; opt out with ``MONK_NO_TRACE=1``."""
    return not tracing_opted_out()


def tracing_enabled() -> bool:
    if tracing_opted_out():
        return False
    return _is_truthy(os.getenv("LANGSMITH_TRACING")) or _is_truthy(
        os.getenv("LANGCHAIN_TRACING_V2")
    )


def setup_langsmith_tracing(*, verbose: bool = False) -> bool:
    """Turn on LangSmith tracing unless opted out; verify the API key can write runs."""
    if tracing_opted_out():
        disable_langsmith_tracing(silent=True)
        return False
    enable_langsmith_tracing()
    return ensure_langsmith_tracing(verbose=verbose)


def flush_langsmith_traces(*, timeout: float = 30.0) -> None:
    """Push buffered LangSmith runs before a short-lived process or task exits."""
    if not tracing_enabled():
        return
    try:
        from langchain_core.tracers.langchain import wait_for_all_tracers
    except ImportError:
        wait_for_all_tracers = None  # type: ignore[assignment,misc]

    try:
        from langsmith import Client

        client = Client()
        if wait_for_all_tracers is not None:
            wait_for_all_tracers()
        client.flush(timeout=timeout)
    except Exception:
        pass


def langsmith_ui_hint() -> str:
    """Human-readable pointer to the project where tool runs land."""
    project = _langsmith_project()
    endpoint = _langsmith_api_url()
    host = "smith.langchain.com" if "eu.api" not in endpoint else "eu.smith.langchain.com"
    return f"View traces at https://{host} → project {project!r} (filter: run type Tool)"


def _quiet_langsmith_logs() -> None:
    for name in ("langsmith", "langsmith.client"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


def _langsmith_api_url() -> str:
    return (
        os.getenv("LANGSMITH_ENDPOINT")
        or os.getenv("LANGCHAIN_ENDPOINT")
        or DEFAULT_LANGSMITH_API_URLS[0]
    ).rstrip("/")


def _langsmith_project() -> str:
    return os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT") or "default"


def _probe_langsmith_write_at(api_url: str) -> tuple[bool, int]:
    """Verify the API key can read the project (no orphan runs created)."""
    api_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
    if not api_key:
        return False, 0

    import httpx

    response = httpx.get(
        f"{api_url.rstrip('/')}/sessions",
        headers={"x-api-key": api_key},
        params={"limit": 1},
        timeout=15.0,
    )
    return response.status_code == 200, response.status_code


def configure_langsmith_endpoint(*, verbose: bool = False) -> bool:
    """Pick a working LangSmith API region (US then EU) and set LANGSMITH_ENDPOINT."""
    configured = os.getenv("LANGSMITH_ENDPOINT") or os.getenv("LANGCHAIN_ENDPOINT")
    candidates: list[str] = []
    if configured:
        candidates.append(configured.rstrip("/"))
    for url in DEFAULT_LANGSMITH_API_URLS:
        if url not in candidates:
            candidates.append(url)

    for api_url in candidates:
        ok, status = _probe_langsmith_write_at(api_url)
        if verbose:
            label = "configured" if configured and api_url == configured.rstrip("/") else "auto"
            print(f"  [{label}] {api_url} → HTTP {status}")
        if ok:
            os.environ["LANGSMITH_ENDPOINT"] = api_url
            os.environ["LANGCHAIN_ENDPOINT"] = api_url
            return True
    return False


def _probe_langsmith_write() -> bool:
    """Return True if the current (or discovered) endpoint accepts run writes."""
    if configure_langsmith_endpoint():
        return True
    api_url = _langsmith_api_url()
    ok, _ = _probe_langsmith_write_at(api_url)
    return ok


@functools.lru_cache(maxsize=1)
def ensure_langsmith_tracing(*, verbose: bool = False) -> bool:
    """Enable tracing only when the API key can write runs; otherwise disable."""
    if not tracing_enabled():
        return False

    api_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
    if not api_key:
        disable_langsmith_tracing(silent=not verbose)
        if verbose:
            print("LangSmith: tracing disabled (missing LANGSMITH_API_KEY in .env)")
        return False

    try:
        if configure_langsmith_endpoint(verbose=verbose):
            return True
    except Exception:
        pass

    disable_langsmith_tracing(silent=not verbose)
    return False
