"""Shared helper for evals that need to run the full research graph."""

from __future__ import annotations

import uuid
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from app.graph import build_state_graph
from app.memory import get_store


def run_full_graph(question: str, *, recursion_limit: int = 25) -> dict[str, Any]:
    """Compile a fresh graph (in-memory checkpointer) and run it end-to-end.

    LangSmith's ``evaluate`` runs targets in worker threads. The app-level
    SqliteSaver is single-threaded and gets closed mid-run when the pool tears
    down, so each eval invocation builds its own ephemeral graph instead.
    """
    graph = build_state_graph().compile(checkpointer=InMemorySaver(), store=get_store())
    thread_id = f"eval-{uuid.uuid4().hex[:12]}"
    config: dict[str, Any] = {
        "configurable": {"thread_id": thread_id, "user_id": "default"},
        "recursion_limit": recursion_limit,
        "tags": ["monk-eval"],
        "metadata": {"thread_id": thread_id, "user_id": "default", "question": question},
        "run_name": f"eval: {question[:60]}",
    }
    state = {
        "question": question,
        "sub_questions": [],
        "findings": [],
        "report": "",
        "memories": [],
        "step_log": [],
    }
    return graph.invoke(state, config=config)
