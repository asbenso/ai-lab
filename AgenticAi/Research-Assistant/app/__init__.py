"""Monk Technologies - AI Research Assistant (Project 1).

This package auto-loads `.env` from the project root on import so that
`MONK_MODEL`, `MONK_EMBEDDINGS`, `POSTGRES_DSN`, etc. resolve correctly when
the app is launched via `uvicorn`, `python -m`, or `pytest`. Shell env vars
take highest priority (e.g. MONK_MODEL=fake overrides .env).
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    from app._env import sync_langsmith_env
    from app.tracing import setup_langsmith_tracing

    # Snapshot shell-provided env before dotenv can override it.
    _shell_env = dict(os.environ)

    _project_root = Path(__file__).resolve().parent.parent
    _env = _project_root / ".env"
    if _env.exists():
        load_dotenv(_env, override=True)

    # Shell env wins over .env — restore any values overwritten above.
    os.environ.update(_shell_env)

    sync_langsmith_env()
    setup_langsmith_tracing()
except Exception:
    pass
