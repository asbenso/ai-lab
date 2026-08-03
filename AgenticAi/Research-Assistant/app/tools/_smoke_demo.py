"""Shared smoke-test demos for Project 1 tools (CLI `python -m app.tools.*`)."""

from __future__ import annotations

from app.tools._smoke_common import (
    FALLBACK_FETCH_URL,
    LOCAL_DOCS_K,
    LOCAL_DOCS_QUERY,
    SEARCH_K,
    SEARCH_QUERY,
    SUMMARIZE_FOCUS,
    pick_fetchable_url,
    preview,
    run_smoke_tool,
    smoke_setup,
    smoke_teardown,
)
from app.tools.fetch_url import _run_fetch_url
from app.tools.search_local_docs import _run_search_local_docs
from app.tools.summarize import _run_summarize
from app.tools.web_search import _run_web_search


def demo_web_search(*, setup: bool = True, teardown: bool = True) -> list[dict]:
    if setup:
        smoke_setup()
    print("=== web_search ===")
    results = run_smoke_tool(_run_web_search, query=SEARCH_QUERY, k=SEARCH_K)
    print(f"Got {len(results)} result(s) for {SEARCH_QUERY!r}:")
    for i, hit in enumerate(results, start=1):
        print(f"\n  [{i}] {hit['title']}")
        print(f"      url:     {hit['url']}")
        print(f"      snippet: {preview(hit['content'])}")
    if teardown:
        smoke_teardown()
    return results


def demo_fetch_url(
    results: list[dict] | None = None, *, setup: bool = True, teardown: bool = True
) -> str:
    if setup:
        smoke_setup()
    print("=== fetch_url ===")
    if results is None:
        results = run_smoke_tool(_run_web_search, query=SEARCH_QUERY, k=SEARCH_K)
    url = pick_fetchable_url(results) or FALLBACK_FETCH_URL
    print(f"Fetching: {url}")
    page = run_smoke_tool(_run_fetch_url, url=url)
    body = page.split("\n", 1)[1] if "\n" in page else page
    print(preview(body))
    print(f"({len(page)} chars total)")
    if teardown:
        smoke_teardown()
    return page


def demo_summarize(
    text: str | None = None,
    focus: str = SUMMARIZE_FOCUS,
    *,
    setup: bool = True,
    teardown: bool = True,
) -> str:
    if text is None:
        text = demo_fetch_url(setup=setup, teardown=False)
    elif setup:
        smoke_setup()
    print("=== summarize ===")
    print(f"Focus: {focus!r}")
    summary = run_smoke_tool(_run_summarize, text=text, focus=focus)
    print(summary)
    if teardown:
        smoke_teardown()
    return summary


def demo_search_local_docs(*, setup: bool = True, teardown: bool = True) -> list[dict]:
    if setup:
        smoke_setup()
    print("=== search_local_docs ===")
    try:
        results = run_smoke_tool(
            _run_search_local_docs,
            query=LOCAL_DOCS_QUERY,
            k=LOCAL_DOCS_K,
            table="docs",
        )
        print(f"Got {len(results)} hit(s) for {LOCAL_DOCS_QUERY!r}:")
        for i, hit in enumerate(results, start=1):
            print(f"\n  [{i}] score={hit['score']:.3f}  {hit['source_url']}")
            print(f"      {preview(hit['text'])}")
        return results
    except Exception as exc:
        print(f"ERR: {type(exc).__name__}: {exc}")
        print(
            "hint: start Postgres with `docker compose up -d postgres`, "
            "then ingest: `make ingest CORPUS=aws-docs`"
        )
        if teardown:
            smoke_teardown()
        return []

    if teardown:
        smoke_teardown()
    return results


def demo_all() -> None:
    smoke_setup()
    results = demo_web_search(setup=False, teardown=False)
    page = demo_fetch_url(results, setup=False, teardown=False)
    demo_summarize(page, setup=False, teardown=False)
    demo_search_local_docs(setup=False, teardown=False)
    smoke_teardown()
    print("\nAll tool smoke checks passed.")
