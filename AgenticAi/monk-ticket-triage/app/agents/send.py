"""Send approved drafts via the send_response tool."""

from __future__ import annotations

from app.state import TicketState
from app.tools.send_response import send_response


def send_node(state: TicketState) -> dict:
    """Dispatch the approved draft. Refuses unless approval is granted."""
    approval = state.get("approval")
    if approval not in ("approved", "edited"):
        raise RuntimeError(f"Send node refused: approval={approval!r}")
    if state.get("sent"):
        raise RuntimeError("Send node refused: already sent")

    draft = state.get("draft") or {}
    raw = state.get("raw") or {}
    external_id = send_response.invoke(
        {
            "ticket_id": state["ticket_id"],
            "subject": str(draft.get("subject", "")),
            "body": str(draft.get("body", "")),
            "recipient": str(raw.get("sender", "")),
        }
    )
    return {
        "sent": True,
        "step_log": state["step_log"] + [f"Send: dispatched response {external_id}"],
    }
