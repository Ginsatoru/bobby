"""Builds the message list sent to the model."""
from app.config import MAX_HISTORY_MESSAGES, PROMPTS_DIR
from app.services import knowledge


def _read(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def email_request(customer_message: str, context: str) -> str:
    text = f"Customer message:\n{customer_message.strip()}"
    if context.strip():
        text += f"\n\nAdditional context:\n{context.strip()}"
    return text


def system_prompt(mode: str, query: str) -> str:
    # Prompt files are re-read on every request, so edits apply without a restart.
    parts = [_read("system.txt")]
    if mode == "email":
        parts.append(_read("email.txt"))
    chunks = knowledge.retrieve(query)
    if chunks:
        parts.append(
            "Company knowledge (the only source for company-specific facts):\n\n"
            + "\n\n---\n\n".join(chunks)
        )
    return "\n\n".join(parts)


def build_messages(mode: str, user_text: str, history: list[dict]) -> list[dict]:
    recent = history[-MAX_HISTORY_MESSAGES:]
    # Follow-ups ("what should I reply?") rarely name the issue, so search with recent user messages too.
    earlier = [m["content"] for m in recent if m["role"] == "user"][-2:]
    query = "\n".join([*earlier, user_text])
    return [
        {"role": "system", "content": system_prompt(mode, query)},
        *recent,
        {"role": "user", "content": user_text},
    ]