"""Shared graph state for the ticket triage agent."""

from __future__ import annotations

from typing import Literal, TypedDict


class TicketState(TypedDict):
    """State carried through the supervisor/worker loop."""

    ticket_id: str
    raw: dict  # subject, body, sender, attachments
    domain: Literal["support", "it-helpdesk", "oncall"]
    classification: dict | None  # category, confidence, rationale
    severity: Literal["P1", "P2", "P3", "P4"] | None
    findings: list[dict]
    draft: dict | None
    approval: Literal["pending", "approved", "edited", "rejected"]
    sent: bool
    step_log: list[str]
    next: str  # set by supervisor for conditional routing
