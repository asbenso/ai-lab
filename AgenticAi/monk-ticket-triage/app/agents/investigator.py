"""Investigator agent: gather context via tools before responding."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.llm import get_chat_model
from app.state import TicketState
from app.tools import get_ticket_history, query_logs, query_metrics, search_runbooks
from app.tools._domain import set_domain

SYSTEM_PROMPT = (
    "You are an investigator. Given a classified ticket, gather enough context "
    "to write an informed response. Use tools to fetch logs, metrics, runbooks, "
    "and the user's ticket history. Stop calling tools when you can clearly explain "
    "what happened and what should be done. Budget: 8 tool calls max."
)

MAX_TOOL_CALLS = 8

TOOLS = [query_logs, query_metrics, search_runbooks, get_ticket_history]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}

SYNTHESIS_PROMPT = (
    "Using ONLY the tool results in the conversation above, reply with a JSON array "
    'of findings. Each object must have keys "claim", "source", and "tool". No prose.'
)


def _ticket_context(state: TicketState) -> str:
    return json.dumps(
        {
            "ticket_id": state["ticket_id"],
            "domain": state["domain"],
            "classification": state.get("classification"),
            "severity": state.get("severity"),
            "raw": state["raw"],
        },
        ensure_ascii=False,
        indent=2,
    )


def _truncate_args(args: dict[str, Any], limit: int = 120) -> str:
    text = json.dumps(args, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _tool_message_text(message: ToolMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return json.dumps(content, default=str)


def _extract_json_list(content: str | list) -> list[dict] | None:
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


def _normalize_findings(parsed: list[dict] | None) -> list[dict]:
    if not parsed:
        return []
    findings: list[dict] = []
    for item in parsed:
        claim = str(item.get("claim", "")).strip()
        source = str(item.get("source", "")).strip()
        tool = str(item.get("tool", "")).strip()
        if not claim:
            continue
        findings.append({"claim": claim, "source": source or "unknown", "tool": tool or "unknown"})
    return findings


def _fallback_findings_from_tools(messages: list[BaseMessage]) -> list[dict]:
    findings: list[dict] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        raw = _tool_message_text(message)
        name = message.name or "unknown"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            if raw.strip():
                findings.append(
                    {
                        "claim": raw.strip()[:280],
                        "source": name,
                        "tool": name,
                    }
                )
            continue

        if name == "query_logs" and isinstance(data, list):
            for entry in data[:3]:
                if not isinstance(entry, dict):
                    continue
                msg = str(entry.get("message", "")).strip()
                if not msg:
                    continue
                findings.append(
                    {
                        "claim": msg,
                        "source": str(entry.get("timestamp", "")).strip() or "logs",
                        "tool": name,
                    }
                )
        elif name == "query_metrics" and isinstance(data, dict):
            metric = str(data.get("metric", "")).strip()
            service = str(data.get("service", "")).strip()
            trend = str(data.get("trend", "")).strip()
            current = data.get("current")
            findings.append(
                {
                    "claim": f"{service}/{metric} trend={trend} current={current}",
                    "source": f"{service}/{metric}",
                    "tool": name,
                }
            )
        elif name == "search_runbooks" and isinstance(data, list):
            for row in data[:2]:
                if not isinstance(row, dict):
                    continue
                text = str(row.get("text", "")).strip()
                source = str(row.get("source_url", "")).strip()
                if not text:
                    continue
                claim = text.splitlines()[0] if text else source
                findings.append({"claim": claim[:280], "source": source or "runbook", "tool": name})
        elif name == "get_ticket_history" and isinstance(data, list):
            for row in data[:2]:
                if not isinstance(row, dict):
                    continue
                subject = str(row.get("subject", "")).strip()
                ticket_id = str(row.get("ticket_id", "")).strip()
                if not subject:
                    continue
                findings.append(
                    {
                        "claim": subject,
                        "source": ticket_id or "historical_tickets",
                        "tool": name,
                    }
                )
        elif isinstance(data, dict):
            findings.append(
                {
                    "claim": json.dumps(data, ensure_ascii=False)[:280],
                    "source": name,
                    "tool": name,
                }
            )
    return findings[:8]


def _synthesize_findings(messages: list[BaseMessage], log: list[str]) -> list[dict]:
    synth_messages = [*messages, HumanMessage(content=SYNTHESIS_PROMPT)]
    ai_msg: AIMessage = get_chat_model().invoke(synth_messages)
    parsed = _extract_json_list(ai_msg.content)
    findings = _normalize_findings(parsed)
    if findings:
        log.append(f"Investigator: synthesized {len(findings)} finding(s)")
        return findings

    fallback = _fallback_findings_from_tools(messages)
    if fallback:
        log.append(f"Investigator: recovered {len(fallback)} finding(s) from tool output")
    return fallback


def investigator_node(state: TicketState) -> dict:
    """Gather logs, metrics, runbooks, and history for the classified ticket."""
    set_domain(state["domain"])
    messages: list[BaseMessage] = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Investigate this ticket:\n{_ticket_context(state)}"),
    ]
    log = list(state["step_log"])
    model = get_chat_model().bind_tools(TOOLS)
    tool_calls_used = 0

    while tool_calls_used < MAX_TOOL_CALLS:
        ai_msg: AIMessage = model.invoke(messages)
        messages.append(ai_msg)

        tool_calls = ai_msg.tool_calls or []
        if not tool_calls:
            log.append("Investigator: finished tool phase")
            break

        for tc in tool_calls:
            if tool_calls_used >= MAX_TOOL_CALLS:
                messages.append(
                    ToolMessage(
                        content="Tool-call budget exhausted.",
                        tool_call_id=tc["id"],
                        name=tc["name"],
                    )
                )
                continue

            tool_calls_used += 1
            args = tc.get("args") or {}
            log.append(f"Investigator: {tc['name']}({_truncate_args(args)})")

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
        log.append(f"Investigator: hit max tool-call budget ({MAX_TOOL_CALLS})")

    findings = _synthesize_findings(messages, log)
    if not findings:
        log.append("Investigator: no findings produced")
    else:
        log.append(f"Investigator: {len(findings)} findings recorded")

    return {"findings": findings, "step_log": log}
