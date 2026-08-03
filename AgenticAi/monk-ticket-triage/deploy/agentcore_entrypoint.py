import asyncio
import logging
import os
import uuid

from bedrock_agentcore import BedrockAgentCoreApp

app = BedrockAgentCoreApp()
logger = logging.getLogger(__name__)

_graph = None
_init_lock: asyncio.Lock | None = None
_backend_cms: dict[str, object] = {}


async def _get_graph():
    """Build and cache the graph with async Postgres checkpoint + store backends."""
    global _graph, _init_lock
    if _graph is not None:
        return _graph

    if _init_lock is None:
        _init_lock = asyncio.Lock()

    async with _init_lock:
        if _graph is not None:
            return _graph

        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from langgraph.store.postgres.aio import AsyncPostgresStore

        from app.graph import build_graph_with_backends

        dsn = os.environ["POSTGRES_DSN"]
        saver_cm = AsyncPostgresSaver.from_conn_string(dsn)
        store_cm = AsyncPostgresStore.from_conn_string(dsn)
        saver = await saver_cm.__aenter__()
        store = await store_cm.__aenter__()
        await saver.setup()
        await store.setup()
        _backend_cms["saver"] = saver_cm
        _backend_cms["store"] = store_cm
        _graph = build_graph_with_backends(saver=saver, store=store)
        return _graph


@app.entrypoint
async def handler(payload, context):
    """Run the ticket graph; return state (stops at HITL with approval=pending)."""
    graph = await _get_graph()
    thread_id = context.session_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    return await graph.ainvoke(payload, config=config)


if __name__ == "__main__":
    app.run()
