"""LangSmith / LangChain tracing helpers."""

from __future__ import annotations

import functools
import logging
import os

_TRUTHY = frozenset({"true", "1", "yes"})
_warned_disabled = False

DEFAULT_LANGSMITH_API_URLS = (
    "https://api.smith.langchain.com",
    "https://eu.api.smith.langchain.com",
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


def tracing_enabled() -> bool:
    return _is_truthy(os.getenv("LANGSMITH_TRACING")) or _is_truthy(os.getenv("LANGCHAIN_TRACING_V2"))


def flush_langsmith_traces(*, timeout: float = 10.0) -> None:
    """Push buffered LangSmith runs before a short-lived CLI process exits."""
    if not tracing_enabled():
        return
    try:
        from langsmith import Client

        Client().flush(timeout=timeout)
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
    """POST a minimal run to a specific LangSmith API host. Returns (ok, status_code)."""
    api_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
    if not api_key:
        return False, 0

    import httpx

    response = httpx.post(
        f"{api_url.rstrip('/')}/runs",
        headers={"x-api-key": api_key},
        json={
            "session_name": _langsmith_project(),
            "name": "tracing-probe",
            "run_type": "chain",
            "inputs": {"probe": True},
        },
        timeout=15.0,
    )
    return response.status_code in (200, 201, 202), response.status_code


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
