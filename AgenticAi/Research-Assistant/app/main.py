"""FastAPI + HTMX entrypoint for the AI Research Assistant."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.graph import stream_research
from app.tracing import flush_langsmith_traces

logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).parent / "ui"
INDEX_HTML = UI_DIR / "index.html"

STREAM_QUEUES: dict[str, asyncio.Queue[dict[str, Any] | None]] = {}
QUEUE_TIMEOUT_SECONDS = 60.0
FLUSH_TIMEOUT_SECONDS = 30.0


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    yield
    await asyncio.to_thread(flush_langsmith_traces, timeout=FLUSH_TIMEOUT_SECONDS)


app = FastAPI(title="Monk AI Research Assistant", lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=UI_DIR), name="static")


class ResearchRequest(BaseModel):
    question: str
    user_id: str = "default"


@app.get("/")
def index() -> Response:
    html = INDEX_HTML.read_text(encoding="utf-8")
    return Response(
        content=html,
        media_type="text/html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@app.get("/health")
@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


async def _run_research(question: str, thread_id: str, user_id: str) -> None:
    """Background task: drive the graph and push each event into a queue."""
    queue = STREAM_QUEUES[thread_id]
    try:
        async for event in stream_research(question, thread_id, user_id=user_id):
            await queue.put(event)
    except Exception as exc:
        logger.exception("research thread %s failed", thread_id)
        await queue.put({"event": "error", "data": {"message": str(exc)}})
    finally:
        # Force LangSmith to upload any buffered child runs (planner/researcher/
        # writer + nested LLM/tool calls) before this background task exits.
        await asyncio.to_thread(flush_langsmith_traces, timeout=FLUSH_TIMEOUT_SECONDS)
        await queue.put(None)


@app.post("/research")
async def research(req: ResearchRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty.")
    user_id = (req.user_id or "default").strip() or "default"
    thread_id = uuid4().hex
    STREAM_QUEUES[thread_id] = asyncio.Queue()
    background_tasks.add_task(_run_research, question, thread_id, user_id)
    return {"thread_id": thread_id, "user_id": user_id}


def _serialise(event: dict[str, Any]) -> str:
    return json.dumps(event, default=str)


@app.get("/stream/{thread_id}")
async def stream(thread_id: str, request: Request) -> EventSourceResponse:
    queue = STREAM_QUEUES.get(thread_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Unknown thread_id.")

    async def generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=QUEUE_TIMEOUT_SECONDS)
                except TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                if event is None:
                    yield {"event": "done", "data": "{}"}
                    break
                yield {"data": _serialise(event)}
        finally:
            STREAM_QUEUES.pop(thread_id, None)

    return EventSourceResponse(generator())
