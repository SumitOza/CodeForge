"""routers/build_router.py — build start, status, session list, WebSocket stream."""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from models import BuildRequest, BuildSession
from database import (create_session, update_session, get_session,
                      list_sessions, get_decrypted_key, increment_user_stats, log_token_usage)
from auth import get_current_user, decode_token
from graph.runtime import get_graph
from config import settings, DEFAULT_AGENT_MODELS, normalize_model_id
import os, uuid, json, asyncio, time

router = APIRouter(prefix="/build", tags=["build"])


def _output_dir(user_id: str, session_id: str) -> str:
    base = settings.output_dir
    path = os.path.join(base, user_id, session_id)
    os.makedirs(path, exist_ok=True)
    return path


@router.post("/start", status_code=202)
async def start_build(body: BuildRequest, current_user: dict = Depends(get_current_user)):
    session_id = body.session_id or str(uuid.uuid4())
    user_id = current_user["id"]

    # Fetch user's stored API keys
    user_keys = {}
    for provider in ["cerebras", "groq", "openrouter"]:
        key = await get_decrypted_key(user_id, provider)
        if key:
            user_keys[provider] = key

    if not user_keys:
        raise HTTPException(
            status_code=400,
            detail="No API keys found. Add at least one provider key in Settings → API Keys."
        )

    # Merge user model choices with defaults; remap deprecated model ids
    agent_models = {}
    for agent in ["architect", "coder", "reviewer", "fixer", "filemanager"]:
        if body.agent_models and agent in body.agent_models:
            cfg = dict(body.agent_models[agent])
        else:
            cfg = dict(DEFAULT_AGENT_MODELS[agent])
        cfg["model_id"] = normalize_model_id(cfg["provider"], cfg["model_id"])
        agent_models[agent] = cfg

    # Validate chosen providers have keys
    for agent, cfg in agent_models.items():
        if cfg["provider"] not in user_keys:
            raise HTTPException(
                status_code=400,
                detail=f"Agent '{agent}' is set to use '{cfg['provider']}' but you have no key for it."
            )

    session = BuildSession(
        session_id=session_id,
        user_id=user_id,
        prompt=body.prompt,
        status="planning",
    )
    await create_session(session)

    # Kick off build in background
    asyncio.create_task(_run_build(session_id, user_id, body.prompt, agent_models, user_keys))

    return {"session_id": session_id, "status": "started"}


async def _run_build(session_id: str, user_id: str, prompt: str, agent_models: dict, user_keys: dict):
    output_dir = _output_dir(user_id, session_id)
    initial_state = {
        "session_id": session_id,
        "user_id": user_id,
        "prompt": prompt,
        "output_dir": output_dir,
        "agent_models": agent_models,
        "user_keys": user_keys,
        "plan": None,
        "file_queue": [],
        "current_file": None,
        "completed_files": {},
        "review_passed": False,
        "review_issues": [],
        "fix_attempts": 0,
        "events": [],
        "total_tokens": 0,
        "error": None,
    }
    try:
        graph = await get_graph()
        config = {"configurable": {"thread_id": session_id}}
        final_state = await graph.ainvoke(initial_state, config=config)
        status = "failed" if final_state.get("error") else "done"
        await update_session(session_id, {
            "status": status,
            "files_done": list(final_state.get("completed_files", {}).keys()),
            "total_tokens": final_state.get("total_tokens", 0),
            "completed_at": time.time(),
        })
        await increment_user_stats(user_id, tokens=final_state.get("total_tokens", 0))
    except Exception:
        import traceback
        traceback.print_exc()
        await update_session(session_id, {"status": "failed"})


@router.get("/sessions")
async def list_user_sessions(current_user: dict = Depends(get_current_user)):
    return await list_sessions(current_user["id"])


@router.get("/sessions/{session_id}")
async def get_build_session(session_id: str, current_user: dict = Depends(get_current_user)):
    session = await get_session(session_id, current_user["id"])
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

import zipfile, io
from fastapi.responses import StreamingResponse

@router.get("/sessions/{session_id}/download")
async def download_session_files(session_id: str, current_user: dict = Depends(get_current_user)):
    session = await get_session(session_id, current_user["id"])
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] not in ("done", "failed"):
        raise HTTPException(status_code=400, detail="Build not complete yet")

    output_dir = _output_dir(current_user["id"], session_id)
    if not os.path.exists(output_dir) or not os.listdir(output_dir):
        raise HTTPException(status_code=404, detail="No output files found")

    # Zip everything in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(output_dir):
            for filename in files:
                abs_path = os.path.join(root, filename)
                arc_name = os.path.relpath(abs_path, output_dir)
                zf.write(abs_path, arc_name)
    buf.seek(0)

    zip_name = f"codeforge_{session_id[:8]}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_name}"}
    )

@router.websocket("/ws/{session_id}")
async def ws_stream(websocket: WebSocket, session_id: str):
    await websocket.accept()
    try:
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=4001, reason="No token")
            return
        payload = decode_token(token)
        user_id = payload["sub"]

        graph = await get_graph()
        config = {"configurable": {"thread_id": session_id}}
        async for event in graph.astream(None, config=config):
            for node_name, state in event.items():
                events = state.get("events", [])
                for e in events:
                    await websocket.send_text(e.model_dump_json())
            await asyncio.sleep(0.1)

        await websocket.send_text(json.dumps({"type": "stream_end"}))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
