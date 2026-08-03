"""Tiny LangGraph demo (Day 3 H1)."""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith.run_helpers import get_current_run_tree

from app.tracing import flush_langsmith_traces, setup_langsmith_tracing

trace_url: str | None = None


class S(TypedDict):
    q: str
    a: str


def respond(state: S) -> dict:
    global trace_url
    run = get_current_run_tree()
    while run and run.parent_run:
        run = run.parent_run
    if run:
        trace_url = run.get_url()
    return {"a": f"You asked: {state['q']}"}


g = StateGraph(S)
g.add_node("respond", respond)
g.add_edge(START, "respond")
g.add_edge("respond", END)
app = g.compile()


if __name__ == "__main__":
    setup_langsmith_tracing()
    print(app.invoke({"q": "hello"}))
    if trace_url:
        print(f"LangSmith trace: {trace_url}")
    flush_langsmith_traces()
