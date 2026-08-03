"""LangGraph research assistant: recall -> planner -> researcher -> writer -> guard -> extract."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.guardrails import validate_citations
from app.memory import get_store
from app.tracing import flush_langsmith_traces

CHECKPOINT_PATH = "checkpoints.sqlite"
_checkpointer: SqliteSaver | None = None
_checkpointer_cm = None
_async_checkpointer: AsyncSqliteSaver | None = None
_async_checkpointer_cm = None
_compiled_graph: CompiledStateGraph | None = None
_compiled_async_graph: CompiledStateGraph | None = None


class ResearchState(TypedDict):
    """Shared graph state for the research assistant."""

    question: str
    sub_questions: list[dict]  # {"text": str, "source": Literal["web", "local", "both"]}
    findings: list[dict]  # {"sub_question_index", "claim", "evidence_url", "evidence_text"}
    report: str
    memories: list[dict]  # {"key", "value", "score"} from recall_node
    step_log: list[str]


def guard_node(state: ResearchState) -> dict:
    """Validate report citations against researcher findings; warn on hallucinated URLs."""
    findings = state.get("findings") or []
    report = state.get("report") or ""
    allowed_urls = {
        str(f["evidence_url"]).strip()
        for f in findings
        if f.get("evidence_url")
    }
    ok, bad_urls = validate_citations(report, allowed_urls)
    if not ok:
        report = (
            f"> WARNING: filtered hallucinated citations: {bad_urls}\n\n{report}"
        )
    return {
        "report": report,
        "step_log": state["step_log"] + ["Guard: citations validated"],
    }


def _get_checkpointer() -> SqliteSaver:
    """Return a process-lifetime SqliteSaver (from_conn_string closes on context exit)."""
    global _checkpointer, _checkpointer_cm
    if _checkpointer is None:
        _checkpointer_cm = SqliteSaver.from_conn_string(CHECKPOINT_PATH)
        _checkpointer = _checkpointer_cm.__enter__()
    return _checkpointer


def build_state_graph() -> StateGraph:
    """Public builder so evals can compile a fresh graph with their own checkpointer."""
    from app.nodes.extract import extract_node
    from app.nodes.planner import planner_node
    from app.nodes.recall import recall_node
    from app.nodes.researcher import researcher_node
    from app.nodes.writer import writer_node

    builder = StateGraph(ResearchState)
    builder.add_node("recall", recall_node)
    builder.add_node("planner", planner_node)
    builder.add_node("researcher", researcher_node)
    builder.add_node("writer", writer_node)
    builder.add_node("guard", guard_node)
    builder.add_node("extract", extract_node)
    builder.add_edge(START, "recall")
    builder.add_edge("recall", "planner")
    builder.add_edge("planner", "researcher")
    builder.add_edge("researcher", "writer")
    builder.add_edge("writer", "guard")
    builder.add_edge("guard", "extract")
    builder.add_edge("extract", END)
    return builder


_build_state_graph = build_state_graph  # backward-compat alias


def build_graph() -> CompiledStateGraph:
    """Compile (or return the cached) research graph with SQLite checkpointer + memory store."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_state_graph().compile(
            checkpointer=_get_checkpointer(),
            store=get_store(),
        )
    return _compiled_graph


def _patch_aiosqlite_is_alive() -> None:
    """Shim for langgraph-checkpoint-sqlite 2.0.11 vs aiosqlite >=0.21.

    `AsyncSqliteSaver.setup` calls `self.conn.is_alive()`, but newer aiosqlite
    Connections no longer expose that attribute. Provide a minimal stand-in so
    the async checkpointer works without pinning aiosqlite back.
    """
    import aiosqlite

    if hasattr(aiosqlite.Connection, "is_alive"):
        return

    def _is_alive(self: aiosqlite.Connection) -> bool:
        return True

    aiosqlite.Connection.is_alive = _is_alive


async def _get_async_checkpointer() -> AsyncSqliteSaver:
    """Process-lifetime AsyncSqliteSaver for `astream_events`."""
    global _async_checkpointer, _async_checkpointer_cm
    if _async_checkpointer is None:
        _patch_aiosqlite_is_alive()
        _async_checkpointer_cm = AsyncSqliteSaver.from_conn_string(CHECKPOINT_PATH)
        _async_checkpointer = await _async_checkpointer_cm.__aenter__()
    return _async_checkpointer


async def _build_async_graph() -> CompiledStateGraph:
    global _compiled_async_graph
    if _compiled_async_graph is None:
        saver = await _get_async_checkpointer()
        _compiled_async_graph = build_state_graph().compile(
            checkpointer=saver,
            store=get_store(),
        )
    return _compiled_async_graph


def _initial_state(question: str) -> ResearchState:
    return {
        "question": question,
        "sub_questions": [],
        "findings": [],
        "report": "",
        "memories": [],
        "step_log": [],
    }


def _research_run_name(question: str) -> str:
    snippet = " ".join(question.split())
    if len(snippet) > 60:
        snippet = snippet[:57].rstrip() + "..."
    return f"research: {snippet}" if snippet else "research"


_GRAPH_PROGRESS_NODES = frozenset({"recall", "planner", "researcher", "writer", "guard", "extract"})


def _extract_progress_detail(event: dict[str, Any]) -> dict[str, Any] | None:
    """Return a UI-friendly progress payload for top-level graph node completions."""
    if event.get("event") != "on_chain_end":
        return None
    meta = event.get("metadata") or {}
    node = meta.get("langgraph_node") or event.get("name")
    if node not in _GRAPH_PROGRESS_NODES:
        return None
    output = (event.get("data") or {}).get("output")
    if not isinstance(output, dict):
        return None

    step_log = output.get("step_log")
    if not isinstance(step_log, list):
        return None

    if node == "planner" and not output.get("sub_questions"):
        return None
    if node == "researcher" and "findings" not in output:
        return None
    if node == "recall" and "memories" not in output:
        return None
    if node in {"writer", "guard"} and "report" not in output:
        return None
    if node == "extract" and not any(str(line).startswith("Extract:") for line in step_log):
        return None

    return {"node": node, "output": output}


async def stream_research(
    question: str,
    thread_id: str,
    *,
    user_id: str = "default",
) -> AsyncIterator[dict[str, Any]]:
    """Yield LangGraph v2 events for a research run, scoped to ``thread_id``.

    The root LangSmith run is named after the user's question so it's easy to
    find in the Tracing list view; ``thread_id``/``question`` land in run
    metadata so you can filter or jump back to a specific run.
    """
    graph = await _build_async_graph()
    config: dict[str, Any] = {
        "configurable": {"thread_id": thread_id, "user_id": user_id},
        "run_name": _research_run_name(question),
        "tags": ["monk-research", f"thread:{thread_id}", f"user:{user_id}"],
        "metadata": {"thread_id": thread_id, "user_id": user_id, "question": question},
    }
    async for event in graph.astream_events(
        _initial_state(question),
        config=config,
        version="v2",
    ):
        yield event
        detail = _extract_progress_detail(event)
        if detail is not None:
            yield {"event": "progress_detail", "data": detail}
    flush_langsmith_traces()


__all__ = ["ResearchState", "build_graph", "stream_research"]
