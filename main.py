"""main.py — CodeForge FastAPI application entrypoint."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.auth_router import router as auth_router
from routers.keys_router import router as keys_router
from routers.build_router import router as build_router
from config import settings
import os

app = FastAPI(
    title="CodeForge API",
    description="Multi-agent AI code builder — plan, code, review, fix, save.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router,  prefix="/api")
app.include_router(keys_router,  prefix="/api")
app.include_router(build_router, prefix="/api")

os.makedirs(settings.output_dir, exist_ok=True)


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.app_name}


@app.get("/api/providers")
async def providers():
    from config import PROVIDER_MODELS, DEFAULT_AGENT_MODELS
    return {"providers": PROVIDER_MODELS, "defaults": DEFAULT_AGENT_MODELS}
