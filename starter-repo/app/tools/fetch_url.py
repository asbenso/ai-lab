"""Fetch and extract readable text from a URL."""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup
from langchain_core.tools import tool
from langsmith import traceable

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
MAX_CONTENT_CHARS = 8000
REQUEST_TIMEOUT_SECONDS = 10.0


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


@traceable(run_type="tool", name="fetch_url")
def _run_fetch_url(url: str) -> str:
    headers = {"User-Agent": BROWSER_USER_AGENT}
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
    text = _extract_text(response.text)
    if len(text) > MAX_CONTENT_CHARS:
        text = text[:MAX_CONTENT_CHARS]
    return f"[Source: {url}]\n{text}"


@tool
def fetch_url(url: str) -> str:
    """Download a web page and return its main text with scripts and markup removed. Use this when you have a specific URL from search results and need the page body to read or summarize."""
    return _run_fetch_url(url)


if __name__ == "__main__":
    from app.tools._smoke_demo import demo_fetch_url

    demo_fetch_url()
