"""graph/runtime.py — lazy async init for the compiled LangGraph + SQLite checkpointer."""
import os
import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from graph.builder import compile_graph
from config import settings

_connections : dict = {}

async def get_graph(session_id: str = None):
    """Return a compiled graph with an isolated checkpointer for this session."""
    os.makedirs(settings.checkpoint_dir, exist_ok=True)
    
    # Use one DB file per session to fully isolate concurrent builds
    if session_id:
        db_path = os.path.join(settings.checkpoint_dir, f"{session_id}.db")
    else:
        db_path = os.path.join(settings.checkpoint_dir, "codeforge.db")
    
    conn = await aiosqlite.connect(db_path)
    saver = AsyncSqliteSaver(conn)
    await saver.setup()
    graph = compile_graph(saver)
    # Store conn so caller can close it
    _connections[session_id or "default"] = conn
    return graph, conn


async def close_graph():
    """Close all open connections (app shutdown)."""
    for conn in list(_connections.values()):
        try:
            await conn.close()
        except Exception:
            pass
    _connections.clear()