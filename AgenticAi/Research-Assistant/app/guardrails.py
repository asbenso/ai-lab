"""Citation guardrails for research reports."""

from __future__ import annotations

import re

_MD_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^\s)]+)\)")
_BARE_URL_RE = re.compile(r"https?://[^\s)\]\"'<>]+")


def extract_urls(text: str) -> set[str]:
    """Find URLs in markdown ``[text](url)`` links and bare ``https://...`` patterns."""
    urls: set[str] = set()
    urls.update(_MD_LINK_RE.findall(text))
    urls.update(_BARE_URL_RE.findall(text))
    return urls


def validate_citations(report: str, allowed_urls: set[str]) -> tuple[bool, list[str]]:
    """Return ``(ok, bad_urls)`` where *bad_urls* are cited but not in *allowed_urls*."""
    cited = extract_urls(report)
    bad_urls = sorted(cited - allowed_urls)
    return (len(bad_urls) == 0, bad_urls)


__all__ = ["extract_urls", "validate_citations"]
