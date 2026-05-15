"""models.py — all Pydantic schemas for CodeForge."""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Literal, List, Dict, Any
import time, uuid


# ── Auth ──────────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    email: str
    full_name: str

class UserProfile(BaseModel):
    id: str
    email: str
    full_name: str
    created_at: str
    total_builds: int = 0
    total_tokens_used: int = 0


# ── API Keys ──────────────────────────────────────────────────────────────────
class ApiKeyCreate(BaseModel):
    provider: Literal["cerebras", "groq", "openrouter"]
    key_value: str = Field(..., min_length=8)

class ApiKeyResponse(BaseModel):
    id: str
    provider: str
    key_preview: str   # e.g. "sk-...abc4"
    created_at: str
    is_valid: Optional[bool] = None

class ApiKeyUpdate(BaseModel):
    key_value: str = Field(..., min_length=8)


# ── Build ─────────────────────────────────────────────────────────────────────
class AgentModelChoice(BaseModel):
    provider: Literal["cerebras", "groq", "openrouter"]
    model_id: str

class BuildRequest(BaseModel):
    prompt: str = Field(..., min_length=10)
    agent_models: Optional[Dict[str, Dict[str, str]]] = None
    session_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))

class FileSpec(BaseModel):
    path: str
    description: str
    depends_on: List[str] = []
    status: Literal["pending","coding","reviewing","fixing","done","failed"] = "pending"
    retries: int = 0
    content: Optional[str] = None
    issues: List[str] = []

class ProjectPlan(BaseModel):
    name: str
    description: str
    tech_stack: List[str]
    files: List[FileSpec]
    setup_commands: List[str] = []
    run_command: str = ""

class BuildEvent(BaseModel):
    type: Literal[
        "plan_ready","file_start","file_done","file_failed",
        "review_pass","review_fail","fix_attempt","build_complete","log","error"
    ]
    message: str
    file_path: Optional[str] = None
    data: Optional[Any] = None
    timestamp: float = Field(default_factory=time.time)

class BuildSession(BaseModel):
    session_id: str
    user_id: str
    prompt: str
    status: Literal["planning","building","done","failed","paused"] = "planning"
    plan: Optional[ProjectPlan] = None
    files_done: List[str] = []
    files_failed: List[str] = []
    total_tokens: int = 0
    started_at: float = Field(default_factory=time.time)
    completed_at: Optional[float] = None

class ReviewResult(BaseModel):
    passed: bool
    issues: List[str] = []
    file_path: str

class TokenUsage(BaseModel):
    agent: str
    provider: str
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
