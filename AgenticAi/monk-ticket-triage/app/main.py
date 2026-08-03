"""FastAPI service for ticket ingest and human approval."""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from langgraph.types import Command
from pydantic import BaseModel

import app._env
from app.graph import build_graph, init_production_graph, shutdown_production_graph
from app.state import TicketState
from app.thread_registry import (
    init_registry,
    list_threads,
    register_thread,
    remove_thread,
    shutdown_registry,
)

logger = logging.getLogger(__name__)
UI_DIR = Path(__file__).resolve().parent / "ui"
_graph = None
_approve_locks: dict[str, threading.Lock] = {}
_approve_locks_guard = threading.Lock()


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _graph
    if os.getenv("MONK_CHECKPOINT", "").lower() == "postgres" or (
        os.getenv("MONK_MEMORY") == "postgres"
        and os.getenv("POSTGRES_DSN")
        and "localhost" not in os.getenv("POSTGRES_DSN", "")
    ):
        init_registry()
        _graph = init_production_graph()
    yield
    shutdown_production_graph()
    shutdown_registry()


class IngestRequest(BaseModel):
    ticket: dict[str, Any]
    domain: Literal["support", "it-helpdesk", "oncall"]


class ApproveRequest(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_body: str | None = None


def _initial_state(ticket: dict[str, Any], domain: str) -> TicketState:
    ticket_id = str(ticket.get("id") or ticket.get("ticket_id") or f"TCK-{uuid.uuid4().hex[:8]}")
    return {
        "ticket_id": ticket_id,
        "raw": ticket,
        "domain": domain,  # type: ignore[typeddict-item]
        "classification": None,
        "severity": None,
        "findings": [],
        "draft": None,
        "approval": "pending",
        "sent": False,
        "step_log": [],
        "next": "",
    }


def _interrupt_payload(snapshot) -> dict[str, Any] | None:
    for task in snapshot.tasks or ():
        for item in task.interrupts or ():
            value = item.value
            if isinstance(value, dict):
                return value
    return None


def _is_processed(snapshot) -> bool:
    values = snapshot.values or {}
    if values.get("sent"):
        return True
    if values.get("approval") in ("approved", "edited", "rejected"):
        return True
    return False


def _wait_for_interrupt(graph, config: dict[str, Any], *, attempts: int = 8, delay_s: float = 0.4):
    """Poll checkpoint until HITL interrupt is visible or the run is clearly finished."""
    snapshot = graph.get_state(config)
    for attempt in range(attempts):
        payload = _interrupt_payload(snapshot)
        if payload is not None:
            return snapshot, payload
        if _is_processed(snapshot):
            raise HTTPException(status_code=409, detail="Already processed")
        if attempt < attempts - 1:
            time.sleep(delay_s)
            snapshot = graph.get_state(config)
    raise HTTPException(status_code=409, detail="Draft not ready for approval yet")


def _approve_lock(thread_id: str) -> threading.Lock:
    with _approve_locks_guard:
        lock = _approve_locks.get(thread_id)
        if lock is None:
            lock = threading.Lock()
            _approve_locks[thread_id] = lock
        return lock


def _run_graph(thread_id: str, state: TicketState) -> None:
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    try:
        graph.invoke(state, config=config)
    except Exception:
        logger.exception("Graph run failed for thread %s", thread_id)


app = FastAPI(title="Monk Ticket Triage", version="0.1.0", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def approval_page() -> FileResponse:
    return FileResponse(UI_DIR / "approval.html")


@app.post("/ingest")
def ingest_ticket(body: IngestRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    thread_id = str(uuid.uuid4())
    register_thread(thread_id)
    state = _initial_state(body.ticket, body.domain)
    background_tasks.add_task(_run_graph, thread_id, state)
    return {"thread_id": thread_id, "ticket_id": state["ticket_id"]}


@app.get("/pending")
def list_pending() -> list[dict[str, Any]]:
    graph = get_graph()
    pending: list[dict[str, Any]] = []
    for thread_id in sorted(list_threads()):
        config = {"configurable": {"thread_id": thread_id}}
        snapshot = graph.get_state(config)
        payload = _interrupt_payload(snapshot)
        if payload is not None:
            pending.append({"thread_id": thread_id, "payload": payload})
        elif _is_processed(snapshot):
            remove_thread(thread_id)
    return pending


@app.post("/approve/{thread_id}")
def approve_ticket(thread_id: str, body: ApproveRequest) -> dict[str, Any]:
    if thread_id not in list_threads():
        raise HTTPException(status_code=404, detail=f"Unknown thread_id: {thread_id}")

    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    with _approve_lock(thread_id):
        _wait_for_interrupt(graph, config)

        resume_payload = {"action": body.action, "edited_body": body.edited_body}
        result = graph.invoke(Command(resume=resume_payload), config=config)
        if _is_processed(graph.get_state(config)) or result.get("sent"):
            remove_thread(thread_id)
        return {
            "thread_id": thread_id,
            "approval": result.get("approval"),
            "sent": result.get("sent", False),
            "step_log": result.get("step_log", []),
        }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=False)
