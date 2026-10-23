import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import backup, db
from app.auth import user_from_request
from app.config import COOKIE_SECURE, ROOT, STATIC_DIR
from app.routes import admin, auth, chat, conversations, knowledge


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    backups = asyncio.create_task(backup.run_schedule())
    yield
    backups.cancel()


_SECURITY_HEADERS = [
    (b"content-security-policy",
     b"default-src 'self'; img-src 'self' data: blob:; object-src 'none'; "
     b"base-uri 'self'; form-action 'self'; frame-ancestors 'none'"),
    (b"x-frame-options", b"DENY"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
] + ([(b"strict-transport-security", b"max-age=31536000")] if COOKIE_SECURE else [])


class SecurityHeaders:
    """Add browser security headers to every response (works with streaming)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + _SECURITY_HEADERS
            await send(message)

        await self.app(scope, receive, send_with_headers)


app = FastAPI(title="Bobby", lifespan=lifespan)
app.add_middleware(SecurityHeaders)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(chat.router)
app.include_router(knowledge.router)
app.include_router(conversations.router)


def _brand_file(name: str):
    """Serve bobby.png / favicon.ico from the project root (or app/static)."""

    def handler():
        for base in (ROOT, STATIC_DIR):
            path = base / name
            if path.is_file():
                return FileResponse(path)
        raise HTTPException(404, f"{name} not found. Put it in: {ROOT}")

    return handler


for _name in ("bobby.png", "favicon.ico"):
    app.add_api_route(f"/{_name}", _brand_file(_name), include_in_schema=False)


@app.get("/", include_in_schema=False)
def index(request: Request):
    if not user_from_request(request):
        return RedirectResponse("/login.html")
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")