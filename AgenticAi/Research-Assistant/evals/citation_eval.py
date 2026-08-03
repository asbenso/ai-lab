"""Citation eval: full graph -> three programmatic checks on the rendered report.

For each golden row we:

1. Run planner -> researcher -> writer -> guard end-to-end.
2. Apply three programmatic checks:
     (a) number of unique URLs in the report >= ``min_citations``
     (b) every ``[n]`` marker in the body has a matching numbered Sources entry
     (c) every URL in Sources is referenced from the body
         (either the bare URL text appears, or its ``[n]`` marker is cited)

Run:
    uv run python -m evals.citation_eval
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from app.tracing import flush_langsmith_traces, setup_langsmith_tracing
from evals._graph_runner import run_full_graph
from evals.planner_eval import load_golden

GOLDEN_PATH = Path(__file__).resolve().parent / "golden.jsonl"

# Locate the Sources heading (## Sources, ### Sources, etc.) and split there.
_SOURCES_HEADING_RE = re.compile(r"(?im)^#{1,6}\s*sources\b.*$")
# A bracketed citation marker [n] in the body. Skips markdown links [text](url)
# by requiring the closing bracket NOT to be followed by '('.
_CITATION_MARKER_RE = re.compile(r"\[(\d+)\](?!\()")
_URL_RE = re.compile(r"https?://[^\s)\]\"'<>]+")
# Numbered Sources entries: "1. https://...", "1) https://...", "[1] https://...",
# "[1]: https://...". We allow any text between the number and the URL on the same line.
_SOURCES_ENTRY_RE = re.compile(
    r"(?m)^\s*(?:\[(?P<bn>\d+)\]:?\s+|(?P<dn>\d+)[\.\)]\s+).*?(?P<url>https?://\S+)"
)


def _split_report(report: str) -> tuple[str, str]:
    """Return ``(body_before_sources, sources_section_including_heading)``."""
    match = _SOURCES_HEADING_RE.search(report)
    if not match:
        return report, ""
    return report[: match.start()], report[match.start() :]


def _all_urls(text: str) -> set[str]:
    return {url.rstrip(".,;)") for url in _URL_RE.findall(text)}


def _body_markers(body: str) -> set[int]:
    return {int(n) for n in _CITATION_MARKER_RE.findall(body)}


def _sources_entries(sources: str) -> dict[int, str]:
    """Parse ``{n: url}`` from the Sources section."""
    entries: dict[int, str] = {}
    for match in _SOURCES_ENTRY_RE.finditer(sources):
        n = int(match.group("bn") or match.group("dn"))
        entries[n] = match.group("url").rstrip(".,;)")
    return entries


def evaluate_report(report: str, min_citations: int) -> tuple[bool, list[str]]:
    """Run the three programmatic checks. Return ``(passed, failure_messages)``."""
    failures: list[str] = []
    body, sources = _split_report(report)
    unique_urls = _all_urls(report)
    markers = _body_markers(body)
    entries = _sources_entries(sources)
    # Fallback for malformed/unstructured Sources sections (no numbered entries).
    sources_url_set = set(entries.values()) or _all_urls(sources)

    if len(unique_urls) < min_citations:
        failures.append(
            f"(a) {len(unique_urls)} unique URLs in report, need >= {min_citations}"
        )

    missing_entries = sorted(n for n in markers if n not in entries)
    if missing_entries:
        failures.append(
            f"(b) body cites {missing_entries} with no matching numbered Sources entry"
        )

    orphans: list[str] = []
    for n, url in entries.items():
        if n in markers or url in body:
            continue
        orphans.append(f"[{n}] {url}")
    # Unstructured Sources fallback: check URL-in-body for the loose set.
    if not entries and sources_url_set:
        orphans.extend(sorted(url for url in sources_url_set if url not in body))
    if orphans:
        preview = orphans[:3]
        more = "" if len(orphans) <= 3 else f" (+{len(orphans) - 3} more)"
        failures.append(
            f"(c) {len(orphans)} Sources entr{'y' if len(orphans) == 1 else 'ies'} "
            f"unreferenced in body: {preview}{more}"
        )

    return (not failures, failures)


def _print_header(total: int) -> None:
    print(f"\n{'=' * 78}")
    print("Citation eval - programmatic checks")
    print("  (a) unique URLs >= min_citations")
    print("  (b) every [n] in body has a numbered Sources entry")
    print("  (c) every Sources entry is referenced from the body")
    print(f"{'=' * 78}")
    print(f"Running {total} golden rows through the full graph...\n")


def main() -> int:
    setup_langsmith_tracing()
    rows = load_golden()
    if not rows:
        print(f"No rows found in {GOLDEN_PATH}", file=sys.stderr)
        return 1

    print(f"Loaded {len(rows)} golden questions from {GOLDEN_PATH.name}")
    _print_header(len(rows))

    passed = 0
    for index, row in enumerate(rows, start=1):
        question = row["question"]
        min_citations = int(row.get("min_citations") or 0)
        snippet = question if len(question) <= 56 else question[:53] + "..."

        try:
            final_state = run_full_graph(question)
        except Exception as exc:
            print(f"{index:2d}. [FAIL] {snippet}")
            print(f"      -> graph crashed: {type(exc).__name__}: {exc}")
            continue

        report = (final_state or {}).get("report") or ""
        ok, failures = evaluate_report(report, min_citations)
        passed += int(ok)
        status = "PASS" if ok else "FAIL"
        print(f"{index:2d}. [{status}] {snippet}")
        for failure in failures:
            print(f"      -> {failure}")

    total = len(rows)
    pct = 100.0 * passed / total if total else 0.0
    print(f"{'-' * 78}")
    print(f"Aggregate: {passed}/{total} passed ({pct:.0f}%)")
    flush_langsmith_traces()
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
