"""graph/state.py — LangGraph state schema shared across all nodes."""
from typing import TypedDict, Optional, List, Dict, Any
from models import ProjectPlan, FileSpec, BuildEvent


class CodeForgeState(TypedDict):
    # Session context
    session_id: str
    user_id: str
    prompt: str
    output_dir: str

    # Agent model assignments {agent_name: {provider, model_id}}
    agent_models: Dict[str, Dict[str, str]]

    # User API keys {provider: decrypted_key}
    user_keys: Dict[str, str]

    # Build state
    plan: Optional[ProjectPlan]
    file_queue: List[FileSpec]
    current_file: Optional[FileSpec]
    completed_files: Dict[str, str]  # path → content

    # Review/fix cycle
    review_passed: bool
    review_issues: List[str]
    fix_attempts: int

    # Events emitted to UI
    events: List[BuildEvent]

    # Token tracking
    total_tokens: int
    error: Optional[str]
