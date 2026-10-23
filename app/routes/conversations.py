from fastapi import APIRouter, Depends, HTTPException

from app import db
from app.auth import current_user

router = APIRouter(prefix="/api/conversations")


def _get_or_404(cid: int, uid: int) -> dict:
    conv = db.get_conversation(cid, uid)
    if not conv:
        raise HTTPException(404, "Conversation not found.")
    return conv


@router.get("")
def list_conversations(user: dict = Depends(current_user)):
    return db.list_conversations(user["id"])


@router.get("/{cid}")
def get_conversation(cid: int, user: dict = Depends(current_user)):
    conv = _get_or_404(cid, user["id"])
    return {**conv, "messages": db.get_messages(cid)}


@router.post("/{cid}/clear")
def clear_conversation(cid: int, user: dict = Depends(current_user)):
    _get_or_404(cid, user["id"])
    db.clear_messages(cid)
    return {"ok": True}


@router.delete("/{cid}")
def delete_conversation(cid: int, user: dict = Depends(current_user)):
    _get_or_404(cid, user["id"])
    db.delete_conversation(cid)
    return {"ok": True}