"""LangSmith tracing health check. Run: `uv run python -m app.tracing_check`"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from app._env import sync_langsmith_env
from app.tracing import (
    configure_langsmith_endpoint,
    setup_langsmith_tracing,
    tracing_opted_out,
    tracing_requested,
)


def check_langsmith_tracing() -> bool:
    """Verify tracing is on and the API key can reach LangSmith."""
    if tracing_opted_out():
        print("LangSmith tracing is opted out (MONK_NO_TRACE=1 or LANGSMITH_TRACING=false).")
        print("Event tracking is on by default — unset those to re-enable.")
        return False
    if not tracing_requested():
        print("LangSmith tracing is OFF.")
        return False

    api_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
    if not api_key:
        print("Missing LANGSMITH_API_KEY in .env")
        return False

    if not api_key.startswith(("lsv2_pt_", "lsv2_sk_")):
        print("Warning: key should start with lsv2_pt_ (personal) or lsv2_sk_ (service).")

    project = os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT") or "default"
    print(f"Checking LangSmith (project={project!r})...")

    try:
        if configure_langsmith_endpoint(verbose=True):
            endpoint = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
            print(
                f"LangSmith tracing OK ({endpoint}) — check project '{project}' on smith.langchain.com"
            )
            return True
        print("LangSmith tracing FAILED: API key cannot reach LangSmith (403/401 on all regions).")
    except Exception as exc:
        print(f"LangSmith tracing FAILED: {type(exc).__name__}: {str(exc)[:200]}")

    print(
        "Fix:\n"
        "  1. smith.langchain.com → Settings → API Keys → Create API Key (Personal Access Token)\n"
        "  2. Paste into .env as LANGSMITH_API_KEY=lsv2_pt_...\n"
        "  3. Confirm project exists (or create 'resonance' in the UI)\n"
        "  4. Do NOT set LANGSMITH_WORKSPACE_ID for personal tokens\n"
        "  5. EU accounts: add LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com to .env"
    )
    return False


def main() -> int:
    load_dotenv(override=True)
    sync_langsmith_env()
    setup_langsmith_tracing()
    return 0 if check_langsmith_tracing() else 1


if __name__ == "__main__":
    raise SystemExit(main())
