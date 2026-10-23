"""SQLite storage for users, sessions, conversations, messages and knowledge cases."""
import sqlite3
import time
from contextlib import contextmanager

from app.config import DB_PATH


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at REAL NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS login_failures (
                key TEXT NOT NULL,
                at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_login_failures ON login_failures(key, at);
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'chat',
                updated_at REAL NOT NULL,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL
                    REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                problem TEXT NOT NULL,
                cause TEXT NOT NULL DEFAULT '',
                fix TEXT NOT NULL,
                keywords TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL,
                conversation_id INTEGER UNIQUE
                    REFERENCES conversations(id) ON DELETE SET NULL,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_conv
                ON messages(conversation_id, id);
            """
        )
        # Older databases: add the admin flag, and make the first user admin if none is.
        if "is_admin" not in {r["name"] for r in c.execute("PRAGMA table_info(users)")}:
            c.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
        if not c.execute("SELECT 1 FROM users WHERE is_admin = 1").fetchone():
            c.execute("UPDATE users SET is_admin = 1 WHERE id = (SELECT MIN(id) FROM users)")
        # Older databases: add the owner column to existing conversations.
        cols = {r["name"] for r in c.execute("PRAGMA table_info(conversations)")}
        if "user_id" not in cols:
            c.execute(
                "ALTER TABLE conversations ADD COLUMN user_id INTEGER "
                "REFERENCES users(id) ON DELETE CASCADE"
            )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_user "
            "ON conversations(user_id, updated_at)"
        )
        # Bobby never shows em dashes: clean any saved before this rule existed.
        dash = "\u2014"
        c.execute("UPDATE messages SET content = REPLACE(content, ?, '-') WHERE instr(content, ?)", (dash, dash))
        c.execute("UPDATE conversations SET title = REPLACE(title, ?, '-') WHERE instr(title, ?)", (dash, dash))
        for col in ("title", "problem", "cause", "fix", "keywords"):
            c.execute(f"UPDATE cases SET {col} = REPLACE({col}, ?, '-') WHERE instr({col}, ?)", (dash, dash))


# ---------- users ----------


_USER_COLS = "id, username, password_hash, is_admin"


def get_user(username: str) -> dict | None:
    with _conn() as c:
        row = c.execute(
            f"SELECT {_USER_COLS} FROM users WHERE username = ?", (username,)
        ).fetchone()
    return dict(row) if row else None


def get_user_by_id(uid: int) -> dict | None:
    with _conn() as c:
        row = c.execute(f"SELECT {_USER_COLS} FROM users WHERE id = ?", (uid,)).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, username, is_admin, created_at FROM users ORDER BY username"
        ).fetchall()
    return [dict(r) for r in rows]


def count_admins() -> int:
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1").fetchone()[0]


def create_user(username: str, password_hash: str, is_admin: bool = False) -> int:
    with _conn() as c:
        uid = c.execute(
            "INSERT INTO users (username, password_hash, created_at, is_admin) VALUES (?, ?, ?, ?)",
            (username, password_hash, time.time(), int(is_admin)),
        ).lastrowid
        # The first user is admin and takes over chats created before logins existed.
        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1:
            c.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (uid,))
            c.execute("UPDATE conversations SET user_id = ? WHERE user_id IS NULL", (uid,))
    return uid


def set_admin(uid: int, is_admin: bool) -> None:
    with _conn() as c:
        c.execute("UPDATE users SET is_admin = ? WHERE id = ?", (int(is_admin), uid))


def set_password(uid: int, password_hash: str) -> None:
    with _conn() as c:
        c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, uid))
        c.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))


def delete_user(uid: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM users WHERE id = ?", (uid,))


# ---------- sessions ----------


def create_session(token_hash: str, uid: int, expires_at: float) -> None:
    with _conn() as c:
        c.execute("DELETE FROM sessions WHERE expires_at <= ?", (time.time(),))
        c.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, uid, expires_at),
        )


def session_user(token_hash: str) -> dict | None:
    with _conn() as c:
        row = c.execute(
            "SELECT u.id, u.username, u.is_admin FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ? AND s.expires_at > ?",
            (token_hash, time.time()),
        ).fetchone()
    return dict(row) if row else None


def delete_session(token_hash: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))


def delete_user_sessions(uid: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))


# ---------- failed sign-ins ----------


def add_login_failure(keys: list[str], keep_seconds: float) -> None:
    now = time.time()
    with _conn() as c:
        c.execute("DELETE FROM login_failures WHERE at < ?", (now - keep_seconds,))
        c.executemany("INSERT INTO login_failures (key, at) VALUES (?, ?)", [(k, now) for k in keys])


def recent_login_failures(key: str, since: float, limit: int) -> list[float]:
    """Newest-first failure times for `key` after `since`."""
    with _conn() as c:
        rows = c.execute(
            "SELECT at FROM login_failures WHERE key = ? AND at > ? ORDER BY at DESC LIMIT ?",
            (key, since, limit),
        ).fetchall()
    return [r["at"] for r in rows]


def clear_login_failures(key: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM login_failures WHERE key = ?", (key,))


# ---------- conversations ----------


def list_conversations(uid: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, title, mode, updated_at FROM conversations "
            "WHERE user_id = ? ORDER BY updated_at DESC",
            (uid,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_conversation(cid: int, uid: int) -> dict | None:
    with _conn() as c:
        row = c.execute(
            "SELECT id, title, mode FROM conversations WHERE id = ? AND user_id = ?",
            (cid, uid),
        ).fetchone()
    return dict(row) if row else None


def create_conversation(mode: str, uid: int) -> dict:
    title = "New email draft" if mode == "email" else "New chat"
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO conversations (title, mode, updated_at, user_id) "
            "VALUES (?, ?, ?, ?)",
            (title, mode, time.time(), uid),
        )
        return {"id": cur.lastrowid, "title": title, "mode": mode}


def set_title(cid: int, title: str) -> None:
    with _conn() as c:
        c.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, cid))


def get_messages(cid: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id",
            (cid,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_message(cid: int, role: str, content: str) -> None:
    now = time.time()
    with _conn() as c:
        c.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?)",
            (cid, role, content, now),
        )
        c.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, cid))


def clear_messages(cid: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM messages WHERE conversation_id = ?", (cid,))


def delete_conversation(cid: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM conversations WHERE id = ?", (cid,))


# ---------- knowledge cases ----------

_CASE_COLS = "id, title, problem, cause, fix, keywords"


def list_cases() -> list[dict]:
    with _conn() as c:
        rows = c.execute(f"SELECT {_CASE_COLS} FROM cases ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def get_case_by_conversation(cid: int) -> dict | None:
    with _conn() as c:
        row = c.execute(
            f"SELECT {_CASE_COLS} FROM cases WHERE conversation_id = ?", (cid,)
        ).fetchone()
    return dict(row) if row else None


def add_case(case: dict, source: str, uid: int, cid: int | None = None) -> int:
    now = time.time()
    with _conn() as c:
        return c.execute(
            "INSERT INTO cases (title, problem, cause, fix, keywords, source, "
            "conversation_id, user_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (case["title"], case["problem"], case["cause"], case["fix"],
             case["keywords"], source, cid, uid, now, now),
        ).lastrowid


def update_case(case_id: int, case: dict) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE cases SET title = ?, problem = ?, cause = ?, fix = ?, keywords = ?, "
            "updated_at = ? WHERE id = ?",
            (case["title"], case["problem"], case["cause"], case["fix"],
             case["keywords"], time.time(), case_id),
        )


def list_cases_admin() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT c.id, c.title, c.problem, c.cause, c.fix, c.source, c.created_at, "
            "u.username AS added_by FROM cases c LEFT JOIN users u ON u.id = c.user_id "
            "ORDER BY c.created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def edit_case(case_id: int, title: str, problem: str, cause: str, fix: str) -> bool:
    with _conn() as c:
        return c.execute(
            "UPDATE cases SET title = ?, problem = ?, cause = ?, fix = ?, updated_at = ? WHERE id = ?",
            (title, problem, cause, fix, time.time(), case_id),
        ).rowcount > 0


def delete_case(case_id: int) -> bool:
    with _conn() as c:
        return c.execute("DELETE FROM cases WHERE id = ?", (case_id,)).rowcount > 0