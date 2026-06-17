"""Monk Technologies - AI Research Assistant (Project 1).

This package auto-loads `.env` from the project root on import so that
`MONK_MODEL`, `MONK_EMBEDDINGS`, `POSTGRES_DSN`, etc. resolve correctly when
the app is launched via `uvicorn`, `python -m`, or `pytest`. Project `.env`
values override stale shell exports (`override=True`).
"""
from __future__ import annotations

from pathlib import Path

try:
    from dotenv import load_dotenv

    from app._env import sync_langsmith_env
    from app.tracing import ensure_langsmith_tracing

    _project_root = Path(__file__).resolve().parent.parent
    _env = _project_root / ".env"
    if _env.exists():
        load_dotenv(_env, override=True)
    sync_langsmith_env()
    ensure_langsmith_tracing()
except Exception:
    pass
