"""Deterministic fake chat model and embeddings for offline tests."""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from typing import Any, ClassVar
from uuid import uuid4

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "is", "are",
    "what", "which", "how", "why", "do", "does", "did", "can", "should", "with",
    "this", "that", "these", "those", "i", "you", "we", "they", "it", "by", "as",
}


def _keywords(text: str, k: int = 6) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-]+", (text or "").lower())
    out: list[str] = []
    for w in words:
        if w in _STOPWORDS or len(w) <= 2:
            continue
        if w in out:
            continue
        out.append(w)
        if len(out) >= k:
            break
    return out


def _system_text(messages: list[BaseMessage]) -> str:
    for message in messages:
        if isinstance(message, SystemMessage):
            content = message.content
            return content if isinstance(content, str) else json.dumps(content)
    return ""


def _all_tool_messages(messages: list[BaseMessage]) -> list[ToolMessage]:
    return [message for message in messages if isinstance(message, ToolMessage)]


def _build_tool_call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "args": args, "id": f"call_{uuid4().hex[:12]}"}


def _pick_investigator_tool(
    messages: list[BaseMessage], used: list[str]
) -> tuple[str, dict[str, Any]] | None:
    human = _last_human_text(messages)
    low = (human + "\n" + _system_text(messages)).lower()
    if "vpn" in low or "tunnel" in low:
        service, metric = "vpn-gateway", "connection_errors"
    elif "503" in low or "outage" in low or "api-gateway" in low:
        service, metric = "api-gateway", "error_rate"
    elif "mfa" in low or "login" in low or "auth" in low:
        service, metric = "auth-service", "errors_per_min"
    elif "billing" in low or "refund" in low:
        service, metric = "billing-service", "refund_queue_depth"
    elif "report" in low or "export" in low:
        service, metric = "reports-service", "export_timeout_rate"
    else:
        service, metric = "app", "errors_per_min"

    candidates: list[tuple[str, dict[str, Any]]] = [
        ("query_logs", {"service": service, "since": "1h"}),
        ("search_runbooks", {"query": " ".join(_keywords(human, k=4)) or "general"}),
        ("query_metrics", {"service": service, "metric": metric, "since": "1h"}),
    ]
    email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", human)
    user_id = email_match.group(0) if email_match else "unknown@example.com"
    candidates.append(("get_ticket_history", {"user_id": user_id, "k": 3}))

    for name, args in candidates:
        if name not in used:
            return name, args
    return None


def _investigator_findings_json(messages: list[BaseMessage]) -> str:
    findings: list[dict[str, str]] = []
    for message in _all_tool_messages(messages):
        content = message.content if isinstance(message.content, str) else json.dumps(message.content)
        name = message.name or "unknown"
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            continue
        if name == "query_logs" and isinstance(data, list):
            for entry in data[:2]:
                if not isinstance(entry, dict):
                    continue
                msg = str(entry.get("message", "")).strip()
                if msg:
                    findings.append(
                        {
                            "claim": msg,
                            "source": str(entry.get("timestamp", "")).strip() or "logs",
                            "tool": name,
                        }
                    )
        elif name == "query_metrics" and isinstance(data, dict):
            findings.append(
                {
                    "claim": (
                        f"{data.get('service')}/{data.get('metric')} trend is "
                        f"{data.get('trend')} (current={data.get('current')})"
                    ),
                    "source": f"{data.get('service')}/{data.get('metric')}",
                    "tool": name,
                }
            )
        elif name == "search_runbooks" and isinstance(data, list):
            for row in data[:1]:
                if not isinstance(row, dict):
                    continue
                text = str(row.get("text", "")).strip()
                source = str(row.get("source_url", "")).strip()
                if text:
                    findings.append(
                        {
                            "claim": text.splitlines()[2] if len(text.splitlines()) > 2 else text[:120],
                            "source": source or "runbook",
                            "tool": name,
                        }
                    )
        elif name == "get_ticket_history" and isinstance(data, list):
            for row in data[:1]:
                if not isinstance(row, dict):
                    continue
                subject = str(row.get("subject", "")).strip()
                ticket_id = str(row.get("ticket_id", "")).strip()
                if subject:
                    findings.append(
                        {"claim": subject, "source": ticket_id or "historical_tickets", "tool": name}
                    )
    if not findings:
        findings = [
            {
                "claim": "Examined logs, metrics, runbooks, and ticket history.",
                "source": "investigator",
                "tool": "investigator",
            }
        ]
    return json.dumps(findings, ensure_ascii=False)


def _route_with_tools(messages: list[BaseMessage], bound_tools: list[Any]) -> tuple[str, list[dict[str, Any]]]:
    tool_names = {getattr(tool, "name", None) or getattr(tool, "__name__", "") for tool in bound_tools}
    used = [message.name for message in _all_tool_messages(messages) if message.name]
    p2_tools = {"query_logs", "query_metrics", "search_runbooks", "get_ticket_history"}
    if p2_tools & tool_names:
        if len(used) >= min(3, len(p2_tools & tool_names)):
            return "Ready to summarise findings.", []
        nxt = _pick_investigator_tool(messages, used)
        if nxt is None:
            return "All available signals examined; ready to summarise findings.", []
        name, args = nxt
        if name not in tool_names:
            remaining = [tool_name for tool_name in tool_names if tool_name not in used]
            if remaining:
                name = remaining[0]
                args = {}
        return "", [_build_tool_call(name, args)]
    return "OK.", []


def _last_human_text(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content
            return content if isinstance(content, str) else json.dumps(content)
    return ""


def _classify_ticket(body: str, subject: str, categories: list[str]) -> tuple[str, str, float, str]:
    text = f"{subject}\n{body}".lower()
    rules: list[tuple[str, list[str], str]] = [
        ("account_security", ["suspicious", "unauthorized", "compromised"], "P1"),
        ("security", ["suspicious", "unauthorized", "breach", "credential"], "P1"),
        ("service_outage", ["outage", "down", "unavailable", "503"], "P1"),
        ("vpn_access", ["vpn", "remote access", "tunnel"], "P2"),
        ("login_issue", ["mfa", "login", "log in", "password", "locked"], "P2"),
        ("password_reset", ["password", "locked", "mfa", "authenticator"], "P2"),
        ("billing", ["refund", "invoice", "charge", "subscription"], "P2"),
        ("latency", ["latency", "slow", "timeout"], "P2"),
        ("error_spike", ["5xx", "error rate", "spike", "exception"], "P2"),
        ("bug_report", ["bug", "broken", "crash", "hangs"], "P3"),
        ("software_install", ["install", "update", "license", "crash"], "P3"),
        ("network", ["wifi", "dns", "network", "connectivity"], "P3"),
        ("deployment", ["deploy", "rollback", "release"], "P3"),
        ("capacity", ["cpu", "memory", "disk", "saturation", "queue"], "P3"),
        ("feature_request", ["feature", "please add", "would be nice"], "P4"),
    ]
    for category, keywords, severity in rules:
        if category in categories and any(keyword in text for keyword in keywords):
            return category, severity, 0.82, f"Matched keyword(s) for category {category}."
    if "other" in categories:
        return "other", "P3", 0.55, "No high-confidence keyword match; defaulting to 'other'."
    return categories[0], "P3", 0.5, "Defaulting to first known category."


def _structured_triage_output(schema: type, messages: list[BaseMessage]) -> Any:
    prompt_text = "\n".join(
        message.content if isinstance(message.content, str) else str(message.content)
        for message in messages
    )
    match = re.search(r"Available categories:\s*([^\n]+)", prompt_text)
    categories = []
    if match:
        categories = [part.strip() for part in match.group(1).split(",") if part.strip()]
    if not categories:
        categories = ["other"]
    body = _last_human_text(messages)
    subject_match = re.search(r"Subject:\s*(.+)", body)
    subject = subject_match.group(1).strip() if subject_match else ""
    category, severity, confidence, rationale = _classify_ticket(body, subject, categories)
    payload: dict[str, Any] = {}
    fields = getattr(schema, "model_fields", {})
    if "category" in fields:
        payload["category"] = category
    if "severity" in fields:
        payload["severity"] = severity
    if "confidence" in fields:
        payload["confidence"] = confidence
    if "rationale" in fields:
        payload["rationale"] = rationale
    return schema(**payload)


_PII_PATTERNS: tuple[tuple[str, str], ...] = (
    ("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ("phone", r"(?:(?:\+?\d{1,3}[-.\s])?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})"),
)

_ESCALATION_KEYWORDS = ("refund", "credit", "guarantee", "tomorrow", "by eod", "by end of day")


def _detect_risk_flags(body: str) -> list[str]:
    flags: list[str] = []
    low = body.lower()
    for keyword in _ESCALATION_KEYWORDS:
        if keyword in low:
            flags.append(f"keyword:{keyword}")
            break
    for name, pattern in _PII_PATTERNS:
        if re.search(pattern, body):
            flags.append(f"pii:{name}")
    seen: set[str] = set()
    out: list[str] = []
    for flag in flags:
        if flag not in seen:
            seen.add(flag)
            out.append(flag)
    return out


def _structured_responder_output(schema: type, messages: list[BaseMessage]) -> Any:
    human = _last_human_text(messages)
    body_text = human
    sender = ""
    subject_line = "Re: your request"
    try:
        if "Draft a customer-facing reply" in human:
            json_start = human.index("{")
            data = json.loads(human[json_start:])
            raw = data.get("raw") or {}
            body_text = str(raw.get("body", "")) or human
            sender = str(raw.get("sender", ""))
            ticket_subject = str(raw.get("subject", "")).strip()
            if ticket_subject:
                subject_line = f"Re: {ticket_subject}"
    except Exception:
        pass

    flags = _detect_risk_flags(body_text)
    escalate = bool(flags)
    confidence = 0.5 if escalate else 0.85
    action = "escalate" if (escalate or confidence < 0.6) else "send"

    body = (
        "Hello,\n\n"
        "Thanks for contacting support. Based on our investigation, please try the "
        "standard remediation steps documented in our runbook. If the issue persists, "
        "reply to this thread and we will escalate.\n\nBest regards,\nMonk Support"
    )
    low = body_text.lower()
    if "vpn" in low:
        body = (
            "Hello,\n\n"
            "We reviewed your VPN connection logs and see handshake failures that often "
            "indicate a stale client profile. Please quit the VPN client, remove the old "
            "profile, re-import the latest bundle from the self-service portal, and try "
            "again.\n\nBest regards,\nMonk IT Helpdesk"
        )
    elif "mfa" in low or "login" in low:
        body = (
            "Hello,\n\n"
            "We reviewed the authentication logs and can see the MFA loop you reported. "
            "Please resync your authenticator app and try again from a fresh browser "
            "window.\n\nBest regards,\nMonk Support"
        )
    if sender:
        body = body.replace("Hello,", f"Hello {sender.split('@')[0]},", 1)

    fields = getattr(schema, "model_fields", {})
    payload: dict[str, Any] = {}
    if "subject" in fields:
        payload["subject"] = subject_line
    if "body" in fields:
        payload["body"] = body
    if "recommended_action" in fields:
        payload["recommended_action"] = action
    if "confidence" in fields:
        payload["confidence"] = confidence
    if "risk_flags" in fields:
        payload["risk_flags"] = flags
    return schema(**payload)


def _structured_for(schema: type, messages: list[BaseMessage]) -> Any:
    name = getattr(schema, "__name__", "")
    if name == "TriageOutput":
        return _structured_triage_output(schema, messages)
    if name == "ResponderOutput":
        return _structured_responder_output(schema, messages)
    return _structured_triage_output(schema, messages)


class FakeMonkChatModel(BaseChatModel):
    model_name: str = "fake"
    bound_tools: ClassVar[list[Any] | None] = None

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        object.__setattr__(self, "_bound_tools", [])

    @property
    def _llm_type(self) -> str:
        return "fake-monk"

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> FakeMonkChatModel:
        new = FakeMonkChatModel(model_name=self.model_name)
        object.__setattr__(new, "_bound_tools", list(tools))
        return new

    def with_structured_output(self, schema: type, **kwargs: Any) -> Any:
        def _run(value: Any) -> Any:
            messages = value if isinstance(value, list) else value.get("messages", [])
            return _structured_for(schema, messages)

        return RunnableLambda(_run)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        bound = getattr(self, "_bound_tools", []) or []
        if bound:
            text, tool_calls = _route_with_tools(messages, bound)
        else:
            human = _last_human_text(messages).lower()
            if '"claim"' in human and '"source"' in human and '"tool"' in human:
                text = _investigator_findings_json(messages)
            else:
                text = "fake triager response"
            tool_calls = []
        ai = AIMessage(content=text, tool_calls=tool_calls)
        return ChatResult(generations=[ChatGeneration(message=ai)])


class FakeMonkEmbeddings(Embeddings):
    """Deterministic hashed 1024-dim vectors for pgvector compatibility."""

    DIM: ClassVar[int] = 1024

    def _embed_one(self, text: str) -> list[float]:
        text = text or ""
        n_floats_per_block = 16
        n_blocks = math.ceil(self.DIM / n_floats_per_block)
        out: list[float] = []
        for i in range(n_blocks):
            digest = hashlib.sha256(f"{i}|{text}".encode()).digest()[:64]
            for j in range(n_floats_per_block):
                start = (j * 4) % (len(digest) - 4)
                (val,) = struct.unpack(">i", digest[start : start + 4])
                out.append(val / 2_147_483_647.0)
        out = out[: self.DIM]
        norm = math.sqrt(sum(v * v for v in out)) or 1.0
        return [v / norm for v in out]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)


def is_fake_chat_model(name: str | None) -> bool:
    return (name or "").strip().lower() in {"fake", "fake-monk", "offline"}


def is_fake_embeddings(name: str | None) -> bool:
    return (name or "").strip().lower() in {"fake", "fake-monk", "offline", "stub"}


def fake_chat_model(**kwargs: Any) -> FakeMonkChatModel:
    return FakeMonkChatModel(**kwargs)


def fake_embeddings(**_kwargs: Any) -> FakeMonkEmbeddings:
    return FakeMonkEmbeddings()
