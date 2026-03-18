import json
import os
import urllib.request
from cryptography.fernet import Fernet
from jose import jwt, jwk, JWTError

# ---------------------------------------------------------------------------
# Supabase JWT verification (supports both ES256 via JWKS and legacy HS256)
# ---------------------------------------------------------------------------

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")

_jwks_cache: dict | None = None


def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is None:
        url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        with urllib.request.urlopen(url, timeout=5) as resp:
            _jwks_cache = json.loads(resp.read())
    return _jwks_cache


def decode_supabase_token(token: str) -> dict:
    """Verify and decode a Supabase-issued JWT. Supports ES256 (JWKS) and HS256."""
    # Try ES256 via JWKS first (new Supabase asymmetric signing)
    if SUPABASE_URL:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            jwks = _get_jwks()
            key_data = next((k for k in jwks["keys"] if k.get("kid") == kid), jwks["keys"][0])
            public_key = jwk.construct(key_data)
            return jwt.decode(token, public_key, algorithms=["ES256"], audience="authenticated")
        except JWTError:
            raise
        except Exception:
            pass  # Fall through to HS256

    # Fallback: legacy HS256 shared secret
    if SUPABASE_JWT_SECRET:
        return jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")

    raise JWTError("No JWT verification method configured: set SUPABASE_URL or SUPABASE_JWT_SECRET")


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
