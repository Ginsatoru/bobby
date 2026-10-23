"""The only module that talks to Ollama."""
import json
from typing import AsyncIterator

import httpx

from app.config import OLLAMA_MODEL, OLLAMA_NUM_CTX, OLLAMA_TIMEOUT, OLLAMA_URL


def no_em_dash(text: str) -> str:
    """Bobby never outputs em dashes."""
    return text.replace("\u2014", "-")


class OllamaError(Exception):
    """Error with a message that is safe to show to the user."""


async def check() -> dict:
    """Report whether Ollama is reachable and the configured model is installed."""
    result = {"connected": False, "model": OLLAMA_MODEL, "model_installed": False}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            res = await client.get(f"{OLLAMA_URL}/api/tags")
            res.raise_for_status()
            names = {m.get("name") for m in res.json().get("models", [])}
    except (httpx.HTTPError, ValueError):
        return result
    result["connected"] = True
    result["model_installed"] = (
        OLLAMA_MODEL in names or f"{OLLAMA_MODEL}:latest" in names
    )
    return result


def _http_error(status: int, body: str) -> str:
    try:
        detail = json.loads(body).get("error", "")
    except ValueError:
        detail = ""
    if status == 404 and "not found" in detail.lower():
        return (
            f"The model '{OLLAMA_MODEL}' isn't installed. "
            f"Run this in a terminal, then try again: ollama pull {OLLAMA_MODEL}"
        )
    return f"Ollama returned an error ({status}). {detail}".strip()


async def stream_chat(messages: list[dict]) -> AsyncIterator[str]:
    """Yield the model's reply as text chunks."""
    payload = {"model": OLLAMA_MODEL, "messages": messages, "stream": True,
               "options": {"num_ctx": OLLAMA_NUM_CTX}}
    timeout = httpx.Timeout(OLLAMA_TIMEOUT, connect=5)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", f"{OLLAMA_URL}/api/chat", json=payload
            ) as res:
                if res.status_code != 200:
                    body = (await res.aread()).decode(errors="replace")
                    raise OllamaError(_http_error(res.status_code, body))
                async for line in res.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except ValueError:
                        continue
                    if "error" in data:
                        raise OllamaError(f"Ollama error: {data['error']}")
                    chunk = no_em_dash(data.get("message", {}).get("content", ""))
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break
    except httpx.ConnectError:
        raise OllamaError(
            "Can't reach Ollama. Start the Ollama app, then try again."
        ) from None
    except httpx.TimeoutException:
        raise OllamaError(
            "Ollama took too long to respond. The model may still be loading; try again."
        ) from None
    except httpx.HTTPError as exc:
        raise OllamaError(f"The request to Ollama failed: {exc}") from None


async def complete_json(messages: list[dict], schema: dict) -> dict:
    """Return the model's reply as JSON matching `schema` (non-streaming)."""
    payload = {
        "model": OLLAMA_MODEL, "messages": messages, "stream": False,
        "format": schema, "options": {"temperature": 0, "num_ctx": OLLAMA_NUM_CTX},
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(OLLAMA_TIMEOUT, connect=5)) as client:
            res = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
    except httpx.ConnectError:
        raise OllamaError("Can't reach Ollama. Start the Ollama app, then try again.") from None
    except httpx.TimeoutException:
        raise OllamaError("Ollama took too long to respond. Try again.") from None
    except httpx.HTTPError as exc:
        raise OllamaError(f"The request to Ollama failed: {exc}") from None
    if res.status_code != 200:
        raise OllamaError(_http_error(res.status_code, res.text))
    try:
        data = json.loads(no_em_dash(res.json()["message"]["content"]))
    except (ValueError, KeyError, TypeError):
        raise OllamaError("Couldn't read the model's answer. Try again.") from None
    if not isinstance(data, dict):
        raise OllamaError("Couldn't read the model's answer. Try again.")
    return data