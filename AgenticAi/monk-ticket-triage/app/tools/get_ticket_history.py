"""Fetch prior tickets for a user in the current domain."""

from __future__ import annotations

import json

from langchain_core.tools import tool

from app.tools._domain import get_domain
from app.tools._paths import domain_data_dir


def _load_history(domain: str) -> list[dict]:
    path = domain_data_dir(domain) / "historical_tickets.jsonl"
    if not path.is_file():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _user_id(row: dict) -> str:
    return str(row.get("user_id") or row.get("sender") or "").strip()


@tool
def get_ticket_history(user_id: str, k: int = 5) -> list[dict]:
    """Return the user's recent tickets. Use this when prior incidents or patterns may explain the current issue."""
    domain = get_domain()
    matches = [row for row in _load_history(domain) if _user_id(row) == user_id.strip()]
    return matches[-k:]
