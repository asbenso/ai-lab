"""Shared smoke-test demos for Project 1 tools (CLI `python -m app.tools.*`)."""

from __future__ import annotations

from app.tools._smoke_common import (
    FALLBACK_FETCH_URL,
    SEARCH_K,
    SEARCH_QUERY,
    SUMMARIZE_FOCUS,
    pick_fetchable_url,
    preview,
    smoke_setup,
)
from app.tools.fetch_url import fetch_url
from app.tools.summarize import summarize
from app.tools.web_search import web_search


def demo_web_search() -> list[dict]:
    print("=== web_search ===")
    results = web_search.invoke({"query": SEARCH_QUERY, "k": SEARCH_K})
    print(f"Got {len(results)} result(s) for {SEARCH_QUERY!r}:")
    for i, hit in enumerate(results, start=1):
        print(f"\n  [{i}] {hit['title']}")
        print(f"      url:     {hit['url']}")
        print(f"      snippet: {preview(hit['content'])}")
    return results


def demo_fetch_url(results: list[dict] | None = None) -> str:
    print("=== fetch_url ===")
    if results is None:
        results = web_search.invoke({"query": SEARCH_QUERY, "k": SEARCH_K})
    url = pick_fetchable_url(results) or FALLBACK_FETCH_URL
    print(f"Fetching: {url}")
    page = fetch_url.invoke({"url": url})
    body = page.split("\n", 1)[1] if "\n" in page else page
    print(preview(body))
    print(f"({len(page)} chars total)")
    return page


def demo_summarize(text: str | None = None, focus: str = SUMMARIZE_FOCUS) -> str:
    if text is None:
        text = demo_fetch_url()
    print("=== summarize ===")
    print(f"Focus: {focus!r}")
    summary = summarize.invoke({"text": text, "focus": focus})
    print(summary)
    return summary


def demo_all() -> None:
    smoke_setup()
    results = demo_web_search()
    page = demo_fetch_url(results)
    demo_summarize(page)
    print("\nAll tool smoke checks passed.")
