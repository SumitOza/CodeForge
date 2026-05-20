"""routers/workspace_router.py — local file ops. Only mounted when MODE=local."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from pathlib import Path
import subprocess, os

router = APIRouter(prefix="/workspace", tags=["workspace"])

class WriteRequest(BaseModel):
    path: str
    content: str

class RunRequest(BaseModel):
    path: str
    args: list = []

@router.get("/tree")
async def file_tree(root: str):
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists():
        raise HTTPException(404, "Directory not found")
    skip = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache"}
    items = []
    for p in sorted(root_path.rglob("*")):
        if any(part in skip for part in p.parts):
            continue
        try:
            items.append({
                "path": str(p),
                "relative": str(p.relative_to(root_path)),
                "is_dir": p.is_dir(),
                "size": p.stat().st_size if p.is_file() else 0,
            })
        except (PermissionError, OSError):
            pass
    return items

@router.get("/file", response_class=PlainTextResponse)
async def read_file(path: str):
    p = Path(path).expanduser()
    if not p.exists():
        raise HTTPException(404, "File not found")
    return p.read_text(errors="replace")

@router.post("/file")
async def write_file(body: WriteRequest):
    p = Path(body.path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body.content)
    return {"saved": True, "path": str(p)}

@router.post("/run")
async def run_file(body: RunRequest):
    p = Path(body.path).expanduser()
    if not p.exists():
        raise HTTPException(404, "File not found")
    ext = p.suffix.lstrip(".")
    cmd = {"py": "python", "js": "node", "sh": "bash"}.get(ext, "python")
    try:
        result = subprocess.run(
            [cmd, str(p)] + body.args,
            capture_output=True, text=True, timeout=30, cwd=str(p.parent)
        )
        return {"stdout": result.stdout, "stderr": result.stderr,
                "returncode": result.returncode}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "Timed out after 30s", "returncode": -1}

@router.websocket("/watch")
async def watch_dir(websocket: WebSocket, root: str):
    await websocket.accept()
    try:
        import watchfiles
        async for changes in watchfiles.awatch(root):
            await websocket.send_json([
                {"type": str(c[0].name), "path": c[1]} for c in changes
            ])
    except WebSocketDisconnect:
        pass
    except ImportError:
        await websocket.send_json({"error": "watchfiles not installed"})