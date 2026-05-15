"""graph/builder.py — assembles the CodeForge LangGraph state machine."""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from graph.state import CodeForgeState
from graph.nodes import (
    plan_node, pick_file_node, code_node, review_node,
    fix_node, save_node, mark_failed_node
)
from config import settings
import os
import sqlite3


def should_continue_coding(state: CodeForgeState) -> str:
    """After pick_file: if there's a file to code, go to code; else done."""
    if state.get("current_file") is None:
        return "done"
    return "code"


def should_fix_or_save(state: CodeForgeState) -> str:
    """After review: pass → save, fail → fix or give up."""
    if state.get("review_passed"):
        return "save"
    if state.get("fix_attempts", 0) >= settings.max_retries:
        return "mark_failed"
    return "fix"


def should_loop_or_done(state: CodeForgeState) -> str:
    """After save or mark_failed: check if more files remain."""
    queue = state.get("file_queue", [])
    pending = [f for f in queue if f.status == "pending"]
    return "pick" if pending else "done"


def build_graph(checkpoint_dir: str = "/data/checkpoints"):
    os.makedirs(checkpoint_dir, exist_ok=True)
    db_path = os.path.join(checkpoint_dir, "codeforge.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    saver = SqliteSaver(conn)

    graph = StateGraph(CodeForgeState)

    graph.add_node("plan",        plan_node)
    graph.add_node("pick",        pick_file_node)
    graph.add_node("code",        code_node)
    graph.add_node("review",      review_node)
    graph.add_node("fix",         fix_node)
    graph.add_node("save",        save_node)
    graph.add_node("mark_failed", mark_failed_node)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "pick")

    graph.add_conditional_edges("pick",        should_continue_coding, {"code": "code", "done": END})
    graph.add_edge("code", "review")
    graph.add_conditional_edges("review",      should_fix_or_save, {"save": "save", "fix": "fix", "mark_failed": "mark_failed"})
    graph.add_edge("fix", "review")
    graph.add_conditional_edges("save",        should_loop_or_done, {"pick": "pick", "done": END})
    graph.add_conditional_edges("mark_failed", should_loop_or_done, {"pick": "pick", "done": END})

    return graph.compile(checkpointer=SqliteSaver(saver))
