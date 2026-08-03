"""Search runbooks for the current domain."""

from __future__ import annotations

from langchain_core.tools import tool

from app.tools._domain import get_domain
from app.tools.search_local_docs import search_local_docs


@tool
def search_runbooks(query: str, k: int = 3) -> list[dict]:
    """Search internal runbooks for remediation steps. Use this when you need documented procedures for a ticket category or symptom."""
    domain = get_domain()
    table = "runbooks_" + domain.replace("-", "_")
    return search_local_docs(query, k=k, table=table)
