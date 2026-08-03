"""Load Project 2 env from monk-ticket-triage/.env (fallback: Research-Assistant/.env)."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None  # type: ignore[misc, assignment]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_ENV = PROJECT_ROOT / ".env"
RESEARCH_ASSISTANT_ENV = PROJECT_ROOT.parent / "Research-Assistant" / ".env"


def load_monk_env() -> Path | None:
    """Load .env files with priority: shell env > local .env > Research-Assistant/.env."""
    if load_dotenv is None:
        return None

    # Snapshot shell-provided env before dotenv can override it.
    _shell_env = dict(os.environ)

    loaded: Path | None = None
    if RESEARCH_ASSISTANT_ENV.exists():
        load_dotenv(RESEARCH_ASSISTANT_ENV, override=False)
        loaded = RESEARCH_ASSISTANT_ENV
    if LOCAL_ENV.exists():
        load_dotenv(LOCAL_ENV, override=True)
        loaded = LOCAL_ENV

    # Shell env takes highest priority — restore any values overwritten by dotenv.
    os.environ.update(_shell_env)
    return loaded


load_monk_env()
