import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import auth, db

router = APIRouter(prefix="/api/admin", dependencies=[Depends(auth.require_admin)])


class NewUser(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=8, max_length=256)
    is_admin: bool = False


class NewPassword(BaseModel):
    password: str = Field(min_length=8, max_length=256)


class AdminFlag(BaseModel):
    is_admin: bool


class CaseEdit(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    problem: str = Field(min_length=1, max_length=5000)
    cause: str = Field("", max_length=5000)
    fix: str = Field(min_length=1, max_length=10000)


def _user_or_404(uid: int) -> dict:
    user = db.get_user_by_id(uid)
    if not user:
        raise HTTPException(404, "User not found.")
    return user


# ---------- users ----------


@router.get("/users")
def list_users():
    return [
        {**u, "is_admin": bool(u["is_admin"]), "locked": auth.lock_seconds(auth.user_key(u["username"])) > 0}
        for u in db.list_users()
    ]


@router.post("/users")
def add_user(req: NewUser):
    try:
        db.create_user(req.username, auth.hash_password(req.password), req.is_admin)
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"User '{req.username}' already exists.") from None
    return {"ok": True}


@router.post("/users/{uid}/password")
def reset_password(uid: int, req: NewPassword):
    user = _user_or_404(uid)
    db.set_password(uid, auth.hash_password(req.password))
    db.clear_login_failures(auth.user_key(user["username"]))
    return {"ok": True}


@router.post("/users/{uid}/admin")
def set_admin(uid: int, req: AdminFlag, me: dict = Depends(auth.current_user)):
    user = _user_or_404(uid)
    if not req.is_admin and user["is_admin"] and (uid == me["id"] or db.count_admins() <= 1):
        raise HTTPException(400, "You can't remove your own admin access or the last admin.")
    db.set_admin(uid, req.is_admin)
    return {"ok": True}


@router.post("/users/{uid}/unlock")
def unlock_user(uid: int):
    db.clear_login_failures(auth.user_key(_user_or_404(uid)["username"]))
    return {"ok": True}


@router.delete("/users/{uid}")
def delete_user(uid: int, me: dict = Depends(auth.current_user)):
    _user_or_404(uid)
    if uid == me["id"]:
        raise HTTPException(400, "You can't delete your own account.")
    db.delete_user(uid)
    return {"ok": True}


# ---------- knowledge ----------


@router.get("/cases")
def list_cases():
    return db.list_cases_admin()


@router.put("/cases/{case_id}")
def edit_case(case_id: int, req: CaseEdit):
    fields = {k: v.strip() for k, v in req.model_dump().items()}
    if not (fields["title"] and fields["problem"] and fields["fix"]):
        raise HTTPException(422, "Title, problem and fix can't be empty.")
    if not db.edit_case(case_id, **fields):
        raise HTTPException(404, "Case not found.")
    return {"ok": True}


@router.delete("/cases/{case_id}")
def delete_case(case_id: int):
    if not db.delete_case(case_id):
        raise HTTPException(404, "Case not found.")
    return {"ok": True}