"""LangGraph wiring for the ticket triage supervisor loop."""

from __future__ import annotations

import os
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.investigator import investigator_node
from app.agents.responder import responder_node
from app.agents.send import send_node
from app.agents.supervisor import supervisor_node
from app.agents.triager import triager_node
from app.hitl import hitl_node
from app.state import TicketState

CHECKPOINT_PATH = "checkpoints.sqlite"
_checkpointer: SqliteSaver | None = None
_checkpointer_cm = None
_postgres_graph: CompiledStateGraph | None = None
_postgres_pool: Any = None
_postgres_saver: Any = None
_postgres_store: Any = None
_postgres_init_lock = None


def _init_lock():
    global _postgres_init_lock
    if _postgres_init_lock is None:
        import threading

        _postgres_init_lock = threading.Lock()
    return _postgres_init_lock


def _use_postgres_backends() -> bool:
    """Use Postgres checkpoint/store when deployed (App Runner, AgentCore)."""
    if os.getenv("MONK_CHECKPOINT", "").lower() == "postgres":
        return bool(os.getenv("POSTGRES_DSN"))
    dsn = os.getenv("POSTGRES_DSN", "")
    if os.getenv("MONK_MEMORY") == "postgres" and dsn:
        return "localhost" not in dsn and "127.0.0.1" not in dsn
    return False


def _route(state: TicketState) -> str:
    return state["next"]


def _wire_graph(builder: StateGraph) -> StateGraph:
    """Register supervisor/worker nodes and edges on ``builder``."""
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("triager", triager_node)
    builder.add_node("investigator", investigator_node)
    builder.add_node("responder", responder_node)
    builder.add_node("hitl", hitl_node)
    builder.add_node("send", send_node)

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        _route,
        {
            "triager": "triager",
            "investigator": "investigator",
            "responder": "responder",
            "hitl": "hitl",
            "send": "send",
            "END": END,
        },
    )
    for worker in ("triager", "investigator", "responder", "hitl", "send"):
        builder.add_edge(worker, "supervisor")
    return builder


def build_graph_with_backends(saver: Any, store: Any | None = None) -> CompiledStateGraph:
    """Compile the graph with injected checkpoint/store backends (production)."""
    builder = _wire_graph(StateGraph(TicketState))
    compile_kwargs: dict[str, Any] = {"checkpointer": saver}
    if store is not None:
        compile_kwargs["store"] = store
    return builder.compile(**compile_kwargs)


def _get_checkpointer() -> SqliteSaver:
    global _checkpointer, _checkpointer_cm
    if _checkpointer is None:
        _checkpointer_cm = SqliteSaver.from_conn_string(CHECKPOINT_PATH)
        _checkpointer = _checkpointer_cm.__enter__()
    return _checkpointer


def _get_postgres_graph() -> CompiledStateGraph:
    global _postgres_graph, _postgres_pool, _postgres_saver, _postgres_store
    if _postgres_graph is not None:
        return _postgres_graph

    with _init_lock():
        if _postgres_graph is not None:
            return _postgres_graph

        from langgraph.checkpoint.postgres import PostgresSaver
        from langgraph.store.postgres import PostgresStore
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        dsn = os.environ["POSTGRES_DSN"]
        _postgres_pool = ConnectionPool(
            dsn,
            min_size=1,
            max_size=10,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
        _postgres_saver = PostgresSaver(_postgres_pool)
        _postgres_store = PostgresStore(_postgres_pool)
        _postgres_saver.setup()
        _postgres_store.setup()
        _postgres_graph = build_graph_with_backends(saver=_postgres_saver, store=_postgres_store)
    return _postgres_graph


def init_production_graph() -> CompiledStateGraph:
    """Initialize and retain Postgres backends for the process lifetime."""
    return _get_postgres_graph()


def shutdown_production_graph() -> None:
    """Close Postgres pool on app shutdown."""
    global _postgres_graph, _postgres_pool, _postgres_saver, _postgres_store
    _postgres_graph = None
    _postgres_saver = None
    _postgres_store = None
    if _postgres_pool is not None:
        try:
            _postgres_pool.close()
        except Exception:
            pass
        _postgres_pool = None


def build_graph() -> CompiledStateGraph:
    """Compile the graph with Postgres (production) or SQLite (local dev)."""
    if _use_postgres_backends():
        return _get_postgres_graph()
    return build_graph_with_backends(saver=_get_checkpointer())


def sample_ticket() -> TicketState:
    """Minimal ticket payload for local smoke tests."""
    return {
        "ticket_id": "TCK-1001",
        "raw": {
            "subject": "Cannot log in to VPN",
            "body": "VPN client hangs on connecting since this morning.",
            "sender": "alex@example.com",
            "attachments": [],
        },
        "domain": "it-helpdesk",
        "classification": None,
        "severity": None,
        "findings": [],
        "draft": None,
        "approval": "pending",
        "sent": False,
        "step_log": [],
        "next": "",
    }


def _print_routing_steps(final_state: TicketState) -> None:
    print(f"Ticket {final_state['ticket_id']} ({final_state['domain']})")
    print("-" * 60)
    for line in final_state["step_log"]:
        print(line)
    print("-" * 60)
    print(f"Final route target: {final_state.get('next', 'END')}")
    print(f"Sent: {final_state['sent']}")


if __name__ == "__main__":
    graph = build_graph()
    config = {"configurable": {"thread_id": "skeleton-demo"}}
    result = graph.invoke(sample_ticket(), config=config)
    _print_routing_steps(result)
