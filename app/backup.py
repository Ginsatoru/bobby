"""Safe SQLite backups to data/backups (works while Bobby is running).

Bobby backs up automatically every BACKUP_HOURS. Run one now with: python -m app.backup
"""
import asyncio
import logging
import sqlite3
import time

from app.config import BACKUP_HOURS, BACKUP_KEEP, DB_PATH

log = logging.getLogger("uvicorn.error")
FOLDER = DB_PATH.parent / "backups"


def backup_now() -> str:
    FOLDER.mkdir(parents=True, exist_ok=True)
    target = FOLDER / f"bobby-{time.strftime('%Y%m%d-%H%M%S')}.db"
    src, dst = sqlite3.connect(DB_PATH), sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    for old in sorted(FOLDER.glob("bobby-*.db"))[:-BACKUP_KEEP]:
        old.unlink()
    return str(target)


def _last_backup() -> float:
    files = sorted(FOLDER.glob("bobby-*.db"))
    return files[-1].stat().st_mtime if files else 0.0


async def run_schedule() -> None:
    """Back up when the newest backup is older than BACKUP_HOURS, then keep checking."""
    interval = BACKUP_HOURS * 3600
    while True:
        wait = _last_backup() + interval - time.time()
        if wait <= 0:
            try:
                log.info("Database backed up to %s", await asyncio.to_thread(backup_now))
            except Exception as exc:  # never let a failed backup stop Bobby
                log.error("Database backup failed: %s", exc)
            wait = interval
        await asyncio.sleep(min(wait, 3600))


if __name__ == "__main__":
    print(f"Backed up to {backup_now()}")