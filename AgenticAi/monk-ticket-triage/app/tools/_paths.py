"""Resolve mock data paths under ``data/{domain}/``."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def domain_data_dir(domain: str) -> Path:
    return DATA_DIR / domain
