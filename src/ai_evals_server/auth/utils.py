import os
from cryptography.fernet import Fernet
from jose import jwt, JWTError

# ---------------------------------------------------------------------------
# Supabase JWT verification
# ---------------------------------------------------------------------------

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")


def decode_supabase_token(token: str) -> dict:
    """Verify and decode a Supabase-issued JWT. Raises JWTError on failure."""
    if not SUPABASE_JWT_SECRET:
        raise JWTError("SUPABASE_JWT_SECRET env var is not set")
    return jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")


# ---------------------------------------------------------------------------
# API key encryption at rest (Fernet)
# ---------------------------------------------------------------------------

_FERNET_KEY = os.environ.get("FERNET_KEY", "")
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        if _FERNET_KEY:
            _fernet = Fernet(_FERNET_KEY.encode())
        else:
            # Dev fallback — keys won't survive a restart; set FERNET_KEY in production
            _fernet = Fernet(Fernet.generate_key())
    return _fernet


def encrypt_api_key(plain_key: str) -> str:
    return _get_fernet().encrypt(plain_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    return _get_fernet().decrypt(encrypted_key.encode()).decode()
