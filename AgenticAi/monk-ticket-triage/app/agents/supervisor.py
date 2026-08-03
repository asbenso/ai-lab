"""Supervisor: pure routing logic, no LLM."""

from __future__ import annotations

from app.state import TicketState


def supervisor_node(state: TicketState) -> dict:
    """Decide the next worker from current ticket state."""
    log = list(state["step_log"])

    if state.get("classification") is None:
        route = "triager"
    elif not state.get("findings"):
        route = "investigator"
    elif state.get("draft") is None:
        route = "responder"
    elif state.get("approval") == "pending":
        route = "hitl"
    elif state.get("approval") in ("approved", "edited") and not state.get("sent"):
        route = "send"
    else:
        route = "END"

    log.append(f"Supervisor: route -> {route}")
    return {"next": route, "step_log": log}
