"""routers/keys_router.py — CRUD for user API keys (stored encrypted in Supabase)."""
from fastapi import APIRouter, Depends, HTTPException
from models import ApiKeyCreate, ApiKeyResponse
from database import save_api_key, get_api_keys, delete_api_key
from auth import get_current_user
from typing import List

router = APIRouter(prefix="/keys", tags=["api-keys"])


@router.get("/", response_model=List[ApiKeyResponse])
async def list_keys(current_user: dict = Depends(get_current_user)):
    return await get_api_keys(current_user["id"])


@router.post("/", response_model=ApiKeyResponse, status_code=201)
async def add_key(body: ApiKeyCreate, current_user: dict = Depends(get_current_user)):
    return await save_api_key(current_user["id"], body.provider, body.key_value)


@router.delete("/{provider}", status_code=204)
async def remove_key(provider: str, current_user: dict = Depends(get_current_user)):
    await delete_api_key(current_user["id"], provider)
