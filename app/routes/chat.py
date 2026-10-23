import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import db, ollama_client
from app.auth import current_user
from app.ollama_client import OllamaError
from app.services import knowledge, prompts

router = APIRouter(prefix="/api")


class ChatRequest(BaseModel):
    conversation_id: int | None = None
    mode: Literal["chat", "email"] = "chat"  # used only when starting a conversation
    message: str = Field(min_length=1, max_length=20000)
    context: str = Field("", max_length=10000)  # extra context, email mode only


def _line(event: dict) -> str:
    return json.dumps(event) + "\n"


def _title(text: str, mode: str) -> str:
    short = " ".join(text.split())
    short = short[:40] + "…" if len(short) > 40 else short
    return f"Email: {short}" if mode == "email" else short


@router.get("/status")
async def status(_: dict = Depends(current_user)):
    return await ollama_client.check()


@router.post("/chat")
async def chat(req: ChatRequest, user: dict = Depends(current_user)):
    text = req.message.strip()
    if not text:
        raise HTTPException(422, "Message is empty.")
    if req.conversation_id is not None:
        conv = db.get_conversation(req.conversation_id, user["id"])
        if not conv:
            raise HTTPException(404, "Conversation not found.")
    else:
        conv = db.create_conversation(req.mode, user["id"])
    cid, mode = conv["id"], conv["mode"]

    history = db.get_messages(cid)
    first = not history
    if mode == "email" and first:
        user_text = prompts.email_request(text, req.context)
    else:
        user_text = text
    if first:
        conv["title"] = _title(text, mode)
        db.set_title(cid, conv["title"])

    messages = prompts.build_messages(mode, user_text, history)
    db.add_message(cid, "user", user_text)

    async def stream():
        yield _line(
            {
                "type": "meta",
                "conversation_id": cid,
                "title": conv["title"],
                "user_message": user_text,
            }
        )
        parts: list[str] = []
        try:
            async for chunk in ollama_client.stream_chat(messages):
                parts.append(chunk)
                yield _line({"type": "token", "text": chunk})
            save_case = mode == "chat" and knowledge.looks_fixed(text)
            yield _line({"type": "done", "save_case": save_case})
        except OllamaError as exc:
            yield _line({"type": "error", "message": str(exc)})
        finally:
            # Also runs when the user presses Stop, so partial replies are kept.
            if parts:
                db.add_message(cid, "assistant", "".join(parts))

    return StreamingResponse(stream(), media_type="application/x-ndjson")