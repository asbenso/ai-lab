"""Human-in-the-loop approval gate."""

from __future__ import annotations

from langgraph.types import interrupt

from app.state import TicketState


def hitl_node(state: TicketState) -> dict:
    """Pause for human review; resume with approve, edit, or reject."""
    payload = interrupt(
        {
            "draft": state["draft"],
            "classification": state["classification"],
            "severity": state["severity"],
            "findings": state["findings"],
            "raw": state["raw"],
        }
    )
    if not isinstance(payload, dict):
        payload = {"action": "reject", "edited_body": None}

    action = str(payload.get("action", "reject")).strip().lower()
    edited_body = payload.get("edited_body")
    draft = dict(state["draft"] or {})
    log = list(state["step_log"])

    if action == "approve":
        log.append("HITL: approved")
        return {"approval": "approved", "draft": draft, "step_log": log}
    if action == "edit":
        if edited_body is not None:
            draft["body"] = str(edited_body)
        log.append("HITL: edited and approved")
        return {"approval": "edited", "draft": draft, "step_log": log}

    log.append("HITL: rejected")
    return {"approval": "rejected", "draft": draft, "step_log": log}
