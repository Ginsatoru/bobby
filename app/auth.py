"""Password hashing and the logged-in user dependency."""
import hashlib
import hmac
import math
import secrets
import time

from fastapi import HTTPException, Request

from app import db
from app.config import LOGIN_LOCK_MINUTES, LOGIN_MAX_ATTEMPTS

COOKIE = "bobby_session"
_DUMMY = None  # hash checked for unknown usernames, so timing doesn't reveal them


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"{salt.hex()}${_scrypt(password, salt).hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    global _DUMMY
    if stored is None:
        _DUMMY = _DUMMY or hash_password(secrets.token_hex(8))
    salt, digest = (stored or _DUMMY).split("$")
    match = hmac.compare_digest(_scrypt(password, bytes.fromhex(salt)).hex(), digest)
    return stored is not None and match


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def user_from_request(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE)
    return db.session_user(token_hash(token)) if token else None


def current_user(request: Request) -> dict:
    user = user_from_request(request)
    if not user:
        raise HTTPException(401, "Please sign in.")
    return user


def require_admin(request: Request) -> dict:
    user = current_user(request)
    if not user["is_admin"]:
        raise HTTPException(403, "Only admins can do that.")
    return user


def lock_seconds(key: str, limit: int = LOGIN_MAX_ATTEMPTS) -> int:
    """Seconds until `key` may try signing in again, or 0 if it isn't locked."""
    window = LOGIN_LOCK_MINUTES * 60
    times = db.recent_login_failures(key, time.time() - window, limit)
    return max(0, math.ceil(times[-1] + window - time.time())) if len(times) >= limit else 0


def user_key(username: str) -> str:
    return f"user:{username.lower()}"