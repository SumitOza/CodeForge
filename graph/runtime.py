"""graph/runtime.py — lazy async init for the compiled LangGraph + SQLite checkpointer."""
import os
import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from graph.builder import compile_graph
from config import settings

_graph = None
_db_conn = None


async def get_graph():
    """Return the compiled graph, initializing the async checkpointer on first use."""
    global _graph, _db_conn
    if _graph is not None:
        return _graph

    os.makedirs(settings.checkpoint_dir, exist_ok=True)
    db_path = os.path.join(settings.checkpoint_dir, "codeforge.db")
    _db_conn = await aiosqlite.connect(db_path)
    saver = AsyncSqliteSaver(_db_conn)
    await saver.setup()
    _graph = compile_graph(saver)
    return _graph


async def close_graph():
    """Close the SQLite connection (app shutdown)."""
    global _graph, _db_conn
    _graph = None
    if _db_conn is not None:
        await _db_conn.close()
        _db_conn = None
