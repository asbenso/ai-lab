"""Mock outbound response delivery."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from langchain_core.tools import tool

from app.tools._paths import DATA_DIR

SENT_LOG = DATA_DIR / "sent_responses.jsonl"


@tool
def send_response(ticket_id: str, subject: str, body: str, recipient: str) -> str:
    """Send the approved draft to the customer (mock: append to a local log file)."""
    external_id = f"EXT-{uuid4().hex[:8].upper()}"
    entry = {
        "external_id": external_id,
        "ticket_id": ticket_id,
        "subject": subject,
        "body": body,
        "recipient": recipient,
        "sent_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }
    SENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SENT_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return external_id
