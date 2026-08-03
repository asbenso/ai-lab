"""Writer node: draft the final markdown report from researcher findings."""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.graph import ResearchState
from app.llm import get_chat_model
from app.nodes._retry import call_with_retry
from app.nodes.recall import format_memories_for_writer, format_preference_instructions

SYSTEM_PROMPT = (
    "You are writing a research report. Produce a markdown report with: "
    "1) a 2-3 sentence executive summary, "
    "2) one H2 section per sub-question, "
    "3) inline `[n]` citations after each factual claim, numbered starting at "
    "[1] using contiguous integers, "
    "4) a numbered Sources section at the end. "
    "The Sources list must contain EXACTLY the URLs you cited inline - no "
    "orphan entries and no URLs you did not cite. If a finding's URL is not "
    "cited in the body, do NOT list it in Sources. "
    "Never invent a URL or fact - only use the supplied findings. "
    "When user memories are provided, use stable facts to tailor tone and focus, "
    "and follow any recalled format/style preferences over the default layout."
)


def _writer_system_prompt(memories: list[dict]) -> str:
    format_block = format_preference_instructions(memories)
    if not format_block:
        return SYSTEM_PROMPT
    return f"{SYSTEM_PROMPT}\n\n{format_block}"


def _writer_human_content(
    *,
    question: str,
    sub_questions: list[dict],
    findings: list[dict],
    memories: list[dict],
) -> str:
    payload = json.dumps(
        {
            "question": question,
            "sub_questions": sub_questions,
            "findings": findings,
            "memories": memories,
        },
        ensure_ascii=False,
    )
    memory_block = format_memories_for_writer(memories)
    if not memory_block:
        return payload
    return f"{memory_block}\n\nResearch payload:\n{payload}"

_URL_RE = re.compile(r"https?://[^\s)\]\"'<>]+")
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^\s)]+)\)")
# Inline [n] citation markers in the body. Excludes markdown links [text](url).
_BODY_MARKER_RE = re.compile(r"\[(\d+)\](?!\()")
# Numbered Sources entries (same patterns as evals/citation_eval.py).
_SOURCES_ENTRY_RE = re.compile(
    r"(?m)^\s*(?:\[(?P<bn>\d+)\]:?\s+|(?P<dn>\d+)[\.\)]\s+).*?(?P<url>https?://\S+)"
)


def _message_text(content: str | list) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "\n".join(part for part in parts if part)


def _sources_section(report: str) -> str:
    """Return text from the last 'Sources' heading onwards, or '' if missing."""
    match = re.search(r"(?im)^#{1,6}\s*sources\b", report)
    if not match:
        return ""
    return report[match.start() :]


def _extract_report_urls(report: str) -> set[str]:
    urls: set[str] = set()
    urls.update(_MD_LINK_RE.findall(report))
    sources = _sources_section(report)
    if sources:
        urls.update(_URL_RE.findall(sources))
    return urls


def _parse_sources_entries(sources: str) -> dict[int, str]:
    entries: dict[int, str] = {}
    for match in _SOURCES_ENTRY_RE.finditer(sources):
        n = int(match.group("bn") or match.group("dn"))
        entries[n] = match.group("url").rstrip(".,;)")
    return entries


def _body_markers(body: str) -> set[int]:
    return {int(n) for n in _BODY_MARKER_RE.findall(body)}


def _finding_urls(findings: list[dict]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for finding in findings:
        url = str(finding.get("evidence_url") or "").strip()
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _split_at_sources(report: str) -> tuple[str, str]:
    match = re.search(r"(?im)^#{1,6}\s*sources\b", report)
    if not match:
        return report, ""
    return report[: match.start()], report[match.start() :]


def _append_cite_line(body: str, marker_numbers: list[int]) -> str:
    if not marker_numbers:
        return body
    cite_line = "Evidence cited: " + " ".join(f"[{n}]" for n in marker_numbers)
    return body.rstrip() + f"\n\n{cite_line}\n"


def _inject_missing_citation_markers(report: str) -> str:
    """Add ``[n]`` markers to the body for every numbered Sources entry."""
    body, sources = _split_at_sources(report)
    if not sources:
        return report
    entries = _parse_sources_entries(sources)
    if not entries:
        return report
    markers = _body_markers(body)
    orphans = sorted(
        n for n, url in entries.items() if n not in markers and url not in body
    )
    if not orphans:
        return report
    body = _append_cite_line(body, orphans)
    return body + sources


def _rebuild_citations_from_findings(report: str, findings: list[dict]) -> str:
    """When the LLM omitted citations, append markers + a fresh Sources block."""
    urls = _finding_urls(findings)
    if len(urls) < 2:
        return report
    if len(_extract_report_urls(report)) >= len(urls):
        return report

    body, _ = _split_at_sources(report)
    body = body.rstrip()
    body = _append_cite_line(body, list(range(1, len(urls) + 1)))
    lines = ["\n\n## Sources\n"]
    lines.extend(f"{index}. {url}" for index, url in enumerate(urls, start=1))
    return body + "\n".join(lines)


def _ensure_sources_section(report: str, findings: list[dict]) -> str:
    """Append a numbered Sources list from findings when the LLM omitted it.

    When the body has inline `[n]` markers we only emit entries for those
    indices (assuming `[n]` -> `findings[n-1]`), so the auto-generated Sources
    section never carries orphan URLs. Falls back to listing every unique
    finding URL when the body has no markers at all.
    """
    if re.search(r"(?im)^#{1,6}\s*sources\b", report):
        return report

    body_markers = sorted({int(n) for n in _BODY_MARKER_RE.findall(report)})
    if body_markers:
        urls: list[tuple[int, str]] = []
        seen: set[str] = set()
        for n in body_markers:
            idx = n - 1
            if idx < 0 or idx >= len(findings):
                continue
            url = str(findings[idx].get("evidence_url") or "").strip()
            if url and url not in seen:
                seen.add(url)
                urls.append((n, url))
        if not urls:
            return report
        lines = ["\n\n## Sources\n"]
        lines.extend(f"{n}. {url}" for n, url in urls)
        return report.rstrip() + "\n".join(lines)

    urls_only = _finding_urls(findings)
    if not urls_only:
        return report
    body = report.rstrip()
    body = _append_cite_line(body, list(range(1, len(urls_only) + 1)))
    lines = ["\n\n## Sources\n"]
    for index, url in enumerate(urls_only, start=1):
        lines.append(f"{index}. {url}")
    return body + "\n".join(lines)


def _prune_unreferenced_sources(report: str) -> tuple[str, list[str]]:
    """Drop Sources entries whose `[n]` isn't cited in the body.

    No-op when the body has no inline markers (we don't want to nuke the
    whole Sources block if the writer forgot to cite anything). Continuation
    lines that don't start with a numbered marker are kept as-is, since they
    might belong to a still-kept entry above them.
    """
    match = re.search(r"(?im)^#{1,6}\s*sources\b", report)
    if not match:
        return report, []
    body = report[: match.start()]
    sources = report[match.start() :]

    body_markers = _body_markers(body)
    if not body_markers:
        return report, []

    kept_lines: list[str] = []
    dropped: list[str] = []
    for line in sources.splitlines():
        entry = _SOURCES_ENTRY_RE.match(line)
        if entry is None:
            kept_lines.append(line)
            continue
        n = int(entry.group("bn") or entry.group("dn"))
        if n in body_markers:
            kept_lines.append(line)
            continue
        url_match = _URL_RE.search(line)
        if url_match:
            dropped.append(url_match.group(0).rstrip(".,;)"))

    if not dropped:
        return report, []
    pruned_sources = "\n".join(kept_lines)
    if not pruned_sources.endswith("\n"):
        pruned_sources += "\n"
    return body + pruned_sources, dropped


def writer_node(state: ResearchState) -> dict:
    findings = state.get("findings") or []
    memories = state.get("memories") or []
    question = state.get("question", "")
    sub_questions = state.get("sub_questions") or []
    model = get_chat_model()
    ai_msg = call_with_retry(
        model.invoke,
        [
            SystemMessage(content=_writer_system_prompt(memories)),
            HumanMessage(
                content=_writer_human_content(
                    question=question,
                    sub_questions=sub_questions,
                    findings=findings,
                    memories=memories,
                )
            ),
        ],
        label="writer",
    )
    report = _message_text(ai_msg.content).strip()

    log: list[str] = ["Writer: report drafted"]
    if memories:
        format_prefs = sum(
            1
            for item in memories
            if (item.get("value") or {}).get("kind") == "preference"
        )
        log.append(
            f"Writer: used {len(memories)} recalled memor"
            f"{'y' if len(memories) == 1 else 'ies'}"
            + (f" ({format_prefs} preference{'s' if format_prefs != 1 else ''})" if format_prefs else "")
        )
    if not findings:
        report = (
            report
            + "\n\n> NOTE: The researcher collected no verified findings with source URLs, "
            "so this report has no citations."
        )
    else:
        report = _rebuild_citations_from_findings(report, findings)
        report = _ensure_sources_section(report, findings)
        report = _inject_missing_citation_markers(report)
        report, dropped = _prune_unreferenced_sources(report)
        if dropped:
            log.append(
                f"Writer: pruned {len(dropped)} unreferenced Sources entr"
                f"{'y' if len(dropped) == 1 else 'ies'}"
            )

    allowed = {f["evidence_url"] for f in findings if f.get("evidence_url")}
    cited = _extract_report_urls(report)
    bad_urls = sorted(cited - allowed)
    if bad_urls:
        report = f"{report}\n\n> WARNING: filtered hallucinated citations: {bad_urls}"

    return {
        "report": report,
        "step_log": state["step_log"] + log,
    }
