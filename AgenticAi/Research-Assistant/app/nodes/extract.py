"""Extract node: persist stable user facts/preferences after a research run."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from app.graph import ResearchState
from app.llm import get_chat_model
from app.memory import get_store, remember
from app.nodes._retry import call_with_retry
from app.nodes.recall import _user_namespace

EXTRACT_SYSTEM = (
    "You identify durable user preferences or stable facts worth storing for future "
    "research sessions. Reply with strict JSON only."
)
EXTRACT_PROMPT = (
    "Looking at the user's question and the report, is there any preference or stable "
    "fact about this user worth remembering?\n\n"
    "Question:\n{question}\n\n"
    "Report:\n{report}\n\n"
    "Return JSON with keys:\n"
    '- "worth_remembering": bool\n'
    '- "content": str (empty when not worth remembering)\n'
    '- "kind": "preference" or "fact" (when worth remembering)\n\n'
    "Use kind=preference for report format/style choices (e.g. bullet lists, concise "
    "summaries). Use kind=fact for stable background about the user."
)


class ExtractOutput(BaseModel):
    worth_remembering: bool
    content: str = ""
    kind: Literal["preference", "fact"] = "fact"


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


def _parse_extract_output(text: str) -> ExtractOutput | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        return ExtractOutput.model_validate_json(text)
    except ValidationError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            return ExtractOutput.model_validate(json.loads(match.group(0)))
        except (json.JSONDecodeError, ValidationError):
            return None


def extract_node(state: ResearchState, config: dict[str, Any]) -> dict:
    """Ask the LLM whether to persist a new memory; write via ``remember`` when yes."""
    question = state.get("question") or ""
    report = state.get("report") or ""
    log = list(state["step_log"])

    if not report.strip():
        log.append("Extract: skipped (empty report)")
        return {"step_log": log}

    model = get_chat_model()
    reply = call_with_retry(
        model.invoke,
        [
            SystemMessage(content=EXTRACT_SYSTEM),
            HumanMessage(
                content=EXTRACT_PROMPT.format(
                    question=question,
                    report=report[:8000],
                )
            ),
        ],
        label="extract",
    )
    parsed = _parse_extract_output(_message_text(reply.content))
    if parsed is None:
        log.append("Extract: could not parse LLM JSON")
        return {"step_log": log}

    if not parsed.worth_remembering or not parsed.content.strip():
        log.append("Extract: nothing worth remembering")
        return {"step_log": log}

    store = get_store()
    namespace = _user_namespace(config)
    key = remember(store, namespace, parsed.content.strip(), parsed.kind)
    log.append(f"Extract: remembered {parsed.kind!r} as {key!r}")
    return {"step_log": log}
