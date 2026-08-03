"""Triager agent: classify tickets with structured LLM output."""

from __future__ import annotations

import json
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.llm import get_chat_model
from app.state import TicketState
from app.taxonomy import category_names, format_taxonomy_for_prompt, load_taxonomy


class TriageOutput(BaseModel):
    category: str
    severity: Literal["P1", "P2", "P3", "P4"]
    confidence: float
    rationale: str


def _format_ticket(raw: dict) -> str:
    return json.dumps(
        {
            "subject": raw.get("subject", ""),
            "body": raw.get("body", ""),
            "sender": raw.get("sender", ""),
            "attachments": raw.get("attachments") or [],
        },
        ensure_ascii=False,
        indent=2,
    )


def _normalize_output(
    output: TriageOutput,
    *,
    allowed_categories: set[str],
) -> TriageOutput:
    if output.category in allowed_categories:
        return output
    return output.model_copy(
        update={
            "category": "unknown",
            "severity": "P3",
            "rationale": (
                f"{output.rationale} Category {output.category!r} was not in taxonomy; "
                "defaulted to unknown/P3."
            ).strip(),
        }
    )


def triager_node(state: TicketState) -> dict:
    """Classify the ticket using the domain taxonomy and structured LLM output."""
    domain = state["domain"]
    taxonomy = load_taxonomy(domain)
    allowed = category_names(taxonomy)
    taxonomy_text = format_taxonomy_for_prompt(taxonomy)
    ticket_text = _format_ticket(state["raw"])

    # TODO: episodic memory examples
    prompt = (
        f"You are a {domain} triage analyst. Available categories: {taxonomy_text}. "
        f"Given this ticket: {ticket_text}, choose the best category and severity. "
        "Provide a brief rationale. Be conservative on severity."
    )

    model = get_chat_model().with_structured_output(TriageOutput)
    result = model.invoke(
        [
            SystemMessage(content="You classify support tickets with structured JSON output."),
            HumanMessage(content=prompt),
        ]
    )
    if not isinstance(result, TriageOutput):
        raise TypeError(f"Triager expected TriageOutput, got {type(result)!r}")

    normalized = _normalize_output(result, allowed_categories=allowed | {"unknown"})
    log = state["step_log"] + [
        (
            "Triager: "
            f"{normalized.category} / {normalized.severity} "
            f"(confidence={normalized.confidence:.2f})"
        ),
        f"Triager rationale: {normalized.rationale}",
    ]
    return {
        "classification": {
            "category": normalized.category,
            "confidence": normalized.confidence,
            "rationale": normalized.rationale,
        },
        "severity": normalized.severity,
        "step_log": log,
    }
