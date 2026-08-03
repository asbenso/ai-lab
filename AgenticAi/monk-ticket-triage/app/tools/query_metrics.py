"""Query mock metric snapshots for the current domain."""

from __future__ import annotations

import json

from langchain_core.tools import tool

from app.tools._domain import get_domain
from app.tools._paths import domain_data_dir


def _load_metrics(domain: str) -> dict:
    path = domain_data_dir(domain) / "mock_metrics.json"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


@tool
def query_metrics(service: str, metric: str, since: str = "1h") -> dict:
    """Fetch a metric snapshot (current, avg, p95, trend) for a service. Use this when checking whether latency, errors, or saturation are abnormal."""
    domain = get_domain()
    data = _load_metrics(domain)
    service_metrics = data.get(service) or {}
    snapshot = service_metrics.get(metric)
    if not isinstance(snapshot, dict):
        return {
            "service": service,
            "metric": metric,
            "current": None,
            "avg": None,
            "p95": None,
            "trend": "unknown",
            "since": since,
            "note": f"No metric data for {service}/{metric} in domain {domain!r}",
        }
    return {
        "service": service,
        "metric": metric,
        "current": snapshot.get("current"),
        "avg": snapshot.get("avg"),
        "p95": snapshot.get("p95"),
        "trend": snapshot.get("trend", "unknown"),
        "since": since,
    }
