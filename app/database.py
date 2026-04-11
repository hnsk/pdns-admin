import os
from pathlib import Path

import aiosqlite

from app.config import settings

_db: aiosqlite.Connection | None = None
_MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


async def get_db() -> aiosqlite.Connection:
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


async def init_db() -> aiosqlite.Connection:
    global _db
    os.makedirs(os.path.dirname(settings.database_path), exist_ok=True)
    _db = await aiosqlite.connect(settings.database_path)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")
    await _run_migrations(_db)
    return _db


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def _run_migrations(db: aiosqlite.Connection) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS _migrations (name TEXT PRIMARY KEY, applied_at TEXT DEFAULT (datetime('now')))"
    )
    await db.commit()

    applied = {row[0] for row in await db.execute_fetchall("SELECT name FROM _migrations")}

    migration_files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    for mf in migration_files:
        if mf.name not in applied:
            sql = mf.read_text()
            await db.executescript(sql)
            await db.execute("INSERT INTO _migrations (name) VALUES (?)", (mf.name,))
            await db.commit()
