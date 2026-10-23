from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import db
from app.auth import current_user
from app.ollama_client import OllamaError
from app.services import knowledge

router = APIRouter(prefix="/api/knowledge")


class FeedRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200000)


class FromChatRequest(BaseModel):
    conversation_id: int


@router.post("")
async def feed(req: FeedRequest, user: dict = Depends(current_user)):
    if not req.text.strip():
        raise HTTPException(422, "Nothing to add.")
    try:
        return {"results": await knowledge.save_from_text(req.text, user["id"])}
    except OllamaError as exc:
        raise HTTPException(502, str(exc)) from None


@router.post("/from-chat")
async def from_chat(req: FromChatRequest, user: dict = Depends(current_user)):
    if not db.get_conversation(req.conversation_id, user["id"]):
        raise HTTPException(404, "Conversation not found.")
    try:
        return await knowledge.save_from_chat(req.conversation_id, user["id"])
    except OllamaError as exc:
        raise HTTPException(502, str(exc)) from None