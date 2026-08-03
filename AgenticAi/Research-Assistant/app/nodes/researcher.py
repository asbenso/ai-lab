"""Researcher node: gather findings for each sub-question via tool calls."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.graph import ResearchState
from app.llm import get_chat_model
from app.nodes._retry import call_with_retry
from app.tools.fetch_url import fetch_url
from app.tools.search_local_docs import search_local_docs
from app.tools.summarize import summarize
from app.tools.web_search import web_search

SYSTEM_PROMPT = (
    "You are a focused researcher. Use tools to find 1-3 supporting facts with real "
    "source URLs for the given sub-question. When you have enough, reply with a JSON "
    "list of findings. Each finding must be an object with keys 'claim', "
    "'evidence_url', and 'evidence_text'."
)

MAX_TOOL_CALLS_PER_SUB_Q = 6
TOOLS = [web_search, fetch_url, search_local_docs, summarize]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}

SYNTHESIS_PROMPT = (
    "Using ONLY the tool results in the conversation above, reply with a JSON array of "
    "1-3 findings. Each object must have keys claim, evidence_url, and evidence_text. "
    "evidence_url must be a URL that literally appeared in a tool message. No prose."
)


def _url_in_tool_text(url: str, tool_text: str) -> bool:
    url = url.strip().rstrip("/")
    if not url:
        return False
    if url in tool_text:
        return True
    return f"{url}/" in tool_text or url.rstrip("/") in tool_text


def _arg_preview(args: dict[str, Any]) -> str:
    """Short, single-line preview of the tool args for the step log."""
    if not args:
        return ""
    primary = args.get("query") or args.get("url") or args.get("text") or ""
    primary = str(primary).strip()
    if len(primary) > 80:
        primary = primary[:77] + "..."
    return primary


def _tool_message_text(message: ToolMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return json.dumps(content, default=str)


def _extract_json_list(content: str | list) -> list[dict] | None:
    """Find the first JSON array of objects in the model's reply, if any."""
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        text = "\n".join(parts)
    else:
        text = content or ""
    text = text.strip()
    if not text:
        return None
    candidates: list[str] = [text]
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, flags=re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1))
    bracketed = re.search(r"\[\s*\{.*\}\s*\]", text, flags=re.DOTALL)
    if bracketed:
        candidates.append(bracketed.group(0))
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list) and all(isinstance(item, dict) for item in data):
            return data
    return None


def _tool_messages_text(messages: list[BaseMessage]) -> str:
    return "\n".join(_tool_message_text(m) for m in messages if isinstance(m, ToolMessage))


def _findings_from_parsed(
    parsed: list[dict] | None,
    messages: list[BaseMessage],
    sub_index: int,
    log_lines: list[str],
    total: int,
) -> list[dict]:
    if not parsed:
        return []
    tool_text = _tool_messages_text(messages)
    findings: list[dict] = []
    for item in parsed:
        url = str(item.get("evidence_url", "")).strip()
        if not url or not _url_in_tool_text(url, tool_text):
            log_lines.append(
                f"[sub {sub_index + 1}/{total}] dropped unverifiable URL {url!r}"
            )
            continue
        findings.append(
            {
                "sub_question_index": sub_index,
                "claim": str(item.get("claim", "")).strip(),
                "evidence_url": url,
                "evidence_text": str(item.get("evidence_text", "")).strip(),
            }
        )
    return findings


def _fallback_findings_from_tools(
    messages: list[BaseMessage],
    sub_index: int,
    fetch_urls: dict[str, str],
) -> list[dict]:
    """Build minimal findings from tool JSON when the model never returns JSON."""
    findings: list[dict] = []
    seen_urls: set[str] = set()

    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        raw = _tool_message_text(message)
        url = fetch_urls.get(message.tool_call_id, "")

        if message.name == "fetch_url" and url and len(raw) > 80:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            snippet = " ".join(raw.split())[:280]
            findings.append(
                {
                    "sub_question_index": sub_index,
                    "claim": snippet,
                    "evidence_url": url,
                    "evidence_text": snippet,
                }
            )
            continue

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, list):
            continue

        for row in data[:4]:
            if not isinstance(row, dict):
                continue
            row_url = str(row.get("url") or row.get("source_url") or "").strip()
            body = str(row.get("content") or row.get("text") or row.get("title") or "").strip()
            if not row_url or not body or row_url in seen_urls:
                continue
            seen_urls.add(row_url)
            claim = body if len(body) <= 280 else body[:277] + "..."
            findings.append(
                {
                    "sub_question_index": sub_index,
                    "claim": claim,
                    "evidence_url": row_url,
                    "evidence_text": claim,
                }
            )
    return findings[:4]


def _emergency_findings_from_tool_urls(
    messages: list[BaseMessage],
    sub_index: int,
    existing: list[dict],
    *,
    min_count: int = 2,
) -> list[dict]:
    """Scrape extra URLs from raw tool text when structured extraction returned too few."""
    if len({f.get("evidence_url") for f in existing if f.get("evidence_url")}) >= min_count:
        return existing
    seen = {str(f.get("evidence_url", "")).strip() for f in existing}
    extra: list[dict] = list(existing)
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        text = _tool_message_text(message)
        for raw_url in re.findall(r"https?://[^\s)\]\"'<>]+", text):
            url = raw_url.rstrip(".,;)")
            if not url or url in seen:
                continue
            seen.add(url)
            extra.append(
                {
                    "sub_question_index": sub_index,
                    "claim": f"Source referenced in {message.name} results.",
                    "evidence_url": url,
                    "evidence_text": url,
                }
            )
            if len({f.get("evidence_url") for f in extra if f.get("evidence_url")}) >= min_count:
                return extra[:4]
    return extra[:4]


def _synthesize_findings(
    messages: list[BaseMessage],
    sub_index: int,
    total: int,
    fetch_urls: dict[str, str],
    log_lines: list[str],
) -> list[dict]:
    """After tool budget: extract from tools, then ask LLM without tools."""
    fallback = _fallback_findings_from_tools(messages, sub_index, fetch_urls)
    if fallback:
        log_lines.append(
            f"[sub {sub_index + 1}/{total}] recovered {len(fallback)} finding(s) from tool output"
        )
        return fallback

    if not any(isinstance(m, ToolMessage) for m in messages):
        return []

    synth_messages = [*messages, HumanMessage(content=SYNTHESIS_PROMPT)]
    ai_msg = call_with_retry(
        get_chat_model().invoke,
        synth_messages,
        label=f"researcher.sub{sub_index + 1}.synthesis",
    )
    parsed = _extract_json_list(ai_msg.content)
    findings = _findings_from_parsed(parsed, messages, sub_index, log_lines, total)
    if findings:
        log_lines.append(
            f"[sub {sub_index + 1}/{total}] synthesized {len(findings)} finding(s) after tool budget"
        )
    return findings


def _run_sub_question(
    sub_q: dict,
    sub_index: int,
    total: int,
    model,
) -> tuple[list[dict], list[str]]:
    """Run the tool-call loop for one sub-question. Returns (findings, log_lines)."""
    text = sub_q.get("text", "")
    messages: list[BaseMessage] = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=text),
    ]
    log_lines: list[str] = []
    tool_calls_used = 0
    findings: list[dict] = []
    fetch_urls: dict[str, str] = {}

    while tool_calls_used < MAX_TOOL_CALLS_PER_SUB_Q:
        ai_msg: AIMessage = call_with_retry(
            model.invoke,
            messages,
            label=f"researcher.sub{sub_index + 1}",
        )
        messages.append(ai_msg)

        tool_calls = ai_msg.tool_calls or []
        if not tool_calls:
            parsed = _extract_json_list(ai_msg.content)
            if parsed is None:
                log_lines.append(
                    f"[sub {sub_index + 1}/{total}] no findings parsed from model reply"
                )
            else:
                findings = _findings_from_parsed(parsed, messages, sub_index, log_lines, total)
            break

        for tc in tool_calls:
            if tool_calls_used >= MAX_TOOL_CALLS_PER_SUB_Q:
                messages.append(
                    ToolMessage(
                        content="Tool-call budget exhausted for this sub-question.",
                        tool_call_id=tc["id"],
                        name=tc["name"],
                    )
                )
                continue
            tool_calls_used += 1
            args = tc.get("args") or {}
            if tc["name"] == "fetch_url" and args.get("url"):
                fetch_urls[tc["id"]] = str(args["url"]).strip()
            log_lines.append(
                f"[sub {sub_index + 1}/{total}] {tc['name']}({_arg_preview(args)!r})"
            )
            tool_fn = TOOLS_BY_NAME.get(tc["name"])
            if tool_fn is None:
                result: Any = f"Unknown tool: {tc['name']}"
            else:
                try:
                    result = tool_fn.invoke(args)
                except Exception as exc:
                    result = f"Tool error ({type(exc).__name__}): {exc}"
            content = result if isinstance(result, str) else json.dumps(result, default=str)
            messages.append(ToolMessage(content=content, tool_call_id=tc["id"], name=tc["name"]))
    else:
        log_lines.append(
            f"[sub {sub_index + 1}/{total}] hit max tool-call budget ({MAX_TOOL_CALLS_PER_SUB_Q})"
        )

    if not findings:
        findings = _synthesize_findings(messages, sub_index, total, fetch_urls, log_lines)

    findings = _emergency_findings_from_tool_urls(messages, sub_index, findings)
    return findings, log_lines


def researcher_node(state: ResearchState) -> dict:
    sub_questions = state.get("sub_questions") or []
    if not sub_questions:
        return {
            "findings": [],
            "step_log": state["step_log"] + ["Researcher: no sub-questions to investigate"],
        }

    model = get_chat_model().bind_tools(TOOLS)
    all_findings: list[dict] = []
    new_logs: list[str] = []
    for i, sub_q in enumerate(sub_questions):
        try:
            findings, logs = _run_sub_question(sub_q, i, len(sub_questions), model)
        except Exception as exc:
            new_logs.append(
                f"[sub {i + 1}/{len(sub_questions)}] aborted after retries "
                f"({type(exc).__name__}: {exc})"
            )
            continue
        all_findings.extend(findings)
        new_logs.extend(logs)
    new_logs.append(f"Researcher: {len(all_findings)} findings")
    for index, finding in enumerate(all_findings, start=1):
        claim = str(finding.get("claim") or "").strip()
        url = str(finding.get("evidence_url") or "").strip()
        if claim and url:
            preview = claim if len(claim) <= 120 else claim[:117] + "..."
            new_logs.append(f"Researcher: {index}. {preview} → {url}")
    return {"findings": all_findings, "step_log": state["step_log"] + new_logs}
