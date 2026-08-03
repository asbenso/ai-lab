"""Query mock service logs for the current domain."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from langchain_core.tools import tool

from app.tools._domain import get_domain
from app.tools._paths import domain_data_dir
from app.tools._since import parse_since


def _parse_ts(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text).astimezone(UTC)


def _filter_by_since(entries: list[dict], since: str) -> list[dict]:
    if not entries:
        return []
    window = parse_since(since)
    timestamps = [_parse_ts(str(item["timestamp"])) for item in entries if item.get("timestamp")]
    if not timestamps:
        return entries
    anchor = max(timestamps)
    cutoff = anchor - window
    return [
        item
        for item in entries
        if item.get("timestamp") and _parse_ts(str(item["timestamp"])) >= cutoff
    ]


def _load_logs(domain: str) -> dict[str, list[dict]]:
    path = domain_data_dir(domain) / "mock_logs.json"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


@tool
def query_logs(service: str, since: str = "1h") -> list[dict]:
    """Fetch recent log lines for a service. Use this when investigating errors, outages, or auth failures in application logs."""
    domain = get_domain()
    logs_by_service = _load_logs(domain)
    entries = logs_by_service.get(service, [])
    return _filter_by_since(entries, since)
