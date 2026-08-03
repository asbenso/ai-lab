"""Web search via Tavily."""

from __future__ import annotations

import os

from langchain_core.tools import tool
from tavily import TavilyClient

from app.tracing import tool_trace, truncate_trace_search_results

MOCK_RESULT = {"title": "mock", "url": "https://example.com", "content": ""}


def _mock_results(query: str) -> list[dict]:
    return [{**MOCK_RESULT, "content": query}]


def _tavily_results(query: str, k: int) -> list[dict]:
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    response = client.search(query, max_results=k)
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
        }
        for item in response.get("results", [])[:k]
    ]


@tool_trace("web_search", process_outputs=truncate_trace_search_results)
def _run_web_search(query: str, k: int = 5) -> list[dict]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return _mock_results(query)
    return _tavily_results(query, k)


@tool
def web_search(query: str, k: int = 5) -> list[dict]:
    """Search the public web for pages relevant to a query and return title, URL, and snippet for each hit. Use this when you need fresh external sources before fetching or summarizing pages."""
    return _run_web_search(query, k)


if __name__ == "__main__":
    from app.tools._smoke_demo import demo_web_search

    demo_web_search()
