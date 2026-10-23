import math
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app import auth, db
from app.config import COOKIE_SECURE, LOGIN_LOCK_MINUTES, LOGIN_MAX_ATTEMPTS, SESSION_DAYS

router = APIRouter(prefix="/api")
IP_MAX_ATTEMPTS = LOGIN_MAX_ATTEMPTS * 4  # one address trying many usernames


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class PasswordRequest(BaseModel):
    current: str = Field(min_length=1, max_length=256)
    new: str = Field(min_length=8, max_length=256)


def _start_session(response: Response, uid: int) -> None:
    token = secrets.token_urlsafe(32)
    max_age = SESSION_DAYS * 86400
    db.create_session(auth.token_hash(token), uid, time.time() + max_age)
    response.set_cookie(
        auth.COOKIE, token, max_age=max_age, httponly=True,
        samesite="lax", secure=COOKIE_SECURE,
    )


@router.post("/login")
def login(req: LoginRequest, request: Request, response: Response):
    name = req.username.strip()
    user_key = auth.user_key(name)
    ip_key = f"ip:{request.client.host if request.client else 'unknown'}"
    wait = max(auth.lock_seconds(user_key), auth.lock_seconds(ip_key, IP_MAX_ATTEMPTS))
    if wait:
        minutes = math.ceil(wait / 60)
        raise HTTPException(
            429, f"Too many failed attempts. Try again in {minutes} minute{'s' if minutes > 1 else ''}."
        )
    user = db.get_user(name)
    if not auth.verify_password(req.password, user["password_hash"] if user else None):
        db.add_login_failure([user_key, ip_key], LOGIN_LOCK_MINUTES * 60)
        time.sleep(1)  # slows down password guessing
        left = LOGIN_MAX_ATTEMPTS - len(
            db.recent_login_failures(user_key, time.time() - LOGIN_LOCK_MINUTES * 60, LOGIN_MAX_ATTEMPTS))
        if left <= 0:
            raise HTTPException(429, f"Too many failed attempts. Try again in {LOGIN_LOCK_MINUTES} minutes.")
        hint = f" {left} attempt{'s' if left > 1 else ''} left." if left <= 2 else ""
        raise HTTPException(401, "Wrong username or password." + hint)
    db.clear_login_failures(user_key)
    _start_session(response, user["id"])
    return {"username": user["username"]}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(auth.COOKIE)
    if token:
        db.delete_session(auth.token_hash(token))
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


@router.post("/logout-all")
def logout_all(response: Response, user: dict = Depends(auth.current_user)):
    db.delete_user_sessions(user["id"])
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


@router.post("/password")
def change_password(req: PasswordRequest, response: Response, user: dict = Depends(auth.current_user)):
    stored = db.get_user_by_id(user["id"])
    if not auth.verify_password(req.current, stored["password_hash"]):
        time.sleep(1)
        raise HTTPException(400, "Current password is wrong.")
    db.set_password(user["id"], auth.hash_password(req.new))  # signs out every device
    _start_session(response, user["id"])  # ...except this one
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(auth.current_user)):
    return {"id": user["id"], "username": user["username"], "is_admin": bool(user["is_admin"])}