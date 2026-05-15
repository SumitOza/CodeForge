"""routers/auth_router.py — register, login, profile, logout endpoints."""
from fastapi import APIRouter, HTTPException, status, Depends
from models import RegisterRequest, LoginRequest, TokenResponse, UserProfile
from database import create_user, get_user_by_email, get_user_by_id
from auth import hash_password, verify_password, create_access_token, get_current_user, settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest):
    existing = await get_user_by_email(body.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    hashed = hash_password(body.password)
    user = await create_user(body.email, hashed, body.full_name)

    token = create_access_token(user["id"], user["email"])
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
        user_id=user["id"],
        email=user["email"],
        full_name=user["full_name"],
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    user = await get_user_by_email(body.email)
    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user["id"], user["email"])
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
        user_id=user["id"],
        email=user["email"],
        full_name=user["full_name"],
    )


@router.get("/me", response_model=UserProfile)
async def me(current_user: dict = Depends(get_current_user)):
    return UserProfile(
        id=current_user["id"],
        email=current_user["email"],
        full_name=current_user["full_name"],
        created_at=current_user["created_at"],
        total_builds=current_user.get("total_builds", 0),
        total_tokens_used=current_user.get("total_tokens_used", 0),
    )
