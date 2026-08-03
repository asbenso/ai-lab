"""Responder agent: draft replies using procedural, episodic, and semantic memory."""

from __future__ import annotations

import json
import re
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.llm import get_chat_model
from app.memory import get_responder_prompt, recall_user, similar_past_cases
from app.state import TicketState

_ESCALATION_KEYWORDS = (
    "refund",
    "credit",
    "guarantee",
    "tomorrow",
    "by eod",
    "by end of day",
)

_PII_PATTERNS: tuple[tuple[str, str], ...] = (
    ("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ("phone", r"(?:(?:\+?\d{1,3}[-.\s])?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})"),
)


class ResponderOutput(BaseModel):
    subject: str
    body: str
    recommended_action: Literal["send", "escalate"]
    confidence: float = Field(ge=0.0, le=1.0)
    risk_flags: list[str] = Field(default_factory=list)


def _format_episodic_examples(cases: list[dict]) -> str:
    if not cases:
        return ""
    lines = ["Few-shot examples from similar past cases:"]
    for index, case in enumerate(cases, start=1):
        lines.append(f"Example {index} ticket: {case.get('ticket_text', '')}")
        lines.append(f"Example {index} resolution: {case.get('resolution_text', '')}")
    return "\n".join(lines)


def _format_semantic_memories(memories: list[dict]) -> str:
    lines = ["What we know about this user:"]
    found = False
    for memory in memories:
        value = memory.get("value") or {}
        content = str(value.get("content", "")).strip()
        if content:
            lines.append(f"- {content}")
            found = True
    if not found:
        lines.append("- (no stored memories yet)")
    return "\n".join(lines)


def _ticket_payload(state: TicketState) -> str:
    return json.dumps(
        {
            "ticket_id": state["ticket_id"],
            "raw": state["raw"],
            "classification": state.get("classification"),
            "severity": state.get("severity"),
            "findings": state.get("findings") or [],
        },
        ensure_ascii=False,
        indent=2,
    )


def _build_messages(state: TicketState) -> list[SystemMessage | HumanMessage]:
    domain = state["domain"]
    raw = state["raw"]
    style_prompt = get_responder_prompt(domain)
    episodic = similar_past_cases(raw.get("body", ""), domain, k=3)
    semantic = recall_user(str(raw.get("sender", "")), k=3)

    episodic_text = _format_episodic_examples(episodic)
    semantic_text = _format_semantic_memories(semantic)
    human_parts = [
        part
        for part in (
            episodic_text,
            semantic_text,
            "Draft a customer-facing reply for this ticket:",
            _ticket_payload(state),
        )
        if part
    ]

    return [
        SystemMessage(content=style_prompt),
        HumanMessage(content="\n\n".join(human_parts)),
    ]


def _post_process(output: ResponderOutput) -> ResponderOutput:
    flags = list(output.risk_flags)
    escalate = False

    if output.confidence < 0.6:
        escalate = True
        if "low_confidence" not in flags:
            flags.append("low_confidence")

    body_lower = output.body.lower()
    for keyword in _ESCALATION_KEYWORDS:
        if keyword in body_lower:
            escalate = True
            flag = f"keyword:{keyword}"
            if flag not in flags:
                flags.append(flag)

    for name, pattern in _PII_PATTERNS:
        if re.search(pattern, output.body):
            escalate = True
            flag = f"pii:{name}"
            if flag not in flags:
                flags.append(flag)

    action: Literal["send", "escalate"] = "escalate" if escalate else output.recommended_action
    return output.model_copy(update={"recommended_action": action, "risk_flags": flags})


def responder_node(state: TicketState) -> dict:
    """Draft a reply using memory layers and structured LLM output."""
    messages = _build_messages(state)
    model = get_chat_model().with_structured_output(ResponderOutput)
    result = model.invoke(messages)
    if not isinstance(result, ResponderOutput):
        raise TypeError(f"Responder expected ResponderOutput, got {type(result)!r}")

    final = _post_process(result)
    log = state["step_log"] + [
        (
            "Responder: "
            f"action={final.recommended_action} confidence={final.confidence:.2f} "
            f"flags={final.risk_flags or ['none']}"
        ),
        f"Responder subject: {final.subject}",
    ]
    return {
        "draft": final.model_dump(),
        "approval": "pending",
        "step_log": log,
    }
