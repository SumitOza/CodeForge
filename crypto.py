"""crypto.py — AES-256-GCM encryption for user API keys stored in Supabase."""
import base64, os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from config import settings


def _get_key() -> bytes:
    raw = settings.encryption_key
    key_bytes = base64.urlsafe_b64decode(raw + "==")
    assert len(key_bytes) == 32, "ENCRYPTION_KEY must be 32 bytes base64-encoded"
    return key_bytes


def encrypt_key(plaintext: str) -> str:
    """Encrypt an API key string. Returns base64 encoded ciphertext with nonce prefix."""
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.urlsafe_b64encode(nonce + ct).decode()


def decrypt_key(ciphertext: str) -> str:
    """Decrypt an encrypted API key string."""
    key = _get_key()
    aesgcm = AESGCM(key)
    raw = base64.urlsafe_b64decode(ciphertext)
    nonce, ct = raw[:12], raw[12:]
    return aesgcm.decrypt(nonce, ct, None).decode()


def preview_key(key_value: str) -> str:
    """Return a safe preview like sk-...ab3c for display."""
    if len(key_value) <= 8:
        return "****"
    return key_value[:4] + "..." + key_value[-4:]


def generate_encryption_key() -> str:
    """Helper: generate a new 32-byte key. Run once and store in .env."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
